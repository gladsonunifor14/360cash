"""Torre de controle (pendências por criticidade, multiempresa) e busca global."""

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, get_principal
from app.models import BankAccount, BankTransaction, Client, Contract, Invoice, PowerOfAttorney, Title
from app.schemas import BankConnectionOut, SearchHit
from app.services import reconciliation as recon
from app.services.cnpj import format_cnpj, only_digits
from app.services.reconciliation import brl
from app.services.titles import FINAL_STATUSES

router = APIRouter(tags=["Torre de controle"])

SEVERITY_ORDER = {"atrasado": 0, "hoje": 1, "atencao": 2, "concluido": 3}


def _clients(p: Principal, db: Session) -> list[Client]:
    stmt = select(Client).where(Client.office_id == p.office_id, Client.is_active).order_by(Client.razao_social)
    if not p.is_staff:
        stmt = stmt.where(Client.id == p.user.client_id)
    return list(db.scalars(stmt))


@router.get("/control-tower", summary="Pendências de todas as empresas por criticidade",
            description="Cada item traz `severity` (atrasado, hoje, atencao, concluido) e `route` com a tela e o "
                        "filtro que resolvem a pendência.")
def control_tower(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    today = date.today()
    soon = today + timedelta(days=30)
    clients = _clients(p, db)
    ids = [c.id for c in clients]
    names = {c.id: c.nome_fantasia or c.razao_social for c in clients}
    per_client = {c.id: {"client_id": c.id, "client_name": names[c.id], "atrasado": 0, "hoje": 0, "concluido": 0,
                         "valor_atrasado": Decimal(0), "valor_hoje": Decimal(0), "a_classificar": 0,
                         "a_conciliar": 0, "integracoes_com_falha": 0} for c in clients}
    tasks = []

    def task(client_id, severity, title, detail, route, count=1, amount=None):
        tasks.append({"client_id": client_id, "client_name": names[client_id], "severity": severity, "title": title,
                      "detail": detail, "route": route, "count": count, "amount": amount})

    if not ids:
        return {"date": today, "totals": {}, "clients": [], "tasks": [], "connections": []}

    # títulos
    rows = db.execute(
        select(Title.client_id, Title.kind, Title.due_date, Title.status, Title.settled_at,
               Title.amount - Title.paid_amount)
        .where(Title.client_id.in_(ids), or_(Title.status.not_in(FINAL_STATUSES), Title.settled_at == today))
    ).all()
    agg: dict[tuple, list] = {}
    for cid, kind, due, status, settled, open_ in rows:
        if status == "liquidado" and settled == today:
            sev = "concluido"
        elif status in FINAL_STATUSES:
            continue
        elif due < today:
            sev = "atrasado"
        elif due == today:
            sev = "hoje"
        else:
            continue
        a = agg.setdefault((cid, kind, sev), [0, Decimal(0)])
        a[0] += 1
        a[1] += Decimal(open_ if sev != "concluido" else 0)
        per_client[cid][sev] += 1
        if sev in ("atrasado", "hoje"):
            per_client[cid][f"valor_{sev}"] += Decimal(open_)
    labels = {"atrasado": "vencidas", "hoje": "vencem hoje", "concluido": "liquidadas hoje"}
    for (cid, kind, sev), (n, total) in agg.items():
        task(cid, sev, f"{n} conta(s) a {kind} {labels[sev]}",
             f"Saldo em aberto {brl(total)}" if sev != "concluido" else "Baixadas hoje",
             f"/financeiro?kind={kind}&urgency={sev}", n, total if sev != "concluido" else None)

    # classificação pendente
    for cid, n in db.execute(select(BankTransaction.client_id, func.count())
                             .where(BankTransaction.client_id.in_(ids), BankTransaction.account_id.is_(None))
                             .group_by(BankTransaction.client_id)).all():
        per_client[cid]["a_classificar"] = n
        task(cid, "atencao", f"{n} lançamento(s) do extrato sem classificação",
             "Classifique ou aceite as sugestões da IA", "/extratos?status=pendente", n)

    # conciliação sugerida
    for cid in ids:
        n = len(recon.suggestions(db, cid, limit=100))
        if n:
            per_client[cid]["a_conciliar"] = n
            task(cid, "hoje", f"{n} conciliação(ões) sugerida(s) aguardando confirmação",
                 "Confira extrato × título e confirme", "/conciliacao", n)

    # integrações bancárias
    connections = list(db.scalars(select(BankAccount).where(BankAccount.client_id.in_(ids),
                                                            BankAccount.kind == "corrente")))
    for acc in connections:
        if acc.connection_status in ("reautenticar", "erro"):
            per_client[acc.client_id]["integracoes_com_falha"] += 1
            task(acc.client_id, "atrasado",
                 f"{acc.bank_name}: " + ("reautenticação necessária" if acc.connection_status == "reautenticar"
                                         else "falha na sincronização"),
                 acc.last_sync_error or "Peça ao cliente para renovar o consentimento no banco", "/extratos")

    # contratos e procurações
    for cid, n in db.execute(select(Contract.client_id, func.count())
                             .where(Contract.client_id.in_(ids), Contract.status == "pendente")
                             .group_by(Contract.client_id)).all():
        task(cid, "atencao", f"{n} contrato(s) aguardando aceite do cliente", "Contrato de adesão", "/contratos", n)
    for poa in db.scalars(select(PowerOfAttorney).where(
            PowerOfAttorney.client_id.in_(ids), PowerOfAttorney.revoked_at.is_(None),
            PowerOfAttorney.valid_until.is_not(None), PowerOfAttorney.valid_until <= soon)):
        expired = poa.valid_until < today
        task(poa.client_id, "atrasado" if expired else "atencao",
             f"Procuração {'vencida' if expired else 'vencendo'}: {poa.finalidade}",
             f"Validade {poa.valid_until:%d/%m/%Y}", "/contratos")

    tasks.sort(key=lambda t: (SEVERITY_ORDER[t["severity"]], t["client_name"]))
    totals = {k: sum(c[k] for c in per_client.values()) for k in ("atrasado", "hoje", "concluido", "a_classificar",
                                                                   "a_conciliar", "integracoes_com_falha")}
    return {
        "date": today,
        "totals": totals,
        "clients": sorted(per_client.values(), key=lambda c: (-c["atrasado"], -c["hoje"], c["client_name"])),
        "tasks": tasks,
        "connections": [BankConnectionOut.model_validate(a) for a in connections],
    }


def _parse_amount(q: str) -> Decimal | None:
    s = q.strip().replace("R$", "").replace(" ", "")
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d{1,2})?|\d+([.,]\d{1,2})?", s):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


