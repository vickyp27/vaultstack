from celery_app import app
from datetime import datetime
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob
from models.settings import StorageSettings
from models.tenant_storage import TenantStorageConfig
from services import openstack as os_svc
from services.storage import ensure_backup_dir, get_backup_path, get_size_gb, get_s3_key, upload_to_s3
import uuid


def _get_storage_cfg(db, project_id):
    """Return tenant-specific S3 config if exists and enabled, else global config."""
    if project_id:
        tenant_cfg = db.query(TenantStorageConfig).filter(
            TenantStorageConfig.project_id == project_id,
            TenantStorageConfig.enabled == True,
        ).first()
        if tenant_cfg:
            return tenant_cfg
    return db.query(StorageSettings).filter(StorageSettings.id == 1).first()


def _upload_and_store(job_id, vm_id, image_id, local_path, db, job, label=""):
    """Download Glance image → optionally push to S3 → update job."""
    print(f"[{job_id}] Downloading {label}image to {local_path}")
    os_svc.download_image(image_id, local_path)
    os_svc.delete_snapshot(image_id)

    size_gb = get_size_gb(local_path)

    storage_cfg = _get_storage_cfg(db, getattr(job, "project_id", None))
    if storage_cfg and storage_cfg.storage_type == "s3":
        # Include project_id in S3 key for per-tenant isolation
        project_prefix = (getattr(job, "project_id", None) or "global")[:8]
        s3_key = f"{project_prefix}/{get_s3_key(vm_id, job_id)}"
        print(f"[{job_id}] Uploading {label}to S3: {s3_key} (bucket: {storage_cfg.s3_bucket_name})")
        s3_path = upload_to_s3(local_path, s3_key, storage_cfg)
        os.remove(local_path)
        job.backup_path = s3_path
    else:
        job.backup_path = local_path

    return size_gb


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
        job.vm_name   = vm["name"]
        job.project_id = vm.get("project_id")
        db.commit()

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        snapshot_name = f"vaultstack-{vm['name']}-{timestamp}"

        ensure_backup_dir(job.vm_id)
        local_path = get_backup_path(job.vm_id, job_id)

        volumes = vm.get("volumes", [])

        if volumes:
            # Volume-backed VM: backup the first attached volume via Cinder snapshot
            # (Nova createImage returns 0-byte for BFV instances)
            volume_id = volumes[0]
            print(f"[{job_id}] Volume-backed VM — creating Cinder snapshot of {volume_id}")
            snap_id = os_svc.create_volume_snapshot(volume_id, snapshot_name)
            job.snapshot_id = snap_id
            db.commit()

            print(f"[{job_id}] Converting volume snapshot to Glance image")
            image_id = os_svc.volume_snapshot_to_glance_image(snap_id, snapshot_name)

            size_gb = _upload_and_store(job_id, job.vm_id, image_id, local_path, db, job, "volume ")

            # Cleanup Cinder snapshot (temp volume deleted inside volume_snapshot_to_glance_image)
            try:
                os_svc.delete_volume_snapshot(snap_id)
            except Exception:
                pass
        else:
            # Image-backed VM: standard Nova snapshot
            print(f"[{job_id}] Creating Nova snapshot: {snapshot_name}")
            image_id = os_svc.create_vm_snapshot(job.vm_id, snapshot_name)
            job.snapshot_id = image_id
            db.commit()

            size_gb = _upload_and_store(job_id, job.vm_id, image_id, local_path, db, job)

        job.size_gb = size_gb
        job.status = "success"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Backup complete: {size_gb} GB at {job.backup_path}")
        try:
            from routers.monitoring import send_success_alert
            send_success_alert(db, job)
        except Exception:
            pass

    except Exception as e:
        job.status = "failed"
        job.error_msg = str(e)
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
