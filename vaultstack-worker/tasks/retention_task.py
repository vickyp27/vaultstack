from celery_app import app
from datetime import datetime, timedelta
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob
from models.policy import BackupPolicy
from services.storage import delete_backup_file


def _get_storage_cfg(db, project_id=None):
    from models.settings import StorageSettings
    from models.tenant_storage import TenantStorageConfig
    if project_id:
        t = db.query(TenantStorageConfig).filter(
            TenantStorageConfig.project_id == project_id,
            TenantStorageConfig.enabled == True,
        ).first()
        if t:
            return t
    return db.query(StorageSettings).filter(StorageSettings.id == 1).first()


def _delete_from_storage(backup_path, project_id, db):
    if not backup_path:
        return
    if backup_path.startswith("s3://"):
        from services.storage import delete_from_s3
        s3_key = "/".join(backup_path.split("/")[3:])
        cfg = _get_storage_cfg(db, project_id)
        if cfg and cfg.storage_type == "s3":
            delete_from_s3(s3_key, cfg)
    else:
        delete_backup_file(backup_path)


@app.task(name="tasks.retention_task.enforce_retention")
def enforce_retention():
    db = SessionLocal()
    deleted_count = 0
    freed_gb = 0.0

    try:
        policies = db.query(BackupPolicy).all()
        retention_map = {str(p.id): p.retention_days for p in policies}

        now = datetime.utcnow()
        all_jobs = db.query(BackupJob).filter(
            BackupJob.status == "success",
            BackupJob.completed_at.isnot(None),
        ).all()

        expired = []
        for job in all_jobs:
            retention_days = retention_map.get(str(job.policy_id), 30)
            expires_at = job.completed_at + timedelta(days=retention_days)
            if expires_at < now:
                expired.append(job)

        print(f"[retention] Found {len(expired)} expired backup(s) to clean up")

        for job in expired:
            try:
                freed_gb += float(job.size_gb or 0)
                _delete_from_storage(job.backup_path, job.project_id, db)
                db.delete(job)
                deleted_count += 1
                print(f"[retention] Deleted expired backup {job.id} (VM: {job.vm_name}, age: {(now - job.completed_at).days}d)")
            except Exception as e:
                print(f"[retention] Failed to delete {job.id}: {e}")

        db.commit()
        print(f"[retention] Done — deleted {deleted_count} backups, freed {freed_gb:.2f} GB")

        # Send alert summary if anything was deleted
        if deleted_count > 0:
            try:
                from routers.monitoring import _send_email, _send_slack
                from models.alert import AlertConfig
                cfg = db.query(AlertConfig).filter(AlertConfig.id == 1).first()
                if cfg and cfg.email_enabled and cfg.email_smtp_host:
                    subj = f"[VaultStack] Retention Cleanup — {deleted_count} backup(s) deleted"
                    body = (
                        f"Auto-retention enforcement completed.\n\n"
                        f"Deleted: {deleted_count} expired backup(s)\n"
                        f"Freed:   {freed_gb:.2f} GB\n"
                        f"Time:    {now.strftime('%Y-%m-%d %H:%M UTC')}"
                    )
                    _send_email(cfg, subj, body)
            except Exception:
                pass

        return {"deleted": deleted_count, "freed_gb": round(freed_gb, 2)}

    except Exception as e:
        print(f"[retention] Error: {e}")
        raise
    finally:
        db.close()
