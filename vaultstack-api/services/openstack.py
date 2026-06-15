import openstack
import time
from config import settings

def get_connection(project_id: str = None):
    kwargs = dict(
        auth_url=settings.os_auth_url,
        username=settings.os_username,
        password=settings.os_password,
        user_domain_name=settings.os_user_domain_name,
        project_domain_name=settings.os_project_domain_name,
    )
    if project_id:
        kwargs["project_id"] = project_id
    else:
        kwargs["project_name"] = settings.os_project_name
    return openstack.connect(**kwargs)

def list_vms(project_id=None):
    conn = get_connection()
    try:
        project_map = {p.id: p.name for p in conn.identity.projects()}
    except Exception:
        project_map = {}
    servers = list(conn.compute.servers(all_projects=True, **({"project_id": project_id} if project_id else {})))
    return [
        {
            "id": s.id,
            "name": s.name,
            "status": s.status,
            "flavor": s.flavor.get("original_name", "") if s.flavor else "",
            "volumes": [v["id"] for v in s.attached_volumes],
            "project_id": s.project_id or "",
            "project_name": project_map.get(s.project_id, (s.project_id or "")[:8]),
        }
        for s in servers
    ]

def get_provider_conn(provider_id):
    """Load provider credentials from DB and return an OpenStack connection."""
    from database import SessionLocal
    from models.provider import Provider
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    db = SessionLocal()
    try:
        p = db.query(Provider).filter(Provider.id == provider_id).first()
        if not p:
            return get_connection()
        creds = p.credentials or {}
        conn = openstack.connect(
            auth_url=p.endpoint or creds.get("auth_url"),
            username=creds.get("username"),
            password=creds.get("password"),
            project_name=creds.get("project_name", "admin"),
            project_id=creds.get("project_id") or None,
            user_domain_name=creds.get("user_domain_name", "Default"),
            project_domain_name=creds.get("project_domain_name", "Default"),
            insecure=True,
            verify=False,
        )
        # Patch the underlying requests session so large uploads don't hit
        # SSL record-layer errors (bad_record_mac) on self-signed endpoints
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.poolmanager import PoolManager

            class _InsecureAdapter(HTTPAdapter):
                def init_poolmanager(self, num_pools, maxsize, block=False, **kw):
                    self.poolmanager = PoolManager(
                        num_pools=num_pools, maxsize=maxsize, block=block,
                        cert_reqs="CERT_NONE", assert_hostname=False,
                    )

            adapter = _InsecureAdapter(max_retries=3)
            sess = conn.session.session
            sess.mount("https://", adapter)
            sess.verify = False
        except Exception:
            pass
        return conn
    finally:
        db.close()

def get_vm(vm_id: str, conn=None):
    conn = conn or get_connection()
    server = conn.compute.get_server(vm_id)
    try:
        ports = list(conn.network.ports(device_id=vm_id))
        network_ids = list({p.network_id for p in ports if p.network_id})
    except Exception:
        network_ids = []
    return {
        "id": server.id,
        "name": server.name,
        "status": server.status,
        "project_id": getattr(server, "project_id", None) or getattr(server, "tenant_id", None),
        "volumes": [v["id"] for v in server.attached_volumes],
        "network_ids": network_ids,
    }

def create_vm_snapshot(vm_id: str, snapshot_name: str, conn=None) -> str:
    conn = conn or get_connection()
    # Use raw REST call — SDK's create_server_image internally calls wait_for_image
    # which doesn't exist in this SDK version's image Proxy
    resp = conn.compute.post(
        f"/servers/{vm_id}/action",
        json={"createImage": {"name": snapshot_name, "metadata": {}}},
    )
    # Nova < microversion 2.45: image id is in Location header
    # Nova >= microversion 2.45: image id is in response body
    image_id = None
    try:
        image_id = resp.json().get("image_id")
    except Exception:
        pass
    if not image_id:
        location = resp.headers.get("Location", "")
        image_id = location.rstrip("/").split("/")[-1]
    if not image_id:
        raise RuntimeError("Could not determine snapshot image ID from Nova response")

    # Poll until active — no hard timeout, handles any size
    while True:
        image = conn.image.get_image(image_id)
        if image.status == "active":
            return image_id
        if image.status == "error":
            raise RuntimeError(f"Snapshot entered error state: {image_id}")
        time.sleep(10)

