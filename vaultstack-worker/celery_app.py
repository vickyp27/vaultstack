from celery import Celery
from celery.schedules import crontab
import os

app = Celery(
    "vaultstack",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=[
        "tasks.backup_task",
        "tasks.restore_task",
        "tasks.workload_task",
        "tasks.scheduler_task",
        "tasks.retention_task",
        "tasks.report_task",
    ],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    beat_schedule={
        "check-policies-every-minute": {
            "task": "tasks.scheduler_task.check_and_trigger_policies",
            "schedule": 60.0,
        },
        "enforce-retention-daily": {
            "task": "tasks.retention_task.enforce_retention",
            "schedule": crontab(hour=1, minute=0),    # 1:00 AM UTC daily
        },
        "daily-backup-report": {
            "task": "tasks.report_task.send_daily_report",
            "schedule": crontab(hour=8, minute=0),    # 8:00 AM UTC daily
        },
    },
)
