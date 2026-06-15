from celery_app import app
from datetime import datetime
import sys, os, time
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob
from models.restore import RestoreJob
from models.test_restore_result import TestRestoreResult
from services import openstack as os_svc
import uuid


@app.task(name="tasks.test_restore_task.run_test_restore")
def run_test_restore(result_id: str, backup_id: str):
    db = SessionLocal()
    result = db.query(TestRestoreResult).filter(
        TestRestoreResult.id == uuid.UUID(result_id)
    ).first()
    if not result:
        return

    try:
        backup = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(backup_id)).first()
        if not backup:
            raise ValueError(f"Backup {backup_id} not found")

        # Create a restore job for the test
        test_vm_name = f"test-restore-{result_id[:8]}"
        _provider_id = getattr(backup, "provider_id", None)
        _conn = os_svc.get_provider_conn(_provider_id) if _provider_id else None

        flavors = os_svc.list_flavors(conn=_conn)
        flavor_id = flavors[0]["id"] if flavors else None
        networks = os_svc.list_networks(
            project_id=getattr(backup, "project_id", None), conn=_conn
        )
        network_id = networks[0]["id"] if networks else None

        restore_job = RestoreJob(
            id=uuid.uuid4(),
            backup_job_id=uuid.UUID(backup_id),
            target_vm_name=test_vm_name,
            target_network_id=network_id,
            target_project_id=getattr(backup, "project_id", None),
            flavor_id=flavor_id,
            mode="instant",
            status="queued",
        )
        db.add(restore_job)
        db.commit()
        db.refresh(restore_job)

        result.restore_job_id = restore_job.id
        db.commit()

        # Trigger restore inline (instant mode)
        from tasks.restore_task import run_instant_restore
        run_instant_restore(str(restore_job.id))

        # Reload to get updated status
        db.refresh(restore_job)

        if restore_job.status != "success":
            raise RuntimeError(restore_job.error_msg or "Restore did not complete successfully")

        test_vm_id = restore_job.new_vm_id
        result.test_vm_id = test_vm_id

        # Wait briefly then delete the test VM
        time.sleep(10)
        try:
            _conn.compute.delete_server(test_vm_id)
        except Exception as e:
            print(f"[test_restore] Warning: could not delete test VM {test_vm_id}: {e}")

        rto_seconds = int((datetime.utcnow() - result.started_at).total_seconds())
        result.rto_seconds = rto_seconds
        result.status = "passed"
        result.completed_at = datetime.utcnow()
        db.commit()
        print(f"[test_restore] {result_id} passed — RTO: {rto_seconds}s, test VM: {test_vm_id}")

    except Exception as e:
        result.status = "failed"
        result.error_msg = str(e)
        result.completed_at = datetime.utcnow()
        db.commit()
        print(f"[test_restore] {result_id} failed: {e}")
    finally:
        db.close()
