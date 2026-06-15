from sqlalchemy import Column, String, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid
from database import Base

class BackupPolicy(Base):
    __tablename__ = "backup_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    vm_ids = Column(ARRAY(String), default=[])
    schedule = Column(String, default="0 2 * * *")  # cron format
    retention_days = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)
    storage_path = Column(String, default="/var/vaultstack/backups")
    incremental_enabled = Column(Boolean, default=False)
    full_backup_interval = Column(Integer, default=6)  # full every N backups
    gfs_enabled = Column(Boolean, default=False)
    gfs_daily   = Column(Integer, default=7)   # keep last N daily backups
    gfs_weekly  = Column(Integer, default=4)   # keep last N weekly backups
    gfs_monthly = Column(Integer, default=12)  # keep last N monthly backups
    cbt_enabled = Column(Boolean, default=False)
