from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from database import get_db
from models.policy import BackupPolicy
from models.backup import BackupJob

router = APIRouter(prefix="/api/v1/sla", tags=["sla"])


def _compute_vm_sla(vm_id: str, last_backup: BackupJob, policy: BackupPolicy):
    if not policy.sla_max_age_hours:
        return None
    if not last_backup or not last_backup.completed_at:
        return {
            "vm_id": vm_id,
            "status": "breach",
            "last_backup_at": None,
            "age_hours": None,
            "sla_max_age_hours": policy.sla_max_age_hours,
            "policy_id": str(policy.id),
            "policy_name": policy.name,
        }
    age_hours = (datetime.utcnow() - last_backup.completed_at).total_seconds() / 3600
    if age_hours <= policy.sla_max_age_hours * 0.8:
        status = "compliant"
    elif age_hours <= policy.sla_max_age_hours:
        status = "at_risk"
    else:
        status = "breach"
    return {
        "vm_id": vm_id,
        "vm_name": last_backup.vm_name,
        "status": status,
        "last_backup_at": str(last_backup.completed_at),
        "age_hours": round(age_hours, 1),
        "sla_max_age_hours": policy.sla_max_age_hours,
        "policy_id": str(policy.id),
        "policy_name": policy.name,
    }


@router.get("/compliance")
def sla_compliance(db: Session = Depends(get_db)):
    policies = db.query(BackupPolicy).filter(
        BackupPolicy.sla_max_age_hours.isnot(None),
        BackupPolicy.is_active == True,
    ).all()

    results = []
    for policy in policies:
        vm_ids = policy.vm_ids or []
        for vm_id in vm_ids:
            last_backup = (
                db.query(BackupJob)
                .filter(
                    BackupJob.vm_id == vm_id,
                    BackupJob.policy_id == policy.id,
                    BackupJob.status == "success",
                )
                .order_by(BackupJob.completed_at.desc())
                .first()
            )
            entry = _compute_vm_sla(vm_id, last_backup, policy)
            if entry:
                results.append(entry)

    return results


@router.get("/summary")
def sla_summary(db: Session = Depends(get_db)):
    items = sla_compliance(db=db)
    compliant = sum(1 for i in items if i["status"] == "compliant")
    at_risk   = sum(1 for i in items if i["status"] == "at_risk")
    breach    = sum(1 for i in items if i["status"] == "breach")
    return {
        "total": len(items),
        "compliant": compliant,
        "at_risk": at_risk,
        "breach": breach,
    }
