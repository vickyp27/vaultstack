# VaultStack

**Open-source VM backup & restore platform for OpenStack.**

VaultStack gives OpenStack operators enterprise-grade backup, restore, and compliance — scheduled policies, incremental backups, instant recovery, file-level restore, WORM locks, SLA dashboards, and audit logs — all without touching your cloud's core infrastructure.

---

## Features

- **Protection Groups** — group VMs into policies with cron schedules, retention, SLA thresholds, and per-VM overrides
- **Full + Incremental + CBT Backups** — full disk, VSDT incremental (qemu-img delta), or Cinder native CBT for minimum backup size
- **AES-256-CTR Encryption** — backups encrypted at rest before upload; auto-decrypted on restore
- **Multi-volume backup** — tar-based backup for VMs with multiple Cinder volumes; app-consistent freeze/thaw
- **GFS Retention** — Grandfather-Father-Son daily/weekly/monthly tiers
- **Per-VM Retention Override** — individual retention per VM within a policy
- **WORM / Retention Lock** — immutable lock on any backup; delete blocked (HTTP 423) until expiry
- **Full Restore** — restore to a new VM with custom name, flavor, and network
- **Instant Restore** — boot directly from Glance image in ~1–2 min
- **Restore to Original VM** — stop + delete original, replace with restored VM
- **Single Disk Restore** — restore only selected volume indices from a multi-volume backup
- **File-Level Restore (FLR)** — browse and download individual files from a backup as ZIP (libguestfs)
- **SLA Compliance Dashboard** — compliant / at-risk / breach per VM; configurable hour threshold
- **Test Restore Automation** — scheduled auto-test restore, records RTO in seconds
- **Audit Log** — all write actions recorded with timestamp, actor, and details
- **Multi-provider OpenStack** — multiple OpenStack clouds in one VaultStack instance
- **Multi-tenant S3 isolation** — per-project S3 bucket and credentials
- **Swift Storage** — OpenStack Swift backend in addition to S3/MinIO and local disk
- **Policy delete guard** — cannot delete a policy with active running/queued jobs
- **React Operations Portal** — JWT-authenticated SPA with live job tracking, all features accessible
- **OpenStack Horizon Plugin** — native Data Protection panel per project
- **Monitoring & Alerts** — email + Slack on backup failure/success; daily report; 7-day trend chart

See [FEATURES.md](./FEATURES.md) for the complete feature reference.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│             React Portal  :3000                        │  JWT auth, live refresh
│             Horizon Plugin  /dashboard/                │  per-project scoped
└──────────────────────┬─────────────────────────────────┘
                       │ REST
                       ▼
┌────────────────────────────────────────────────────────┐
│             vaultstack-api  (FastAPI)  :8000           │
│  policies · backups · restores · sla · audit           │
│  providers · monitoring · tenant-storage · settings    │
└────────────┬───────────────────────┬───────────────────┘
             │ PostgreSQL            │ Celery / Redis
             ▼                       ▼
┌──────────────────┐   ┌─────────────────────────────────┐
│  PostgreSQL 15   │   │  vaultstack-worker (Celery)      │
│                  │   │  backup · restore · retention    │
└──────────────────┘   │  test-restore · file-restore     │
                       │  scheduler (Beat, 60s tick)      │
                       └──────────────┬──────────────────┘
                                      │ OpenStack SDK
                                      ▼
                       ┌─────────────────────────────────┐
                       │  OpenStack                      │
                       │  Nova · Cinder · Glance         │
                       └──────────────┬──────────────────┘
                                      │ .qcow2 / .tar
                                      ▼
                       ┌─────────────────────────────────┐
                       │  Storage Backend                │
                       │  MinIO / S3 · Swift · Local     │
                       └─────────────────────────────────┘
```

---

## Stack

| Layer | Technology |
|---|---|
| API | Python 3.11 · FastAPI · SQLAlchemy · Pydantic v2 |
| Worker | Celery 5 · Redis · croniter · libguestfs |
| Database | PostgreSQL 15 |
| Storage | MinIO (S3-compatible) · boto3 · python-swiftclient |
| OpenStack | openstacksdk (Nova, Cinder, Glance, Keystone) |
| Encryption | cryptography (AES-256-CTR) |
| Portal | React 18 · Vite · Tailwind CSS · Recharts |
| Horizon Plugin | Django · OpenStack Horizon |
| Auth | PyJWT |
| Infrastructure | Docker Compose |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- OpenStack (Nova, Cinder, Glance)
- S3-compatible storage (MinIO bundled) or OpenStack Swift

### 1. Clone & configure

```bash
git clone https://github.com/vickyp27/vaultstack.git
cd vaultstack
```

Edit `docker-compose.yml` — set your OpenStack credentials:

```yaml
OS_AUTH_URL: http://<openstack-ip>/identity
OS_USERNAME: admin
OS_PASSWORD: <password>
OS_PROJECT_NAME: admin
BACKUP_ENCRYPTION_KEY: <your-strong-secret>   # optional — enables AES-256 encryption
```

### 2. Start

```bash
docker compose up -d
```

Services: `postgres`, `redis`, `minio`, `vaultstack-api` (:8000), `vaultstack-worker`, `vaultstack-beat`.

### 3. Access

| URL | Description |
|---|---|
| `http://<host>:3000` | React Operations Portal |
| `http://<host>:8000/docs` | Swagger API docs |

Default portal credentials: `vaultadmin / VaultStack@2025`

### 4. Install Horizon Plugin (optional)

```bash
# DevStack
cd vaultstack-dashboard
bash install_on_devstack.sh

# Kolla Ansible
bash install_on_kolla.sh

# Manual
pip install -e vaultstack-dashboard/
echo "VAULTSTACK_API_URL = 'http://<host>:8000'" >> local_settings.py
cp vaultstack_dashboard/enabled/_90_vaultstack.py <horizon>/enabled/
python manage.py collectstatic --noinput && sudo systemctl restart apache2
```

After install: **Project → Data Protection** in Horizon.

---

## How Backup Works

**Volume-backed VM (single volume):**
`Cinder snapshot → temp volume → Glance image → download .qcow2 → encrypt → upload to S3`

**Volume-backed VM (multi-volume):**
`Cinder snapshots (all volumes) → Glance images → download each → pack into .tar → encrypt → upload`

**Image-backed VM (ephemeral):**
`Nova snapshot → Glance image → download .qcow2 → encrypt → upload to S3`

**CBT (Cinder native):**
`Cinder Backup API → incremental backup export → encrypt → upload`

All paths clean up temporary Glance images and Cinder snapshots after upload.

## How Restore Works

**Full / Instant:**
`Download from storage → decrypt → upload to Glance → Nova boot → cleanup`

**Incremental:**
`Download base + delta → decrypt → qemu-img flatten → upload → Nova boot`

**File-Level Restore:**
`Download → decrypt → libguestfs mount → browse/extract → ZIP → browser download`

---

## Security

- JWT-protected portal (12hr tokens)
- AES-256-CTR backup encryption — key from env only, never stored in DB
- WORM locks — immutable until expiry, respected by both manual delete and auto-retention
- Per-project storage isolation
- Full audit log of all write actions

---

## License

MIT
