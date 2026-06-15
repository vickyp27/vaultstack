from celery_app import app
from datetime import datetime
import subprocess, sys, os, tarfile, json
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.restore import RestoreJob
from models.backup import BackupJob
from models.settings import StorageSettings
from models.tenant_storage import TenantStorageConfig
from services import openstack as os_svc
from services.storage import download_from_s3
import uuid


def _progress(db, job, pct, msg):
    job.progress     = pct
    job.progress_msg = msg
    db.commit()
    print(f"[{job.id}] [{pct}%] {msg}")


def _get_storage_cfg(db, project_id):
    if project_id:
        tenant_cfg = db.query(TenantStorageConfig).filter(
            TenantStorageConfig.project_id == project_id,
            TenantStorageConfig.enabled == True,
        ).first()
        if tenant_cfg:
            return tenant_cfg
    return db.query(StorageSettings).filter(StorageSettings.id == 1).first()


def _local_path_for_backup(backup, tmp_dir, storage_cfg):
    """
    Ensure the backup file is on local disk. Decrypts if backup.encrypted is set.
    Returns (path, owned) — owned=True means caller must delete the file.
    """
    if backup.backup_path and backup.backup_path.startswith("s3://"):
        local = os.path.join(tmp_dir, f"{backup.id}.qcow2")
        s3_key = "/".join(backup.backup_path.split("/")[3:])
        print(f"  Downloading {backup.backup_type} backup {backup.id} from S3…")
        download_from_s3(s3_key, local, storage_cfg)
        owned = True
    else:
        local = backup.backup_path
        owned = False

    if getattr(backup, "encrypted", False):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))
        from services.encryption import get_encryption_key, decrypt_file
        key = get_encryption_key()
        if not key:
            raise RuntimeError("Backup is encrypted but BACKUP_ENCRYPTION_KEY is not set")
        dec_path = os.path.join(tmp_dir, f"{backup.id}.dec.qcow2")
        print(f"  Decrypting backup {backup.id} (AES-256-CTR)…")
        decrypt_file(local, dec_path, key)
        if owned:
            os.remove(local)
        return dec_path, True

    return local, owned


def _is_multivolume_tar(path: str) -> bool:
    try:
        with tarfile.open(path, "r") as tar:
            return "manifest.json" in tar.getnames()
    except Exception:
        return False


