import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from database import Base, engine
from routers import backups, policies, restores, dashboard, settings, workloads, auth, monitoring, tenant_storage

# Import all models so Base.metadata.create_all picks them up
import models.backup    # noqa
import models.policy    # noqa
import models.restore   # noqa
import models.settings  # noqa
import models.workload  # noqa
import models.alert          # noqa
import models.tenant_storage  # noqa

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
