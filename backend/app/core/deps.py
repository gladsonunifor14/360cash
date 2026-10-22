"""Dependências de autenticação, autorização (RBAC) e isolamento multi-tenant."""

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import current_ctx
from app.core.database import get_db
from app.core.security import decode_jwt, hash_token, utcnow
from app.models import ApiKey, Client, User

bearer = HTTPBearer(auto_error=False, description="Access token JWT obtido em /auth/otp/verify")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Chave de integração")

STAFF_ROLES = {"admin", "contador"}


@dataclass
class Principal:
    user: User

    @property
    def office_id(self) -> str:
        return self.user.office_id

    @property
    def is_staff(self) -> bool:
        return self.user.role in STAFF_ROLES


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Não autenticado", headers={"WWW-Authenticate": "Bearer"}
    )


def get_principal(
    creds: HTTPAuthorizationCredentials | None = Security(bearer),
    api_key: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Principal:
    user: User | None = None
    if creds:
        try:
            payload = decode_jwt(creds.credentials, "access")
        except jwt.PyJWTError:
            raise _unauthorized() from None
        user = db.get(User, payload["sub"])
        # tokens emitidos antes de uma troca de senha são invalidados
        if user and user.password_changed_at and payload.get("pwd", 0) < int(user.password_changed_at.timestamp()):
            user = None
    elif api_key:
        key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_token(api_key), ApiKey.revoked_at.is_(None)))
        if key:
            key.last_used_at = utcnow()
            db.commit()
            user = db.get(User, key.user_id)
    if not user or not user.is_active:
        raise _unauthorized()
    ctx = current_ctx()
    ctx.user_id, ctx.office_id = user.id, user.office_id
    return Principal(user)


def require_staff(p: Principal = Depends(get_principal)) -> Principal:
    if not p.is_staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso restrito ao escritório")
    return p


def require_admin(p: Principal = Depends(get_principal)) -> Principal:
    if p.user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Acesso restrito ao administrador do escritório")
    return p


def get_client_for(client_id: str, p: Principal, db: Session) -> Client:
    """Carrega o cliente garantindo isolamento: mesmo escritório e, para usuário cliente, a própria empresa."""
    client = db.get(Client, client_id)
    if not client or client.office_id != p.office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado")
    if not p.is_staff and p.user.client_id != client.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente não encontrado")
    return client
