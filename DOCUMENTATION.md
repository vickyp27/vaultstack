# VaultStack — Technical Documentation

## What is VaultStack?

VaultStack is a VM backup and restore solution built on top of OpenStack. It integrates directly into the OpenStack Horizon dashboard and lets users create **Protection Groups** (backup policies), schedule automatic backups, take on-demand backups, and restore VMs to any past recovery point.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        OpenStack Horizon                             │
│              (Project → Data Protection panel)                       │
│              (Admin → VaultStack → Storage Config)                   │
└────────────────────────────┬─────────────────────────────────────────┘
                             │ HTTP (REST API)
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      vaultstack-api  (FastAPI)                       │
│  • /api/v1/policies/       • /api/v1/backups/                        │
│  • /api/v1/restores/       • /api/v1/workloads/                      │
│  • /api/v1/settings/       • /api/v1/dashboard/stats                 │
└───────────┬──────────────────────────────────┬───────────────────────┘
            │ SQLAlchemy (PostgreSQL)           │ Celery tasks (Redis)
            ▼                                  ▼
┌─────────────────────┐          ┌─────────────────────────────────────┐
│     PostgreSQL       │          │    vaultstack-worker  (Celery)      │
│  (jobs, policies,   │          │  • backup_task    • restore_task     │
│   settings, etc.)   │          │  • workload_task  • scheduler_task   │
└─────────────────────┘          └───────────┬─────────────────────────┘
                                             │ OpenStack SDK
                                             ▼
                                 ┌────────────────────────┐
                                 │      OpenStack          │
                                 │  Nova / Cinder / Glance │
                                 └────────────────────────┘
                                             │ backup files (.qcow2)
                                             ▼
                                 ┌────────────────────────┐
                                 │   MinIO / S3 Storage    │
                                 │  (vaultstack-backups)   │
                                 └────────────────────────┘
```

---

## Components

### 1. vaultstack-api (FastAPI)
REST API server. Runs inside Docker. Handles all CRUD operations and queues background tasks via Celery.

- **Port:** 8000
- **Database:** PostgreSQL (models below)
- **Key endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/policies/` | List all Protection Groups |
| POST | `/api/v1/policies/` | Create a Protection Group |
| GET | `/api/v1/policies/{id}` | Get policy details (includes next_run, schedule_description) |
| PUT | `/api/v1/policies/{id}` | Update policy (enable/disable schedule, etc.) |
| DELETE | `/api/v1/policies/{id}` | Delete a Protection Group |
| GET | `/api/v1/backups/` | List all backup jobs |
| POST | `/api/v1/backups/` | Trigger an adhoc backup |
| DELETE | `/api/v1/backups/{id}` | Delete a recovery point |
| GET | `/api/v1/backups/vms/list` | List OpenStack VMs (filtered by project_id) |
| POST | `/api/v1/workloads/` | Trigger a workload backup for a policy |
| GET | `/api/v1/workloads/` | List workload snapshots |
| GET | `/api/v1/restores/` | List restore jobs (filterable by policy_id) |
| POST | `/api/v1/restores/` | Start a restore |
| GET | `/api/v1/settings/storage` | Get S3/storage config |
| PUT | `/api/v1/settings/storage` | Update S3/storage config |
| POST | `/api/v1/settings/storage/test` | Test S3 connection |

---

### 2. vaultstack-worker (Celery Worker)
Background task executor. Runs inside Docker. Handles the actual backup and restore operations by talking to OpenStack APIs.

**Tasks:**
- `tasks.backup_task.run_backup` — performs a single VM backup
- `tasks.restore_task.run_restore` — restores a VM from a backup
- `tasks.workload_task.run_workload_backup` — runs backup for all VMs in a policy
- `tasks.scheduler_task.check_and_trigger_policies` — checks cron schedules every 60s

---

### 3. vaultstack-beat (Celery Beat)
Scheduler process. Runs `check_and_trigger_policies` every 60 seconds to fire scheduled backups.

---

### 4. vaultstack-dashboard (Horizon Plugin)
OpenStack Horizon dashboard plugin. Provides the UI.

**Navigation:**
- **Project → Data Protection** — Protection Groups management (per-project, user-facing)
- **Admin → VaultStack → Storage Config** — S3/MinIO storage configuration (admin-only)

---

### 5. PostgreSQL
Persistent database for all VaultStack state.

**Tables:**

