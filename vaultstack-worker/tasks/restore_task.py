from celery_app import app
from datetime import datetime
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.restore import RestoreJob
from models.backup import BackupJob
from models.settings import StorageSettings
from services import openstack as os_svc
import uuid


def _progress(db, job, pct, msg):
    job.progress = pct
    job.progress_msg = msg
    db.commit()
    print(f"[{job.id}] [{pct}%] {msg}")


@app.task(name="tasks.restore_task.run_restore")
def run_restore(job_id: str):
    db = SessionLocal()
    job = db.query(RestoreJob).filter(RestoreJob.id == uuid.UUID(job_id)).first()
    if not job:
        return

    tmp_path = None
    try:
        job.status = "running"
        db.commit()

        backup = db.query(BackupJob).filter(BackupJob.id == job.backup_job_id).first()
        local_path = backup.backup_path

        # Step 1 — Download from S3 if needed
        if backup.backup_path and backup.backup_path.startswith("s3://"):
            from services.storage import download_from_s3
            storage_cfg = db.query(StorageSettings).filter(StorageSettings.id == 1).first()
            s3_key = "/".join(backup.backup_path.split("/")[3:])
            tmp_path = f"/tmp/vaultstack-restore-{job_id}.qcow2"
            _progress(db, job, 10, "Downloading backup from S3...")
            download_from_s3(s3_key, tmp_path, storage_cfg)
            local_path = tmp_path
            _progress(db, job, 35, "Download complete")
        else:
            _progress(db, job, 35, "Using local backup file")

        # Step 2 — Upload to Glance
        _progress(db, job, 40, "Uploading image to Glance...")
        restore_image_name = f"vaultstack-restore-{job.target_vm_name}"
        image_id = os_svc.upload_image(restore_image_name, local_path)
        _progress(db, job, 65, "Image uploaded to Glance")

        # Step 3 — Pick flavor and network
        networks = os_svc.list_networks()
        flavor_id = job.flavor_id
        if not flavor_id:
            flavors = os_svc.list_flavors()
            flavor_id = flavors[0]["id"] if flavors else None
        network_id = job.target_network_id or (networks[0]["id"] if networks else None)

        # Step 4 — Boot VM
        _progress(db, job, 70, f"Booting VM '{job.target_vm_name}'...")
        new_vm_id = os_svc.create_vm_from_image(
            name=job.target_vm_name,
            image_id=image_id,
            flavor_id=flavor_id,
            network_id=network_id,
        )
        _progress(db, job, 90, "VM booted, cleaning up...")

        os_svc.delete_snapshot(image_id)

        job.new_vm_id = new_vm_id
        job.status = "success"
        job.progress = 100
        job.progress_msg = f"Restore complete. New VM: {new_vm_id}"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Restore complete. New VM: {new_vm_id}")

    except Exception as e:
        job.status = "failed"
        job.progress_msg = f"Failed: {str(e)}"
        job.error_msg = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Restore failed: {e}")
        raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        db.close()
