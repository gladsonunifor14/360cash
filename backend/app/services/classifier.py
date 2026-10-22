"""Classificação de lançamentos bancários.

Fluxo: o cliente classifica os primeiros lançamentos conforme o histórico; o motor
aprende com essas classificações e replica para os novos lançamentos:

1. Correspondência exata do histórico normalizado (mesmo sinal crédito/débito) → voto majoritário.
2. Similaridade TF-IDF (cosseno) contra o histórico já classificado → k vizinhos mais próximos.
3. (Opcional) Claude, quando `CASH360_ANTHROPIC_API_KEY` está configurada, para o que sobrar
   com baixa confiança. Apenas descrição, sinal e plano de contas são enviados — nunca
   dados de identificação do cliente.

Acima de `AUTO_APPLY` a classificação é aplicada (classified_by="ia"); abaixo, fica como
sugestão para revisão humana.
"""

import json
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BankTransaction, ChartAccount

log = logging.getLogger("cash360.classifier")

AUTO_APPLY = 0.80
SUGGEST = 0.45
K = 5
HUMAN_SOURCES = ("cliente", "contador")


@dataclass
class Prediction:
    account_id: str
    confidence: float
    method: str


def _tokens(text: str) -> list[str]:
    return [t for t in text.split() if len(t) > 1]


class Model:
    """Índice TF-IDF em memória sobre lançamentos classificados por humanos."""

    def __init__(self, examples: list[tuple[str, int, str]]):
        # examples: (descrição normalizada, sinal, account_id)
        self.exact: dict[tuple[str, int], Counter] = defaultdict(Counter)
        df: Counter = Counter()
        docs = []
        for desc, sign, account in examples:
            self.exact[(desc, sign)][account] += 1
            toks = set(_tokens(desc))
            df.update(toks)
            docs.append((toks, sign, account))
        n = max(len(docs), 1)
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
        self.docs = [(self._vec(toks), sign, acc) for toks, sign, acc in docs]

    def _vec(self, toks) -> dict[str, float]:
        v = {t: self.idf.get(t, 1.0) for t in toks}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def predict(self, desc: str, sign: int) -> Prediction | None:
        votes = self.exact.get((desc, sign))
        if votes:
            account, count = votes.most_common(1)[0]
            return Prediction(account, round(0.6 + 0.4 * count / sum(votes.values()), 4), "historico_exato")
        q = self._vec(set(_tokens(desc)))
        if not q:
            return None
        scored = []
        for vec, s, acc in self.docs:
            if s != sign:
                continue
            sim = sum(w * vec.get(t, 0.0) for t, w in q.items())
            if sim > 0:
                scored.append((sim, acc))
        if not scored:
            return None
        scored.sort(reverse=True)
        top = scored[:K]
        weight: Counter = Counter()
        for sim, acc in top:
            weight[acc] += sim
        account, w = weight.most_common(1)[0]
        confidence = top[0][0] * (w / sum(weight.values()))
        return Prediction(account, round(confidence, 4), "similaridade")


def build_model(db: Session, client_id: str) -> Model:
    rows = db.execute(
        select(BankTransaction.normalized_description, BankTransaction.amount, BankTransaction.account_id).where(
            BankTransaction.client_id == client_id,
            BankTransaction.account_id.is_not(None),
            BankTransaction.classified_by.in_(HUMAN_SOURCES),
        )
    ).all()
    return Model([(d, 1 if a >= 0 else -1, acc) for d, a, acc in rows])


def _claude_classify(txs: list[BankTransaction], accounts: list[ChartAccount]) -> dict[str, Prediction]:
    s = get_settings()
    if not s.anthropic_api_key or not txs:
        return {}
    try:
        import anthropic
    except ImportError:
        return {}
    chart = "\n".join(f"{a.code} | {a.name} | {a.nature}" for a in accounts)
    items = [
        {"id": t.id, "historico": t.normalized_description, "tipo": "credito" if t.amount >= 0 else "debito"}
        for t in txs
    ]
    schema = {
        "type": "object",
        "properties": {
            "classificacoes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "conta": {"type": "string"},
                        "confianca": {"type": "number"},
                    },
                    "required": ["id", "conta", "confianca"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["classificacoes"],
        "additionalProperties": False,
    }
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    try:
        resp = client.beta.messages.create(
            model=s.anthropic_model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            system=(
                "Você é um analista de BPO financeiro no Brasil. Classifique cada lançamento de extrato "
                "bancário em uma conta do plano de contas gerencial abaixo, usando o código da conta. "
                "Créditos normalmente são receitas, empréstimos, aportes ou transferências; débitos, "
                "despesas, custos, impostos ou transferências. Informe confiança de 0 a 1.\n\n"
                f"Plano de contas (código | nome | natureza):\n{chart}"
            ),
            messages=[{"role": "user", "content": json.dumps(items, ensure_ascii=False)}],
        )
    except anthropic.APIError as exc:
        log.warning("Falha na classificação por IA: %s", exc)
        return {}
    if resp.stop_reason != "end_turn":
        return {}
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    by_code = {a.code: a.id for a in accounts}
    out = {}
    for c in json.loads(text).get("classificacoes", []):
        if c.get("conta") in by_code:
            out[c["id"]] = Prediction(by_code[c["conta"]], min(float(c["confianca"]), 0.95), "claude")
    return out


def classify_pending(db: Session, client_id: str, office_id: str, use_llm: bool = True) -> dict[str, int]:
    """Classifica lançamentos pendentes do cliente. Retorna contadores do resultado."""
    model = build_model(db, client_id)
    pending = list(
        db.scalars(
            select(BankTransaction).where(
                BankTransaction.client_id == client_id, BankTransaction.account_id.is_(None)
            )
        )
    )
    stats = {"aplicados": 0, "sugeridos": 0, "sem_sugestao": 0}
    leftovers = []
    for tx in pending:
        pred = model.predict(tx.normalized_description, 1 if tx.amount >= 0 else -1)
        if pred and pred.confidence >= AUTO_APPLY:
            tx.account_id, tx.classified_by, tx.confidence = pred.account_id, "ia", pred.confidence
            tx.suggested_account_id = pred.account_id
            stats["aplicados"] += 1
        elif pred and pred.confidence >= SUGGEST:
            tx.suggested_account_id, tx.confidence = pred.account_id, pred.confidence
            stats["sugeridos"] += 1
        else:
            leftovers.append(tx)
    if use_llm and leftovers:
        accounts = list(
            db.scalars(select(ChartAccount).where(ChartAccount.office_id == office_id, ChartAccount.is_active))
        )
        preds = _claude_classify(leftovers[:200], accounts)
        for tx in leftovers:
            if tx.id in preds:
                tx.suggested_account_id, tx.confidence = preds[tx.id].account_id, preds[tx.id].confidence
                stats["sugeridos"] += 1
            else:
                stats["sem_sugestao"] += 1
    else:
        stats["sem_sugestao"] += len(leftovers)
    return stats
