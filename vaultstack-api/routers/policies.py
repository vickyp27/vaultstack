from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from croniter import croniter
from database import get_db
from models.policy import BackupPolicy

_CRON_LABELS = {
    "* * * * *":    "Every minute",
    "0 * * * *":    "Every hour",
    "0 */6 * * *":  "Every 6 hours",
    "0 */4 * * *":  "Every 4 hours",
    "0 */2 * * *":  "Every 2 hours",
    "0 2 * * *":    "Daily at 2:00 AM",
    "0 0 * * *":    "Daily at midnight",
    "0 2 * * 0":    "Weekly — Sunday at 2:00 AM",
    "0 2 * * 1":    "Weekly — Monday at 2:00 AM",
    "0 2 1 * *":    "Monthly — 1st at 2:00 AM",
}

def _describe_schedule(cron: str) -> str:
    return _CRON_LABELS.get(cron.strip(), f"Custom: {cron}")

def _next_run(cron: str) -> Optional[str]:
    try:
        nxt = croniter(cron, datetime.now(timezone.utc)).get_next(datetime)
        return nxt.strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return None

def _policy_dict(p) -> dict:
    return {
        "id": str(p.id),
        "project_id": p.project_id,
        "name": p.name,
        "vm_ids": p.vm_ids,
        "schedule": p.schedule,
        "schedule_description": _describe_schedule(p.schedule),
        "next_run": _next_run(p.schedule) if p.is_active else None,
        "retention_days": p.retention_days,
        "is_active": p.is_active,
        "incremental_enabled": p.incremental_enabled,
        "full_backup_interval": p.full_backup_interval,
    }

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])

class PolicyCreate(BaseModel):
    name: str
    vm_ids: List[str]
    schedule: str = "0 2 * * *"
    retention_days: int = 30
    project_id: Optional[str] = None
    incremental_enabled: bool = False
    full_backup_interval: int = 6

class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    vm_ids: Optional[List[str]] = None
    schedule: Optional[str] = None
    retention_days: Optional[int] = None
    is_active: Optional[bool] = None
    incremental_enabled: Optional[bool] = None
    full_backup_interval: Optional[int] = None

@router.get("/")
def list_policies(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(BackupPolicy)
    if project_id:
        q = q.filter(BackupPolicy.project_id == project_id)
    return [_policy_dict(p) for p in q.all()]

@router.post("/")
def create_policy(payload: PolicyCreate, db: Session = Depends(get_db)):
    policy = BackupPolicy(
        id=uuid.uuid4(),
        project_id=payload.project_id,
        name=payload.name,
        vm_ids=payload.vm_ids,
        schedule=payload.schedule,
        retention_days=payload.retention_days,
        is_active=True,
        incremental_enabled=payload.incremental_enabled,
        full_backup_interval=payload.full_backup_interval,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return {"id": str(policy.id), "message": "Policy created"}

@router.get("/{policy_id}")
def get_policy(policy_id: str, db: Session = Depends(get_db)):
    policy = db.query(BackupPolicy).filter(BackupPolicy.id == uuid.UUID(policy_id)).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return _policy_dict(policy)

@router.put("/{policy_id}")
def update_policy(policy_id: str, payload: PolicyUpdate, db: Session = Depends(get_db)):
    policy = db.query(BackupPolicy).filter(BackupPolicy.id == uuid.UUID(policy_id)).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    for field, value in payload.dict(exclude_none=True).items():
        setattr(policy, field, value)
    db.commit()
    return {"message": "Policy updated"}

@router.delete("/{policy_id}")
def delete_policy(policy_id: str, db: Session = Depends(get_db)):
    policy = db.query(BackupPolicy).filter(BackupPolicy.id == uuid.UUID(policy_id)).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db.delete(policy)
    db.commit()
    return {"message": "Policy deleted"}
