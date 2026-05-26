from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid
from database import get_db
from models.backup import BackupJob
from services import openstack as os_svc

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])

class BackupCreate(BaseModel):
    vm_id: str
    policy_id: Optional[str] = None

class BackupResponse(BaseModel):
    id: str
    vm_id: str
    vm_name: Optional[str]
    status: str
    size_gb: Optional[float]
    backup_path: Optional[str]
    started_at: str
    completed_at: Optional[str]

    class Config:
        from_attributes = True

@router.get("/")
def list_backups(db: Session = Depends(get_db)):
    jobs = db.query(BackupJob).order_by(BackupJob.started_at.desc()).all()
    return [
        {
            "id": str(j.id),
            "policy_id": str(j.policy_id) if j.policy_id else None,
            "vm_id": j.vm_id,
            "vm_name": j.vm_name,
            "status": j.status,
            "backup_type": j.backup_type or "full",
            "parent_backup_id": str(j.parent_backup_id) if j.parent_backup_id else None,
            "size_gb": j.size_gb,
            "backup_path": j.backup_path,
            "error_msg": j.error_msg,
            "started_at": str(j.started_at),
            "completed_at": str(j.completed_at) if j.completed_at else None,
        }
        for j in jobs
    ]

@router.post("/")
def create_backup(payload: BackupCreate, db: Session = Depends(get_db)):
    from celery_app import app as celery_app

    job = BackupJob(
        id=uuid.uuid4(),
        vm_id=payload.vm_id,
        policy_id=uuid.UUID(payload.policy_id) if payload.policy_id else None,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    celery_app.send_task("tasks.backup_task.run_backup", args=[str(job.id)])

    return {"job_id": str(job.id), "status": "queued", "message": "Backup queued"}

@router.get("/{backup_id}")
def get_backup(backup_id: str, db: Session = Depends(get_db)):
    job = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(backup_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {
        "id": str(job.id),
        "vm_id": job.vm_id,
        "vm_name": job.vm_name,
        "status": job.status,
        "size_gb": job.size_gb,
        "backup_path": job.backup_path,
        "error_msg": job.error_msg,
        "started_at": str(job.started_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }

@router.delete("/{backup_id}")
def delete_backup(backup_id: str, db: Session = Depends(get_db)):
    job = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(backup_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Backup not found")
    from services.storage import delete_backup_file
    if job.backup_path:
        delete_backup_file(job.backup_path)
    db.delete(job)
    db.commit()
    return {"message": "Backup deleted"}

@router.get("/vms/list")
def list_vms(project_id: Optional[str] = None):
    try:
        return os_svc.list_vms(project_id=project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
