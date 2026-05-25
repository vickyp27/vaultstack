from sqlalchemy import Column, Integer, String
from database import Base


class StorageSettings(Base):
    __tablename__ = "storage_settings"

    id = Column(Integer, primary_key=True, default=1)
    storage_type = Column(String, default="local")   # "local" or "s3"
    s3_endpoint_url = Column(String, default="")
    s3_access_key = Column(String, default="")
    s3_secret_key = Column(String, default="")
    s3_bucket_name = Column(String, default="vaultstack-backups")
    s3_region = Column(String, default="us-east-1")
