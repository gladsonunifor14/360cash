"""Contas a pagar e receber, ações em lote e conciliação bancária."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, get_client_for, get_principal, require_staff
from app.core.security import utcnow
from app.core.validation import FieldError
from app.models import BankTransaction, ChartAccount, Title
from app.routers.common import read_limited
from app.routers.compliance import ALLOWED_TYPES, store_document
from app.schemas import (
    DUE_BEFORE_ISSUE,
    BatchIn,
    BatchPreviewIn,
    BatchPreviewOut,
    Message,
    ReconcileIn,
    ReconciliationOut,
    SuggestionOut,
    TitleDetail,
    TitleIn,
    TitleOut,
    TitleUpdate,
    TransactionOut,
)
from app.services import reconciliation as recon
from app.services.reconciliation import brl
from app.services.titles import BATCH_ACTIONS, FINAL_STATUSES, history, settle, urgency

router = APIRouter(tags=["Contas a pagar e receber"])

STATUS_LABEL = {"aberto": "em aberto", "aprovado": "aprovado", "agendado": "agendado", "parcial": "pago parcialmente",
                "liquidado": "liquidado", "cancelado": "cancelado"}
ACTION_PAST = {"aprovar": "aprovado", "agendar": "agendado", "liquidar": "liquidado", "cancelar": "cancelado"}


def _out(t: Title, today: date | None = None) -> TitleOut:
    o = TitleOut.model_validate(t)
    o.urgency = urgency(t, today or date.today())
    return o


def _title(title_id: str, p: Principal, db: Session) -> Title:
    t = db.get(Title, title_id)
    if not t or t.office_id != p.office_id:
        raise HTTPException(404, "Título não encontrado")
    get_client_for(t.client_id, p, db)
    return t


def _check_account(account_id: str | None, p: Principal, db: Session) -> None:
    if account_id:
        acc = db.get(ChartAccount, account_id)
        if not acc or acc.office_id != p.office_id:
            raise FieldError("account_id", "O campo 'Conta gerencial' não corresponde a uma conta do plano de contas")


@router.get("/clients/{client_id}/titles", response_model=list[TitleOut], summary="Lista títulos")
def list_titles(
    client_id: str,
    kind: str | None = Query(None, pattern="^(pagar|receber)$"),
    status: str | None = Query(None, description="situação ou 'pendentes'"),
    urgency_filter: str | None = Query(None, alias="urgency", pattern="^(atrasado|hoje|proximo|concluido)$"),
    q: str | None = Query(None, max_length=100),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_for(client_id, p, db)
    stmt = select(Title).where(Title.client_id == client.id)
    if kind:
        stmt = stmt.where(Title.kind == kind)
    if status == "pendentes":
        stmt = stmt.where(Title.status.not_in(FINAL_STATUSES))
    elif status:
        stmt = stmt.where(Title.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Title.counterparty_name.ilike(like), Title.document_number.ilike(like),
                              Title.description.ilike(like)))
    today = date.today()
    out = [_out(t, today) for t in db.scalars(stmt.order_by(Title.due_date, Title.counterparty_name).limit(1000))]
    return [o for o in out if not urgency_filter or o.urgency == urgency_filter]


@router.post("/titles", response_model=TitleOut, status_code=201, summary="Cria título a pagar ou a receber")
def create_title(body: TitleIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    client = get_client_for(body.client_id, p, db)
    _check_account(body.account_id, p, db)
    t = Title(office_id=p.office_id, created_by=p.user.id, **{**body.model_dump(), "client_id": client.id})
    db.add(t)
    db.commit()
    return _out(t)


@router.get("/titles/{title_id}", response_model=TitleDetail, summary="Título com histórico de alterações")
def get_title(title_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    t = _title(title_id, p, db)
    return TitleDetail(**_out(t).model_dump(), history=history(db, t))


@router.patch("/titles/{title_id}", response_model=TitleDetail, summary="Altera título")
def update_title(title_id: str, body: TitleUpdate, p: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    t = _title(title_id, p, db)
    if t.status in FINAL_STATUSES:
        raise HTTPException(409, f"O título está {STATUS_LABEL[t.status]} e não pode ser alterado.")
    data = body.model_dump(exclude_unset=True)
    _check_account(data.get("account_id"), p, db)
    issue, due = data.get("issue_date", t.issue_date), data.get("due_date", t.due_date)
    if due < issue:
        raise FieldError("due_date", DUE_BEFORE_ISSUE)
    if "amount" in data and data["amount"] < t.paid_amount:
        raise FieldError("amount", f"O campo 'Valor' não pode ser menor que o valor já pago ({brl(t.paid_amount)}).")
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    return TitleDetail(**_out(t).model_dump(), history=history(db, t))


@router.post("/titles/{title_id}/attachment", response_model=TitleOut, summary="Anexa boleto/nota ao título")
async def attach(title_id: str, file: UploadFile = File(...), p: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    t = _title(title_id, p, db)
    if (file.content_type or "") not in ALLOWED_TYPES:
        raise HTTPException(415, "Envie o anexo em PDF, imagem (PNG/JPG) ou XML")
    data = await read_limited(file)
    doc = store_document(db, p, t.client_id, "fiscal", file.filename or "anexo", file.content_type, data)
    t.document_id = doc.id
    db.commit()
    return _out(t)


def _preview(body: BatchPreviewIn, p: Principal, db: Session) -> tuple[BatchPreviewOut, list[Title]]:
    ids = list(dict.fromkeys(body.title_ids))
    titles = {t.id: t for t in db.scalars(select(Title).where(Title.id.in_(ids), Title.office_id == p.office_id))}
    allowed = BATCH_ACTIONS[body.action]
    eligible, ineligible = [], []
    for i in ids:
        t = titles.get(i)
        if not t:
            ineligible.append({"id": i, "motivo": "Título não encontrado"})
            continue
        get_client_for(t.client_id, p, db)
        if t.status not in allowed:
            ineligible.append({"id": i, "motivo": f"{t.document_number or t.counterparty_name}: título "
                                                  f"{STATUS_LABEL[t.status]} não pode ser {ACTION_PAST[body.action]}"})
            continue
        eligible.append(t)

    def total(kind=None):
        return sum((t.open_amount for t in eligible if kind in (None, t.kind)), Decimal("0.00"))

    return BatchPreviewOut(action=body.action, count=len(eligible), total=total(), total_pagar=total("pagar"),
                           total_receber=total("receber"), eligible_ids=[t.id for t in eligible],
                           ineligible=ineligible), eligible


@router.post("/titles/batch/preview", response_model=BatchPreviewOut,
             summary="Pré-visualiza ação em lote (quantidade e somatório antes de confirmar)")
def batch_preview(body: BatchPreviewIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return _preview(body, p, db)[0]


@router.post("/titles/batch", response_model=BatchPreviewOut, summary="Executa ação em lote confirmada",
             description="Exige `expected_total` igual ao somatório da pré-visualização, evitando confirmar "
                         "um lote diferente do que foi exibido ao operador.")
def batch_execute(body: BatchIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    preview, eligible = _preview(body, p, db)
    if not eligible:
        raise HTTPException(422, "Nenhum dos títulos selecionados pode receber esta ação. "
                                 + "; ".join(i.motivo for i in preview.ineligible[:3]))
    if preview.total != body.expected_total:
        raise HTTPException(409, f"O total do lote mudou de R$ {body.expected_total} para R$ {preview.total} "
                                 "desde a pré-visualização. Revise a seleção e confirme novamente.")
    when = body.on_date or date.today()
    now = utcnow()
    for t in eligible:
        if body.action == "aprovar":
            t.status, t.approved_by, t.approved_at = "aprovado", p.user.id, now
        elif body.action == "agendar":
            t.status, t.scheduled_for = "agendado", when
        elif body.action == "liquidar":
            settle(t, t.open_amount, when)
        elif body.action == "cancelar":
            t.status = "cancelado"
    db.commit()
    return preview


# --------------------------------------------------------------------------- conciliação


@router.get("/clients/{client_id}/reconciliation/suggestions", response_model=list[SuggestionOut],
            tags=["Conciliação bancária"], summary="Sugestões de conciliação extrato × títulos")
def reconciliation_suggestions(client_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    today = date.today()
    return [SuggestionOut(transaction=TransactionOut.model_validate(s.transaction), title=_out(s.title, today),
                          score=s.score, difference=s.difference, actions=s.actions)
            for s in recon.suggestions(db, client.id)]


@router.get("/clients/{client_id}/reconciliation/pending", response_model=list[TransactionOut],
            tags=["Conciliação bancária"], summary="Lançamentos do extrato ainda não conciliados")
def reconciliation_pending(client_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    done = recon.reconciled_ids(db, client.id)
    txs = db.scalars(select(BankTransaction).where(BankTransaction.client_id == client.id)
                     .order_by(BankTransaction.date.desc()).limit(1000))
    return [t for t in txs if t.id not in done]


@router.post("/reconciliations", response_model=list[ReconciliationOut], status_code=201,
             tags=["Conciliação bancária"], summary="Confirma conciliação (exata, juros/multa, desconto ou parcial)")
def reconcile(body: ReconcileIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    tx = db.get(BankTransaction, body.transaction_id)
    if not tx or tx.office_id != p.office_id:
        raise HTTPException(404, "Lançamento do extrato não encontrado")
    get_client_for(tx.client_id, p, db)
    t = _title(body.title_id, p, db)
    try:
        rows = recon.apply(db, tx, t, body.action, p.user.id)
    except recon.ReconciliationError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return rows


@router.delete("/reconciliations/{transaction_id}", response_model=Message, tags=["Conciliação bancária"],
               summary="Desfaz a conciliação de um lançamento")
def undo_reconcile(transaction_id: str, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    tx = db.get(BankTransaction, transaction_id)
    if not tx or tx.office_id != p.office_id:
        raise HTTPException(404, "Lançamento do extrato não encontrado")
    try:
        recon.undo(db, tx)
    except recon.ReconciliationError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return Message(detail="Conciliação desfeita")
