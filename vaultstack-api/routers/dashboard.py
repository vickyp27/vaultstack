from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from models.backup import BackupJob
from models.policy import BackupPolicy
from models.restore import RestoreJob

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

@router.get("/stats")
def get_stats(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    bq = db.query(BackupJob)
    if project_id:
        bq = bq.filter(BackupJob.project_id == project_id)

    total_backups   = bq.count()
    success_backups = bq.filter(BackupJob.status == "success").count()
    failed_backups  = bq.filter(BackupJob.status == "failed").count()
    running_backups = bq.filter(BackupJob.status == "running").count()

    pq = db.query(BackupPolicy).filter(BackupPolicy.is_active == True)
    if project_id:
        pq = pq.filter(BackupPolicy.project_id == project_id)
    total_policies = pq.count()

    total_restores = db.query(RestoreJob).count()

    storage_rows = bq.filter(
        BackupJob.status == "success",
        BackupJob.size_gb != None,
    ).with_entities(BackupJob.size_gb).all()
    total_storage_gb = round(sum(s[0] for s in storage_rows), 2)

    last_backup = bq.order_by(BackupJob.started_at.desc()).first()

    return {
        "total_backups": total_backups,
        "success_backups": success_backups,
        "failed_backups": failed_backups,
        "running_backups": running_backups,
        "total_policies": total_policies,
        "total_restores": total_restores,
        "total_storage_gb": total_storage_gb,
        "last_backup_at": str(last_backup.started_at) if last_backup else None,
        "last_backup_status": last_backup.status if last_backup else None,
    }
