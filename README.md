# VaultStack

**Open-source VM backup & restore platform for OpenStack.**

VaultStack gives OpenStack operators scheduled backups, on-demand snapshots, one-click restores, S3 storage, multi-tenancy, and a full operations portal — all without touching your cloud's core infrastructure.

---

## Features

- **Protection Groups** — group VMs into policies with cron schedules (hourly → monthly) and configurable retention
- **Scheduled & Adhoc Backups** — Beat-driven scheduler fires automatically; one-click manual backups from the portal or Horizon
- **One-Click Restore** — restore any VM to any recovery point, choose flavor and target name, get a brand-new VM in minutes
- **Volume-backed VM support** — handles both Nova (image-backed) and Cinder BFV instances correctly
- **S3 / MinIO Storage** — backups uploaded as `.qcow2` objects; local disk fallback included
- **Multi-tenancy** — each OpenStack project gets its own S3 bucket config; backup paths are project-prefixed for full isolation
- **React Operations Portal** — JWT-authenticated SPA with live job tracking, restore modal with flavor picker, monitoring dashboards
- **OpenStack Horizon Plugin** — native Data Protection panel under each project; project-scoped so users only see their own data
- **Monitoring & Alerts** — email (SMTP) + Slack webhook alerts on backup success/failure; 7-day trend charts; alert log
- **Workload Snapshots** — snapshot all VMs in a policy in one atomic operation

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│            React Portal  /portal/                │   JWT auth, live refresh
│            Horizon Plugin  /dashboard/           │   per-project scoped
└──────────────────────┬───────────────────────────┘
                       │ REST
                       ▼
┌──────────────────────────────────────────────────┐
│            vaultstack-api  (FastAPI)             │   port 8000
│  policies · backups · restores · workloads       │
│  monitoring · tenant-storage · dashboard stats   │
└────────────┬─────────────────────┬───────────────┘
             │ PostgreSQL          │ Celery / Redis
             ▼                    ▼
┌────────────────┐   ┌────────────────────────────┐
│  PostgreSQL 15 │   │  vaultstack-worker (Celery) │
│                │   │  backup · restore · workload│
└────────────────┘   │  scheduler (Beat, 60s tick) │
                     └──────────────┬──────────────┘
                                    │ OpenStack SDK
                                    ▼
                     ┌──────────────────────────────┐
                     │  OpenStack                   │
                     │  Nova · Cinder · Glance       │
                     └──────────────┬───────────────┘
                                    │ .qcow2 images
                                    ▼
                     ┌──────────────────────────────┐
                     │  MinIO / S3                  │
                     │  bucket/project-id/vm-id/    │
                     └──────────────────────────────┘
```

---

## Stack

| Layer | Technology |
|---|---|
| API | Python 3.11 · FastAPI · SQLAlchemy · Pydantic v2 |
| Worker | Celery 5 · Redis · croniter |
| Database | PostgreSQL 15 |
| Storage | MinIO (S3-compatible) · boto3 |
| OpenStack | openstacksdk (Nova, Cinder, Glance) |
| Portal | React 18 · Vite · Tailwind CSS · Recharts |
| Horizon Plugin | Django · OpenStack Horizon |
| Auth | PyJWT (portal) · OpenStack session (Horizon) |
| Infrastructure | Docker Compose |

---

## Project Structure

```
vaultstack/
├── docker-compose.yml
├── vaultstack-api/              # FastAPI REST API
│   ├── main.py
│   ├── models/                  # SQLAlchemy models
│   ├── routers/                 # Route handlers
│   └── services/                # OpenStack + S3 clients
│
├── vaultstack-worker/           # Celery worker + Beat scheduler
│   ├── celery_app.py
│   └── tasks/
│       ├── backup_task.py
│       ├── restore_task.py
│       ├── workload_task.py
│       └── scheduler_task.py
│
├── vaultstack-portal/           # React SPA
│   └── src/
│       ├── pages/               # Overview, Jobs, Restores, Policies,
│       │                        # Workloads, Monitoring, TenantStorage
│       ├── components/          # Sidebar, RestoreModal
│       └── hooks/useData.js
│
└── vaultstack-dashboard/        # Horizon plugin
    └── vaultstack_dashboard/
        ├── backup/              # Project panel (Data Protection)
        └── storage_admin/       # Admin panel (S3 config)
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- OpenStack environment (with Nova, Cinder, Glance)
- An S3-compatible bucket (MinIO included)

### 1. Clone & configure

```bash
git clone https://github.com/vickyp27/vaultstack.git
cd vaultstack
```

Edit `docker-compose.yml` — set your OpenStack credentials:
```yaml
OS_AUTH_URL: http://<your-openstack-ip>/identity
OS_USERNAME: admin
OS_PASSWORD: <your-password>
OS_PROJECT_NAME: admin
```

### 2. Start the stack

```bash
docker compose up -d
```

Services started: `postgres`, `redis`, `minio`, `vaultstack-api` (port 8000), `vaultstack-worker`, `vaultstack-beat`.

### 3. Access the portal

```
http://<host>:8000/portal/
```

Default credentials: `admin / admin` (change via API).

API docs (Swagger): `http://<host>:8000/docs`

### 4. Install the Horizon plugin (optional)

```bash
cp -r vaultstack-dashboard/vaultstack_dashboard /path/to/horizon/
cp vaultstack-dashboard/enabled/*.py /path/to/horizon/openstack_dashboard/enabled/
sudo systemctl restart apache2
```

---

## How Backup Works

**Volume-backed VMs (BFV):**
`Cinder snapshot → temp volume → Glance image → download .qcow2 → upload to S3`

**Image-backed VMs (ephemeral):**
`Nova snapshot → Glance image → download .qcow2 → upload to S3`

Both paths clean up all temporary Glance images and Cinder snapshots after the backup completes.

## How Restore Works

`Read S3 path → download .qcow2 → upload to Glance → Nova boot → delete temp image`

The restored VM is completely independent. The original VM is unaffected.

---

## Multi-Tenancy

Each OpenStack project can have its own S3 bucket:

- Configure via **Admin → VaultStack → Tenant Storage** (Horizon) or the React portal
- The worker checks for a project-specific config before falling back to the global S3 config
- Backup paths are project-prefixed: `s3://bucket/<project-id-prefix>/<vm-id>/<job-id>.qcow2`
- Horizon Protection Groups are scoped per project — users only see their own data

---

## Monitoring & Alerts

Configure in the React portal under **Monitoring**:

- **Email** — SMTP credentials + recipient list
- **Slack** — incoming webhook URL
- Alerts fire on backup **failure** and/or **success** (configurable)
- 7-day backup trend chart + recent failure log

---

## Verified Test

Full end-to-end test passed:
1. Created a VM, wrote test files to it
2. Took a backup → stored in MinIO as `.qcow2`
3. Restored to a new VM → SSH'd in → both test files present with identical content ✓

---

## License

MIT