def _wait_for_snapshot(conn, snapshot_id: str):
    while True:
        snap = conn.block_storage.get_snapshot(snapshot_id)
        if snap.status == "available":
            return snap
        if snap.status == "error":
            raise RuntimeError(f"Snapshot {snapshot_id} entered error state")
        time.sleep(10)


def _wait_for_volume(conn, volume_id: str):
    while True:
        vol = conn.block_storage.get_volume(volume_id)
        if vol.status == "available":
            return vol
        if "error" in vol.status:
            raise RuntimeError(f"Volume {volume_id} entered error state: {vol.status}")
        time.sleep(10)


def create_volume_snapshot(volume_id: str, name: str, conn=None) -> str:
    conn = conn or get_connection()
    snapshot = conn.block_storage.create_snapshot(
        volume_id=volume_id,
        name=name,
        force=True,
    )
    _wait_for_snapshot(conn, snapshot.id)
    return snapshot.id


def volume_snapshot_to_glance_image(snapshot_id: str, image_name: str, conn=None) -> str:
    """Create a Glance image from a Cinder snapshot. Returns image_id."""
    conn = conn or get_connection()

    snap = conn.block_storage.get_snapshot(snapshot_id)

    # Create a temporary volume from the snapshot
    temp_vol = conn.block_storage.create_volume(
        size=snap.size,
        snapshot_id=snapshot_id,
        name=f"vaultstack-tmp-{snapshot_id[:8]}",
    )
    _wait_for_volume(conn, temp_vol.id)

    # Upload volume to Glance via Cinder REST API
    resp = conn.block_storage.post(
        f"/volumes/{temp_vol.id}/action",
        json={
            "os-volume_upload_image": {
                "image_name": image_name,
                "disk_format": "qcow2",
                "container_format": "bare",
                "force": True,
            }
        },
    )
    image_id = resp.json()["os-volume_upload_image"]["image_id"]

    # Poll until active — no hard timeout, handles TB-sized volumes
    while True:
        img = conn.image.get_image(image_id)
        if img.status == "active":
            try:
                conn.block_storage.delete_volume(temp_vol.id)
            except Exception:
                pass
            return image_id
        if img.status == "error":
            raise RuntimeError(f"Volume→Image upload failed for image {image_id}")
        time.sleep(10)

def download_image(image_id: str, dest_path: str, conn=None):
    conn = conn or get_connection()
    with open(dest_path, "wb") as f:
        for chunk in conn.image.download_image(image_id, stream=True):
            f.write(chunk)

def delete_snapshot(image_id: str, conn=None):
    conn = conn or get_connection()
    try:
        conn.image.delete_image(image_id)
    except Exception:
        pass

def delete_volume_snapshot(snapshot_id: str, conn=None):
    conn = conn or get_connection()
    conn.block_storage.delete_snapshot(snapshot_id)

def upload_image(name: str, image_path: str, project_id: str = None, conn=None) -> str:
    conn = conn or get_connection(project_id=project_id)
    image = conn.image.create_image(
        name=name,
        disk_format="qcow2",
        container_format="bare",
        visibility="community" if project_id else "private",
    )
    # Use raw PUT to avoid SDK version inconsistencies with upload_image()
    with open(image_path, "rb") as f:
        conn.image.put(
            f"/images/{image.id}/file",
            data=f,
            headers={"Content-Type": "application/octet-stream"},
        )
    return image.id

