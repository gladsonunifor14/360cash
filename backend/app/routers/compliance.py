"""Contrato de adesão, termos LGPD/confidencialidade, procurações e repositório de documentos."""

from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_event
from app.core.database import get_db
from app.core.deps import Principal, get_client_for, get_principal, require_admin, require_staff
from app.core.ratelimit import client_ip
from app.core.security import utcnow
from app.models import Contract, ContractTemplate, Document, Office, PowerOfAttorney, Term, TermAcceptance
from app.routers.common import read_limited
from app.schemas import (
    ContractIn,
    ContractOut,
    ContractTemplateIn,
    ContractTemplateOut,
    DocCategory,
    DocumentOut,
    Message,
    PoaIn,
    PoaOut,
    TermAcceptanceOut,
    TermIn,
    TermOut,
)
from app.services import storage
from app.services.cnpj import format_cnpj
from app.services.defaults import accept_current_terms, current_terms, pending_terms, sha256

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf", "application/xml", "text/xml", "image/png", "image/jpeg", "text/csv", "text/plain",
    "application/zip", "application/x-ofx", "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


# --------------------------------------------------------------------------- termos


@router.get("/terms", response_model=list[TermOut], tags=["LGPD e Termos"], summary="Termos vigentes")
def list_terms(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return current_terms(db, p.office_id)


@router.get("/terms/pending", response_model=list[TermOut], tags=["LGPD e Termos"],
            summary="Termos vigentes ainda não aceitos pelo usuário")
def my_pending_terms(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return pending_terms(db, p.user)


@router.post("/terms/accept", response_model=list[TermAcceptanceOut], tags=["LGPD e Termos"],
             summary="Aceita todos os termos vigentes pendentes (registra IP, data/hora e hash)")
def accept_terms(request: Request, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    out = accept_current_terms(db, p.user, client_ip(request), request.headers.get("user-agent"))
    db.commit()
    return out


@router.post("/terms", response_model=TermOut, status_code=201, tags=["LGPD e Termos"],
             summary="Publica nova versão de termo (exige novo aceite dos usuários)")
def publish_term(body: TermIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    version = (db.scalar(select(func.max(Term.version)).where(Term.office_id == p.office_id,
                                                             Term.kind == body.kind)) or 0) + 1
    term = Term(office_id=p.office_id, kind=body.kind, version=version, title=body.title, body=body.body,
                content_sha256=sha256(body.body))
    db.add(term)
    db.commit()
    return term


@router.get("/terms/acceptances", response_model=list[TermAcceptanceOut], tags=["LGPD e Termos"],
            summary="Evidências de aceite dos termos (escritório)")
def list_acceptances(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return db.scalars(
        select(TermAcceptance).join(Term, Term.id == TermAcceptance.term_id)
        .where(Term.office_id == p.office_id).order_by(TermAcceptance.accepted_at.desc())
    ).all()


# --------------------------------------------------------------------------- contrato de adesão


@router.get("/contract-templates", response_model=list[ContractTemplateOut], tags=["Contratos"],
            summary="Modelos de contrato de adesão")
def list_templates(p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    return db.scalars(select(ContractTemplate).where(ContractTemplate.office_id == p.office_id)
                      .order_by(ContractTemplate.version.desc())).all()


@router.post("/contract-templates", response_model=ContractTemplateOut, status_code=201, tags=["Contratos"],
             summary="Publica nova versão do modelo de contrato")
def create_template(body: ContractTemplateIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    version = (db.scalar(select(func.max(ContractTemplate.version))
                         .where(ContractTemplate.office_id == p.office_id)) or 0) + 1
    tpl = ContractTemplate(office_id=p.office_id, version=version, title=body.title, body=body.body)
    db.add(tpl)
    db.commit()
    return tpl


def _brl(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@router.post("/contracts", response_model=ContractOut, status_code=201, tags=["Contratos"],
             summary="Gera contrato de adesão para o cliente (aguarda aceite)")
def create_contract(body: ContractIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    client = get_client_for(body.client_id, p, db)
    stmt = select(ContractTemplate).where(ContractTemplate.office_id == p.office_id, ContractTemplate.is_active)
    if body.template_id:
        stmt = stmt.where(ContractTemplate.id == body.template_id)
    tpl = db.scalar(stmt.order_by(ContractTemplate.version.desc()))
    if not tpl:
        raise HTTPException(404, "Modelo de contrato não encontrado")
    office = db.get(Office, p.office_id)
    content = tpl.body
    for k, v in {
        "cliente_razao_social": client.razao_social, "cliente_cnpj": format_cnpj(client.cnpj),
        "escritorio_razao_social": office.razao_social, "escritorio_cnpj": format_cnpj(office.cnpj),
        "mensalidade": _brl(body.monthly_fee), "data_inicio": body.start_date.strftime("%d/%m/%Y"),
    }.items():
        content = content.replace("{{" + k + "}}", v)
    contract = Contract(office_id=p.office_id, client_id=client.id, template_id=tpl.id, content=content,
                        content_sha256=sha256(content), monthly_fee=body.monthly_fee, start_date=body.start_date)
    db.add(contract)
    db.commit()
    return contract


@router.get("/contracts", response_model=list[ContractOut], tags=["Contratos"], summary="Lista contratos")
def list_contracts(client_id: str | None = None, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Contract).where(Contract.office_id == p.office_id).order_by(Contract.created_at.desc())
    if not p.is_staff:
        stmt = stmt.where(Contract.client_id == p.user.client_id)
    elif client_id:
        stmt = stmt.where(Contract.client_id == client_id)
    return db.scalars(stmt).all()


def _get_contract(contract_id: str, p: Principal, db: Session) -> Contract:
    c = db.get(Contract, contract_id)
    if not c or c.office_id != p.office_id or (not p.is_staff and c.client_id != p.user.client_id):
        raise HTTPException(404, "Contrato não encontrado")
    return c


@router.post("/contracts/{contract_id}/accept", response_model=ContractOut, tags=["Contratos"],
             summary="Aceite eletrônico do contrato pelo cliente (IP, data/hora, usuário e hash)")
def accept_contract(contract_id: str, request: Request, p: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)):
    c = _get_contract(contract_id, p, db)
    if p.is_staff:
        raise HTTPException(403, "O aceite deve ser feito por usuário da empresa contratante")
    if c.status != "pendente":
        raise HTTPException(409, f"Contrato já está {c.status}")
    if sha256(c.content) != c.content_sha256:
        raise HTTPException(409, "Integridade do contrato violada")
    c.status, c.accepted_at, c.accepted_by = "aceito", utcnow(), p.user.id
    c.accepted_ip, c.accepted_user_agent = client_ip(request), (request.headers.get("user-agent") or "")[:300]
    db.commit()
    return c


@router.post("/contracts/{contract_id}/cancel", response_model=ContractOut, tags=["Contratos"],
             summary="Cancela contrato")
def cancel_contract(contract_id: str, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    c = _get_contract(contract_id, p, db)
    c.status = "cancelado"
    db.commit()
    return c


# --------------------------------------------------------------------------- procurações


@router.get("/powers-of-attorney", response_model=list[PoaOut], tags=["Procurações"], summary="Lista procurações")
def list_poa(client_id: str | None = None, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(PowerOfAttorney).where(PowerOfAttorney.office_id == p.office_id)
    if not p.is_staff:
        stmt = stmt.where(PowerOfAttorney.client_id == p.user.client_id)
    elif client_id:
        stmt = stmt.where(PowerOfAttorney.client_id == client_id)
    return db.scalars(stmt.order_by(PowerOfAttorney.valid_from.desc())).all()


@router.post("/powers-of-attorney", response_model=PoaOut, status_code=201, tags=["Procurações"],
             summary="Registra procuração")
def create_poa(body: PoaIn, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    get_client_for(body.client_id, p, db)
    if body.document_id:
        _get_document(body.document_id, p, db)
    if body.valid_until and body.valid_until < body.valid_from:
        raise HTTPException(422, "Validade final anterior à inicial")
    poa = PowerOfAttorney(office_id=p.office_id, **body.model_dump())
    db.add(poa)
    db.commit()
    return poa


@router.post("/powers-of-attorney/{poa_id}/revoke", response_model=PoaOut, tags=["Procurações"],
             summary="Revoga procuração")
def revoke_poa(poa_id: str, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    poa = db.get(PowerOfAttorney, poa_id)
    if not poa or poa.office_id != p.office_id:
        raise HTTPException(404, "Procuração não encontrada")
    poa.revoked_at = utcnow()
    db.commit()
    return poa


# --------------------------------------------------------------------------- documentos


def _get_document(doc_id: str, p: Principal, db: Session) -> Document:
    d = db.get(Document, doc_id)
    if (not d or d.deleted_at or d.office_id != p.office_id
            or (not p.is_staff and d.client_id != p.user.client_id)):
        raise HTTPException(404, "Documento não encontrado")
    return d


def store_document(db: Session, p: Principal, client_id: str | None, category: str, filename: str,
                   content_type: str, data: bytes) -> Document:
    key, sha = storage.put(p.office_id, data)
    doc = Document(office_id=p.office_id, client_id=client_id, category=category, filename=filename[:255],
                   content_type=content_type or "application/octet-stream", size_bytes=len(data), sha256=sha,
                   storage_key=key, uploaded_by=p.user.id)
    db.add(doc)
    db.flush()
    return doc


@router.post("/documents", response_model=DocumentOut, status_code=201, tags=["Documentos"],
             summary="Envia documento ao repositório")
async def upload_document(
    file: UploadFile = File(...),
    category: DocCategory = Form("outros"),
    client_id: str | None = Form(None),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not p.is_staff:
        client_id = p.user.client_id
    if client_id:
        get_client_for(client_id, p, db)
    if (file.content_type or "application/octet-stream") not in ALLOWED_TYPES:
        raise HTTPException(415, "Tipo de arquivo não permitido")
    data = await read_limited(file)
    doc = store_document(db, p, client_id, category, file.filename or "arquivo", file.content_type, data)
    db.commit()
    return doc


@router.get("/documents", response_model=list[DocumentOut], tags=["Documentos"], summary="Lista documentos")
def list_documents(client_id: str | None = None, category: DocCategory | None = None,
                   p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    stmt = select(Document).where(Document.office_id == p.office_id, Document.deleted_at.is_(None))
    if not p.is_staff:
        stmt = stmt.where(Document.client_id == p.user.client_id)
    elif client_id:
        stmt = stmt.where(Document.client_id == client_id)
    if category:
        stmt = stmt.where(Document.category == category)
    return db.scalars(stmt.order_by(Document.created_at.desc()).limit(500)).all()


@router.get("/documents/{doc_id}/download", tags=["Documentos"], summary="Baixa documento",
            response_class=Response)
def download_document(doc_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    d = _get_document(doc_id, p, db)
    log_event(db, "download", "documents", d.id)
    db.commit()
    safe_name = "".join(c for c in d.filename if c.isalnum() or c in "._- ") or "arquivo"
    return Response(storage.get(d.storage_key), media_type=d.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{safe_name}"',
                             "X-Content-Type-Options": "nosniff"})


@router.delete("/documents/{doc_id}", response_model=Message, tags=["Documentos"],
               summary="Remove documento (exclusão lógica, preservada para auditoria)")
def delete_document(doc_id: str, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    d = _get_document(doc_id, p, db)
    d.deleted_at = utcnow()
    db.commit()
    return Message(detail="Documento removido")
