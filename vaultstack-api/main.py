import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from database import Base, engine
from routers import backups, policies, restores, dashboard, settings, workloads, auth, monitoring, tenant_storage, providers

# Import all models so Base.metadata.create_all picks them up
import models.backup    # noqa
import models.policy    # noqa
import models.restore   # noqa
import models.settings  # noqa
import models.workload  # noqa
import models.alert          # noqa
import models.tenant_storage  # noqa
import models.provider        # noqa

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="VaultStack API",
    description="OpenStack Backup Solution",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(backups.router)
app.include_router(policies.router)
app.include_router(restores.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(workloads.router)
app.include_router(monitoring.router)
app.include_router(tenant_storage.router)
app.include_router(providers.router)


@app.on_event("startup")
def seed_default_provider():
    import os
    from database import SessionLocal
    from models.provider import Provider
    db = SessionLocal()
    try:
        if db.query(Provider).count() == 0:
            auth_url = os.getenv("OS_AUTH_URL", "")
            if auth_url:
                p = Provider(
                    id=__import__('uuid').uuid4(),
                    name="OpenStack (Default)",
                    type="openstack",
                    endpoint=auth_url,
                    credentials={
                        "username": os.getenv("OS_USERNAME", "admin"),
                        "password": os.getenv("OS_PASSWORD", ""),
                        "project_name": os.getenv("OS_PROJECT_NAME", "admin"),
                        "user_domain_name": os.getenv("OS_USER_DOMAIN_NAME", "Default"),
                        "project_domain_name": os.getenv("OS_PROJECT_DOMAIN_NAME", "Default"),
                    },
                    status="unknown",
                )
                db.add(p)
                db.commit()
    except Exception:
        pass
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "vaultstack-api"}

@app.get("/portal", include_in_schema=False)
def portal_redirect():
    return RedirectResponse(url="/portal/")

# Serve the portal UI — must be mounted after all API routes
_portal_dir = os.path.join(os.path.dirname(__file__), "portal")
if os.path.isdir(_portal_dir):
    app.mount("/portal", StaticFiles(directory=_portal_dir, html=True), name="portal")
