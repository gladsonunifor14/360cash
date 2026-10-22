"""Contas bancárias, extratos (OFX/CSV/Open Finance), classificação e aplicações financeiras."""

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, get_client_for, get_principal, require_staff
from app.models import BankAccount, BankTransaction, ChartAccount, InvestmentStatement
from app.routers.common import read_limited
from app.routers.compliance import store_document
from app.schemas import (
    AcceptSuggestionsIn,
    BankAccountIn,
    BankAccountOut,
    InvestmentIn,
    InvestmentOut,
    IrSimulationIn,
    StatementImportOut,
    TransactionClassifyIn,
    TransactionOut,
)
from app.services import bank_parser, classifier, investments, open_finance

router = APIRouter()


def _account(bank_account_id: str, p: Principal, db: Session) -> BankAccount:
    acc = db.get(BankAccount, bank_account_id)
    if not acc or acc.office_id != p.office_id:
        raise HTTPException(404, "Conta bancária não encontrada")
    get_client_for(acc.client_id, p, db)
    return acc


def _save_transactions(db: Session, acc: BankAccount, txs: list[bank_parser.ParsedTransaction]) -> tuple[int, int]:
    existing = set(db.scalars(select(BankTransaction.fitid).where(BankTransaction.bank_account_id == acc.id)))
    new = dup = 0
    for t in txs:
        if t.fitid in existing:
            dup += 1
            continue
        existing.add(t.fitid)
        db.add(BankTransaction(
            office_id=acc.office_id, client_id=acc.client_id, bank_account_id=acc.id, fitid=t.fitid,
            date=t.date, description=t.description,
            normalized_description=bank_parser.normalize_description(t.description) or "SEM HISTORICO",
            amount=t.amount,
        ))
        new += 1
    db.flush()
    return new, dup


# --------------------------------------------------------------------------- contas


@router.get("/clients/{client_id}/bank-accounts", response_model=list[BankAccountOut],
            tags=["Extratos bancários"], summary="Contas bancárias e de aplicação do cliente")
