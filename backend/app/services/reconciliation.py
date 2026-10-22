"""Conciliação bancária: casamento extrato × títulos e tratamento de divergências."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BankAccount, BankTransaction, Reconciliation, Title
from app.services.accounting import account_by_code, seed_chart
from app.services.bank_parser import normalize_description
from app.services.titles import FINAL_STATUSES, settle

MIN_SCORE = 0.6
MAX_AMOUNT_DIFF = Decimal("0.10")  # acima de 10% de diferença, só sugere com evidência no histórico
DAYS_BEFORE_ISSUE = 5    # lançamento até 5 dias antes da emissão do título
DAYS_AFTER_DUE = 60      # e até 60 dias após o vencimento
ZERO = Decimal("0")

# conta da diferença por (tipo do título, ação)
DIFF_ACCOUNT = {
    ("pagar", "juros"): "4.07",     # juros/multa pagos
    ("receber", "juros"): "1.06",   # juros/multa recebidos
    ("pagar", "desconto"): "1.05",  # desconto obtido
    ("receber", "desconto"): "4.09",  # desconto concedido
}


class ReconciliationError(Exception):
    pass


def brl(v: Decimal) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class Suggestion:
    transaction: BankTransaction
    title: Title
    score: float
    difference: Decimal  # valor do extrato − saldo do título (em módulo)

    @property
    def actions(self) -> list[str]:
        if self.difference == 0:
            return ["exato"]
        return ["juros"] if self.difference > 0 else ["desconto", "parcial"]


def reconciled_ids(db: Session, client_id: str) -> set[str]:
    return set(db.scalars(select(Reconciliation.transaction_id).where(Reconciliation.client_id == client_id)))


def _score(tx: BankTransaction, t: Title) -> float:
    value = abs(Decimal(tx.amount))
    open_ = t.open_amount
    if open_ <= 0:
        return 0.0
    if not (t.issue_date - timedelta(days=DAYS_BEFORE_ISSUE) <= tx.date
            <= (t.scheduled_for or t.due_date) + timedelta(days=DAYS_AFTER_DUE)):
        return 0.0
    name_tokens = {w for w in normalize_description(t.counterparty_name).split() if len(w) > 2}
    desc_tokens = set(tx.normalized_description.split())
    name_score = len(name_tokens & desc_tokens) / len(name_tokens) if name_tokens else 0.0
    doc_bonus = 0.2 if t.document_number and t.document_number.split()[-1] in tx.description else 0.0
    rel = abs(value - open_) / open_
    # diferença grande (ex.: pagamento parcial) só com evidência no histórico: favorecido ou nº do documento
    if rel > MAX_AMOUNT_DIFF and not (doc_bonus or name_score >= 0.5):
        return 0.0
    amount_score = 1.0 if rel == 0 else max(0.0, 1 - float(rel) * 5)  # 20% de diferença zera
    days = abs((tx.date - (t.scheduled_for or t.due_date)).days)
    date_score = max(0.0, 1 - days / 30)
    return min(1.0, 0.6 * amount_score + 0.25 * date_score + 0.15 * name_score + doc_bonus)


def suggestions(db: Session, client_id: str, limit: int = 200) -> list[Suggestion]:
    done = reconciled_ids(db, client_id)
    txs = [t for t in db.scalars(
        select(BankTransaction).join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
        .where(BankTransaction.client_id == client_id, BankAccount.kind == "corrente")
        .order_by(BankTransaction.date.desc()).limit(2000)
    ) if t.id not in done]
    titles = list(db.scalars(select(Title).where(Title.client_id == client_id,
                                                 Title.status.not_in(FINAL_STATUSES))))
    out, used = [], set()
    for tx in txs:
        kind = "receber" if tx.amount > 0 else "pagar"
        best = max(((t, _score(tx, t)) for t in titles if t.kind == kind and t.id not in used),
                   key=lambda x: x[1], default=None)
        if best and best[1] >= MIN_SCORE:
            t, score = best
            used.add(t.id)
            out.append(Suggestion(tx, t, round(score, 3), abs(Decimal(tx.amount)) - t.open_amount))
        if len(out) >= limit:
            break
    return out


def apply(db: Session, tx: BankTransaction, title: Title, action: str, user_id: str | None) -> list[Reconciliation]:
    if tx.id in reconciled_ids(db, tx.client_id):
        raise ReconciliationError(
            "Este lançamento do extrato já está conciliado. Desfaça a conciliação para refazê-la.")
    if title.client_id != tx.client_id:
        raise ReconciliationError("O título e o lançamento pertencem a empresas diferentes.")
    if title.status in FINAL_STATUSES:
        raise ReconciliationError(
            f"O título {title.document_number or ''} está {title.status} e não pode ser conciliado.")
    expected = "receber" if tx.amount > 0 else "pagar"
    if title.kind != expected:
        raise ReconciliationError(
            f"Um {'crédito' if tx.amount > 0 else 'débito'} no extrato só pode baixar uma conta a {expected}.")

    value, open_ = abs(Decimal(tx.amount)), title.open_amount
    sign = Decimal(1) if title.kind == "receber" else Decimal(-1)
    diff = value - open_
    if action == "exato" and diff != 0:
        raise ReconciliationError(
            f"O valor do extrato ({brl(value)}) difere do saldo do título ({brl(open_)}) em {brl(abs(diff))}. "
            + ("Use “Juros/multa” para registrar o excedente."
               if diff > 0 else "Use “Desconto” ou “Pagamento parcial” para registrar a diferença."))
    if action == "juros" and diff <= 0:
        raise ReconciliationError(f"Juros/multa só se aplica quando o extrato ({brl(value)}) é maior que o saldo "
                                  f"do título ({brl(open_)}).")
    if action in ("desconto", "parcial") and diff >= 0:
        raise ReconciliationError(f"{'Desconto' if action == 'desconto' else 'Pagamento parcial'} só se aplica "
                                  f"quando o extrato ({brl(value)}) é menor que o saldo do título ({brl(open_)}).")
    if action not in ("exato", "juros", "desconto", "parcial"):
        raise ReconciliationError("Ação inválida. Use exato, juros, desconto ou parcial.")

    seed_chart(db, tx.office_id)  # garante as contas de juros/desconto em escritórios antigos
    db.flush()
    accounts = account_by_code(db, tx.office_id)
    base = dict(office_id=tx.office_id, client_id=tx.client_id, transaction_id=tx.id, title_id=title.id,
                created_by=user_id)
    principal = value if action == "parcial" else open_
    rows = [Reconciliation(**base, kind="principal", amount=sign * principal, account_id=title.account_id)]
    if action == "juros":
        rows.append(Reconciliation(**base, kind="juros", amount=sign * diff,
                                   account_id=accounts[DIFF_ACCOUNT[(title.kind, "juros")]].id))
    elif action == "desconto":
        rows.append(Reconciliation(**base, kind="desconto", amount=-sign * abs(diff),
                                   account_id=accounts[DIFF_ACCOUNT[(title.kind, "desconto")]].id))
    db.add_all(rows)
    settle(title, principal, tx.date)
    tx.account_id, tx.classified_by, tx.confidence, tx.suggested_account_id = title.account_id, "conciliacao", 1.0, None
    return rows


def undo(db: Session, tx: BankTransaction) -> None:
    rows = list(db.scalars(select(Reconciliation).where(Reconciliation.transaction_id == tx.id)))
    if not rows:
        raise ReconciliationError("Este lançamento não está conciliado.")
    for r in rows:
        if r.kind == "principal" and r.title_id:
            t = db.get(Title, r.title_id)
            t.paid_amount = max(ZERO, Decimal(t.paid_amount) - abs(Decimal(r.amount)))
            t.status = "parcial" if t.paid_amount > 0 else ("aprovado" if t.approved_at else "aberto")
            t.settled_at = None
        db.delete(r)
    tx.account_id, tx.classified_by, tx.confidence = None, None, None


def split_rows(db: Session, client_id: str, start: date, end: date) -> list[tuple[date, Decimal, str | None]]:
    """Linhas de caixa para relatórios: lançamentos conciliados viram seus rateios."""
    txs = db.execute(
        select(BankTransaction.id, BankTransaction.date, BankTransaction.amount, BankTransaction.account_id)
        .join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
        .where(BankTransaction.client_id == client_id, BankAccount.kind == "corrente",
               BankTransaction.date >= start, BankTransaction.date <= end)
    ).all()
    ids = [t.id for t in txs]
    splits: dict[str, list[Reconciliation]] = {}
    if ids:
        for r in db.scalars(select(Reconciliation).where(Reconciliation.transaction_id.in_(ids))):
            splits.setdefault(r.transaction_id, []).append(r)
    out = []
    for tid, d, amount, account_id in txs:
        if tid in splits:
            out.extend((d, Decimal(r.amount), r.account_id) for r in splits[tid])
        else:
            out.append((d, Decimal(amount), account_id))
    return out
