import requests
from django.conf import settings

VAULTSTACK_API = getattr(settings, "VAULTSTACK_API_URL", "http://localhost:8000")


def _get(path, params=None):
    resp = requests.get(f"{VAULTSTACK_API}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _post(path, data=None):
    resp = requests.post(f"{VAULTSTACK_API}{path}", json=data or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _put(path, data):
    resp = requests.put(f"{VAULTSTACK_API}{path}", json=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _delete(path):
    resp = requests.delete(f"{VAULTSTACK_API}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


# Dashboard
def get_stats(project_id=None):
    params = {"project_id": project_id} if project_id else None
    return _get("/api/v1/dashboard/stats", params=params)


# Backups
def list_backups():
    return _get("/api/v1/backups/")


def get_backup(backup_id):
    return _get(f"/api/v1/backups/{backup_id}")


def create_backup(vm_id, policy_id=None):
    return _post("/api/v1/backups/", {"vm_id": vm_id, "policy_id": policy_id})


def delete_backup(backup_id):
    return _delete(f"/api/v1/backups/{backup_id}")


def list_vms(project_id=None):
    params = {"project_id": project_id} if project_id else None
    return _get("/api/v1/backups/vms/list", params=params)


def list_flavors():
    return _get("/api/v1/restores/flavors")


# Policies
def list_policies(project_id=None):
    params = {"project_id": project_id} if project_id else None
    return _get("/api/v1/policies/", params=params)


def create_policy(name, vm_ids, schedule, retention_days,
                  incremental_enabled=False, full_backup_interval=6,
                  project_id=None):
    return _post("/api/v1/policies/", {
        "name": name,
        "vm_ids": vm_ids,
        "schedule": schedule,
        "retention_days": retention_days,
        "incremental_enabled": incremental_enabled,
        "full_backup_interval": full_backup_interval,
        "project_id": project_id,
    })


def get_policy(policy_id):
    return _get(f"/api/v1/policies/{policy_id}")


def delete_policy(policy_id):
    return _delete(f"/api/v1/policies/{policy_id}")


def toggle_policy(policy_id, is_active):
    return _put(f"/api/v1/policies/{policy_id}", {"is_active": is_active})


# Restores
def list_restores(policy_id=None):
    params = {"policy_id": policy_id} if policy_id else None
    return _get("/api/v1/restores/", params=params)


def create_restore(backup_job_id, target_vm_name, flavor_id=None, target_network_id=None):
    return _post("/api/v1/restores/", {
        "backup_job_id": backup_job_id,
        "target_vm_name": target_vm_name,
        "flavor_id": flavor_id,
        "target_network_id": target_network_id,
    })


# Workloads
def list_workloads():
    return _get("/api/v1/workloads/")


def get_workload(workload_id):
    return _get(f"/api/v1/workloads/{workload_id}")


def trigger_workload_backup(policy_id):
    return _post("/api/v1/workloads/", {"policy_id": policy_id})


def delete_workload(workload_id):
    return _delete(f"/api/v1/workloads/{workload_id}")


# Storage settings
def get_storage_settings():
    return _get("/api/v1/settings/storage")


def update_storage_settings(data):
    return _put("/api/v1/settings/storage", data)


def test_s3_connection():
    return _post("/api/v1/settings/storage/test")
