from celery import Celery
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
    },
)
