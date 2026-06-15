from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import uuid
from database import get_db
from models.restore import RestoreJob
from models.backup import BackupJob
from services import openstack as os_svc

router = APIRouter(prefix="/api/v1/restores", tags=["restores"])

class RestoreCreate(BaseModel):
    backup_job_id: str
    target_vm_name: str
    target_network_id: Optional[str] = None
    target_project_id: Optional[str] = None
    flavor_id: Optional[str] = None
    instant: bool = False

@router.get("/flavors")
def list_flavors(provider_id: Optional[str] = None):
    conn = os_svc.get_provider_conn(provider_id) if provider_id else None
    return os_svc.list_flavors(conn=conn)

@router.get("/networks")
def list_networks(project_id: Optional[str] = None, provider_id: Optional[str] = None):
    conn = os_svc.get_provider_conn(provider_id) if provider_id else None
    return os_svc.list_networks(project_id=project_id, conn=conn)

@router.post("/")
def create_restore(payload: RestoreCreate, db: Session = Depends(get_db)):
    backup = db.query(BackupJob).filter(
        BackupJob.id == uuid.UUID(payload.backup_job_id)
    ).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    if backup.status != "success":
        raise HTTPException(status_code=400, detail="Backup is not in success state")

    from celery_app import app as celery_app

    # Auto-detect project from backup if not specified
    target_project_id = payload.target_project_id or getattr(backup, "project_id", None)

    job = RestoreJob(
        id=uuid.uuid4(),
        backup_job_id=uuid.UUID(payload.backup_job_id),
        target_vm_name=payload.target_vm_name,
        target_network_id=payload.target_network_id,
        target_project_id=target_project_id,
        flavor_id=payload.flavor_id,
        mode="instant" if payload.instant else "full",
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    task_name = "tasks.restore_task.run_instant_restore" if payload.instant else "tasks.restore_task.run_restore"
    celery_app.send_task(task_name, args=[str(job.id)])

    return {"job_id": str(job.id), "status": "queued"}

@router.get("/{restore_id}")
def get_restore(restore_id: str, db: Session = Depends(get_db)):
    job = db.query(RestoreJob).filter(RestoreJob.id == uuid.UUID(restore_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Restore job not found")
    return {
        "id": str(job.id),
        "backup_job_id": str(job.backup_job_id),
        "target_vm_name": job.target_vm_name,
        "new_vm_id": job.new_vm_id,
        "mode": job.mode or "full",
        "status": job.status,
        "error_msg": job.error_msg,
        "started_at": str(job.started_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }

@router.get("/")
def list_restores(policy_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(RestoreJob)
    if policy_id:
        query = query.join(BackupJob, RestoreJob.backup_job_id == BackupJob.id).filter(
            BackupJob.policy_id == uuid.UUID(policy_id)
        )
    jobs = query.order_by(RestoreJob.started_at.desc()).all()
    return [
        {
            "id": str(j.id),
            "backup_job_id": str(j.backup_job_id),
            "target_vm_name": j.target_vm_name,
            "new_vm_id": j.new_vm_id,
            "mode": j.mode or "full",
            "status": j.status,
            "progress": j.progress or 0,
            "progress_msg": j.progress_msg or "",
            "started_at": str(j.started_at),
        }
        for j in jobs
    ]
