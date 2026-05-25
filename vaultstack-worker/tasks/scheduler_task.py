import os
import sys
import uuid
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from celery_app import app
from croniter import croniter
from database import SessionLocal
from models.policy import BackupPolicy
from models.workload import WorkloadSnapshot


@app.task(name="tasks.scheduler_task.check_and_trigger_policies")
def check_and_trigger_policies():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        policies = db.query(BackupPolicy).filter(BackupPolicy.is_active == True).all()

        for policy in policies:
            try:
                if not policy.schedule:
                    continue

                cron = croniter(policy.schedule, now)
                prev_run = cron.get_prev(datetime)
                seconds_since = (now - prev_run).total_seconds()

                # Only trigger if we're within 90s of the scheduled time
                if seconds_since > 90:
                    continue

                # Dedup: skip if a workload already started at this slot
                already_triggered = db.query(WorkloadSnapshot).filter(
                    WorkloadSnapshot.policy_id == policy.id,
                    WorkloadSnapshot.started_at >= prev_run - timedelta(seconds=30),
                    WorkloadSnapshot.started_at <= prev_run + timedelta(seconds=90),
                ).first()

                if already_triggered:
                    continue

                ws = WorkloadSnapshot(
                    id=uuid.uuid4(),
                    policy_id=policy.id,
                    policy_name=policy.name,
                    vm_count=len(policy.vm_ids or []),
                    status="queued",
                )
                db.add(ws)
                db.commit()
                db.refresh(ws)

                app.send_task(
                    "tasks.workload_task.run_workload_backup",
                    args=[str(ws.id)],
                )
                print(f"[scheduler] Triggered workload {ws.id} for policy '{policy.name}' (schedule: {policy.schedule})")

            except Exception as e:
                print(f"[scheduler] Error processing policy {policy.id}: {e}")

    finally:
        db.close()
