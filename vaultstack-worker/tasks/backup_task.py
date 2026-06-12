from celery_app import app
from datetime import datetime
import subprocess, sys, os, json, tarfile
sys.path.append(os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))

from database import SessionLocal
from models.backup import BackupJob
from models.policy import BackupPolicy
from models.settings import StorageSettings
from models.tenant_storage import TenantStorageConfig
from services import openstack as os_svc
from services.storage import (
    ensure_backup_dir, get_backup_path, get_size_gb,
    get_s3_key, upload_to_s3, download_from_s3,
)
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


def _s3_key_for_job(job, job_id, vm_id):
    project_prefix = (getattr(job, "project_id", None) or "global")[:8]
    return f"{project_prefix}/{get_s3_key(vm_id, job_id)}"


def _maybe_encrypt(local_path, job, job_id):
    """Encrypt local_path in-place if BACKUP_ENCRYPTION_KEY is set."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../vaultstack-api"))
    from services.encryption import get_encryption_key, encrypt_file
    key = get_encryption_key()
    if not key:
        job.encrypted = False
        return
    enc_path = local_path + ".enc"
    print(f"[{job_id}] Encrypting backup (AES-256-CTR)…")
    encrypt_file(local_path, enc_path, key)
    os.remove(local_path)
    os.rename(enc_path, local_path)
    job.encrypted = True
    print(f"[{job_id}] Encryption complete")


def _upload(local_path, job_id, vm_id, job, storage_cfg):
    """Upload local file to S3 (or keep local). Returns stored path."""
    if storage_cfg and storage_cfg.storage_type == "s3":
        s3_key = _s3_key_for_job(job, job_id, vm_id)
        print(f"[{job_id}] Uploading to S3: {s3_key}")
        s3_path = upload_to_s3(local_path, s3_key, storage_cfg)
        os.remove(local_path)
        return s3_path
    return local_path


def _download_base_backup(parent_backup, storage_cfg, tmp_path):
    """Download the parent (full) backup to a local temp file for delta computation."""
    if parent_backup.backup_path.startswith("s3://"):
        s3_key = "/".join(parent_backup.backup_path.split("/")[3:])
        print(f"  Downloading base backup from S3: {s3_key}")
        download_from_s3(s3_key, tmp_path, storage_cfg)
        return tmp_path, True
    else:
        return parent_backup.backup_path, False


def _qemu_rebase(new_path, base_path):
    delta_path = new_path + ".delta"
    subprocess.run(
        ["qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", new_path, delta_path],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["qemu-img", "rebase", "-f", "qcow2", "-F", "qcow2", "-b", base_path, delta_path],
        check=True, capture_output=True,
    )
    return delta_path


def _snapshot_volume_to_image(db, job, job_id, volume_id, snap_name, vol_index, total_vols, conn):
    """Snapshot a single Cinder volume and convert to Glance image. Returns image_id."""
    pct_base = 10 + (vol_index * 20 // total_vols)
    _progress(db, job, pct_base,
              f"Creating snapshot: volume {vol_index+1}/{total_vols} ({volume_id[:8]})…")
    snap_id = os_svc.create_volume_snapshot(volume_id, snap_name, conn=conn)
    if vol_index == 0:
        job.snapshot_id = snap_id
        db.commit()

    _progress(db, job, pct_base + 10 // total_vols,
              f"Converting snapshot → Glance: volume {vol_index+1}/{total_vols}…")
    image_id = os_svc.volume_snapshot_to_glance_image(snap_id, snap_name, conn=conn)
    try:
        os_svc.delete_volume_snapshot(snap_id, conn=conn)
    except Exception:
        pass
    return image_id


def _do_full_backup_multivolume(db, job, job_id, volumes, snapshot_name, local_path, storage_cfg, conn=None, vm_id=None):
    """
    Snapshot ALL volumes (with optional app-consistent freeze), then download +
    pack into tar one volume at a time.
    Returns (total_size_gb, app_consistent_bool).
    """
    import io as _io
    n = len(volumes)
    manifest = []
    tar_path  = local_path + ".tar"

    # ── Phase 1: [Freeze VM] → snapshot every volume → [Unfreeze VM] ──────
    # VM stays frozen only during snapshot creation (fast COW), not during
    # the slow Glance conversion + download phases that follow.
    snap_ids = []
    _frozen  = False
    try:
        if vm_id:
            _frozen = os_svc.freeze_vm(vm_id, conn=conn)
            if _frozen:
                print(f"[{job_id}] VM frozen for app-consistent snapshot…")
        for i, volume_id in enumerate(volumes):
            snap_name = f"{snapshot_name}-v{i}"
            pct = 10 + (i * 10 // n)
            _progress(db, job, pct, f"Creating snapshot: volume {i+1}/{n}…")
            snap_id = os_svc.create_volume_snapshot(volume_id, snap_name, conn=conn)
            if i == 0:
                job.snapshot_id = snap_id
                db.commit()
            snap_ids.append(snap_id)
    finally:
        if _frozen:
            os_svc.unfreeze_vm(vm_id, conn=conn)
            print(f"[{job_id}] VM unfrozen after snapshot trigger…")

    # ── Phase 2: Convert each Cinder snapshot → Glance image ──────────────
    image_ids = []
    for i, snap_id in enumerate(snap_ids):
        snap_name = f"{snapshot_name}-v{i}"
        pct = 20 + (i * 20 // n)
        _progress(db, job, pct, f"Converting snapshot → Glance: volume {i+1}/{n}…")
        image_id = os_svc.volume_snapshot_to_glance_image(snap_id, snap_name, conn=conn)
        try:
            os_svc.delete_volume_snapshot(snap_id, conn=conn)
        except Exception:
            pass
        image_ids.append(image_id)

    # ── Phase 3: Download one volume at a time → stream into tar → delete ─
    with tarfile.open(tar_path, "w") as tar:
        for i, image_id in enumerate(image_ids):
            pct = 45 + (i * 35 // n)
            _progress(db, job, pct, f"Downloading volume {i+1}/{n} from Glance…")
            vol_path = f"{local_path}.vol{i}.qcow2"
            try:
                os_svc.download_image(image_id, vol_path, conn=conn)
                os_svc.delete_snapshot(image_id, conn=conn)
                manifest.append({
                    "index":     i,
                    "volume_id": volumes[i],
                    "filename":  f"vol_{i}.qcow2",
                    "is_boot":   (i == 0),
                    "size_gb":   get_size_gb(vol_path),
                })
                _progress(db, job, pct + (15 // n),
                          f"Packing volume {i+1}/{n} into archive…")
                tar.add(vol_path, arcname=f"vol_{i}.qcow2")
            finally:
                if os.path.exists(vol_path):
                    os.remove(vol_path)

        manifest_bytes = json.dumps(manifest, indent=2).encode()
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_bytes)
        tar.addfile(info, _io.BytesIO(manifest_bytes))

    os.rename(tar_path, local_path)

    total_size = get_size_gb(local_path)
    _maybe_encrypt(local_path, job, job_id)
    stored_path = _upload(local_path, job_id, job.vm_id, job, storage_cfg)
    job.backup_path = stored_path
    job.backup_type = "full"
    return total_size, _frozen


def _do_full_backup(job_id, vm_id, image_id, local_path, job, storage_cfg, conn=None):
    """Single-volume full backup (image-backed VMs). Download Glance image → encrypt → upload."""
    print(f"[{job_id}] Downloading full image to {local_path}")
    os_svc.download_image(image_id, local_path, conn=conn)
    os_svc.delete_snapshot(image_id, conn=conn)
    size_gb = get_size_gb(local_path)
    _maybe_encrypt(local_path, job, job_id)
    stored_path = _upload(local_path, job_id, vm_id, job, storage_cfg)
    job.backup_path = stored_path
    job.backup_type = "full"
    return size_gb


def _do_incremental_backup(job_id, vm_id, image_id, local_path, job, storage_cfg, parent_backup, conn=None):
    """Single-volume incremental backup via qemu-img rebase delta."""
    new_path  = local_path + ".new"
    base_tmp  = local_path + ".base"
    delta_path = None
    base_owned = False

    try:
        print(f"[{job_id}] [INCREMENTAL] Downloading new snapshot…")
        os_svc.download_image(image_id, new_path, conn=conn)
        os_svc.delete_snapshot(image_id, conn=conn)

        base_path, base_owned = _download_base_backup(parent_backup, storage_cfg, base_tmp)

        print(f"[{job_id}] [INCREMENTAL] Computing delta vs base backup…")
        delta_path = _qemu_rebase(new_path, base_path)
        os.remove(new_path)

        size_gb = get_size_gb(delta_path)
        print(f"[{job_id}] [INCREMENTAL] Delta size: {size_gb} GB")

        os.rename(delta_path, local_path)
        delta_path = None

        _maybe_encrypt(local_path, job, job_id)
        stored_path = _upload(local_path, job_id, vm_id, job, storage_cfg)
        job.backup_path = stored_path
        job.backup_type = "incremental"
        job.parent_backup_id = parent_backup.id
        return size_gb

    finally:
        if delta_path and os.path.exists(delta_path):
            os.remove(delta_path)
        if os.path.exists(new_path):
            os.remove(new_path)
        if base_owned and os.path.exists(base_tmp):
            os.remove(base_tmp)


def _should_do_incremental(db, vm_id, policy_id):
    if not policy_id:
        return False, None

    policy = db.query(BackupPolicy).filter(BackupPolicy.id == policy_id).first()
    if not policy or not policy.incremental_enabled:
        return False, None

    last_full = (
        db.query(BackupJob)
        .filter(
            BackupJob.vm_id == vm_id,
            BackupJob.policy_id == policy_id,
            BackupJob.status == "success",
            BackupJob.backup_type == "full",
        )
        .order_by(BackupJob.started_at.desc())
        .first()
    )

    if not last_full:
        return False, None

    incrementals_since_full = (
        db.query(BackupJob)
        .filter(
            BackupJob.vm_id == vm_id,
            BackupJob.policy_id == policy_id,
            BackupJob.status == "success",
            BackupJob.backup_type == "incremental",
            BackupJob.started_at > last_full.started_at,
        )
        .count()
    )

    interval = policy.full_backup_interval or 6
    if incrementals_since_full >= interval - 1:
        return False, None

    return True, last_full


@app.task(name="tasks.backup_task.run_backup")
def run_backup(job_id: str):
    db  = SessionLocal()
    job = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(job_id)).first()
    if not job:
        return

    try:
        job.status = "running"
        _progress(db, job, 2, "Starting backup…")

        _conn = None
        if getattr(job, "provider_id", None):
            try:
                _conn = os_svc.get_provider_conn(job.provider_id)
                print(f"[{job_id}] Using provider connection for {job.provider_id}")
            except Exception as e:
                print(f"[{job_id}] Could not load provider conn, falling back: {e}")

        vm = os_svc.get_vm(job.vm_id, conn=_conn)
        job.vm_name    = vm["name"]
        job.project_id = vm.get("project_id")
        db.commit()

        timestamp     = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        snapshot_name = f"vaultstack-{vm['name']}-{timestamp}"

        ensure_backup_dir(job.vm_id)
        local_path  = get_backup_path(job.vm_id, job_id)
        storage_cfg = _get_storage_cfg(db, job.project_id)
        volumes     = vm.get("volumes", [])

        # ── Volume-backed VM (Cinder) ────────────────────────────────────────
        if volumes:
            if len(volumes) > 1:
                # Multi-volume: freeze → snapshot all → unfreeze → pack tar
                _progress(db, job, 5, f"Multi-volume VM: {len(volumes)} volumes detected…")
                size_gb, _frozen = _do_full_backup_multivolume(
                    db, job, job_id, volumes, snapshot_name, local_path, storage_cfg,
                    conn=_conn, vm_id=job.vm_id,
                )
                job.app_consistent = _frozen
            else:
                # Single volume: freeze → snapshot → unfreeze → convert → download
                do_incremental, parent_backup = _should_do_incremental(
                    db, job.vm_id, job.policy_id
                )
                volume_id = volumes[0]
                _frozen = False
                try:
                    _progress(db, job, 10, f"Creating Cinder snapshot of volume {volume_id[:8]}…")
                    _frozen = os_svc.freeze_vm(job.vm_id, conn=_conn)
                    snap_id = os_svc.create_volume_snapshot(volume_id, snapshot_name, conn=_conn)
                    job.snapshot_id = snap_id
                    db.commit()
                finally:
                    if _frozen:
                        os_svc.unfreeze_vm(job.vm_id, conn=_conn)
                job.app_consistent = _frozen

                _progress(db, job, 30, "Converting volume snapshot → Glance image…")
                image_id = os_svc.volume_snapshot_to_glance_image(snap_id, snapshot_name, conn=_conn)
                try:
                    os_svc.delete_volume_snapshot(snap_id, conn=_conn)
                except Exception:
                    pass

                if do_incremental:
                    _progress(db, job, 45, "Incremental backup — downloading new snapshot…")
                    size_gb = _do_incremental_backup(
                        job_id, job.vm_id, image_id, local_path,
                        job, storage_cfg, parent_backup, conn=_conn,
                    )
                else:
                    _progress(db, job, 45, "Full backup — downloading image from Glance…")
                    size_gb = _do_full_backup(
                        job_id, job.vm_id, image_id, local_path, job, storage_cfg, conn=_conn,
                    )

        # ── Image-backed VM (Nova snapshot) ──────────────────────────────────
        else:
            do_incremental, parent_backup = _should_do_incremental(
                db, job.vm_id, job.policy_id
            )
            # Freeze → trigger snapshot → unfreeze immediately → wait for active
            # VM stays frozen only during the brief createImage request, not
            # during the potentially long image upload to Glance.
            _frozen = False
            try:
                _progress(db, job, 10, f"Creating Nova snapshot of VM {vm['name']}…")
                _frozen = os_svc.freeze_vm(job.vm_id, conn=_conn)
                image_id = os_svc.trigger_vm_snapshot(job.vm_id, snapshot_name, conn=_conn)
                job.snapshot_id = image_id
                db.commit()
            finally:
                if _frozen:
                    os_svc.unfreeze_vm(job.vm_id, conn=_conn)
            job.app_consistent = _frozen

            _progress(db, job, 20, "Waiting for snapshot to become active…")
            os_svc.wait_for_image_active(image_id, conn=_conn)
            _progress(db, job, 30, "Snapshot active in Glance…")

            if do_incremental:
                _progress(db, job, 45, "Incremental backup — downloading new snapshot…")
                size_gb = _do_incremental_backup(
                    job_id, job.vm_id, image_id, local_path,
                    job, storage_cfg, parent_backup, conn=_conn,
                )
            else:
                _progress(db, job, 45, "Full backup — downloading image from Glance…")
                size_gb = _do_full_backup(
                    job_id, job.vm_id, image_id, local_path, job, storage_cfg, conn=_conn,
                )

        _progress(db, job, 90, "Finalizing…")
        job.size_gb      = size_gb
        job.status       = "success"
        job.progress     = 100
        job.progress_msg = f"Backup complete — {size_gb:.2f} GB"
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Backup complete ({job.backup_type}): {size_gb:.2f} GB → {job.backup_path}")

        try:
            from routers.monitoring import send_success_alert
            send_success_alert(db, job)
        except Exception:
            pass

    except Exception as e:
        job.status       = "failed"
        job.error_msg    = str(e)
        job.completed_at = datetime.utcnow()
        db.commit()
        print(f"[{job_id}] Backup failed: {e}")
        try:
            from routers.monitoring import send_failure_alert
            send_failure_alert(db, job)
        except Exception:
            pass
        raise
    finally:
        db.close()