def list_bank_accounts(client_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    return db.scalars(select(BankAccount).where(BankAccount.client_id == client.id)
                      .order_by(BankAccount.bank_name)).all()


@router.post("/bank-accounts", response_model=BankAccountOut, status_code=201, tags=["Extratos bancários"],
             summary="Cadastra conta corrente ou de aplicação")
def create_bank_account(body: BankAccountIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    client = get_client_for(body.client_id, p, db)
    acc = BankAccount(office_id=p.office_id, **{**body.model_dump(), "client_id": client.id})
    db.add(acc)
    db.commit()
    return acc


# --------------------------------------------------------------------------- extratos


@router.post("/bank-accounts/{bank_account_id}/statements", response_model=StatementImportOut,
             tags=["Extratos bancários"], summary="Importa extrato OFX ou CSV e aplica a classificação aprendida")
async def import_statement(bank_account_id: str, file: UploadFile = File(...), p: Principal = Depends(get_principal),
                           db: Session = Depends(get_db)):
    acc = _account(bank_account_id, p, db)
    if acc.kind != "corrente":
        raise HTTPException(422, "Para aplicações, informe o extrato mensal em /investments")
    data = await read_limited(file)
    try:
        parsed = bank_parser.parse_statement(file.filename or "", data)
    except bank_parser.StatementParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    store_document(db, p, acc.client_id, "extrato", file.filename or "extrato", file.content_type or "", data)
    if acc.source == "manual":
        acc.source = "ofx"
    new, dup = _save_transactions(db, acc, parsed.transactions)
    stats = classifier.classify_pending(db, acc.client_id, acc.office_id)
    db.commit()
    return StatementImportOut(importados=new, duplicados=dup, classificacao=stats)


@router.get("/clients/{client_id}/transactions", response_model=list[TransactionOut], tags=["Extratos bancários"],
            summary="Lançamentos bancários")
def list_transactions(
    client_id: str,
    status: str | None = Query(None, pattern="^(pendente|classificado|sugerido)$"),
    bank_account_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(500, le=2000),
    offset: int = 0,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_for(client_id, p, db)
    stmt = select(BankTransaction).where(BankTransaction.client_id == client.id)
    if status == "pendente":
        stmt = stmt.where(BankTransaction.account_id.is_(None))
    elif status == "classificado":
        stmt = stmt.where(BankTransaction.account_id.is_not(None))
    elif status == "sugerido":
        stmt = stmt.where(BankTransaction.account_id.is_(None), BankTransaction.suggested_account_id.is_not(None))
    if bank_account_id:
        stmt = stmt.where(BankTransaction.bank_account_id == bank_account_id)
    if start:
        stmt = stmt.where(BankTransaction.date >= start)
    if end:
        stmt = stmt.where(BankTransaction.date <= end)
    return db.scalars(stmt.order_by(BankTransaction.date.desc()).limit(limit).offset(offset)).all()


def _owned_transactions(ids: list[str], p: Principal, db: Session) -> list[BankTransaction]:
    txs = db.scalars(select(BankTransaction).where(BankTransaction.id.in_(ids),
                                                   BankTransaction.office_id == p.office_id)).all()
    if len(txs) != len(set(ids)):
        raise HTTPException(404, "Lançamento não encontrado")
    for client_id in {t.client_id for t in txs}:
        get_client_for(client_id, p, db)
    return list(txs)


@router.post("/transactions/classify", response_model=list[TransactionOut], tags=["Extratos bancários"],
             summary="Classifica lançamentos (cliente ou contador) — alimenta o aprendizado da IA")
def classify_transactions(body: TransactionClassifyIn, p: Principal = Depends(get_principal),
                          db: Session = Depends(get_db)):
    acc = db.get(ChartAccount, body.account_id)
    if not acc or acc.office_id != p.office_id:
        raise HTTPException(422, "Conta inválida")
    txs = _owned_transactions(body.transaction_ids, p, db)
    who = "contador" if p.is_staff else "cliente"
    for t in txs:
        t.account_id, t.classified_by, t.confidence = acc.id, who, 1.0
    db.commit()
    return txs


@router.post("/transactions/accept-suggestions", response_model=list[TransactionOut], tags=["Extratos bancários"],
             summary="Confirma as sugestões da IA para os lançamentos informados")
def accept_suggestions(body: AcceptSuggestionsIn, p: Principal = Depends(get_principal),
                       db: Session = Depends(get_db)):
    txs = _owned_transactions(body.transaction_ids, p, db)
    who = "contador" if p.is_staff else "cliente"
    for t in txs:
        if t.suggested_account_id and not t.account_id:
            t.account_id, t.classified_by = t.suggested_account_id, who
    db.commit()
    return txs


@router.post("/clients/{client_id}/transactions/auto-classify", response_model=dict, tags=["Extratos bancários"],
             summary="Replica a classificação aprendida (IA) para os lançamentos pendentes")
def auto_classify(client_id: str, use_llm: bool = True, p: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    stats = classifier.classify_pending(db, client.id, client.office_id, use_llm=use_llm)
    db.commit()
    return stats


# --------------------------------------------------------------------------- Open Finance


@router.post("/bank-accounts/{bank_account_id}/open-finance/sync", response_model=StatementImportOut,
             tags=["Open Finance"], summary="Sincroniza transações via agregador Open Finance")
def open_finance_sync(bank_account_id: str, start: date, end: date, p: Principal = Depends(require_staff),
                      db: Session = Depends(get_db)):
    acc = _account(bank_account_id, p, db)
    if not acc.external_id:
        raise HTTPException(422, "Conta sem vínculo Open Finance (external_id)")
    try:
        txs = open_finance.get_provider().list_transactions(acc.external_id, start, end)
    except open_finance.OpenFinanceError as exc:
        raise HTTPException(503, str(exc)) from exc
    acc.source = "open_finance"
    new, dup = _save_transactions(db, acc, txs)
    stats = classifier.classify_pending(db, acc.client_id, acc.office_id)
    db.commit()
    return StatementImportOut(importados=new, duplicados=dup, classificacao=stats)


# --------------------------------------------------------------------------- aplicações financeiras


@router.post("/investments", response_model=InvestmentOut, status_code=201, tags=["Aplicações financeiras"],
             summary="Registra extrato mensal de aplicação e calcula rendimento, taxas e IRRF")
def upsert_investment(body: InvestmentIn, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    acc = _account(body.bank_account_id, p, db)
    if acc.kind != "aplicacao":
        raise HTTPException(422, "Conta informada não é de aplicação financeira")
    competencia = body.competencia.replace(day=1)
    calc = investments.calcular_mes(body.saldo_inicial, body.aplicacoes, body.resgates, body.saldo_final,
                                    body.irrf, body.iof, body.taxa_administracao, body.benchmark_mes_pct)
    st = db.scalar(select(InvestmentStatement).where(InvestmentStatement.bank_account_id == acc.id,
                                                     InvestmentStatement.competencia == competencia))
    values = {**body.model_dump(exclude={"bank_account_id", "competencia"}), **calc}
    if st:
        for k, v in values.items():
            setattr(st, k, v)
    else:
        st = InvestmentStatement(office_id=acc.office_id, client_id=acc.client_id, bank_account_id=acc.id,
                                 competencia=competencia, **values)
        db.add(st)
    db.commit()
    return st


@router.get("/clients/{client_id}/investments", response_model=list[InvestmentOut], tags=["Aplicações financeiras"],
            summary="Extratos mensais de aplicações")
def list_investments(client_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    return db.scalars(select(InvestmentStatement).where(InvestmentStatement.client_id == client.id)
                      .order_by(InvestmentStatement.competencia)).all()


@router.post("/investments/simulate-ir", response_model=dict, tags=["Aplicações financeiras"],
             summary="Simula IOF e IRRF (tabela regressiva) de um resgate")
def simulate_ir(body: IrSimulationIn, _: Principal = Depends(get_principal)):
    if body.data_resgate < body.data_aplicacao:
        raise HTTPException(422, "Data de resgate anterior à aplicação")
    return investments.calcular_ir_resgate(body.valor_aplicado, body.valor_resgate_bruto, body.data_aplicacao,
                                           body.data_resgate)
