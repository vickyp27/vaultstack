from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
from database import get_db
from models.workload import WorkloadSnapshot
from models.backup import BackupJob
from models.policy import BackupPolicy

router = APIRouter(prefix="/api/v1/workloads", tags=["workloads"])


class WorkloadCreate(BaseModel):
    policy_id: str


@router.get("/")
def list_workloads(db: Session = Depends(get_db)):
    snapshots = db.query(WorkloadSnapshot).order_by(
        WorkloadSnapshot.started_at.desc()
    ).all()
    return [_serialize(ws) for ws in snapshots]


@router.get("/{workload_id}")
def get_workload(workload_id: str, db: Session = Depends(get_db)):
    ws = db.query(WorkloadSnapshot).filter(
        WorkloadSnapshot.id == uuid.UUID(workload_id)
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workload snapshot not found")

    jobs = db.query(BackupJob).filter(
        BackupJob.workload_snapshot_id == ws.id
    ).all()

    data = _serialize(ws)
    data["jobs"] = [
        {
            "id": str(j.id),
            "vm_id": j.vm_id,
            "vm_name": j.vm_name,
            "status": j.status,
            "size_gb": j.size_gb,
            "error_msg": j.error_msg,
            "started_at": str(j.started_at),
            "completed_at": str(j.completed_at) if j.completed_at else None,
        }
        for j in jobs
    ]
    return data


@router.post("/")
def trigger_workload_backup(payload: WorkloadCreate, db: Session = Depends(get_db)):
    from celery_app import app as celery_app

    policy = db.query(BackupPolicy).filter(
        BackupPolicy.id == uuid.UUID(payload.policy_id)
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    ws = WorkloadSnapshot(
        id=uuid.uuid4(),
        policy_id=policy.id,
        policy_name=policy.name,
        status="queued",
        vm_count=len(policy.vm_ids or []),
    )
    db.add(ws)
    db.commit()
    db.refresh(ws)

    celery_app.send_task(
        "tasks.workload_task.run_workload_backup",
        args=[str(ws.id)],
    )

    return {"workload_snapshot_id": str(ws.id), "status": "queued"}


@router.delete("/{workload_id}")
def delete_workload(workload_id: str, db: Session = Depends(get_db)):
    ws = db.query(WorkloadSnapshot).filter(
        WorkloadSnapshot.id == uuid.UUID(workload_id)
    ).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workload snapshot not found")
    # Also delete individual backup jobs
    db.query(BackupJob).filter(
        BackupJob.workload_snapshot_id == ws.id
    ).delete()
    db.delete(ws)
    db.commit()
    return {"message": "Workload snapshot deleted"}


def _serialize(ws: WorkloadSnapshot) -> dict:
    success_rate = (
        round(ws.completed_count / ws.vm_count * 100)
        if ws.vm_count else 0
    )
    return {
        "id": str(ws.id),
        "policy_id": str(ws.policy_id),
        "policy_name": ws.policy_name or "—",
        "status": ws.status,
        "vm_count": ws.vm_count,
        "completed_count": ws.completed_count,
        "failed_count": ws.failed_count,
        "total_size_gb": round(ws.total_size_gb or 0, 3),
        "success_rate": success_rate,
        "started_at": str(ws.started_at),
        "completed_at": str(ws.completed_at) if ws.completed_at else None,
    }
