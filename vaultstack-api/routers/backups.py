from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import uuid
from database import get_db
from models.backup import BackupJob
from models.policy import BackupPolicy
from services import openstack as os_svc

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])

class BackupCreate(BaseModel):
    vm_id: str
    policy_id: Optional[str] = None
    provider_id: Optional[str] = None

class BulkDeleteRequest(BaseModel):
    ids: List[str]

def _recovery_status(job, retention_map: dict) -> str:
    if job.status in ('running', 'queued'):
        return 'executing'
    if job.status == 'failed':
        return 'failed'
    if job.status == 'success':
        retention_days = retention_map.get(str(job.policy_id), 30)
        if job.completed_at:
            expires_at = job.completed_at + timedelta(days=retention_days)
            if expires_at < datetime.utcnow():
                return 'expired'
        return 'available'
    return 'unknown'

def _expires_at(job, retention_map: dict):
    if job.status != 'success' or not job.completed_at:
        return None
    retention_days = retention_map.get(str(job.policy_id), 30)
    return str(job.completed_at + timedelta(days=retention_days))

@router.get("/")
def list_backups(db: Session = Depends(get_db)):
    jobs = db.query(BackupJob).order_by(BackupJob.started_at.desc()).all()
    policies = db.query(BackupPolicy).all()
    retention_map = {str(p.id): p.retention_days for p in policies}
    return [
        {
            "id": str(j.id),
            "policy_id": str(j.policy_id) if j.policy_id else None,
            "vm_id": j.vm_id,
            "vm_name": j.vm_name,
            "status": j.status,
            "recovery_status": _recovery_status(j, retention_map),
            "expires_at": _expires_at(j, retention_map),
            "backup_type": j.backup_type or "full",
            "parent_backup_id": str(j.parent_backup_id) if j.parent_backup_id else None,
            "encrypted": bool(j.encrypted),
            "size_gb": j.size_gb,
            "backup_path": j.backup_path,
            "error_msg": j.error_msg,
            "progress": j.progress or 0,
            "progress_msg": j.progress_msg or "",
            "started_at": str(j.started_at),
            "completed_at": str(j.completed_at) if j.completed_at else None,
        }
        for j in jobs
    ]

@router.post("/")
def create_backup(payload: BackupCreate, db: Session = Depends(get_db)):
    from celery_app import app as celery_app

    provider_id = None
    if payload.provider_id:
        provider_id = uuid.UUID(payload.provider_id)
    else:
        # auto-detect provider from vm_id across all providers
        from models.provider import Provider
        from routers.providers import _os_conn
        for p in db.query(Provider).filter(Provider.type == "openstack").all():
            try:
                conn = _os_conn(p)
                conn.compute.get_server(payload.vm_id)
                provider_id = p.id
                break
            except Exception:
                continue

    job = BackupJob(
        id=uuid.uuid4(),
        vm_id=payload.vm_id,
        policy_id=uuid.UUID(payload.policy_id) if payload.policy_id else None,
        provider_id=provider_id,
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
        "encrypted": bool(job.encrypted),
        "backup_type": job.backup_type or "full",
        "size_gb": job.size_gb,
        "backup_path": job.backup_path,
        "error_msg": job.error_msg,
        "progress": job.progress or 0,
        "progress_msg": job.progress_msg or "",
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
        try:
            delete_backup_file(job.backup_path)
        except Exception:
            pass
    db.delete(job)
    db.commit()
    return {"message": "Backup deleted"}

@router.post("/bulk-delete")
def bulk_delete_backups(payload: BulkDeleteRequest, db: Session = Depends(get_db)):
    from services.storage import delete_backup_file
    deleted, errors = 0, []
    for id_str in payload.ids:
        try:
            job = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(id_str)).first()
            if not job:
                continue
            if job.backup_path:
                try:
                    delete_backup_file(job.backup_path)
                except Exception:
                    pass
            db.delete(job)
            deleted += 1
        except Exception as e:
            errors.append({"id": id_str, "error": str(e)})
    db.commit()
    return {"deleted": deleted, "errors": errors}

@router.get("/vms/list")
def list_vms(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    from models.provider import Provider
    from routers.providers import _os_conn

    providers = db.query(Provider).filter(Provider.type == "openstack").all()

    all_vms = []
    seen_ids = set()

    for p in providers:
        try:
            conn = _os_conn(p)
            creds = p.credentials or {}
            is_admin = creds.get("username") == "admin"

            try:
                project_map = {proj.id: proj.name for proj in conn.identity.projects()}
            except Exception:
                project_map = {}

            kwargs = {}
            if is_admin:
                kwargs["all_projects"] = True
            if project_id:
                kwargs["project_id"] = project_id

            servers = list(conn.compute.servers(**kwargs))
            cred_project = creds.get("project_name", "")

            for s in servers:
                if s.id in seen_ids:
                    continue
                seen_ids.add(s.id)
                all_vms.append({
                    "id": s.id,
                    "name": s.name,
                    "status": s.status,
                    "flavor": s.flavor.get("original_name", "") if s.flavor else "",
                    "volumes": [v["id"] for v in s.attached_volumes],
                    "project_id": s.project_id or "",
                    "project_name": project_map.get(s.project_id, cred_project or (s.project_id or "")[:8]),
                    "provider_id": str(p.id),
                    "provider_name": p.name,
                })
        except Exception:
            continue

    # fallback to default openstack service if no providers configured
    if not all_vms and not providers:
        try:
            return os_svc.list_vms(project_id=project_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return all_vms