def create_vm_from_image(name: str, image_id: str, flavor_id: str, network_id: str,
                         project_id: str = None, volume_size: int = None, conn=None) -> str:
    conn = conn or get_connection(project_id=project_id)

    img = conn.image.get_image(image_id)
    # virtual_size is the actual uncompressed disk size — must fit in the volume
    virt_gb = max(1, ((img.virtual_size or 0) + (1 << 30) - 1) >> 30) if img.virtual_size else 0
    vol_size = volume_size or max(img.min_disk or 0, virt_gb, 10)

    server = conn.compute.create_server(
        name=name,
        flavor_id=flavor_id,
        networks=[{"uuid": network_id}],
        block_device_mapping_v2=[{
            "boot_index": "0",
            "uuid": image_id,
            "source_type": "image",
            "destination_type": "volume",
            "volume_size": vol_size,
            "delete_on_termination": True,
        }],
    )
    server_id = server.id if hasattr(server, "id") else str(server)
    while True:
        s = conn.compute.get_server(server_id)
        if s.status == "ACTIVE":
            return server_id
        if s.status == "ERROR":
            fault = getattr(s, "fault", {}) or {}
            raise RuntimeError(f"VM {server_id} entered ERROR state: {fault.get('message', 'unknown')}")
        time.sleep(10)


def create_vm_instant(name: str, image_id: str, flavor_id: str, network_id: str,
                      project_id: str = None, conn=None) -> str:
    """
    Boot VM directly from a Glance image using ephemeral root disk.
    Nova starts the VM immediately — no Cinder volume copy required.
    Returns server_id as soon as Nova accepts the request (may still be BUILD).
    """
    conn = conn or get_connection(project_id=project_id)
    server = conn.compute.create_server(
        name=name,
        flavor_id=flavor_id,
        image_id=image_id,
        networks=[{"uuid": network_id}],
    )
    server_id = server.id if hasattr(server, "id") else str(server)
    # Wait up to 30 s to catch immediate ERROR, then return regardless of BUILD
    for _ in range(6):
        s = conn.compute.get_server(server_id)
        if s.status == "ACTIVE":
            return server_id
        if s.status == "ERROR":
            fault = getattr(s, "fault", {}) or {}
            raise RuntimeError(f"VM {server_id} entered ERROR: {fault.get('message', 'unknown')}")
        time.sleep(5)
    return server_id


def create_volume_from_image(image_id: str, size_gb: int, name: str, project_id: str = None, conn=None) -> str:
    conn = conn or get_connection(project_id=project_id)
    vol = conn.block_storage.create_volume(size=size_gb, name=name, image_id=image_id)
    _wait_for_volume(conn, vol.id)
    return vol.id


def attach_volume_to_vm(vm_id: str, volume_id: str, project_id: str = None, conn=None):
    conn = conn or get_connection(project_id=project_id)
    conn.compute.create_volume_attachment(vm_id, volumeId=volume_id)
    while True:
        v = conn.block_storage.get_volume(volume_id)
        if v.status == "in-use":
            return
        if "error" in v.status:
            raise RuntimeError(f"Volume {volume_id} attach failed: {v.status}")
        time.sleep(5)


def freeze_vm(vm_id: str, conn=None) -> bool:
    """Freeze guest filesystem via Nova os-freeze (requires qemu-guest-agent).
    Returns True if freeze succeeded, False if not supported."""
    conn = conn or get_connection()
    try:
        conn.compute.post(f"/servers/{vm_id}/action", json={"freeze": None})
        return True
    except Exception as e:
        print(f"  freeze not supported for {vm_id}: {e}")
        return False


def unfreeze_vm(vm_id: str, conn=None):
    """Unfreeze guest filesystem via Nova os-unfreeze."""
    conn = conn or get_connection()
    try:
        conn.compute.post(f"/servers/{vm_id}/action", json={"unfreeze": None})
    except Exception as e:
        print(f"  unfreeze failed for {vm_id}: {e}")


