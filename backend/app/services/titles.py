"""Contas a pagar e receber: geração a partir de NF-e, ações em lote e histórico."""

from collections import Counter
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, ChartAccount, Invoice, Title, User
from app.services.nfe_parser import NfeData, NfeDuplicata

FINAL_STATUSES = {"liquidado", "cancelado"}

# transições permitidas por ação em lote
BATCH_ACTIONS = {
    "aprovar": {"aberto", "parcial"},
    "agendar": {"aberto", "aprovado", "parcial"},
    "liquidar": {"aberto", "aprovado", "agendado", "parcial"},
    "cancelar": {"aberto", "aprovado", "agendado"},
}

FIELD_LABELS = {
    "amount": "Valor", "paid_amount": "Valor pago", "due_date": "Data de vencimento",
    "issue_date": "Data de emissão", "status": "Situação", "counterparty_name": "Favorecido/Pagador",
    "counterparty_doc": "CPF/CNPJ", "document_number": "Nº do documento", "description": "Descrição",
    "account_id": "Conta gerencial", "scheduled_for": "Agendado para", "settled_at": "Liquidado em",
    "document_id": "Anexo",
}
ACTION_LABELS = {"create": "criou", "update": "alterou", "delete": "excluiu"}


def titles_from_invoice(inv: Invoice, parsed: NfeData) -> list[Title]:
    """Recebida ⇒ conta a pagar ao emitente; emitida ⇒ conta a receber do destinatário.

    Usa as duplicatas (cobr/dup); sem duplicatas, gera um título à vista no valor da nota.
    O título herda a conta gerencial predominante (maior valor) dos itens.
    """
    by_account: Counter = Counter()
    for item in inv.items:
        if item.account_id:
            by_account[item.account_id] += item.valor_total
    account_id = by_account.most_common(1)[0][0] if by_account else None
    if not account_id:  # remessas/transferências não geram título
        return []
    receber = inv.direction == "emitida"
    parts = parsed.duplicatas or []
    if not parts:
        parts = [NfeDuplicata(numero=None, vencimento=inv.data_emissao, valor=inv.valor_total)]
    out = []
    for i, dup in enumerate(parts, 1):
        number = f"NF {inv.numero}" + (f"-{dup.numero or i}" if len(parts) > 1 else "")
        out.append(Title(
            office_id=inv.office_id, client_id=inv.client_id, kind="receber" if receber else "pagar",
            counterparty_name=(inv.dest_nome if receber else inv.emit_nome) or "Não informado",
            counterparty_doc=inv.dest_documento if receber else inv.emit_cnpj,
            document_number=number[:60], description=(inv.natureza_operacao or "")[:300] or None,
            issue_date=inv.data_emissao, due_date=max(dup.vencimento, inv.data_emissao), amount=dup.valor,
            account_id=account_id, invoice_id=inv.id, document_id=inv.document_id,
        ))
    return out


def urgency(t: Title, today: date) -> str:
    """Criticidade operacional: atrasado | hoje | proximo | concluido."""
    if t.status in FINAL_STATUSES:
        return "concluido"
    if t.due_date < today:
        return "atrasado"
    if t.due_date == today:
        return "hoje"
    return "proximo"


def history(db: Session, title: Title) -> list[dict]:
    """Mini-feed: quem criou, quem alterou o quê e quem aprovou/liquidou."""
    rows = db.scalars(
        select(AuditLog).where(AuditLog.entity == "titles", AuditLog.entity_id == title.id).order_by(AuditLog.id)
    ).all()
    names = {u.id: u.name for u in db.scalars(select(User).where(User.id.in_({r.user_id for r in rows if r.user_id})))}
    feed = []
    for r in rows:
        who = names.get(r.user_id, "Sistema (importação)")
        if r.action == "create":
            text = f"{who} criou o título"
        else:
            parts = []
            for field, change in (r.changes or {}).items():
                if field not in FIELD_LABELS:
                    continue
                if field == "status":
                    parts.append(f"mudou a situação de “{change['de']}” para “{change['para']}”")
                elif field == "document_id":
                    parts.append("anexou um documento" if not change["de"] else "substituiu o documento anexado")
                else:
                    old, new = _fmt(db, field, change["de"]), _fmt(db, field, change["para"])
                    parts.append(f"alterou {FIELD_LABELS[field]} de {old} para {new}")
            if not parts:
                continue
            text = f"{who} " + "; ".join(parts)
        feed.append({"at": r.at, "user": who, "action": r.action, "text": text})
    return feed


def _fmt(db: Session, field: str, value) -> str:
    """Valor legível no histórico: moeda, data dd/mm/aaaa e nome da conta."""
    if value in (None, ""):
        return "—"
    if field in ("amount", "paid_amount"):
        return "R$ " + f"{Decimal(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if field in ("due_date", "issue_date", "scheduled_for", "settled_at"):
        return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    if field == "account_id":
        acc = db.get(ChartAccount, value)
        return f"{acc.code} {acc.name}" if acc else "—"
    return str(value)


def settle(title: Title, value: Decimal, when: date) -> None:
    """Registra pagamento/recebimento (total ou parcial)."""
    title.paid_amount = Decimal(title.paid_amount or 0) + value
    if title.paid_amount >= title.amount:
        title.status, title.settled_at = "liquidado", when
    else:
        title.status = "parcial"
