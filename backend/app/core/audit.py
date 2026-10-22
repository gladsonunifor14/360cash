"""Trilha de auditoria automática.

Um listener `before_flush` captura INSERT/UPDATE/DELETE de toda entidade marcada com
`__audited__ = True` e grava em `audit_log` quem (usuário), quando, de onde (IP) e o
que mudou (valores antigos e novos por campo). O contexto da requisição é propagado
via `contextvars`, preenchido pelo middleware e pela dependência de autenticação.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models import AuditLog

SENSITIVE_FIELDS = {"password_hash", "token_hash", "code_hash", "key_hash"}


@dataclass
class AuditContext:
    user_id: str | None = None
    office_id: str | None = None
    ip: str | None = None
    request_id: str | None = None


audit_ctx: ContextVar[AuditContext | None] = ContextVar("audit_ctx", default=None)


def current_ctx() -> AuditContext:
    """Contexto da requisição atual (criado sob demanda fora de requisições HTTP, ex.: scripts)."""
    ctx = audit_ctx.get()
    if ctx is None:
        ctx = AuditContext()
        audit_ctx.set(ctx)
    return ctx


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _mask(field: str, value: Any) -> Any:
    return "***" if field in SENSITIVE_FIELDS and value is not None else _jsonable(value)


def _snapshot(obj) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    return {c.key: _mask(c.key, getattr(obj, c.key)) for c in mapper.column_attrs}


def _diff(obj) -> dict[str, Any]:
    state = inspect(obj)
    changes: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        hist = state.attrs[attr.key].history
        if hist.has_changes():
            old = hist.deleted[0] if hist.deleted else None
            new = hist.added[0] if hist.added else None
            if old != new and attr.key != "updated_at":
                changes[attr.key] = {"de": _mask(attr.key, old), "para": _mask(attr.key, new)}
    return changes


def _entry(obj, action: str, changes: dict | None) -> AuditLog:
    ctx = current_ctx()
    return AuditLog(
        office_id=getattr(obj, "office_id", None) or ctx.office_id,
        user_id=ctx.user_id,
        ip=ctx.ip,
        request_id=ctx.request_id,
        action=action,
        entity=obj.__tablename__,
        entity_id=str(getattr(obj, "id", "")) or None,
        changes=changes,
    )


@event.listens_for(Session, "before_flush")
def _audit_before_flush(session: Session, flush_context, instances) -> None:
    entries: list[AuditLog] = []
    for obj in session.new:
        if getattr(obj, "__audited__", False):
            # garante PK antes do flush para referenciar no log
            for col in inspect(obj).mapper.primary_key:
                if getattr(obj, col.key) is None and col.default is not None and callable(col.default.arg):
                    setattr(obj, col.key, col.default.arg(None))
            entries.append(_entry(obj, "create", _snapshot(obj)))
    for obj in session.dirty:
        if getattr(obj, "__audited__", False) and session.is_modified(obj, include_collections=False):
            changes = _diff(obj)
            if changes:
                entries.append(_entry(obj, "update", changes))
    for obj in session.deleted:
        if getattr(obj, "__audited__", False):
            entries.append(_entry(obj, "delete", _snapshot(obj)))
    session.add_all(entries)


def log_event(db: Session, action: str, entity: str, entity_id: str | None = None, **changes: Any) -> None:
    """Registra eventos que não são alterações de entidade (login, falhas de OTP, exportações)."""
    ctx = current_ctx()
    db.add(
        AuditLog(
            office_id=changes.pop("office_id", None) or ctx.office_id,
            user_id=changes.pop("user_id", None) or ctx.user_id,
            ip=ctx.ip,
            request_id=ctx.request_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            changes={k: _jsonable(v) for k, v in changes.items()} or None,
        )
    )
