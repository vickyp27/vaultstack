from celery_app import app
from datetime import datetime, timedelta
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob
from models.restore import RestoreJob
from models.policy import BackupPolicy


@app.task(name="tasks.report_task.send_daily_report")
def send_daily_report():
    db = SessionLocal()
    try:
        from models.alert import AlertConfig
        cfg = db.query(AlertConfig).filter(AlertConfig.id == 1).first()
        if not cfg or not cfg.email_enabled or not cfg.email_smtp_host:
            print("[report] Email not configured, skipping daily report")
            return

        now   = datetime.utcnow()
        since = now - timedelta(hours=24)

        # Last 24h backup stats
        recent_backups = db.query(BackupJob).filter(BackupJob.started_at >= since).all()
        total    = len(recent_backups)
        success  = sum(1 for j in recent_backups if j.status == "success")
        failed   = sum(1 for j in recent_backups if j.status == "failed")
        running  = sum(1 for j in recent_backups if j.status in ("running", "queued"))
        total_gb = sum(float(j.size_gb or 0) for j in recent_backups if j.status == "success")

        # Failed job details
        failed_jobs = [j for j in recent_backups if j.status == "failed"]

        # All-time stats
        all_backups    = db.query(BackupJob).all()
        all_success    = sum(1 for j in all_backups if j.status == "success")
        all_total      = len(all_backups)
        all_success_gb = sum(float(j.size_gb or 0) for j in all_backups if j.status == "success")
        policies       = db.query(BackupPolicy).count()

        # Recent restores
        recent_restores = db.query(RestoreJob).filter(RestoreJob.started_at >= since).all()
        restore_ok  = sum(1 for r in recent_restores if r.status == "success")
        restore_fail = sum(1 for r in recent_restores if r.status == "failed")

        success_rate = round(success / total * 100) if total else 0
        overall_rate = round(all_success / all_total * 100) if all_total else 0

        # Build email
        sep = "─" * 50

        subject = f"[VaultStack] Daily Backup Report — {now.strftime('%b %d, %Y')}"

        body = f"""VaultStack Daily Backup Report
Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}
{sep}

LAST 24 HOURS
  Total jobs     : {total}
  Successful     : {success}  ✓
  Failed         : {failed}  ✗
  Running/Queued : {running}
  Success rate   : {success_rate}%
  Data backed up : {total_gb:.2f} GB

"""

        if failed_jobs:
            body += f"FAILED JOBS\n"
            for j in failed_jobs:
                body += f"  • {j.vm_name or j.vm_id} — {(j.error_msg or 'unknown error')[:80]}\n"
            body += "\n"

        if recent_restores:
            body += f"RESTORE ACTIVITY (last 24h)\n"
            body += f"  Successful restores : {restore_ok}\n"
            body += f"  Failed restores     : {restore_fail}\n\n"

        body += f"""{sep}
OVERALL STATISTICS
  Total policies     : {policies}
  All-time backups   : {all_total}
  All-time success   : {overall_rate}%
  Total stored       : {all_success_gb:.2f} GB
{sep}

-- VaultStack Backup Platform
"""

        from routers.monitoring import _send_email, _log_alert
        ok, err = _send_email(cfg, subject, body)
        _log_alert(db, "info", "email", subject, "Daily report sent", ok, err)

        if ok:
            print(f"[report] Daily report sent to {cfg.email_to}")
        else:
            print(f"[report] Failed to send report: {err}")

        # Slack summary
        if cfg.slack_enabled and cfg.slack_webhook:
            from routers.monitoring import _send_slack
            emoji = ":white_check_mark:" if failed == 0 else ":warning:"
            slack_msg = (
                f"{emoji} *VaultStack Daily Report — {now.strftime('%b %d')}*\n"
                f">Backups: {success}/{total} success ({success_rate}%) | "
                f"{total_gb:.1f} GB backed up"
            )
            if failed > 0:
                slack_msg += f"\n>:x: {failed} job(s) failed — check portal"
            _send_slack(cfg.slack_webhook, slack_msg)

        return {"sent": ok, "total": total, "success": success, "failed": failed}

    except Exception as e:
        print(f"[report] Error: {e}")
        raise
    finally:
        db.close()
