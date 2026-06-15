import os
from pathlib import Path
from config import settings


def ensure_backup_dir(vm_id: str) -> str:
    path = Path(settings.backup_base_path) / vm_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_backup_path(vm_id: str, backup_id: str) -> str:
    return str(Path(settings.backup_base_path) / vm_id / f"{backup_id}.qcow2")


def get_size_gb(path: str) -> float:
    return round(os.path.getsize(path) / (1024 ** 3), 3)


def delete_backup_file(path: str):
    if os.path.exists(path):
        os.remove(path)


def cleanup_old_backups(vm_id: str, retention_days: int):
    import time
    backup_dir = Path(settings.backup_base_path) / vm_id
    if not backup_dir.exists():
        return
    cutoff = time.time() - (retention_days * 86400)
    for f in backup_dir.glob("*.qcow2"):
        if f.stat().st_mtime < cutoff:
            f.unlink()


# ── S3 helpers ──────────────────────────────────────────────────────────────

def get_s3_key(vm_id: str, backup_id: str) -> str:
    return f"vaultstack/{vm_id}/{backup_id}.qcow2"


def _s3_client(cfg):
    import boto3
    kwargs = {
        "aws_access_key_id": cfg.s3_access_key,
        "aws_secret_access_key": cfg.s3_secret_key,
        "region_name": cfg.s3_region or "us-east-1",
    }
    if cfg.s3_endpoint_url:
        kwargs["endpoint_url"] = cfg.s3_endpoint_url
    return boto3.client("s3", **kwargs)


def upload_to_s3(local_path: str, s3_key: str, cfg) -> str:
    client = _s3_client(cfg)
    client.upload_file(local_path, cfg.s3_bucket_name, s3_key)
    return f"s3://{cfg.s3_bucket_name}/{s3_key}"


def download_from_s3(s3_key: str, local_path: str, cfg):
    client = _s3_client(cfg)
    client.download_file(cfg.s3_bucket_name, s3_key, local_path)


def delete_from_s3(s3_key: str, cfg):
    try:
        client = _s3_client(cfg)
        client.delete_object(Bucket=cfg.s3_bucket_name, Key=s3_key)
    except Exception:
        pass


# ── Swift helpers ────────────────────────────────────────────────────────────

def _swift_conn(cfg):
    import swiftclient
    return swiftclient.Connection(
        authurl=cfg.swift_auth_url,
        user=cfg.swift_username,
        key=cfg.swift_password,
        tenant_name=cfg.swift_tenant or None,
        auth_version=cfg.swift_auth_version or "3",
    )


def upload_to_swift(local_path: str, object_name: str, cfg) -> str:
    conn = _swift_conn(cfg)
    container = cfg.swift_container or "vaultstack-backups"
    try:
        conn.head_container(container)
    except Exception:
        conn.put_container(container)
    with open(local_path, "rb") as f:
        conn.put_object(container, object_name, f)
    return f"swift://{container}/{object_name}"


def download_from_swift(object_name: str, local_path: str, cfg):
    conn = _swift_conn(cfg)
    container = cfg.swift_container or "vaultstack-backups"
    _, content = conn.get_object(container, object_name)
    with open(local_path, "wb") as f:
        f.write(content)


def delete_from_swift(object_name: str, cfg):
    try:
        conn = _swift_conn(cfg)
        container = cfg.swift_container or "vaultstack-backups"
        conn.delete_object(container, object_name)
    except Exception:
        pass
