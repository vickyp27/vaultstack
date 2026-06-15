import uuid
from datetime import datetime


def log_action(db, action: str, entity_type: str = None, entity_id: str = None,
               actor: str = None, details: str = None):
    from models.audit_log import AuditLog
    entry = AuditLog(
        id=uuid.uuid4(),
        timestamp=datetime.utcnow(),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        actor=actor,
        details=details,
    )
    db.add(entry)
    try:
        db.commit()
    except Exception:
        db.rollback()
