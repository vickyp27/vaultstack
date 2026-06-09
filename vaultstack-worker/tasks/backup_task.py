from celery_app import app
from datetime import datetime
import subprocess, sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob
from models.policy import BackupPolicy
from models.settings import StorageSettings
from models.tenant_storage import TenantStorageConfig
from services import openstack as os_svc
from services.storage import (
    ensure_backup_dir, get_backup_path, get_size_gb,
    get_s3_key, upload_to_s3, download_from_s3,
)
import uuid


def _get_storage_cfg(db, project_id):
    if project_id:
        tenant_cfg = db.query(TenantStorageConfig).filter(
            TenantStorageConfig.project_id == project_id,
            TenantStorageConfig.enabled == True,
        ).first()
        if tenant_cfg:
            return tenant_cfg
    return db.query(StorageSettings).filter(StorageSettings.id == 1).first()


def _s3_key_for_job(job, job_id, vm_id):
    project_prefix = (getattr(job, "project_id", None) or "global")[:8]
    return f"{project_prefix}/{get_s3_key(vm_id, job_id)}"


def _maybe_encrypt(local_path, job, job_id):
    """Encrypt local_path in-place if BACKUP_ENCRYPTION_KEY is set. Sets job.encrypted."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))
    from services.encryption import get_encryption_key, encrypt_file
    key = get_encryption_key()
    if not key:
        job.encrypted = False
        return
    enc_path = local_path + ".enc"
    print(f"[{job_id}] Encrypting backup (AES-256-CTR)…")
    encrypt_file(local_path, enc_path, key)
    os.remove(local_path)
    os.rename(enc_path, local_path)
    job.encrypted = True
    print(f"[{job_id}] Encryption complete")


def _upload(local_path, job_id, vm_id, job, storage_cfg):
    """Upload local file to S3 (or keep local). Returns stored path."""
    if storage_cfg and storage_cfg.storage_type == "s3":
        s3_key = _s3_key_for_job(job, job_id, vm_id)
        print(f"[{job_id}] Uploading to S3: {s3_key}")
        s3_path = upload_to_s3(local_path, s3_key, storage_cfg)
        os.remove(local_path)
        return s3_path
    return local_path


def _download_base_backup(parent_backup, storage_cfg, tmp_path):
    """Download the parent (full) backup to a local temp file for delta computation."""
    if parent_backup.backup_path.startswith("s3://"):
        s3_key = "/".join(parent_backup.backup_path.split("/")[3:])
        print(f"  Downloading base backup from S3: {s3_key}")
        download_from_s3(s3_key, tmp_path, storage_cfg)
        return tmp_path, True   # True = we own this file, must delete after
    else:
        return parent_backup.backup_path, False  # local file, don't delete


def _qemu_rebase(new_path, base_path):
    """
    Create a delta qcow2 that contains only blocks differing between
    new_path and base_path, with base_path as its backing file.

    Steps:
      1. Create empty overlay backed by new_path  (overlay sees new_path content)
      2. Safe rebase overlay from new_path → base_path
         (blocks where new≠base are written into overlay; backing becomes base)
      Result: overlay = changed blocks only, ~much smaller than full image
    """
    delta_path = new_path + ".delta"

    print(f"  Creating delta overlay backed by new snapshot…")
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", new_path, delta_path],
        check=True, capture_output=True,
    )

    print(f"  Rebasing delta (new→base) to extract changed blocks…")
    subprocess.run(
        ["qemu-img", "rebase", "-f", "qcow2", "-F", "qcow2", "-b", base_path, delta_path],
        check=True, capture_output=True,
    )

    return delta_path


def _do_full_backup(job_id, vm_id, image_id, local_path, job, storage_cfg):
    """Download Glance image → encrypt → upload → return size_gb."""
    print(f"[{job_id}] Downloading full image to {local_path}")
    os_svc.download_image(image_id, local_path)
    os_svc.delete_snapshot(image_id)
    size_gb = get_size_gb(local_path)
    _maybe_encrypt(local_path, job, job_id)
    stored_path = _upload(local_path, job_id, vm_id, job, storage_cfg)
    job.backup_path = stored_path
    job.backup_type = "full"
    return size_gb


def _do_incremental_backup(job_id, vm_id, image_id, local_path, job, storage_cfg, parent_backup):
    """
    Download new snapshot, compute delta against parent (full) backup using
    qemu-img rebase, upload only the delta. Returns size_gb of delta.
    """
    new_path = local_path + ".new"
    base_tmp = local_path + ".base"
    delta_path = None
    base_owned = False

    try:
        print(f"[{job_id}] [INCREMENTAL] Downloading new snapshot…")
        os_svc.download_image(image_id, new_path)
        os_svc.delete_snapshot(image_id)

        base_path, base_owned = _download_base_backup(parent_backup, storage_cfg, base_tmp)

        print(f"[{job_id}] [INCREMENTAL] Computing delta vs base backup…")
        delta_path = _qemu_rebase(new_path, base_path)

        # new_path no longer needed — delta backs to base
        os.remove(new_path)

        size_gb = get_size_gb(delta_path)
        print(f"[{job_id}] [INCREMENTAL] Delta size: {size_gb} GB")

        # Rename delta to expected local_path for consistent upload key
        os.rename(delta_path, local_path)
        delta_path = None

        _maybe_encrypt(local_path, job, job_id)
        stored_path = _upload(local_path, job_id, vm_id, job, storage_cfg)
        job.backup_path = stored_path
        job.backup_type = "incremental"
        job.parent_backup_id = parent_backup.id
        return size_gb

    finally:
        if delta_path and os.path.exists(delta_path):
            os.remove(delta_path)
        if os.path.exists(new_path):
            os.remove(new_path)
        if base_owned and os.path.exists(base_tmp):
            os.remove(base_tmp)


def _should_do_incremental(db, vm_id, policy_id):
    """
    Returns (do_incremental: bool, parent_backup: BackupJob | None).
    Incremental when: policy has incremental_enabled, a previous full backup
    exists for this VM, and we haven't yet hit the full_backup_interval.
    """
    if not policy_id:
        return False, None

    policy = db.query(BackupPolicy).filter(BackupPolicy.id == policy_id).first()
    if not policy or not policy.incremental_enabled:
        return False, None

    # Find the most recent successful FULL backup for this VM under this policy
    last_full = (
        db.query(BackupJob)
        .filter(
            BackupJob.vm_id == vm_id,
            BackupJob.policy_id == policy_id,
            BackupJob.status == "success",
            BackupJob.backup_type == "full",
        )
        .order_by(BackupJob.started_at.desc())
        .first()
    )

    if not last_full:
        return False, None  # No full backup yet → must do full

    # Count incrementals taken since the last full
    incrementals_since_full = (
        db.query(BackupJob)
        .filter(
            BackupJob.vm_id == vm_id,
            BackupJob.policy_id == policy_id,
            BackupJob.status == "success",
            BackupJob.backup_type == "incremental",
            BackupJob.started_at > last_full.started_at,
        )
        .count()
    )

    interval = policy.full_backup_interval or 6
    if incrementals_since_full >= interval - 1:
        # Reached the interval limit → time for a new full
        return False, None

    return True, last_full


@app.task(name="tasks.backup_task.run_backup")
def run_backup(job_id: str):
    db = SessionLocal()
    job = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(job_id)).first()
    if not job:
        return

    try:
        job.status = "running"
        db.commit()

        vm = os_svc.get_vm(job.vm_id)
        job.vm_name    = vm["name"]
        job.project_id = vm.get("project_id")
        db.commit()

        timestamp     = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        snapshot_name = f"vaultstack-{vm['name']}-{timestamp}"

        ensure_backup_dir(job.vm_id)
        local_path   = get_backup_path(job.vm_id, job_id)
        storage_cfg  = _get_storage_cfg(db, job.project_id)

        do_incremental, parent_backup = _should_do_incremental(
            db, job.vm_id, job.policy_id
        )

        volumes = vm.get("volumes", [])

        # ── Take snapshot ────────────────────────────────────────────────────
        if volumes:
            volume_id = volumes[0]
            print(f"[{job_id}] Volume-backed VM — Cinder snapshot of {volume_id}")
            snap_id  = os_svc.create_volume_snapshot(volume_id, snapshot_name)
            job.snapshot_id = snap_id
            db.commit()
            print(f"[{job_id}] Converting volume snapshot → Glance image")
            image_id = os_svc.volume_snapshot_to_glance_image(snap_id, snapshot_name)
            try:
                os_svc.delete_volume_snapshot(snap_id)
            except Exception:
                pass
        else:
            print(f"[{job_id}] Image-backed VM — Nova snapshot: {snapshot_name}")
            image_id = os_svc.create_vm_snapshot(job.vm_id, snapshot_name)
            job.snapshot_id = image_id
            db.commit()

        # ── Full or incremental ──────────────────────────────────────────────
        if do_incremental:
            print(f"[{job_id}] Mode: INCREMENTAL (parent: {parent_backup.id})")
            size_gb = _do_incremental_backup(
                job_id, job.vm_id, image_id, local_path,
                job, storage_cfg, parent_backup,
            )
        else:
            print(f"[{job_id}] Mode: FULL")
            size_gb = _do_full_backup(
                job_id, job.vm_id, image_id, local_path, job, storage_cfg,
            )

        job.size_gb      = size_gb
        job.status       = "success"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Backup complete ({job.backup_type}): {size_gb} GB → {job.backup_path}")

        try:
            from routers.monitoring import send_success_alert
            send_success_alert(db, job)
        except Exception:
            pass

    except Exception as e:
        job.status       = "failed"
        job.error_msg    = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Backup failed: {e}")
        try:
            from routers.monitoring import send_failure_alert
            send_failure_alert(db, job)
        except Exception:
            pass
        raise
    finally:
        db.close()