| Table | Purpose |
|-------|---------|
| `backup_policies` | Protection Groups (name, VM list, schedule, retention) |
| `backup_jobs` | Individual VM backup records (status, size, path) |
| `workload_snapshots` | Group backup runs (one per policy trigger) |
| `restore_jobs` | Restore operations (status, progress, new VM ID) |
| `storage_settings` | S3/MinIO configuration |

---

### 6. MinIO / S3
Object storage for backup files. Backup images are stored as `.qcow2` files at path:
```
s3://vaultstack-backups/vaultstack/{vm_id}/{job_id}.qcow2
```

---

## How Backup Works

### Adhoc Backup (manual)
1. User clicks **Adhoc Backup** on the Protection Group detail page
2. Dashboard calls `POST /api/v1/backups/` with `vm_id`
3. API creates a `BackupJob` record (status: `queued`) in PostgreSQL
4. API queues `tasks.backup_task.run_backup` task via Redis → Celery worker picks it up

### Scheduled Backup (automatic)
1. **Celery Beat** fires `check_and_trigger_policies` every 60 seconds
2. For each active policy, it parses the cron schedule using `croniter`
3. If the previous scheduled time was within the last 90 seconds (and no job was already triggered for that slot), it creates a `WorkloadSnapshot` and queues `tasks.workload_task.run_workload_backup`
4. The workload task creates one `BackupJob` per VM in the policy and queues `run_backup` for each

### Backup Execution (inside the worker)

**For Volume-Backed VMs (BFV — Boot from Volume):**
```
VM has Cinder volume
       │
       ▼
Create Cinder snapshot of the volume
       │
       ▼
Convert snapshot → temp volume → Glance image (qcow2)
       │
       ▼
Delete temp volume + Cinder snapshot
       │
       ▼
Download qcow2 from Glance to local disk
       │
       ▼
If S3 configured → Upload to MinIO/S3 → delete local file
       │
       ▼
Update BackupJob: status=success, size_gb, backup_path
```

**For Image-Backed VMs (ephemeral disk):**
```
VM has no Cinder volume
       │
       ▼
Nova snapshot → Glance image (qcow2)
       │
       ▼
Download qcow2 from Glance to local disk
       │
       ▼
If S3 configured → Upload to MinIO/S3 → delete local file
       │
       ▼
Update BackupJob: status=success, size_gb, backup_path
```

---

## How Restore Works

1. User clicks **Restore** on a recovery point in the Protection Group detail page
2. User provides a target VM name (and optionally a network)
3. Dashboard calls `POST /api/v1/restores/` with `backup_job_id` and `target_vm_name`
4. API creates a `RestoreJob` and queues `tasks.restore_task.run_restore`

**Restore Execution (inside the worker):**
```
Read backup_path from BackupJob
       │
       ▼
If S3 path → Download qcow2 from MinIO/S3 to /tmp/
       │
       ▼
Upload qcow2 to Glance (new image)
       │
       ▼
Pick first available flavor + network (or user-specified network)
       │
       ▼
Nova boot-from-image with the Glance image
       │
       ▼
Delete the temporary Glance image
       │
       ▼
Update RestoreJob: status=success, new_vm_id, progress=100%
```

The restored VM is an independent new VM — the original VM is unaffected.

---

## Protection Groups (Policies)

A Protection Group defines **what** to back up and **when**.

| Field | Description |
|-------|-------------|
| Name | Human-readable group name |
| VMs | One or more VMs to protect (scoped to current OpenStack project) |
| Schedule | Cron expression (e.g. `0 2 * * *` = Daily at 2:00 AM) |
| Retention | Days to keep backups. Older backups are auto-deleted |
| Active/Inactive | Controls whether scheduled backups run |

**Supported schedule presets:**

| Cron | Description |
|------|-------------|
| `* * * * *` | Every minute |
| `0 * * * *` | Every hour |
| `0 */6 * * *` | Every 6 hours |
| `0 2 * * *` | Daily at 2:00 AM |
| `0 0 * * *` | Daily at midnight |
| `0 2 * * 0` | Weekly — Sunday at 2:00 AM |
| `0 2 1 * *` | Monthly — 1st at 2:00 AM |
| Custom | Any valid cron expression |

---

## Scheduler Deduplication

To prevent duplicate backups if the Beat process restarts or the worker is slow, the scheduler uses a **90-second dedup window**:

- Before triggering, it checks if a `WorkloadSnapshot` already exists for this policy within ±90 seconds of the scheduled time
- If yes → skip (already triggered)
- If no → create and trigger

