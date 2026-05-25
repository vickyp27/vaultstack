from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from database import get_db
from models.backup import BackupJob
from models.restore import RestoreJob
from models.alert import AlertConfig, AlertLog

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


# ── Health summary ──────────────────────────────────────────────────────────

@router.get("/health")
def get_health(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    day_ago  = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    all_backups   = db.query(BackupJob).all()
    last24        = [j for j in all_backups if j.started_at and j.started_at >= day_ago]
    last7d        = [j for j in all_backups if j.started_at and j.started_at >= week_ago]

    def rate(jobs):
        if not jobs: return None
        ok = sum(1 for j in jobs if j.status == "success")
        return round(ok / len(jobs) * 100)

    # 7-day daily breakdown
    daily = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end   = day_start + timedelta(days=1)
        day_jobs  = [j for j in all_backups if j.started_at and day_start <= j.started_at < day_end]
        daily.append({
            "date":    day_start.strftime("%b %d"),
            "success": sum(1 for j in day_jobs if j.status == "success"),
            "failed":  sum(1 for j in day_jobs if j.status == "failed"),
            "total":   len(day_jobs),
        })

    failed_jobs = (
        db.query(BackupJob)
        .filter(BackupJob.status == "failed")
        .order_by(BackupJob.started_at.desc())
        .limit(10)
        .all()
    )

    recent_alerts = (
        db.query(AlertLog)
        .order_by(AlertLog.sent_at.desc())
        .limit(20)
        .all()
    )

    return {
        "summary": {
            "success_rate_24h": rate(last24),
            "success_rate_7d":  rate(last7d),
            "total_jobs_24h":   len(last24),
            "total_jobs_7d":    len(last7d),
            "failed_24h":       sum(1 for j in last24 if j.status == "failed"),
            "failed_7d":        sum(1 for j in last7d  if j.status == "failed"),
        },
        "daily": daily,
        "recent_failures": [
            {
                "id":        str(j.id),
                "vm_name":   j.vm_name,
                "policy_id": str(j.policy_id) if j.policy_id else None,
                "error_msg": j.error_msg,
                "started_at": str(j.started_at),
            }
            for j in failed_jobs
        ],
        "alert_logs": [
            {
                "id":       a.id,
                "level":    a.level,
                "channel":  a.channel,
                "subject":  a.subject,
                "sent_at":  str(a.sent_at),
                "success":  a.success,
                "error_detail": a.error_detail,
            }
            for a in recent_alerts
        ],
    }


# ── Alert config ────────────────────────────────────────────────────────────

class AlertConfigIn(BaseModel):
    email_enabled:    bool = False
    email_smtp_host:  str  = ""
    email_smtp_port:  int  = 587
    email_username:   str  = ""
    email_password:   Optional[str] = None
    email_from:       str  = ""
    email_to:         str  = ""
    slack_enabled:    bool = False
    slack_webhook:    str  = ""
    alert_on_failure: bool = True
    alert_on_success: bool = False


@router.get("/alert-config")
def get_alert_config(db: Session = Depends(get_db)):
    cfg = db.query(AlertConfig).filter(AlertConfig.id == 1).first()
    if not cfg:
        return AlertConfigIn().model_dump()
    return {
        "email_enabled":    cfg.email_enabled,
        "email_smtp_host":  cfg.email_smtp_host,
        "email_smtp_port":  cfg.email_smtp_port,
        "email_username":   cfg.email_username,
        "email_password":   "",          # never return password
        "email_from":       cfg.email_from,
        "email_to":         cfg.email_to,
        "slack_enabled":    cfg.slack_enabled,
        "slack_webhook":    cfg.slack_webhook,
        "alert_on_failure": cfg.alert_on_failure,
        "alert_on_success": cfg.alert_on_success,
    }


@router.put("/alert-config")
def save_alert_config(payload: AlertConfigIn, db: Session = Depends(get_db)):
    cfg = db.query(AlertConfig).filter(AlertConfig.id == 1).first()
    if not cfg:
        cfg = AlertConfig(id=1)
        db.add(cfg)

    cfg.email_enabled    = payload.email_enabled
    cfg.email_smtp_host  = payload.email_smtp_host
    cfg.email_smtp_port  = payload.email_smtp_port
    cfg.email_username   = payload.email_username
    if payload.email_password:          # only update if provided
        cfg.email_password = payload.email_password
    cfg.email_from       = payload.email_from
    cfg.email_to         = payload.email_to
    cfg.slack_enabled    = payload.slack_enabled
    cfg.slack_webhook    = payload.slack_webhook
    cfg.alert_on_failure = payload.alert_on_failure
    cfg.alert_on_success = payload.alert_on_success
    db.commit()
    return {"message": "Alert config saved"}


@router.post("/test-alert")
def test_alert(db: Session = Depends(get_db)):
    cfg = db.query(AlertConfig).filter(AlertConfig.id == 1).first()
    if not cfg:
        raise HTTPException(status_code=400, detail="No alert config saved")
    results = []
    if cfg.email_enabled and cfg.email_smtp_host:
        ok, err = _send_email(cfg, "VaultStack Test Alert", "This is a test alert from VaultStack monitoring.")
        _log_alert(db, "info", "email", "VaultStack Test Alert", "Test alert", ok, err)
        results.append({"channel": "email", "success": ok, "error": err})
    if cfg.slack_enabled and cfg.slack_webhook:
        ok, err = _send_slack(cfg.slack_webhook, ":white_check_mark: *VaultStack Test Alert*\nThis is a test alert from VaultStack monitoring.")
        _log_alert(db, "info", "slack", "VaultStack Test Alert", "Test alert", ok, err)
        results.append({"channel": "slack", "success": ok, "error": err})
    if not results:
        raise HTTPException(status_code=400, detail="No alert channels configured")
    return {"results": results}


# ── Internal helpers ────────────────────────────────────────────────────────

def _log_alert(db, level, channel, subject, message, success, error_detail=""):
    db.add(AlertLog(
        level=level, channel=channel, subject=subject,
        message=message, success=success, error_detail=error_detail or "",
    ))
    db.commit()


def _send_email(cfg: AlertConfig, subject: str, body: str):
    try:
        import smtplib
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = cfg.email_from
        msg["To"]      = cfg.email_to
        with smtplib.SMTP(cfg.email_smtp_host, cfg.email_smtp_port, timeout=10) as s:
            s.starttls()
            if cfg.email_username:
                s.login(cfg.email_username, cfg.email_password)
            s.sendmail(cfg.email_from, cfg.email_to.split(","), msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)


def _send_slack(webhook_url: str, text: str):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"text": text}).encode()
        req  = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True, ""
    except Exception as e:
        return False, str(e)


