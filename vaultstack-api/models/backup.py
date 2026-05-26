from sqlalchemy import Column, String, Float, DateTime, Enum
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from database import Base

class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(UUID(as_uuid=True), nullable=True)
    workload_snapshot_id = Column(UUID(as_uuid=True), nullable=True)
    project_id = Column(String, nullable=True)
    vm_id = Column(String, nullable=False)
    vm_name = Column(String)
    snapshot_id = Column(String)
    backup_path = Column(String)
    backup_type = Column(String, default="full")        # "full" or "incremental"
    parent_backup_id = Column(UUID(as_uuid=True), nullable=True)  # last full backup ref
    size_gb = Column(Float)
    status = Column(
        Enum("queued", "running", "success", "failed", name="backup_status"),
        default="queued"
    )
    error_msg = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
