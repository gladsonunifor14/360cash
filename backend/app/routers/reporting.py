"""Relatórios (Fluxo de Caixa, DRE, Gerencial) e trilha de auditoria."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, get_client_for, get_principal, require_admin
from app.models import AuditLog
from app.schemas import AuditOut
from app.services import reports

router = APIRouter()


def _period(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(422, "Data final anterior à inicial")
    if (end - start).days > 366 * 3:
        raise HTTPException(422, "Período máximo de 3 anos")


@router.get("/clients/{client_id}/reports/cash-flow", tags=["Relatórios"], summary="Fluxo de Caixa mensal")
def cash_flow(client_id: str, start: date, end: date, p: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    _period(start, end)
    return reports.cash_flow(db, get_client_for(client_id, p, db), start, end)


@router.get("/clients/{client_id}/reports/dre", tags=["Relatórios"], summary="DRE gerencial mensal")
def dre(client_id: str, start: date, end: date,
        regime: str = Query("competencia", pattern="^(competencia|caixa)$"),
        p: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    _period(start, end)
    return reports.dre(db, get_client_for(client_id, p, db), start, end, regime)


@router.get("/clients/{client_id}/reports/management", tags=["Relatórios"],
            summary="Relatório gerencial (indicadores, rankings, séries para BI)")
def management(client_id: str, start: date, end: date, p: Principal = Depends(get_principal),
               db: Session = Depends(get_db)):
    _period(start, end)
    return reports.management(db, get_client_for(client_id, p, db), start, end)


@router.get("/audit", response_model=list[AuditOut], tags=["Auditoria"],
            summary="Trilha de auditoria: quem, quando e o que foi alterado")
def audit(
    entity: str | None = Query(None, max_length=50),
    entity_id: str | None = Query(None, max_length=36),
    user_id: str | None = Query(None, max_length=36),
    since: datetime | None = None,
    limit: int = Query(200, le=1000),
    p: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).where(AuditLog.office_id == p.office_id)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if since:
        stmt = stmt.where(AuditLog.at >= since)
    return db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit)).all()
