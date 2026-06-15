from sqlalchemy import Column, String, DateTime, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from database import Base


class TestRestoreResult(Base):
    __tablename__ = "test_restore_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    backup_id = Column(UUID(as_uuid=True), nullable=True)
    restore_job_id = Column(UUID(as_uuid=True), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")   # running | passed | failed
    test_vm_id = Column(String, nullable=True)
    rto_seconds = Column(Integer, nullable=True)
    error_msg = Column(String, nullable=True)
