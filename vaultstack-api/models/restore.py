from sqlalchemy import Column, String, DateTime, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from database import Base

class RestoreJob(Base):
    __tablename__ = "restore_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    backup_job_id = Column(UUID(as_uuid=True), nullable=False)
    target_vm_name = Column(String, nullable=False)
    target_network_id = Column(String)
    flavor_id = Column(String)
    new_vm_id = Column(String)
    status = Column(
        Enum("queued", "running", "success", "failed", name="restore_status"),
        default="queued"
    )
    progress = Column(Integer, default=0)
    progress_msg = Column(String, default="")
    error_msg = Column(String)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
