from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
from database import Base

class Provider(Base):
    __tablename__ = "providers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # openstack, kubernetes, vmware, aws
    endpoint = Column(String)
    credentials = Column(JSON, default={})
    status = Column(String, default="unknown")  # connected, error, unknown
    status_msg = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_tested = Column(DateTime)
