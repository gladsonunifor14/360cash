"""Notas fiscais (XML NF-e/NFC-e), plano de contas e regras de CFOP."""

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, get_client_for, get_principal, require_admin, require_staff
from app.models import CfopRule, ChartAccount, Client, Invoice, InvoiceItem, Title
from app.routers.common import expand_zip, read_limited
from app.routers.compliance import store_document
from app.schemas import (
    CfopRuleOut,
    ChartAccountIn,
    ChartAccountOut,
    ImportResult,
    InvoiceDetailOut,
    InvoiceItemOut,
    InvoiceOut,
    ItemClassifyIn,
)
from app.services import nfe_parser
from app.services.accounting import account_by_code, resolve_cfop
from app.services.titles import titles_from_invoice

router = APIRouter(tags=["Notas fiscais"])

_FLIP = {"1": "5", "2": "6", "3": "7", "5": "1", "6": "2", "7": "3"}


def cfop_for_client(cfop: str, direction: str) -> str:
    """Em nota recebida, o CFOP do XML é o do emitente; inverte entrada/saída para o destinatário."""
    if direction == "recebida" and cfop[:1] in _FLIP:
        return _FLIP[cfop[0]] + cfop[1:]
    return cfop


def _classify_item(db: Session, item: InvoiceItem, accounts: dict[str, ChartAccount]) -> None:
    operation, code = resolve_cfop(db, item.cfop_cliente)
    item.operation = operation
    item.account_id = accounts[code].id if code and code in accounts else None
    item.classification_source = "cfop" if item.account_id else None


def _import_one(db: Session, p: Principal, client: Client, filename: str, data: bytes,
                accounts: dict[str, ChartAccount]) -> ImportResult:
    try:
        parsed = nfe_parser.parse(data)
    except nfe_parser.NfeParseError as exc:
        return ImportResult(arquivo=filename, status="erro", detalhe=str(exc))

    if isinstance(parsed, nfe_parser.NfeCancelEvent):
        inv = db.scalar(select(Invoice).where(Invoice.client_id == client.id, Invoice.chave == parsed.chave))
        if not inv:
            return ImportResult(arquivo=filename, status="erro", detalhe="NF-e do cancelamento não importada")
        inv.cancelled = True
        for t in db.scalars(select(Title).where(Title.invoice_id == inv.id, Title.status.in_(("aberto", "aprovado",
                                                                                            "agendado")))):
            t.status = "cancelado"
        return ImportResult(arquivo=filename, status="cancelamento", id=inv.id)

    if parsed.emit_cnpj == client.cnpj:
        direction = "emitida"
    elif parsed.dest_documento == client.cnpj:
        direction = "recebida"
    else:
        return ImportResult(arquivo=filename, status="erro",
                            detalhe="NF-e não pertence ao cliente (CNPJ não é emitente nem destinatário)")
    existing = db.scalar(select(Invoice.id).where(Invoice.client_id == client.id, Invoice.chave == parsed.chave))
    if existing:
        return ImportResult(arquivo=filename, status="duplicado", id=existing)

    doc = store_document(db, p, client.id, "nfe_xml", filename, "application/xml", data)
    inv = Invoice(
        office_id=client.office_id, client_id=client.id, direction=direction, chave=parsed.chave,
        modelo=parsed.modelo, numero=parsed.numero, serie=parsed.serie,
        natureza_operacao=(parsed.natureza_operacao or "")[:200] or None, data_emissao=parsed.data_emissao,
        emit_cnpj=parsed.emit_cnpj, emit_nome=parsed.emit_nome, dest_documento=parsed.dest_documento,
        dest_nome=parsed.dest_nome, document_id=doc.id, **parsed.totais,
    )
    for it in parsed.items:
        item = InvoiceItem(
            n_item=it.n_item, codigo=it.codigo, descricao=it.descricao, ncm=it.ncm, cfop=it.cfop,
            cfop_cliente=cfop_for_client(it.cfop, direction), quantidade=it.quantidade,
            valor_unitario=it.valor_unitario, valor_total=it.valor_total,
        )
        _classify_item(db, item, accounts)
        inv.items.append(item)
    db.add(inv)
    db.flush()
    titles = titles_from_invoice(inv, parsed)
    db.add_all(titles)
    detail = f"{len(titles)} título(s) a {titles[0].kind} gerado(s)" if titles else None
    return ImportResult(arquivo=filename, status="importado", id=inv.id, detalhe=detail)


