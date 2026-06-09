from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models.provider import Provider
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


class ProviderCreate(BaseModel):
    name: str
    type: str
    endpoint: Optional[str] = None
    credentials: Optional[dict] = {}


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    endpoint: Optional[str] = None
    credentials: Optional[dict] = None


def _mask(creds: dict) -> dict:
    out = dict(creds or {})
    for k in ("password", "secret_key", "token"):
        if k in out and out[k]:
            out[k] = "***"
    return out


def _to_dict(p: Provider) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "type": p.type,
        "endpoint": p.endpoint,
        "credentials": _mask(p.credentials or {}),
        "status": p.status,
        "status_msg": p.status_msg,
        "created_at": str(p.created_at),
        "last_tested": str(p.last_tested) if p.last_tested else None,
    }


@router.get("/")
def list_providers(db: Session = Depends(get_db)):
    return [_to_dict(p) for p in db.query(Provider).order_by(Provider.created_at).all()]


@router.post("/")
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)):
    p = Provider(
        id=uuid.uuid4(),
        name=body.name,
        type=body.type,
        endpoint=body.endpoint,
        credentials=body.credentials or {},
        status="unknown",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_dict(p)


@router.put("/{provider_id}")
def update_provider(provider_id: str, body: ProviderUpdate, db: Session = Depends(get_db)):
    p = db.query(Provider).filter(Provider.id == uuid.UUID(provider_id)).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    if body.name is not None:
        p.name = body.name
    if body.endpoint is not None:
        p.endpoint = body.endpoint
    if body.credentials is not None:
        existing = dict(p.credentials or {})
        for k, v in body.credentials.items():
            if v != "***":
                existing[k] = v
        p.credentials = existing
    p.status = "unknown"
    db.commit()
    return _to_dict(p)


@router.delete("/{provider_id}")
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    p = db.query(Provider).filter(Provider.id == uuid.UUID(provider_id)).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    db.delete(p)
    db.commit()
    return {"deleted": provider_id}


@router.post("/{provider_id}/test")
def test_provider(provider_id: str, db: Session = Depends(get_db)):
    p = db.query(Provider).filter(Provider.id == uuid.UUID(provider_id)).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    ok, msg, count = _run_test(p)
    p.status = "connected" if ok else "error"
    p.status_msg = msg
    p.last_tested = datetime.utcnow()
    db.commit()
    return {"ok": ok, "message": msg, "workload_count": count}


@router.get("/{provider_id}/workloads")
def list_workloads(provider_id: str, db: Session = Depends(get_db)):
    p = db.query(Provider).filter(Provider.id == uuid.UUID(provider_id)).first()
    if not p:
        raise HTTPException(404, "Provider not found")
    try:
        return _get_workloads(p)
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Provider implementations ──────────────────────────────────────────────────

def _run_test(p: Provider):
    try:
        if p.type == "openstack":
            return _test_openstack(p)
        if p.type == "kubernetes":
            return _test_kubernetes(p)
        return True, f"{p.type.title()} provider saved (live test coming soon)", 0
    except Exception as e:
        return False, str(e), 0


def _get_workloads(p: Provider):
    if p.type == "openstack":
        return _workloads_openstack(p)
    if p.type == "kubernetes":
        return _workloads_kubernetes(p)
    return []


def _os_conn(p: Provider):
    import openstack
    creds = p.credentials or {}
    return openstack.connect(
        auth_url=p.endpoint or creds.get("auth_url"),
        username=creds.get("username"),
        password=creds.get("password"),
        project_name=creds.get("project_name", "admin"),
        user_domain_name=creds.get("user_domain_name", "Default"),
        project_domain_name=creds.get("project_domain_name", "Default"),
    )


def _test_openstack(p: Provider):
    conn = _os_conn(p)
    servers = list(conn.compute.servers(all_projects=True))
    n = len(servers)
    return True, f"Connected — {n} VM(s) found", n


def _workloads_openstack(p: Provider):
    conn = _os_conn(p)
    servers = list(conn.compute.servers(all_projects=True))
    return [
        {
            "id": s.id,
            "name": s.name,
            "status": s.status,
            "type": "vm",
            "detail": s.flavor.get("original_name", "") if s.flavor else "",
        }
        for s in servers
    ]


def _k8s_client(p: Provider):
    from kubernetes import client as k8s
    creds = p.credentials or {}
    cfg = k8s.Configuration()
    cfg.host = p.endpoint or creds.get("api_url", "")
    cfg.verify_ssl = False
    if creds.get("token"):
        cfg.api_key = {"authorization": f"Bearer {creds['token']}"}
    return k8s.ApiClient(cfg)


def _test_kubernetes(p: Provider):
    from kubernetes import client as k8s
    api = k8s.CoreV1Api(_k8s_client(p))
    ns = api.list_namespace()
    n = len(ns.items)
    return True, f"Connected — {n} namespace(s) found", n


def _workloads_kubernetes(p: Provider):
    from kubernetes import client as k8s
    api_client = _k8s_client(p)
    core = k8s.CoreV1Api(api_client)
    apps = k8s.AppsV1Api(api_client)
    out = []
    for dep in apps.list_deployment_for_all_namespaces().items:
        out.append({
            "id": f"{dep.metadata.namespace}/{dep.metadata.name}",
            "name": dep.metadata.name,
            "status": "ACTIVE" if (dep.status.available_replicas or 0) > 0 else "DEGRADED",
            "type": "deployment",
            "detail": f"ns:{dep.metadata.namespace}  replicas:{dep.spec.replicas}",
        })
    for pvc in core.list_persistent_volume_claim_for_all_namespaces().items:
        storage = ""
        if pvc.spec.resources and pvc.spec.resources.requests:
            storage = pvc.spec.resources.requests.get("storage", "")
        out.append({
            "id": f"{pvc.metadata.namespace}/{pvc.metadata.name}",
            "name": pvc.metadata.name,
            "status": pvc.status.phase or "Unknown",
            "type": "pvc",
            "detail": f"ns:{pvc.metadata.namespace}  size:{storage}",
        })
    return out
