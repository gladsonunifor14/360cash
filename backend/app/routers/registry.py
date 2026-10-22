"""Cadastros: escritório, clientes (via CNPJ na Receita Federal), usuários e chaves de API."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, get_client_for, get_principal, require_admin, require_staff
from app.core.security import hash_password, hash_token, utcnow
from app.models import ApiKey, Client, Office, User
from app.routers.auth import forgot_password
from app.schemas import (
    ApiKeyCreated,
    ApiKeyIn,
    ApiKeyOut,
    ClientCreate,
    ClientOut,
    ClientUpdate,
    CnpjLookupOut,
    ForgotIn,
    Message,
    OfficeOut,
    OfficeUpdate,
    UserCreate,
    UserOut,
)
from app.services import cnpj as cnpj_service

router = APIRouter(tags=["Cadastros"])


def _lookup(cnpj: str) -> tuple[dict, dict]:
    try:
        return cnpj_service.lookup(cnpj)
    except cnpj_service.CnpjError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/cnpj/{cnpj}", response_model=CnpjLookupOut, summary="Consulta CNPJ na base da Receita Federal")
def lookup_cnpj(cnpj: str, _: Principal = Depends(require_staff)):
    data, _raw = _lookup(cnpj)
    return data


# --------------------------------------------------------------------------- escritório


@router.get("/office", response_model=OfficeOut, summary="Dados do escritório")
def get_office(p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return db.get(Office, p.office_id)


@router.patch("/office", response_model=OfficeOut, summary="Atualiza dados complementares do escritório")
def update_office(body: OfficeUpdate, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    office = db.get(Office, p.office_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(office, k, v)
    db.commit()
    return office


@router.post("/office/sync-receita", response_model=OfficeOut, summary="Reimporta dados do escritório da Receita")
def sync_office(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    office = db.get(Office, p.office_id)
    data, raw = _lookup(office.cnpj)
    for k in ("razao_social", "nome_fantasia", "endereco", "cnae_principal", "situacao_cadastral"):
        setattr(office, k, data[k])
    office.dados_receita = raw
    db.commit()
    return office


# --------------------------------------------------------------------------- clientes


@router.get("/clients", response_model=list[ClientOut], summary="Lista empresas clientes")
def list_clients(
    q: str | None = Query(None, max_length=100, description="Busca por razão social, fantasia ou CNPJ"),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    stmt = select(Client).where(Client.office_id == p.office_id).order_by(Client.razao_social)
    if not p.is_staff:
        stmt = stmt.where(Client.id == p.user.client_id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Client.razao_social.ilike(like), Client.nome_fantasia.ilike(like),
                              Client.cnpj.like(f"%{cnpj_service.only_digits(q) or q}%")))
    return db.scalars(stmt).all()


@router.post("/clients", response_model=ClientOut, status_code=201,
             summary="Cadastra cliente importando os dados do CNPJ da Receita Federal")
def create_client(body: ClientCreate, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    if db.scalar(select(Client.id).where(Client.office_id == p.office_id, Client.cnpj == body.cnpj)):
        raise HTTPException(409, "Cliente já cadastrado")
    data, raw = _lookup(body.cnpj)
    client = Client(
        office_id=p.office_id, cnpj=body.cnpj, razao_social=data["razao_social"],
        nome_fantasia=data["nome_fantasia"], email=body.email or data["email"],
        telefone=body.telefone or data["telefone"], endereco=data["endereco"],
        natureza_juridica=data["natureza_juridica"], cnae_principal=data["cnae_principal"],
        situacao_cadastral=data["situacao_cadastral"], data_abertura=data["data_abertura"],
        regime_tributario=body.regime_tributario or data["regime_tributario"], dados_receita=raw,
    )
    db.add(client)
    db.commit()
    return client


@router.get("/clients/{client_id}", response_model=ClientOut, summary="Detalhe do cliente")
def get_client(client_id: str, p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    return get_client_for(client_id, p, db)


@router.patch("/clients/{client_id}", response_model=ClientOut, summary="Atualiza cliente")
def update_client(client_id: str, body: ClientUpdate, p: Principal = Depends(require_staff),
                  db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(client, k, v)
    db.commit()
    return client


@router.post("/clients/{client_id}/sync-receita", response_model=ClientOut,
             summary="Reimporta dados do cliente da Receita Federal")
def sync_client(client_id: str, p: Principal = Depends(require_staff), db: Session = Depends(get_db)):
    client = get_client_for(client_id, p, db)
    data, raw = _lookup(client.cnpj)
    for k in ("razao_social", "nome_fantasia", "endereco", "natureza_juridica", "cnae_principal",
              "situacao_cadastral", "data_abertura"):
        setattr(client, k, data[k])
    client.dados_receita = raw
    db.commit()
    return client


# --------------------------------------------------------------------------- usuários


@router.get("/users", response_model=list[UserOut], summary="Usuários do escritório")
def list_users(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(User).where(User.office_id == p.office_id).order_by(User.name)).all()


@router.post("/users", response_model=UserOut, status_code=201,
             summary="Convida usuário (recebe e-mail para definir a senha)")
def create_user(body: UserCreate, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    if body.role == "cliente":
        if not body.client_id:
            raise HTTPException(422, "Usuário cliente precisa de client_id")
        get_client_for(body.client_id, p, db)
    elif body.client_id:
        raise HTTPException(422, "Somente usuários do tipo cliente são vinculados a uma empresa")
    if db.scalar(select(User.id).where(User.email == body.email.lower())):
        raise HTTPException(409, "E-mail já cadastrado")
    user = User(office_id=p.office_id, client_id=body.client_id, name=body.name, email=body.email.lower(),
                role=body.role, password_hash=hash_password(secrets.token_urlsafe(32)))
    db.add(user)
    db.commit()
    forgot_password(ForgotIn(email=user.email), db)  # convite = link de definição de senha
    return user


@router.post("/users/{user_id}/deactivate", response_model=Message, summary="Desativa usuário")
def deactivate_user(user_id: str, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user or user.office_id != p.office_id:
        raise HTTPException(404, "Usuário não encontrado")
    if user.id == p.user.id:
        raise HTTPException(400, "Não é possível desativar o próprio usuário")
    user.is_active = False
    db.commit()
    return Message(detail="Usuário desativado")


# --------------------------------------------------------------------------- chaves de API


@router.get("/api-keys", response_model=list[ApiKeyOut], tags=["Integrações"], summary="Chaves de API")
def list_keys(p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(ApiKey).where(ApiKey.office_id == p.office_id).order_by(ApiKey.created_at)).all()


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=201, tags=["Integrações"],
             summary="Cria chave de API para integração com outros sistemas")
def create_key(body: ApiKeyIn, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    raw = "c360_" + secrets.token_urlsafe(32)
    key = ApiKey(office_id=p.office_id, user_id=p.user.id, name=body.name, prefix=raw[:12],
                 key_hash=hash_token(raw))
    db.add(key)
    db.commit()
    return ApiKeyCreated.model_validate({**ApiKeyOut.model_validate(key).model_dump(), "key": raw})


@router.delete("/api-keys/{key_id}", response_model=Message, tags=["Integrações"], summary="Revoga chave de API")
def revoke_key(key_id: str, p: Principal = Depends(require_admin), db: Session = Depends(get_db)):
    key = db.get(ApiKey, key_id)
    if not key or key.office_id != p.office_id:
        raise HTTPException(404, "Chave não encontrada")
    key.revoked_at = utcnow()
    db.commit()
    return Message(detail="Chave revogada")