---

## Storage Backends

**S3 / MinIO (recommended):**
- Configured via Admin → VaultStack → Storage Config
- Backups are uploaded as `.qcow2` objects to the configured bucket
- Local file is deleted after upload
- Supports any S3-compatible storage (AWS S3, MinIO, Ceph RGW, etc.)

**Local Disk (fallback):**
- Backups saved to `/var/vaultstack/backups/{vm_id}/{job_id}.qcow2` inside Docker volume
- Used when no S3 is configured

---

## Deployment

**Infrastructure (runs on the compute/controller node):**

```bash
cd /opt/vaultstack
docker compose up -d
```

Services started:
- `postgres` — database
- `redis` — message broker
- `minio` — object storage (+ `createbuckets` one-shot setup)
- `vaultstack-api` — REST API on port 8000
- `vaultstack-worker` — Celery worker
- `vaultstack-beat` — Celery Beat scheduler

**Dashboard (installed on the Horizon node):**
```
Plugin path:  /opt/vaultstack/vaultstack-dashboard/
Enabled files: /opt/stack/horizon/openstack_dashboard/enabled/_91-_94_vaultstack*.py
```

After any dashboard change:
```bash
find /opt/vaultstack/vaultstack-dashboard -name '*.pyc' -delete
sudo service apache2 restart
```

After any API/worker code change:
```bash
cd /opt/vaultstack
sudo docker compose restart vaultstack-api vaultstack-worker vaultstack-beat
```

After any `requirements.txt` change:
```bash
sudo docker compose build --no-cache vaultstack-api
sudo docker compose up -d --force-recreate vaultstack-api
```

---

## End-to-End Test — Verified

The following flow was successfully tested:

1. Created VM `data-test-vm` with floating IP `172.24.4.66`
2. SSH'd into VM, wrote test files:
   - `/tmp/testfile.txt` — "VaultStack Backup Test ... This data should survive backup and restore!"
   - `/tmp/secret.txt` — "SECRET_DATA_VAULTSTACK_12345"
3. Created Protection Group `data-test-policy` for this VM
4. Triggered adhoc backup → completed, `0.03 GB`, stored at `s3://vaultstack-backups/vaultstack/{vm_id}/{job_id}.qcow2`
5. Restored from that backup → new VM `data-test-restored` created
6. Assigned floating IP `172.24.4.122` to restored VM
7. Connected via `virsh console`, logged in as `cirros/gocubsgo`
8. Confirmed both files present with identical content ✓

---

## Project Structure

```
vaultstack/
├── docker-compose.yml
├── vaultstack-api/              # FastAPI REST API
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── backup.py
│   │   ├── policy.py
│   │   ├── restore.py
│   │   ├── workload.py
│   │   └── settings.py
│   ├── routers/                 # API route handlers
│   │   ├── backups.py
│   │   ├── policies.py
│   │   ├── restores.py
│   │   ├── workloads.py
│   │   ├── settings.py
│   │   └── dashboard.py
│   ├── services/
│   │   ├── openstack.py         # Nova/Cinder/Glance operations
│   │   └── storage.py           # S3/local file operations
│   └── requirements.txt
│
├── vaultstack-worker/           # Celery worker + Beat
│   ├── celery_app.py            # Celery config + Beat schedule
│   ├── tasks/
│   │   ├── backup_task.py       # Single VM backup
│   │   ├── restore_task.py      # VM restore
│   │   ├── workload_task.py     # Multi-VM policy backup
│   │   └── scheduler_task.py   # Cron-based policy trigger
│   └── requirements.txt
│
└── vaultstack-dashboard/        # Horizon plugin
    └── vaultstack_dashboard/
        ├── backup/              # Project-level panel
        │   ├── panel.py
        │   ├── urls.py
        │   ├── views.py
        │   ├── api.py           # HTTP client to vaultstack-api
        │   ├── forms.py
        │   ├── tables.py
        │   └── templates/backup/
        ├── storage_admin/       # Admin-level panel (S3 config)
        │   ├── panel.py
        │   ├── urls.py
        │   └── templates/storage_admin/
        └── enabled/             # Horizon panel injection
            ├── _91_vaultstack_project_group.py
            ├── _92_vaultstack_project_backup.py
            ├── _93_vaultstack_admin_group.py
            └── _94_vaultstack_admin_panel.py
```