def _restore_multivolume(db, job, tmp_dir, local_path, flavor_id, network_id,
                         target_project_id, target_vm_name, conn=None, job_id=None):
    """Extract tar, boot from vol_0, attach remaining volumes."""
    extract_dir = os.path.join(tmp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    _progress(db, job, 30, "Extracting multi-volume archive…")
    with tarfile.open(local_path, "r") as tar:
        tar.extractall(extract_dir)

    with open(os.path.join(extract_dir, "manifest.json")) as f:
        manifest = json.load(f)

    manifest.sort(key=lambda v: v["index"])
    boot_entry  = next(v for v in manifest if v["is_boot"])
    data_entries = [v for v in manifest if not v["is_boot"]]

    # ── Boot volume ───────────────────────────────────────────────────────────
    _progress(db, job, 40, "Uploading boot volume to Glance…")
    boot_qcow2 = os.path.join(extract_dir, boot_entry["filename"])
    uid = (str(job_id) if job_id else str(job.id))[:8]
    boot_image_id = os_svc.upload_image(
        f"vaultstack-restore-{uid}-{target_vm_name}-boot",
        boot_qcow2,
        project_id=target_project_id,
        conn=conn,
    )
    try:
        import json as _json
        _info = _json.loads(subprocess.check_output(
            ["qemu-img", "info", "--output=json", boot_qcow2], stderr=subprocess.DEVNULL
        ))
        _vsize_gb = max(1, (_info.get("virtual-size", 0) + (1 << 30) - 1) >> 30)
    except Exception:
        _vsize_gb = int(boot_entry.get("size_gb") or 0)
    boot_size_gb = max(int(boot_entry.get("size_gb") or 0) + 5, _vsize_gb + 1, 20)

    _progress(db, job, 55, f"Booting VM '{target_vm_name}' from boot volume…")
    new_vm_id = os_svc.create_vm_from_image(
        name=target_vm_name,
        image_id=boot_image_id,
        flavor_id=flavor_id,
        network_id=network_id,
        project_id=target_project_id,
        volume_size=boot_size_gb,
        conn=conn,
    )
    os_svc.delete_snapshot(boot_image_id, conn=conn)

    # ── Data volumes ──────────────────────────────────────────────────────────
    n = len(data_entries)
    for i, entry in enumerate(data_entries):
        _progress(db, job, 70 + i * (20 // max(n, 1)),
                  f"Restoring data volume {i+1}/{n}…")
        data_qcow2 = os.path.join(extract_dir, entry["filename"])
        try:
            import json as _json
            _di = _json.loads(subprocess.check_output(
                ["qemu-img", "info", "--output=json", data_qcow2], stderr=subprocess.DEVNULL
            ))
            _dvsize_gb = max(1, (_di.get("virtual-size", 0) + (1 << 30) - 1) >> 30)
        except Exception:
            _dvsize_gb = int(entry.get("size_gb") or 0)
        data_size_gb = max(int(entry.get("size_gb") or 0) + 1, _dvsize_gb + 1, 1)

        data_image_id = os_svc.upload_image(
            f"vaultstack-restore-{uid}-{target_vm_name}-data{i}",
            data_qcow2,
            project_id=target_project_id,
            conn=conn,
        )
        vol_id = os_svc.create_volume_from_image(
            data_image_id,
            data_size_gb,
            f"restore-{target_vm_name}-data{i}",
            project_id=target_project_id,
            conn=conn,
        )
        os_svc.delete_snapshot(data_image_id, conn=conn)
        os_svc.attach_volume_to_vm(new_vm_id, vol_id, project_id=target_project_id, conn=conn)

    return new_vm_id


def _resolve_backup_image(db, job, backup, storage_cfg, tmp_dir, tmp_files):
    """
    Download + decrypt backup (handling incremental merge).
    Returns local_path to the final image ready for upload to Glance.
    Appends any temp file paths to tmp_files.
    """
    if backup.backup_type == "incremental" and backup.parent_backup_id:
        _progress(db, job, 10, "Incremental — downloading full base backup…")
        parent = db.query(BackupJob).filter(BackupJob.id == backup.parent_backup_id).first()
        if not parent:
            raise RuntimeError(f"Parent backup {backup.parent_backup_id} not found")

        full_local, full_owned = _local_path_for_backup(parent, tmp_dir, storage_cfg)
        if full_owned:
            tmp_files.append(full_local)

        _progress(db, job, 25, "Downloading incremental delta…")
        delta_local, delta_owned = _local_path_for_backup(backup, tmp_dir, storage_cfg)
        if delta_owned:
            tmp_files.append(delta_local)

        _progress(db, job, 40, "Merging full + delta…")
        merged_path = os.path.join(tmp_dir, "merged.qcow2")
        tmp_files.append(merged_path)
        _flatten_incremental(full_local, delta_local, merged_path)
        return merged_path
    else:
        _progress(db, job, 10, "Downloading backup…")
        local, owned = _local_path_for_backup(backup, tmp_dir, storage_cfg)
        if owned:
            tmp_files.append(local)
        return local


def _flatten_incremental(full_path, delta_path, out_path):
    """
    Reconstruct full image from base (full_path) + VSDT delta (delta_path).
    Both may be raw or any qemu-supported format; output is a raw image.
    """
    from services.incremental import apply_delta, normalize_to_raw
    import json as _json

    # Normalize base to raw if needed
    info     = _json.loads(subprocess.check_output(
        ["qemu-img", "info", "--output=json", full_path], stderr=subprocess.DEVNULL
    ))
    base_fmt = info.get("format", "raw")
    base_raw = full_path if base_fmt == "raw" else full_path + ".tmp.raw"
    if base_fmt != "raw":
        print(f"  Converting base to raw…")
        normalize_to_raw(full_path, base_raw)

    try:
        apply_delta(base_raw, delta_path, out_path)
    finally:
        if base_raw != full_path and os.path.exists(base_raw):
            os.remove(base_raw)


@app.task(name="tasks.restore_task.run_restore")
def run_restore(job_id: str):
    db       = SessionLocal()
    job      = db.query(RestoreJob).filter(RestoreJob.id == uuid.UUID(job_id)).first()
    if not job:
        return

    tmp_files = []   # track temp files to clean up

    try:
        job.status = "running"
        db.commit()

        backup = db.query(BackupJob).filter(BackupJob.id == job.backup_job_id).first()
        project_id  = getattr(backup, "project_id", None)
        storage_cfg = _get_storage_cfg(db, project_id)
        tmp_dir     = f"/tmp/vaultstack-restore-{job_id}"
        os.makedirs(tmp_dir, exist_ok=True)

        # Use the same OpenStack provider the backup came from
        _provider_id = getattr(backup, "provider_id", None)
        _conn = os_svc.get_provider_conn(_provider_id) if _provider_id else None

        # ── Resolve the backup file to restore ──────────────────────────────
        local_path        = _resolve_backup_image(db, job, backup, storage_cfg, tmp_dir, tmp_files)
        target_project_id = getattr(job, "target_project_id", None)

        # ── Pick flavor and network ──────────────────────────────────────────
        flavor_id  = job.flavor_id
        if not flavor_id:
            flavors   = os_svc.list_flavors(conn=_conn)
            flavor_id = flavors[0]["id"] if flavors else None
        networks   = os_svc.list_networks(project_id=target_project_id, conn=_conn)
        network_id = job.target_network_id or (networks[0]["id"] if networks else None)

        # ── Multi-volume TAR or single qcow2 ─────────────────────────────────
        if _is_multivolume_tar(local_path):
            _progress(db, job, 25, "Multi-volume backup detected…")
            new_vm_id = _restore_multivolume(
                db, job, tmp_dir, local_path, flavor_id, network_id,
                target_project_id, job.target_vm_name, conn=_conn, job_id=job_id,
            )
        else:
            # ── Single volume: upload → boot ─────────────────────────────────
            _progress(db, job, 50, "Uploading image to Glance…")
            image_id = os_svc.upload_image(
                f"vaultstack-restore-{job_id[:8]}-{job.target_vm_name}",
                local_path,
                project_id=target_project_id,
                conn=_conn,
            )
            _progress(db, job, 70, "Image uploaded — booting VM…")
            proj_label = f" in project {target_project_id[:8]}…" if target_project_id else "…"
            _progress(db, job, 75, f"Booting VM '{job.target_vm_name}'{proj_label}")
            new_vm_id = os_svc.create_vm_from_image(
                name=job.target_vm_name,
                image_id=image_id,
                flavor_id=flavor_id,
                network_id=network_id,
                project_id=target_project_id,
                conn=_conn,
            )
            _progress(db, job, 90, "VM booted, cleaning up…")
            os_svc.delete_snapshot(image_id, conn=_conn)

        job.new_vm_id    = new_vm_id
        job.status       = "success"
        job.progress     = 100
        job.progress_msg = f"Restore complete. New VM: {new_vm_id}"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Restore complete. New VM: {new_vm_id}")

    except Exception as e:
        job.status       = "failed"
        job.progress_msg = f"Failed: {str(e)}"
        job.error_msg    = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Restore failed: {e}")
        raise
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        db.close()


@app.task(name="tasks.restore_task.run_instant_restore")
def run_instant_restore(job_id: str):
    """
    Instant Recovery — boot VM directly from Glance image (ephemeral disk).
    Skips Cinder volume provisioning so the VM is accessible in ~1-2 min
    instead of waiting 5-20 min for a full volume copy.
    """
    db  = SessionLocal()
    job = db.query(RestoreJob).filter(RestoreJob.id == uuid.UUID(job_id)).first()
    if not job:
        return

    tmp_files = []
    tmp_dir   = f"/tmp/vaultstack-instant-{job_id}"
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        job.status = "running"
        db.commit()

        backup          = db.query(BackupJob).filter(BackupJob.id == job.backup_job_id).first()
        project_id      = getattr(backup, "project_id", None)
        storage_cfg     = _get_storage_cfg(db, project_id)
        target_project_id = getattr(job, "target_project_id", None)

        _provider_id = getattr(backup, "provider_id", None)
        _conn        = os_svc.get_provider_conn(_provider_id) if _provider_id else None

        # ── Download + decrypt backup (handles incremental merge) ───────────
        local_path = _resolve_backup_image(db, job, backup, storage_cfg, tmp_dir, tmp_files)

        # ── Pick flavor and network ──────────────────────────────────────────
        flavor_id  = job.flavor_id
        if not flavor_id:
            flavors   = os_svc.list_flavors(conn=_conn)
            flavor_id = flavors[0]["id"] if flavors else None
        networks   = os_svc.list_networks(project_id=target_project_id, conn=_conn)
        network_id = job.target_network_id or (networks[0]["id"] if networks else None)

        # ── Upload to Glance ────────────────────────────────────────────────
        _progress(db, job, 55, "Uploading backup image to Glance…")
        image_id = os_svc.upload_image(
            f"vaultstack-instant-{job_id[:8]}-{job.target_vm_name}",
            local_path,
            project_id=target_project_id,
            conn=_conn,
        )

        # ── Boot VM from Glance image (ephemeral disk, no Cinder copy) ──────
        _progress(db, job, 80, f"Booting '{job.target_vm_name}' from image (instant)…")
        new_vm_id = os_svc.create_vm_instant(
            name=job.target_vm_name,
            image_id=image_id,
            flavor_id=flavor_id,
            network_id=network_id,
            project_id=target_project_id,
            conn=_conn,
        )
        # Glance image can be kept for re-use or deleted; delete to save space
        os_svc.delete_snapshot(image_id, conn=_conn)

        job.new_vm_id    = new_vm_id
        job.status       = "success"
        job.progress     = 100
        job.progress_msg = f"Instant restore complete. VM booting: {new_vm_id}"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Instant restore complete. VM: {new_vm_id}")

    except Exception as e:
        job.status       = "failed"
        job.progress_msg = f"Failed: {str(e)}"
        job.error_msg    = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Instant restore failed: {e}")
        raise
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        db.close()
