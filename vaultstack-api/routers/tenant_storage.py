from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import get_db
from models.tenant_storage import TenantStorageConfig

router = APIRouter(prefix="/api/v1/settings/tenants", tags=["tenant-storage"])


class TenantStorageIn(BaseModel):
    project_id:     str
    project_name:   str = ""
    s3_endpoint_url: str = ""
    s3_access_key:  str = ""
    s3_secret_key:  Optional[str] = None
    s3_bucket_name: str
    s3_region:      str = "us-east-1"
    enabled:        bool = True


def _row(t: TenantStorageConfig) -> dict:
    return {
        "project_id":      t.project_id,
        "project_name":    t.project_name,
        "storage_type":    t.storage_type,
        "s3_endpoint_url": t.s3_endpoint_url,
        "s3_access_key":   "***" if t.s3_access_key else "",
        "s3_bucket_name":  t.s3_bucket_name,
        "s3_region":       t.s3_region,
        "enabled":         t.enabled,
    }


@router.get("/")
def list_tenant_configs(db: Session = Depends(get_db)):
    return [_row(t) for t in db.query(TenantStorageConfig).all()]


@router.get("/{project_id}")
def get_tenant_config(project_id: str, db: Session = Depends(get_db)):
    t = db.query(TenantStorageConfig).filter(TenantStorageConfig.project_id == project_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="No config for this project")
    return _row(t)


@router.post("/")
def upsert_tenant_config(payload: TenantStorageIn, db: Session = Depends(get_db)):
    t = db.query(TenantStorageConfig).filter(TenantStorageConfig.project_id == payload.project_id).first()
    if not t:
        t = TenantStorageConfig(project_id=payload.project_id)
        db.add(t)

    t.project_name    = payload.project_name
    t.s3_endpoint_url = payload.s3_endpoint_url
    t.s3_bucket_name  = payload.s3_bucket_name
    t.s3_region       = payload.s3_region
    t.enabled         = payload.enabled
    if payload.s3_access_key and payload.s3_access_key != "***":
        t.s3_access_key = payload.s3_access_key
    if payload.s3_secret_key:
        t.s3_secret_key = payload.s3_secret_key
    db.commit()
    return _row(t)


@router.delete("/{project_id}")
def delete_tenant_config(project_id: str, db: Session = Depends(get_db)):
    t = db.query(TenantStorageConfig).filter(TenantStorageConfig.project_id == project_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(t)
    db.commit()
    return {"message": "Deleted"}


@router.post("/{project_id}/test")
def test_tenant_connection(project_id: str, db: Session = Depends(get_db)):
    t = db.query(TenantStorageConfig).filter(TenantStorageConfig.project_id == project_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="No config for this project")
    try:
        import boto3
        kwargs = {
            "aws_access_key_id":     t.s3_access_key,
            "aws_secret_access_key": t.s3_secret_key,
            "region_name":           t.s3_region or "us-east-1",
        }
        if t.s3_endpoint_url:
            kwargs["endpoint_url"] = t.s3_endpoint_url
        client = boto3.client("s3", **kwargs)
        client.list_objects_v2(Bucket=t.s3_bucket_name, MaxKeys=1)
        return {"success": True, "message": f"Connected to bucket '{t.s3_bucket_name}'"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# Helper used by backup worker
def get_storage_for_project(db: Session, project_id: str):
    """Returns TenantStorageConfig if configured and enabled, else None."""
    if not project_id:
        return None
    t = db.query(TenantStorageConfig).filter(
        TenantStorageConfig.project_id == project_id,
        TenantStorageConfig.enabled == True,
    ).first()
    return t
