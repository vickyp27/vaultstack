from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from database import get_db
from models.policy import BackupPolicy
from models.backup import BackupJob
from models.test_restore_result import TestRestoreResult

router = APIRouter(prefix="/api/v1/test-restores", tags=["test-restores"])


@router.post("/{policy_id}/run")
def run_test_restore(policy_id: str, db: Session = Depends(get_db)):
    policy = db.query(BackupPolicy).filter(BackupPolicy.id == uuid.UUID(policy_id)).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    # Find latest successful backup for any VM in this policy
    backup = None
    for vm_id in (policy.vm_ids or []):
        b = (
            db.query(BackupJob)
            .filter(BackupJob.vm_id == vm_id, BackupJob.policy_id == policy.id,
                    BackupJob.status == "success")
            .order_by(BackupJob.completed_at.desc())
            .first()
        )
        if b:
            backup = b
            break

    if not backup:
        raise HTTPException(status_code=400, detail="No successful backup found for this policy")

    result = TestRestoreResult(
        id=uuid.uuid4(),
        policy_id=uuid.UUID(policy_id),
        backup_id=backup.id,
        status="running",
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    from celery_app import app as celery_app
    celery_app.send_task(
        "tasks.test_restore_task.run_test_restore",
        args=[str(result.id), str(backup.id)],
    )

    return {"result_id": str(result.id), "backup_id": str(backup.id), "status": "running"}


@router.get("/{policy_id}/results")
def list_test_results(policy_id: str, db: Session = Depends(get_db)):
    results = (
        db.query(TestRestoreResult)
        .filter(TestRestoreResult.policy_id == uuid.UUID(policy_id))
        .order_by(TestRestoreResult.started_at.desc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "policy_id": str(r.policy_id),
            "backup_id": str(r.backup_id) if r.backup_id else None,
            "restore_job_id": str(r.restore_job_id) if r.restore_job_id else None,
            "started_at": str(r.started_at),
            "completed_at": str(r.completed_at) if r.completed_at else None,
            "status": r.status,
            "test_vm_id": r.test_vm_id,
            "rto_seconds": r.rto_seconds,
            "error_msg": r.error_msg,
        }
        for r in results
    ]


@router.get("/results/all")
def list_all_test_results(db: Session = Depends(get_db)):
    results = (
        db.query(TestRestoreResult)
        .order_by(TestRestoreResult.started_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "policy_id": str(r.policy_id),
            "backup_id": str(r.backup_id) if r.backup_id else None,
            "started_at": str(r.started_at),
            "completed_at": str(r.completed_at) if r.completed_at else None,
            "status": r.status,
            "rto_seconds": r.rto_seconds,
            "error_msg": r.error_msg,
        }
        for r in results
    ]
