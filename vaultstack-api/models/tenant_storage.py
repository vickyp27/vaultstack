from sqlalchemy import Column, String, Boolean
from database import Base


class TenantStorageConfig(Base):
    __tablename__ = "tenant_storage_configs"

    project_id      = Column(String, primary_key=True)
    project_name    = Column(String, default="")
    storage_type    = Column(String, default="s3")   # always s3 for per-tenant
    s3_endpoint_url = Column(String, default="")
    s3_access_key   = Column(String, default="")
    s3_secret_key   = Column(String, default="")
    s3_bucket_name  = Column(String, default="")
    s3_region       = Column(String, default="us-east-1")
    enabled         = Column(Boolean, default=True)
