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
    if project_id:
        servers = conn.compute.servers(all_projects=True, project_id=project_id)
    else:
        servers = conn.compute.servers()
    return [
        {
            "id": s.id,
            "name": s.name,
            "status": s.status,
            "flavor": s.flavor.get("original_name", ""),
            "volumes": [v["id"] for v in s.attached_volumes],
        }
        for s in servers
    ]

def get_vm(vm_id: str):
    conn = get_connection()
    server = conn.compute.get_server(vm_id)
    return {
        "id": server.id,
        "name": server.name,
        "status": server.status,
        "project_id": getattr(server, "project_id", None) or getattr(server, "tenant_id", None),
        "volumes": [v["id"] for v in server.attached_volumes],
    }

def create_vm_snapshot(vm_id: str, snapshot_name: str) -> str:
    conn = get_connection()
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

    # Poll until active
    for _ in range(120):
        image = conn.image.get_image(image_id)
        if image.status == "active":
            return image_id
        if image.status == "error":
            raise RuntimeError(f"Snapshot entered error state: {image_id}")
        time.sleep(5)
    raise TimeoutError(f"Snapshot {image_id} did not become active within 10 minutes")

def _wait_for_snapshot(conn, snapshot_id: str, timeout: int = 300):
    for _ in range(timeout // 5):
        snap = conn.block_storage.get_snapshot(snapshot_id)
        if snap.status == "available":
            return snap
        if snap.status == "error":
            raise RuntimeError(f"Snapshot {snapshot_id} entered error state")
        time.sleep(5)
    raise TimeoutError(f"Snapshot {snapshot_id} not available after {timeout}s")


def _wait_for_volume(conn, volume_id: str, timeout: int = 300):
    for _ in range(timeout // 5):
        vol = conn.block_storage.get_volume(volume_id)
        if vol.status == "available":
            return vol
        if "error" in vol.status:
            raise RuntimeError(f"Volume {volume_id} entered error state: {vol.status}")
        time.sleep(5)
    raise TimeoutError(f"Volume {volume_id} not available after {timeout}s")


def create_volume_snapshot(volume_id: str, name: str) -> str:
    conn = get_connection()
    snapshot = conn.block_storage.create_snapshot(
        volume_id=volume_id,
        name=name,
        force=True,
    )
    _wait_for_snapshot(conn, snapshot.id)
    return snapshot.id


def volume_snapshot_to_glance_image(snapshot_id: str, image_name: str) -> str:
    """Create a Glance image from a Cinder snapshot. Returns image_id."""
    conn = get_connection()

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

    # Wait for image to become active in Glance
    for _ in range(120):
        img = conn.image.get_image(image_id)
        if img.status == "active":
            try:
                conn.block_storage.delete_volume(temp_vol.id)
            except Exception:
                pass
            return image_id
        if img.status == "error":
            raise RuntimeError(f"Volume→Image upload failed for image {image_id}")
        time.sleep(5)

    raise TimeoutError(f"Volume image {image_id} did not become active in time")

def download_image(image_id: str, dest_path: str):
    conn = get_connection()
    with open(dest_path, "wb") as f:
        for chunk in conn.image.download_image(image_id):
            f.write(chunk)

def delete_snapshot(image_id: str):
    conn = get_connection()
    conn.image.delete_image(image_id)

def delete_volume_snapshot(snapshot_id: str):
    conn = get_connection()
    conn.block_storage.delete_snapshot(snapshot_id)

def upload_image(name: str, image_path: str, project_id: str = None) -> str:
    conn = get_connection(project_id=project_id)
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

def create_vm_from_image(name: str, image_id: str, flavor_id: str, network_id: str, project_id: str = None) -> str:
    conn = get_connection(project_id=project_id)

    # Get image min_disk so we can size the boot volume correctly
    img = conn.image.get_image(image_id)
    vol_size = max(img.min_disk or 0, 10)  # at least 10 GB

    # Boot-from-volume: creates a Cinder volume from the image and boots from it.
    # This bypasses the flavor's ephemeral disk size constraint entirely.
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
    for _ in range(120):
        s = conn.compute.get_server(server_id)
        if s.status == "ACTIVE":
            return server_id
        if s.status == "ERROR":
            fault = getattr(s, "fault", {}) or {}
            raise RuntimeError(f"VM {server_id} entered ERROR state: {fault.get('message', 'unknown')}")
        time.sleep(5)
    raise TimeoutError(f"VM {server_id} did not become ACTIVE within 10 minutes")

def list_networks(project_id: str = None):
    conn = get_connection(project_id=project_id)
    nets = conn.network.networks()
    return [{"id": n.id, "name": n.name} for n in nets]

def list_flavors():
    conn = get_connection()
    return [{"id": f.id, "name": f.name, "ram": f.ram, "vcpus": f.vcpus} for f in conn.compute.flavors()]