# Public helpers used by worker
def send_failure_alert(db, job):
    cfg = db.query(AlertConfig).filter(AlertConfig.id == 1).first()
    if not cfg or not cfg.alert_on_failure:
        return
    vm   = job.vm_name or str(job.vm_id)
    subj = f"[VaultStack] Backup FAILED — {vm}"
    body = f"Backup job failed.\n\nVM: {vm}\nJob ID: {job.id}\nError: {job.error_msg}\nTime: {job.started_at}"
    slack_msg = f":x: *Backup Failed* — `{vm}`\n>Error: {job.error_msg}"

    if cfg.email_enabled and cfg.email_smtp_host:
        ok, err = _send_email(cfg, subj, body)
        _log_alert(db, "error", "email", subj, body, ok, err)
    if cfg.slack_enabled and cfg.slack_webhook:
        ok, err = _send_slack(cfg.slack_webhook, slack_msg)
        _log_alert(db, "error", "slack", subj, slack_msg, ok, err)


def send_success_alert(db, job):
    cfg = db.query(AlertConfig).filter(AlertConfig.id == 1).first()
    if not cfg or not cfg.alert_on_success:
        return
    vm   = job.vm_name or str(job.vm_id)
    subj = f"[VaultStack] Backup Success — {vm}"
    body = f"Backup completed.\n\nVM: {vm}\nJob ID: {job.id}\nSize: {job.size_gb} GB\nTime: {job.completed_at}"
    slack_msg = f":white_check_mark: *Backup Success* — `{vm}` ({job.size_gb} GB)"

    if cfg.email_enabled and cfg.email_smtp_host:
        ok, err = _send_email(cfg, subj, body)
        _log_alert(db, "info", "email", subj, body, ok, err)
    if cfg.slack_enabled and cfg.slack_webhook:
        ok, err = _send_slack(cfg.slack_webhook, slack_msg)
        _log_alert(db, "info", "slack", subj, slack_msg, ok, err)
