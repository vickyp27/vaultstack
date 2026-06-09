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


@router.get("/tenant-stats")
def get_tenant_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = (
        db.query(
            BackupJob.project_id,
            func.count(BackupJob.id).label("total"),
            func.sum(
                (BackupJob.status == "success").cast(db.bind.dialect.name == "postgresql"
                    and __import__("sqlalchemy").Integer or __import__("sqlalchemy").Integer)
            ).label("dummy"),
        )
        .filter(BackupJob.project_id.isnot(None))
        .group_by(BackupJob.project_id)
        .all()
    )

    # Simpler approach: get distinct project_ids and query each
    project_ids = [
        r[0] for r in
        db.query(BackupJob.project_id).filter(BackupJob.project_id.isnot(None)).distinct().all()
    ]

    result = []
    for pid in project_ids:
        jobs = db.query(BackupJob).filter(BackupJob.project_id == pid).all()
        success_jobs = [j for j in jobs if j.status == "success"]
        failed  = sum(1 for j in jobs if j.status == "failed")
        running = sum(1 for j in jobs if j.status in ("running", "queued"))
        storage = round(sum(float(j.size_gb or 0) for j in success_jobs), 2)
        policies = db.query(BackupPolicy).filter(BackupPolicy.project_id == pid).count()
        last = max((j.started_at for j in jobs if j.started_at), default=None)
        success_rate = round(len(success_jobs) / len(jobs) * 100) if jobs else 0

        result.append({
            "project_id": pid,
            "project_id_short": pid[:8],
            "total_backups":   len(jobs),
            "success_backups": len(success_jobs),
            "failed_backups":  failed,
            "running_backups": running,
            "success_rate":    success_rate,
            "storage_gb":      storage,
            "policies":        policies,
            "last_backup_at":  str(last) if last else None,
        })

    result.sort(key=lambda x: x["total_backups"], reverse=True)
    return result
