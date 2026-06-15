from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models.settings import StorageSettings

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class StorageSettingsPayload(BaseModel):
    storage_type: str = "local"
    s3_endpoint_url: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_name: str = "vaultstack-backups"
    s3_region: str = "us-east-1"
    swift_auth_url: str = ""
    swift_username: str = ""
    swift_password: str = ""
    swift_tenant: str = ""
    swift_container: str = "vaultstack-backups"
    swift_auth_version: str = "3"


def _get_or_create(db: Session) -> StorageSettings:
    cfg = db.query(StorageSettings).filter(StorageSettings.id == 1).first()
    if not cfg:
        cfg = StorageSettings(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/storage")
def get_storage_settings(db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    return {
        "storage_type": cfg.storage_type or "local",
        "s3_endpoint_url": cfg.s3_endpoint_url or "",
        "s3_access_key": "***" if cfg.s3_access_key else "",
        "s3_secret_key": "***" if cfg.s3_secret_key else "",
        "s3_bucket_name": cfg.s3_bucket_name or "vaultstack-backups",
        "s3_region": cfg.s3_region or "us-east-1",
        "swift_auth_url": cfg.swift_auth_url or "",
        "swift_username": cfg.swift_username or "",
        "swift_password": "***" if cfg.swift_password else "",
        "swift_tenant": cfg.swift_tenant or "",
        "swift_container": cfg.swift_container or "vaultstack-backups",
        "swift_auth_version": cfg.swift_auth_version or "3",
    }


@router.put("/storage")
def update_storage_settings(payload: StorageSettingsPayload, db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    cfg.storage_type = payload.storage_type
    cfg.s3_endpoint_url = payload.s3_endpoint_url
    cfg.s3_bucket_name = payload.s3_bucket_name
    cfg.s3_region = payload.s3_region
    if payload.s3_access_key and payload.s3_access_key != "***":
        cfg.s3_access_key = payload.s3_access_key
    if payload.s3_secret_key and payload.s3_secret_key != "***":
        cfg.s3_secret_key = payload.s3_secret_key
    cfg.swift_auth_url = payload.swift_auth_url
    cfg.swift_username = payload.swift_username
    cfg.swift_tenant = payload.swift_tenant
    cfg.swift_container = payload.swift_container
    cfg.swift_auth_version = payload.swift_auth_version
    if payload.swift_password and payload.swift_password != "***":
        cfg.swift_password = payload.swift_password
    db.commit()
    return {"message": "Storage settings updated successfully"}


@router.post("/storage/test")
def test_s3_connection(db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    if cfg.storage_type != "s3":
        return {"success": True, "message": "Using local storage — no connection needed."}
    try:
        import boto3
        kwargs = {
            "aws_access_key_id": cfg.s3_access_key,
            "aws_secret_access_key": cfg.s3_secret_key,
            "region_name": cfg.s3_region or "us-east-1",
        }
        if cfg.s3_endpoint_url:
            kwargs["endpoint_url"] = cfg.s3_endpoint_url
        client = boto3.client("s3", **kwargs)
        client.list_objects_v2(Bucket=cfg.s3_bucket_name, MaxKeys=1)
        return {"success": True, "message": f"Connected to bucket '{cfg.s3_bucket_name}' successfully."}
    except Exception as e:
        return {"success": False, "message": str(e)}
