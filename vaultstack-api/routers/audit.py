from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from models.audit_log import AuditLog

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/")
def list_audit_logs(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    logs = q.limit(limit).all()
    return [
        {
            "id": str(l.id),
            "timestamp": str(l.timestamp),
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "actor": l.actor,
            "details": l.details,
        }
        for l in logs
    ]