@router.get("/search", response_model=list[SearchHit], summary="Busca global",
            description="Uma única busca por CNPJ/CPF, nome de cliente ou fornecedor, valor (ex.: 1.234,56) ou "
                        "número de nota fiscal/documento, em todas as empresas acessíveis.")
def search(q: str = Query(min_length=2, max_length=100), p: Principal = Depends(get_principal),
           db: Session = Depends(get_db)):
    clients = _clients(p, db)
    ids = [c.id for c in clients]
    names = {c.id: c.nome_fantasia or c.razao_social for c in clients}
    if not ids:
        return []
    digits = only_digits(q)
    amount = _parse_amount(q)
    text = q.strip()
    like = f"%{text}%"
    hits: list[SearchHit] = []

    def hit(type_, id_, cid, label, detail, route):
        hits.append(SearchHit(type=type_, id=id_, client_id=cid, client_name=names[cid], label=label,
                              detail=detail, route=route))

    # empresas clientes
    conds = [Client.razao_social.ilike(like), Client.nome_fantasia.ilike(like)]
    if len(digits) >= 4:
        conds.append(Client.cnpj.like(f"%{digits}%"))
    for c in db.scalars(select(Client).where(Client.id.in_(ids), or_(*conds)).limit(8)):
        hit("cliente", c.id, c.id, c.razao_social, f"CNPJ {format_cnpj(c.cnpj)}", "/painel")

    # notas fiscais
    conds = [Invoice.emit_nome.ilike(like), Invoice.dest_nome.ilike(like)]
    if digits and len(digits) <= 9:
        conds.append(Invoice.numero == digits.lstrip("0"))
    if len(digits) >= 8:
        conds += [Invoice.emit_cnpj.like(f"%{digits}%"), Invoice.dest_documento.like(f"%{digits}%"),
                  Invoice.chave.like(f"%{digits}%")]
    if amount is not None:
        conds.append(Invoice.valor_total == amount)
    for n in db.scalars(select(Invoice).where(Invoice.client_id.in_(ids), or_(*conds))
                        .order_by(Invoice.data_emissao.desc()).limit(8)):
        other = n.dest_nome if n.direction == "emitida" else n.emit_nome
        hit("nota", n.id, n.client_id, f"NF {n.numero} · {other or ''}",
            f"{n.direction} em {n.data_emissao:%d/%m/%Y} · {brl(n.valor_total)}", f"/notas?nota={n.id}")

    # títulos
    conds = [Title.counterparty_name.ilike(like), Title.document_number.ilike(like)]
    if len(digits) >= 8:
        conds.append(Title.counterparty_doc.like(f"%{digits}%"))
    if amount is not None:
        conds += [Title.amount == amount, (Title.amount - Title.paid_amount) == amount]
    for t in db.scalars(select(Title).where(Title.client_id.in_(ids), or_(*conds))
                        .order_by(Title.due_date.desc()).limit(8)):
        hit("titulo", t.id, t.client_id, f"A {t.kind}: {t.counterparty_name}",
            f"{t.document_number or 's/ nº'} · vence {t.due_date:%d/%m/%Y} · {brl(t.amount)} · {t.status}",
            f"/financeiro?titulo={t.id}")

    # lançamentos bancários
    conds = [BankTransaction.description.ilike(like)]
    if amount is not None:
        conds += [BankTransaction.amount == amount, BankTransaction.amount == -amount]
    for tx in db.scalars(select(BankTransaction).where(BankTransaction.client_id.in_(ids), or_(*conds))
                         .order_by(BankTransaction.date.desc()).limit(8)):
        hit("lancamento", tx.id, tx.client_id, tx.description, f"{tx.date:%d/%m/%Y} · {brl(tx.amount)}",
            "/extratos?status=")
    return hits
