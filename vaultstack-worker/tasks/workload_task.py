from celery_app import app
from datetime import datetime
import sys, os, uuid
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.workload import WorkloadSnapshot
from models.backup import BackupJob
from models.policy import BackupPolicy
from models.settings import StorageSettings
from services import openstack as os_svc
from services.storage import (
    ensure_backup_dir, get_backup_path, get_size_gb, get_s3_key, upload_to_s3
)


def _log(ws_id, msg):
    print(f"[WORKLOAD:{ws_id[:8]}] {msg}")


def _backup_single_vm(db, ws, vm_id, storage_cfg, job_id=None):
    """Backup one VM as part of a workload. Returns (job, success)."""
    job_id = job_id or str(uuid.uuid4())
    job = BackupJob(
        id=uuid.UUID(job_id),
        vm_id=vm_id,
        policy_id=ws.policy_id,
        workload_snapshot_id=ws.id,
        status="running",
    )
    db.add(job)
    db.commit()

    try:
        vm = os_svc.get_vm(vm_id)
        job.vm_name = vm["name"]
        db.commit()

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        snap_name = f"vaultstack-{vm['name']}-{timestamp}"

        ensure_backup_dir(vm_id)
        local_path = get_backup_path(vm_id, job_id)

        volumes = vm.get("volumes", [])
        if volumes:
            _log(str(ws.id), f"  VM {vm['name']}: Cinder snapshot → {volumes[0][:8]}")
            snap_id = os_svc.create_volume_snapshot(volumes[0], snap_name)
            job.snapshot_id = snap_id
            db.commit()
            image_id = os_svc.volume_snapshot_to_glance_image(snap_id, snap_name)
            try:
                os_svc.delete_volume_snapshot(snap_id)
            except Exception:
                pass
        else:
            _log(str(ws.id), f"  VM {vm['name']}: Nova snapshot")
            image_id = os_svc.create_vm_snapshot(vm_id, snap_name)
            job.snapshot_id = image_id
            db.commit()

        _log(str(ws.id), f"  VM {vm['name']}: downloading image")
        os_svc.download_image(image_id, local_path)
        os_svc.delete_snapshot(image_id)

        size_gb = get_size_gb(local_path)

        if storage_cfg and storage_cfg.storage_type == "s3":
            s3_key = get_s3_key(vm_id, job_id)
            _log(str(ws.id), f"  VM {vm['name']}: uploading to S3 → {s3_key}")
            s3_path = upload_to_s3(local_path, s3_key, storage_cfg)
            os.remove(local_path)
            job.backup_path = s3_path
        else:
            job.backup_path = local_path

        job.size_gb = size_gb
        job.status = "success"
        job.completed_at = datetime.utcnow()
        db.commit()
        _log(str(ws.id), f"  VM {vm['name']}: ✓ {size_gb} GB")
        return job, True

    except Exception as e:
        job.status = "failed"
        job.error_msg = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        _log(str(ws.id), f"  VM {vm_id[:8]}: ✗ {e}")
        return job, False


@app.task(name="tasks.workload_task.run_workload_backup")
def run_workload_backup(workload_snapshot_id: str):
    db = SessionLocal()
    ws = db.query(WorkloadSnapshot).filter(
        WorkloadSnapshot.id == uuid.UUID(workload_snapshot_id)
    ).first()
    if not ws:
        return

    try:
        ws.status = "running"
        db.commit()

        policy = db.query(BackupPolicy).filter(
            BackupPolicy.id == ws.policy_id
        ).first()
        if not policy or not policy.vm_ids:
            raise RuntimeError("Policy not found or has no VMs")

        storage_cfg = db.query(StorageSettings).filter(
            StorageSettings.id == 1
        ).first()

        vm_ids = policy.vm_ids
        ws.vm_count = len(vm_ids)
        ws.policy_name = policy.name
        db.commit()

        _log(workload_snapshot_id, f"Starting workload '{policy.name}' — {len(vm_ids)} VMs")

        total_size = 0.0
        for i, vm_id in enumerate(vm_ids, 1):
            _log(workload_snapshot_id, f"[{i}/{len(vm_ids)}] Backing up VM {vm_id[:8]}")
            job, success = _backup_single_vm(db, ws, vm_id, storage_cfg)

            if success:
                ws.completed_count += 1
                total_size += job.size_gb or 0.0
            else:
                ws.failed_count += 1
            db.commit()

        ws.total_size_gb = round(total_size, 3)
        ws.completed_at = datetime.utcnow()

        if ws.failed_count == 0:
            ws.status = "success"
        elif ws.completed_count == 0:
            ws.status = "failed"
        else:
            ws.status = "partial"

        db.commit()
        _log(workload_snapshot_id,
             f"Done — {ws.completed_count} success / {ws.failed_count} failed / {ws.total_size_gb} GB total")

    except Exception as e:
        ws.status = "failed"
        ws.completed_at = datetime.utcnow()
        db.commit()
        _log(workload_snapshot_id, f"Workload failed: {e}")
        raise
    finally:
        db.close()
