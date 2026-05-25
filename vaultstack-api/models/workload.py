from sqlalchemy import Column, String, Float, DateTime, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from database import Base


class WorkloadSnapshot(Base):
    __tablename__ = "workload_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(UUID(as_uuid=True), nullable=False)
    policy_name = Column(String, default="")
    status = Column(
        SAEnum("queued", "running", "partial", "success", "failed",
               name="workload_status"),
        default="queued",
    )
    vm_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    total_size_gb = Column(Float, default=0.0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
