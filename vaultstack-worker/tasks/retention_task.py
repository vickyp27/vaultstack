from celery_app import app
from datetime import datetime, timedelta
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob
from models.policy import BackupPolicy
from services.storage import delete_backup_file


def _gfs_keep_ids(backups, daily, weekly, monthly):
    """
    GFS algorithm — returns set of backup IDs to KEEP.
    Backups must have completed_at set. Sorted newest-first internally.
    Each tier picks the newest backup per calendar-day / ISO-week / month.
    A backup can satisfy multiple tiers; we take the union.
    """
    sorted_b = sorted(backups, key=lambda b: b.completed_at, reverse=True)
    keep = set()

    # Daily: one per calendar day, up to `daily` days
    seen, n = set(), 0
    for b in sorted_b:
        day = b.completed_at.date()
        if day not in seen:
            seen.add(day); keep.add(b.id); n += 1
            if n >= daily:
                break

    # Weekly: one per ISO week, up to `weekly` weeks
    seen, n = set(), 0
    for b in sorted_b:
        week = b.completed_at.isocalendar()[:2]   # (year, week_number)
        if week not in seen:
            seen.add(week); keep.add(b.id); n += 1
            if n >= weekly:
                break

    # Monthly: one per calendar month, up to `monthly` months
    seen, n = set(), 0
    for b in sorted_b:
        month = (b.completed_at.year, b.completed_at.month)
        if month not in seen:
            seen.add(month); keep.add(b.id); n += 1
            if n >= monthly:
                break

    return keep


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
    elif backup_path.startswith("swift://"):
        from services.storage import delete_from_swift
        # swift://container/key
        parts = backup_path[len("swift://"):].split("/", 1)
        obj_name = parts[1] if len(parts) > 1 else backup_path
        cfg = _get_storage_cfg(db, project_id)
        if cfg and cfg.storage_type == "swift":
            delete_from_swift(obj_name, cfg)
    else:
        delete_backup_file(backup_path)


@app.task(name="tasks.retention_task.enforce_retention")
def enforce_retention():
    db = SessionLocal()
    deleted_count = 0
    freed_gb = 0.0

    try:
        policies = db.query(BackupPolicy).all()
        policy_map = {str(p.id): p for p in policies}

        now = datetime.utcnow()
        all_jobs = db.query(BackupJob).filter(
            BackupJob.status == "success",
            BackupJob.completed_at.isnot(None),
        ).all()

        # ── GFS: compute which backups to keep per policy ─────────────────────
        gfs_keep = set()
        jobs_by_policy = {}
        for job in all_jobs:
            pid = str(job.policy_id) if job.policy_id else None
            if pid:
                jobs_by_policy.setdefault(pid, []).append(job)

        for pid, jobs in jobs_by_policy.items():
            p = policy_map.get(pid)
            if p and p.gfs_enabled:
                keep = _gfs_keep_ids(
                    jobs,
                    daily   = p.gfs_daily   or 7,
                    weekly  = p.gfs_weekly  or 4,
                    monthly = p.gfs_monthly or 12,
                )
                gfs_keep |= keep
                print(f"[retention] GFS policy '{p.name}': keeping {len(keep)}/{len(jobs)} backups")

        # ── Build delete list ─────────────────────────────────────────────────
        expired = []
        for job in all_jobs:
            # WORM: skip locked backups
            if getattr(job, 'locked_until', None) and job.locked_until > now:
                print(f"[retention] Skipping WORM-locked backup {job.id} (locked until {job.locked_until})")
                continue

            p = policy_map.get(str(job.policy_id)) if job.policy_id else None
            if p and p.gfs_enabled:
                # GFS policy: delete anything NOT in the keep set
                if job.id not in gfs_keep:
                    expired.append(job)
            else:
                # Per-VM retention override: check if this VM has a custom retention
                vm_overrides = getattr(p, 'vm_retention_overrides', None) or {}
                retention_days = vm_overrides.get(job.vm_id) or (p.retention_days if p else 30)
                if job.completed_at + timedelta(days=retention_days) < now:
                    expired.append(job)

        print(f"[retention] Found {len(expired)} expired backup(s) to clean up")

        for job in expired:
            try:
                freed_gb += float(job.size_gb or 0)
                if getattr(job, 'cinder_backup_id', None):
                    try:
                        from services import openstack as _os_svc
                        _os_svc.delete_cinder_backup(job.cinder_backup_id)
                    except Exception as _e:
                        print(f"[retention] Could not delete Cinder backup {job.cinder_backup_id}: {_e}")
                else:
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
