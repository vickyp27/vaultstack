from celery_app import app
import os, sys, subprocess, json, zipfile, uuid as _uuid, shutil, stat
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob

_BACKUP_ROOT = os.getenv("BACKUP_BASE_PATH", "/var/vaultstack/backups")
_FLR_CACHE   = os.path.join(_BACKUP_ROOT, ".flr_cache")
_FLR_EXTRACT = os.path.join(_BACKUP_ROOT, ".flr_extract")

_GUESTFS_ENV = {
    **os.environ,
    "LIBGUESTFS_BACKEND": "direct",
    "LIBVIRT_DEFAULT_URI": "qemu:///system",
}


def _ensure_dirs():
    os.makedirs(_FLR_CACHE,   exist_ok=True)
    os.makedirs(_FLR_EXTRACT, exist_ok=True)


def _get_s3_cfg(db, backup):
    from models.settings import StorageSettings
    from models.tenant_storage import TenantStorageConfig
    if backup.project_id:
        t = db.query(TenantStorageConfig).filter(
            TenantStorageConfig.project_id == backup.project_id,
            TenantStorageConfig.enabled == True,
        ).first()
        if t:
            return t
    return db.query(StorageSettings).filter(StorageSettings.id == 1).first()


def _local_qcow2(backup, db) -> str:
    """Return local path to decrypted image, downloading+decrypting from S3 if needed."""
    _ensure_dirs()
    cached = os.path.join(_FLR_CACHE, f"{backup.id}.img")
    if os.path.exists(cached):
        print(f"[FLR] Using cached {cached}")
        return cached

    if not backup.backup_path:
        raise ValueError("Backup has no file path")

    if backup.backup_path.startswith("s3://"):
        from services.storage import download_from_s3
        cfg = _get_s3_cfg(db, backup)
        if not cfg:
            raise ValueError("No storage config found")
        s3_key = "/".join(backup.backup_path.split("/")[3:])
        raw_path = cached + ".enc"
        print(f"[FLR] Downloading {s3_key} ...")
        download_from_s3(s3_key, raw_path, cfg)
    else:
        raw_path = backup.backup_path

    if backup.encrypted:
        from services.encryption import decrypt_file, get_encryption_key
        key = get_encryption_key()
        if not key:
            os.unlink(raw_path) if os.path.exists(raw_path) and raw_path.endswith(".enc") else None
            raise ValueError("BACKUP_ENCRYPTION_KEY not set — cannot decrypt backup")
        print(f"[FLR] Decrypting to {cached} ...")
        decrypt_file(raw_path, cached, key)
        if raw_path.endswith(".enc"):
            os.unlink(raw_path)
    else:
        if raw_path != cached:
            os.rename(raw_path, cached)

    return cached


def _run(args, timeout=120) -> str:
    r = subprocess.run(
        args,
        capture_output=True, text=True,
        timeout=timeout, env=_GUESTFS_ENV,
    )
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or f"Command failed: {args[0]}")
    return r.stdout


def _detect_format(image_path: str) -> str:
    r = subprocess.run(
        ["qemu-img", "info", "--output=json", image_path],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        info = json.loads(r.stdout)
        return info.get("format", "raw")
    return "raw"


def _find_root_partition(image_path: str, fmt: str) -> str:
    """
    Return the device path of the root Linux filesystem.
    Prefers the first ext4 partition; falls back to sda1.
    """
    r = subprocess.run(
        ["guestfish", f"--format={fmt}", "-a", image_path,
         "run", ":", "list-filesystems"],
        capture_output=True, text=True, timeout=120, env=_GUESTFS_ENV,
    )
    root = None
    for line in r.stdout.splitlines():
        parts = line.strip().split(":", 1)
        if len(parts) < 2:
            continue
        dev = parts[0].strip()
        fstype = parts[1].strip()
        if fstype in ("ext4", "ext3", "ext2", "xfs", "btrfs"):
            # Prefer sda1/vda1 as the root partition
            if "sda1" in dev or "vda1" in dev or root is None:
                root = dev
    return root or "/dev/sda1"


def _virt_ls(image_path: str, path: str, fmt: str, dev: str) -> list:
    """
    List directory entries using virt-ls -l.
    Format: perms nlinks uid gid size month day time name
    e.g.:   drwxr-xr-x  22 0 0  4096 Jun 12 16:39 .
    """
    output = _run(
        ["virt-ls", f"--format={fmt}", "-a", image_path, "-m", dev, "-l", path],
        timeout=180,
    )
    entries = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("total "):
            continue
        # Split into 9 parts: perms nlinks uid gid size month day time name
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        perms, _, uid, gid, size_str, month, day, timeyear, name = parts
        type_char = perms[0]
        # Strip symlink target  (name -> target)
        name = name.split(" -> ")[0].strip()
        if name in (".", ".."):
            continue
        try:
            size = int(size_str)
        except ValueError:
            size = 0
        full_path = path.rstrip("/") + "/" + name
        entries.append({
            "name": name,
            "path": full_path,
            "type": "dir"  if type_char == "d" else
                    "link" if type_char == "l" else "file",
            "size": size,
        })
    return entries


@app.task(name="tasks.file_restore_task.browse_backup", soft_time_limit=300)
def browse_backup(backup_id: str, path: str = "/"):
    db = SessionLocal()
    try:
        backup = db.query(BackupJob).filter(BackupJob.id == backup_id).first()
        if not backup:
            raise ValueError(f"Backup {backup_id} not found")

        img_path = _local_qcow2(backup, db)
        fmt = _detect_format(img_path)
        dev = _find_root_partition(img_path, fmt)
        print(f"[FLR] browse {path} in {img_path} (fmt={fmt}, dev={dev})")

        entries = _virt_ls(img_path, path, fmt, dev)
        # Sort: dirs first, then files alphabetically
        entries.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))
        return {"path": path, "entries": entries}

    finally:
        db.close()


@app.task(name="tasks.file_restore_task.extract_files", soft_time_limit=600)
def extract_files(backup_id: str, paths: list):
    db = SessionLocal()
    _ensure_dirs()
    tmp_dir  = os.path.join(_FLR_EXTRACT, f"tmp_{backup_id}_{_uuid.uuid4().hex[:8]}")
    zip_path = tmp_dir + ".zip"
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        backup = db.query(BackupJob).filter(BackupJob.id == backup_id).first()
        if not backup:
            raise ValueError(f"Backup {backup_id} not found")

        img_path = _local_qcow2(backup, db)
        fmt = _detect_format(img_path)
        dev = _find_root_partition(img_path, fmt)
        print(f"[FLR] extracting {len(paths)} file(s) from {img_path} (fmt={fmt}, dev={dev})")

        # virt-copy-out wraps: guestfish --ro -i copy-out "$@"
        # The -i flag auto-mounts all filesystems — do NOT also pass -m (conflicts)
        extracted, failed = 0, []
        for file_path in paths:
            try:
                _run(
                    ["virt-copy-out", f"--format={fmt}", "-a", img_path,
                     file_path, tmp_dir],
                    timeout=60,
                )
                extracted += 1
            except Exception as e:
                failed.append({"path": file_path, "error": str(e)})
                print(f"[FLR] failed to extract {file_path}: {e}")

        # Pack everything in tmp_dir into a zip
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(tmp_dir):
                for fname in files:
                    full = os.path.join(root, fname)
                    arcname = os.path.relpath(full, tmp_dir)
                    zf.write(full, arcname)

        return {
            "zip_path": zip_path,
            "vm_name": backup.vm_name or backup_id[:8],
            "extracted": extracted,
            "failed": failed,
        }

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        db.close()