def trigger_vm_snapshot(vm_id: str, snapshot_name: str, conn=None) -> str:
    """Send Nova createImage request and return image_id immediately (no wait)."""
    conn = conn or get_connection()
    resp = conn.compute.post(
        f"/servers/{vm_id}/action",
        json={"createImage": {"name": snapshot_name, "metadata": {}}},
    )
    image_id = None
    try:
        image_id = resp.json().get("image_id")
    except Exception:
        pass
    if not image_id:
        location = resp.headers.get("Location", "")
        image_id = location.rstrip("/").split("/")[-1]
    if not image_id:
        raise RuntimeError("Could not determine snapshot image ID from Nova response")
    return image_id


def wait_for_image_active(image_id: str, conn=None) -> str:
    """Poll until Glance image is active."""
    conn = conn or get_connection()
    while True:
        image = conn.image.get_image(image_id)
        if image.status == "active":
            return image_id
        if image.status == "error":
            raise RuntimeError(f"Snapshot entered error state: {image_id}")
        time.sleep(10)


def list_networks(project_id: str = None, conn=None):
    conn = conn or get_connection(project_id=project_id)
    nets = conn.network.networks()
    return [{"id": n.id, "name": n.name} for n in nets]

def list_flavors(conn=None):
    conn = conn or get_connection()
    return [{"id": f.id, "name": f.name, "ram": f.ram, "vcpus": f.vcpus} for f in conn.compute.flavors()]


def create_cinder_backup(volume_id: str, name: str, incremental: bool = False, conn=None):
    """
    Create a Cinder backup of a volume.
    When incremental=True Cinder uses storage-driver CBT (rbd export-diff on Ceph,
    thin-snapshot diff on LVM) — only changed blocks are stored.
    """
    conn = conn or get_connection()
    backup = conn.block_storage.create_backup(
        volume_id=volume_id,
        name=name,
        incremental=incremental,
        force=True,
    )
    while True:
        b = conn.block_storage.get_backup(backup.id)
        if b.status == "available":
            return b
        if b.status == "error":
            raise RuntimeError(f"Cinder backup {backup.id} failed (status=error)")
        time.sleep(10)


def restore_cinder_backup(backup_id: str, conn=None) -> str:
    """Restore a Cinder backup chain to a new volume. Returns new volume_id."""
    conn = conn or get_connection()
    restore = conn.block_storage.restore_backup(backup_id)
    volume_id = restore.get("volume_id") if isinstance(restore, dict) else restore.volume_id
    _wait_for_volume(conn, volume_id)
    return volume_id


def delete_cinder_backup(backup_id: str, conn=None):
    """Delete a Cinder backup record."""
    conn = conn or get_connection()
    try:
        conn.block_storage.delete_backup(backup_id)
    except Exception as e:
        print(f"  Warning: could not delete Cinder backup {backup_id}: {e}")


def create_vm_from_volume(name: str, volume_id: str, flavor_id: str, network_id: str,
                          project_id: str = None, conn=None) -> str:
    """Boot a VM directly from an existing Cinder volume (no image upload needed)."""
    conn = conn or get_connection(project_id=project_id)
    server = conn.compute.create_server(
        name=name,
        flavor_id=flavor_id,
        networks=[{"uuid": network_id}],
        block_device_mapping_v2=[{
            "boot_index": "0",
            "uuid": volume_id,
            "source_type": "volume",
            "destination_type": "volume",
            "delete_on_termination": True,
        }],
    )
    server_id = server.id if hasattr(server, "id") else str(server)
    while True:
        s = conn.compute.get_server(server_id)
        if s.status == "ACTIVE":
            return server_id
        if s.status == "ERROR":
            fault = getattr(s, "fault", {}) or {}
            raise RuntimeError(f"VM {server_id} entered ERROR: {fault.get('message', 'unknown')}")
        time.sleep(10)