@router.post("/clients/{client_id}/invoices/import", response_model=list[ImportResult],
             summary="Importa XML de NF-e emitidas e recebidas (arquivos .xml ou .zip)",
             description="A direção (emitida/recebida) é identificada pelo CNPJ do cliente. Cada item é "
                         "classificado no plano de contas pelo CFOP na perspectiva do cliente. XML de evento "
                         "de cancelamento (110111) marca a nota como cancelada.")
async def import_invoices(client_id: str, files: list[UploadFile] = File(...),
                          p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    accounts = account_by_code(db, p.office_id)
    results = []
    for f in files:
        data = await read_limited(f)
        for name, content in expand_zip(f.filename or "nfe.xml", data, (".xml",)):
            results.append(_import_one(db, p, client, name, content, accounts))
    db.commit()
    return results


@router.get("/clients/{client_id}/invoices", response_model=list[InvoiceOut], summary="Lista notas fiscais")
def list_invoices(
    client_id: str,
    direction: str | None = Query(None, pattern="^(emitida|recebida)$"),
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(200, le=1000),
    offset: int = 0,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_for(client_id, p, db)
    stmt = select(Invoice).where(Invoice.client_id == client.id)
    if direction:
        stmt = stmt.where(Invoice.direction == direction)
    if start:
        stmt = stmt.where(Invoice.data_emissao >= start)
    if end:
        stmt = stmt.where(Invoice.data_emissao <= end)
    return db.scalars(stmt.order_by(Invoice.data_emissao.desc()).limit(limit).offset(offset)).all()


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut, summary="Detalhe da nota com itens")
def get_invoice(invoice_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    inv = db.scalar(select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id))
    if not inv:
        raise HTTPException(404, "Nota não encontrada")
    get_client_for(inv.client_id, p, db)
    return inv


@router.patch("/invoice-items/{item_id}/classification", response_model=InvoiceItemOut,
              summary="Reclassifica manualmente um item da nota")
def classify_item(item_id: str, body: ItemClassifyIn, p: Principal = Depends(require_staff),
                  db: Session = Depends(get_db)):
    item = db.get(InvoiceItem, item_id)
    if not item:
        raise HTTPException(404, "Item não encontrado")
    get_client_for(item.invoice.client_id, p, db)
    acc = db.get(ChartAccount, body.account_id)
    if not acc or acc.office_id != p.office_id:
        raise HTTPException(422, "Conta inválida")
    item.account_id, item.classification_source = acc.id, "manual"
    db.commit()
    return item


@router.post("/clients/{client_id}/invoices/reclassify", response_model=dict,
             summary="Reaplica regras de CFOP aos itens não classificados manualmente")
def reclassify(client_id: str, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    accounts = account_by_code(db, p.office_id)
    items = db.scalars(
        select(InvoiceItem).join(Invoice).where(
            Invoice.client_id == client.id,
            (InvoiceItem.classification_source.is_(None)) | (InvoiceItem.classification_source == "cfop"))
    ).all()
    for item in items:
        _classify_item(db, item, accounts)
    db.commit()
    return {"itens_reclassificados": len(items)}


# --------------------------------------------------------------------------- plano de contas / CFOP


@router.get("/chart-accounts", response_model=list[ChartAccountOut], tags=["Plano de contas"],
            summary="Plano de contas gerencial")
def list_accounts(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return db.scalars(select(ChartAccount).where(ChartAccount.office_id == p.office_id, ChartAccount.is_active)
                      .order_by(ChartAccount.code)).all()


@router.post("/chart-accounts", response_model=ChartAccountOut, status_code=201, tags=["Plano de contas"],
             summary="Cria conta gerencial")
def create_account(body: ChartAccountIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(ChartAccount.id).where(ChartAccount.office_id == p.office_id,
                                               ChartAccount.code == body.code)):
        raise HTTPException(409, "Código já existe")
    acc = ChartAccount(office_id=p.office_id, **body.model_dump())
    db.add(acc)
    db.commit()
    return acc


@router.get("/cfop-rules", response_model=list[CfopRuleOut], tags=["Plano de contas"],
            summary="Tabela CFOP × operação × conta gerencial")
def list_cfop(cfop: str | None = Query(None, pattern=r"^\d{1,4}$"), _: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    stmt = select(CfopRule).order_by(CfopRule.cfop)
    if cfop:
        stmt = stmt.where(CfopRule.cfop.like(f"{cfop}%"))
    return db.scalars(stmt).all()
