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
    """Upload local file to S3/Swift (or keep local). Returns stored path."""
    if storage_cfg and storage_cfg.storage_type == "s3":
        s3_key = _s3_key_for_job(job, job_id, vm_id)
        print(f"[{job_id}] Uploading to S3: {s3_key}")
        s3_path = upload_to_s3(local_path, s3_key, storage_cfg)
        os.remove(local_path)
        return s3_path
    if storage_cfg and storage_cfg.storage_type == "swift":
        from services.storage import upload_to_swift
        swift_key = _s3_key_for_job(job, job_id, vm_id)
        print(f"[{job_id}] Uploading to Swift: {swift_key}")
        swift_path = upload_to_swift(local_path, swift_key, storage_cfg)
        os.remove(local_path)
        return swift_path
    return local_path


def _download_and_decrypt_base(parent_backup, storage_cfg, tmp_path):
    """
    Download parent backup to tmp_path and decrypt if needed.
    Returns (local_path, owned).
    """
    if parent_backup.backup_path.startswith("s3://"):
        s3_key = "/".join(parent_backup.backup_path.split("/")[3:])
        enc_path = tmp_path + ".enc" if parent_backup.encrypted else tmp_path
        print(f"  Downloading base backup from S3: {s3_key}")
        download_from_s3(s3_key, enc_path, storage_cfg)
        if parent_backup.encrypted:
            from services.encryption import get_encryption_key, decrypt_file
            key = get_encryption_key()
            if not key:
                raise RuntimeError("BACKUP_ENCRYPTION_KEY not set — cannot decrypt base backup")
            print(f"  Decrypting base backup…")
            decrypt_file(enc_path, tmp_path, key)
            os.remove(enc_path)
        return tmp_path, True
    else:
        local = parent_backup.backup_path
        if parent_backup.encrypted:
            from services.encryption import get_encryption_key, decrypt_file
            key = get_encryption_key()
            if not key:
                raise RuntimeError("BACKUP_ENCRYPTION_KEY not set — cannot decrypt base backup")
            decrypt_file(local, tmp_path, key)
            return tmp_path, True
        return local, False


def _create_incremental_delta(new_path, base_path, delta_path):
    """
    Normalize both images to raw and compute a VSDT block-level delta.
    Returns stats dict from create_delta.
    """
    from services.incremental import normalize_to_raw, create_delta

    new_raw  = new_path  + ".raw"
    base_raw = base_path + ".raw"
    try:
        print(f"  Normalizing new snapshot to raw…")
        normalize_to_raw(new_path, new_raw)
        print(f"  Normalizing base backup to raw…")
        normalize_to_raw(base_path, base_raw)
        print(f"  Computing block-level delta…")
        return create_delta(new_raw, base_raw, delta_path)
    finally:
        for p in (new_raw, base_raw):
            if os.path.exists(p) and p not in (new_path, base_path):
                os.remove(p)


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
    """
    Single-volume incremental backup.
    Downloads the new snapshot + base backup, computes a VSDT block-level delta,
    encrypts and uploads only the delta (much smaller than full backup).
    """
    new_path   = local_path + ".new"
    base_tmp   = local_path + ".base"
    delta_path = local_path + ".delta"
    base_owned = False

    try:
        print(f"[{job_id}] [INCREMENTAL] Downloading new snapshot from Glance…")
        os_svc.download_image(image_id, new_path, conn=conn)
        os_svc.delete_snapshot(image_id, conn=conn)

        print(f"[{job_id}] [INCREMENTAL] Downloading + decrypting base backup…")
        base_path, base_owned = _download_and_decrypt_base(parent_backup, storage_cfg, base_tmp)

        print(f"[{job_id}] [INCREMENTAL] Computing block-level delta…")
        stats = _create_incremental_delta(new_path, base_path, delta_path)
        os.remove(new_path)

        size_gb = get_size_gb(delta_path)
        pct     = round(stats["change_ratio"] * 100, 1)
        print(f"[{job_id}] [INCREMENTAL] Delta: {size_gb:.3f} GB ({pct}% changed blocks)")

        os.rename(delta_path, local_path)
        delta_path = None

        _maybe_encrypt(local_path, job, job_id)
        stored_path = _upload(local_path, job_id, vm_id, job, storage_cfg)
        job.backup_path      = stored_path
        job.backup_type      = "incremental"
        job.parent_backup_id = parent_backup.id
        return size_gb

    finally:
        for p in (delta_path, new_path):
            if p and os.path.exists(p):
                os.remove(p)
        if base_owned and base_tmp and os.path.exists(base_tmp):
            os.remove(base_tmp)


