from celery_app import app
from datetime import datetime
import subprocess, sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.restore import RestoreJob
from models.backup import BackupJob
from models.settings import StorageSettings
from models.tenant_storage import TenantStorageConfig
from services import openstack as os_svc
from services.storage import download_from_s3
import uuid


def _progress(db, job, pct, msg):
    job.progress     = pct
    job.progress_msg = msg
    db.commit()
    print(f"[{job.id}] [{pct}%] {msg}")


def _get_storage_cfg(db, project_id):
    if project_id:
        tenant_cfg = db.query(TenantStorageConfig).filter(
            TenantStorageConfig.project_id == project_id,
            TenantStorageConfig.enabled == True,
        ).first()
        if tenant_cfg:
            return tenant_cfg
    return db.query(StorageSettings).filter(StorageSettings.id == 1).first()


def _local_path_for_backup(backup, tmp_dir, storage_cfg):
    """
    Ensure the backup file is on local disk.
    Returns (path, owned) — owned=True means caller must delete the file.
    """
    if backup.backup_path and backup.backup_path.startswith("s3://"):
        local = os.path.join(tmp_dir, f"{backup.id}.qcow2")
        s3_key = "/".join(backup.backup_path.split("/")[3:])
        print(f"  Downloading {backup.backup_type} backup {backup.id} from S3…")
        download_from_s3(s3_key, local, storage_cfg)
        return local, True
    return backup.backup_path, False


def _flatten_incremental(full_path, delta_path, out_path):
    """
    Merge full + delta into a single standalone qcow2 ready for Glance upload.
    1. Point delta's backing file to the locally downloaded full (unsafe rebase)
    2. Flatten with qemu-img convert → out_path
    """
    print(f"  Pointing delta to local full backup…")
    subprocess.run(
        ["qemu-img", "rebase", "-u", "-f", "qcow2", "-F", "qcow2",
         "-b", full_path, delta_path],
        check=True, capture_output=True,
    )
    print(f"  Flattening chain → {out_path}")
    subprocess.run(
        ["qemu-img", "convert", "-f", "qcow2", "-O", "qcow2",
         delta_path, out_path],
        check=True, capture_output=True,
    )


@app.task(name="tasks.restore_task.run_restore")
def run_restore(job_id: str):
    db       = SessionLocal()
    job      = db.query(RestoreJob).filter(RestoreJob.id == uuid.UUID(job_id)).first()
    if not job:
        return

    tmp_files = []   # track temp files to clean up

    try:
        job.status = "running"
        db.commit()

        backup = db.query(BackupJob).filter(BackupJob.id == job.backup_job_id).first()
        project_id  = getattr(backup, "project_id", None)
        storage_cfg = _get_storage_cfg(db, project_id)
        tmp_dir     = f"/tmp/vaultstack-restore-{job_id}"
        os.makedirs(tmp_dir, exist_ok=True)

        # ── Resolve the backup file to restore ──────────────────────────────
        if backup.backup_type == "incremental" and backup.parent_backup_id:
            _progress(db, job, 10, "Incremental restore — downloading full base backup…")

            parent = db.query(BackupJob).filter(
                BackupJob.id == backup.parent_backup_id
            ).first()
            if not parent:
                raise RuntimeError(f"Parent backup {backup.parent_backup_id} not found")

            full_local, full_owned = _local_path_for_backup(parent, tmp_dir, storage_cfg)
            if full_owned:
                tmp_files.append(full_local)

            _progress(db, job, 25, "Downloading incremental delta…")
            delta_local, delta_owned = _local_path_for_backup(backup, tmp_dir, storage_cfg)
            if delta_owned:
                tmp_files.append(delta_local)

            _progress(db, job, 40, "Merging full + delta into restore image…")
            merged_path = os.path.join(tmp_dir, "merged.qcow2")
            tmp_files.append(merged_path)
            _flatten_incremental(full_local, delta_local, merged_path)
            local_path = merged_path

        else:
            _progress(db, job, 10, "Full restore — downloading backup…")
            full_local, full_owned = _local_path_for_backup(backup, tmp_dir, storage_cfg)
            if full_owned:
                tmp_files.append(full_local)
            local_path = full_local

        # ── Upload to Glance ─────────────────────────────────────────────────
        _progress(db, job, 50, "Uploading image to Glance…")
        restore_image_name = f"vaultstack-restore-{job.target_vm_name}"
        image_id = os_svc.upload_image(restore_image_name, local_path)
        _progress(db, job, 70, "Image uploaded to Glance")

        # ── Pick flavor and network ──────────────────────────────────────────
        flavor_id  = job.flavor_id
        if not flavor_id:
            flavors   = os_svc.list_flavors()
            flavor_id = flavors[0]["id"] if flavors else None
        networks   = os_svc.list_networks()
        network_id = job.target_network_id or (networks[0]["id"] if networks else None)

        # ── Boot VM ──────────────────────────────────────────────────────────
        _progress(db, job, 75, f"Booting VM '{job.target_vm_name}'…")
        new_vm_id = os_svc.create_vm_from_image(
            name=job.target_vm_name,
            image_id=image_id,
            flavor_id=flavor_id,
            network_id=network_id,
        )
        _progress(db, job, 90, "VM booted, cleaning up…")
        os_svc.delete_snapshot(image_id)

        job.new_vm_id    = new_vm_id
        job.status       = "success"
        job.progress     = 100
        job.progress_msg = f"Restore complete. New VM: {new_vm_id}"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Restore complete. New VM: {new_vm_id}")

    except Exception as e:
        job.status       = "failed"
        job.progress_msg = f"Failed: {str(e)}"
        job.error_msg    = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Restore failed: {e}")
        raise
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        db.close()