def _do_cbt_backup(db, job, job_id, volume_id, snapshot_name, policy, conn=None):
    """
    CBT backup using Cinder's native incremental backup API.
    Cinder tracks changed blocks at the storage-driver level — no full disk
    download or block comparison needed.
    Falls back to VSDT if Cinder backup service is unavailable.
    """
    from models.backup import BackupJob as BJ

    do_incremental = False
    parent_backup  = None

    if policy and policy.incremental_enabled:
        do_incremental, parent_backup = _should_do_incremental(db, job.vm_id, job.policy_id)
        if do_incremental and (not parent_backup or not getattr(parent_backup, 'cinder_backup_id', None)):
            do_incremental = False  # parent has no Cinder backup — must do full

    try:
        if do_incremental:
            _progress(db, job, 20, "CBT incremental — computing changed blocks via Cinder…")
        else:
            _progress(db, job, 20, "CBT full backup — starting Cinder backup…")

        cinder_bkp = os_svc.create_cinder_backup(
            volume_id, snapshot_name, incremental=do_incremental, conn=conn
        )
    except Exception as e:
        raise RuntimeError(f"Cinder backup service error: {e}. "
                           "Ensure cinder-backup is running. "
                           "Disable CBT in the policy to use VSDT fallback.") from e

    job.cinder_backup_id = cinder_bkp.id
    job.backup_type      = "incremental" if do_incremental else "full"
    job.backup_path      = None   # stored in Cinder backend, not S3
    if do_incremental and parent_backup:
        job.parent_backup_id = parent_backup.id
    db.commit()

    size_gb = float(getattr(cinder_bkp, 'size', 0) or 0)
    _progress(db, job, 90, f"CBT backup complete ({'incremental' if do_incremental else 'full'}) — {size_gb:.1f} GB")
    return size_gb


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
        net_ids = vm.get("network_ids") or []
        job.network_id = net_ids[0] if net_ids else None
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
                # Single volume
                volume_id = volumes[0]
                _policy   = db.query(BackupPolicy).filter(BackupPolicy.id == job.policy_id).first() if job.policy_id else None
                if _policy and getattr(_policy, 'cbt_enabled', False):
                    # ── CBT path: Cinder backup API (no snapshot/Glance needed) ──
                    size_gb = _do_cbt_backup(db, job, job_id, volume_id, snapshot_name, _policy, conn=_conn)
                    _progress(db, job, 90, "Finalizing…")
                    job.size_gb      = size_gb
                    job.status       = "success"
                    job.progress     = 100
                    job.progress_msg = f"Backup complete (CBT {'incremental' if job.backup_type == 'incremental' else 'full'}): {size_gb:.2f} GB"
                    job.completed_at = datetime.utcnow()
                    db.commit()
                    print(f"[{job_id}] Backup complete (CBT {job.backup_type}): {size_gb:.2f} GB")
                    try:
                        from routers.monitoring import send_success_alert
                        send_success_alert(db, job)
                    except Exception:
                        pass
                    return   # early return — skip the rest of run_backup
                do_incremental, parent_backup = _should_do_incremental(
                    db, job.vm_id, job.policy_id
                )
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
