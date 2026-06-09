# VaultStack — Feature Reference

Complete feature list for VaultStack, the open-source VM backup & restore platform for OpenStack.

---

## Protection Groups (Backup Policies)

- Create named policies that group one or more VMs
- Per-policy **cron schedule** — hourly, daily, weekly, monthly, or custom cron expression
- Per-policy **retention** — configurable in days (default 30); expired recovery points are auto-deleted
- **Pause / Resume** — suspend a policy without deleting it
- **Edit in-place** — change VMs, schedule, retention, or backup type at any time
- **Delete with guard** — blocked if the policy has active (running/queued) jobs
- Available in both the React portal and the Horizon dashboard

---

## Backup Engine

### Full Backup
- Nova snapshot (image-backed VMs) or Cinder snapshot → Glance image path (volume-backed VMs)
- Downloads the snapshot as a `.qcow2` file
- Uploads to S3/MinIO (or retains on local disk as fallback)
- All temporary Glance images and Cinder snapshots are cleaned up after each run

### Incremental Backup
- Toggle **Enable Incremental Backup** per policy
- Stores only changed blocks since the last full backup using `qemu-img rebase`
- Configurable **full backup interval** (2–30 runs) — after N incremental runs a new full resets the chain
- Incremental backups are typically **70–90% smaller** than full backups
- Restore automatically merges the delta + base before booting the VM

### Backup Types at a Glance

| Type | What is stored | Storage impact |
|---|---|---|
| Full | Complete disk image | High |
| Incremental | Changed blocks only | Low (70–90% savings) |

---

## AES-256 Encryption

- Backups are encrypted with **AES-256-CTR** before upload to S3
- Streaming encryption — no full file copy needed, works on large disks
- Each backup gets a unique random 16-byte IV prepended to the file
- Encryption key is supplied via the `BACKUP_ENCRYPTION_KEY` environment variable
- Encrypted backups are marked with `encrypted = true` in the database
- Restore pipeline detects the flag and decrypts automatically before use
- Purple **🔒 AES-256** badge shown in both the Horizon backup table and policy detail page
- Encryption is transparent — existing unencrypted backups continue to restore normally

**To enable:**
```bash
# In docker-compose.yml or as an env var
BACKUP_ENCRYPTION_KEY=your-strong-secret-key
```

---

## Scheduling

- Celery Beat scheduler ticks every **60 seconds** and evaluates all active policies
- Supports standard cron expressions (`0 2 * * *`) as well as human-readable presets
- Prevents duplicate jobs — skips a policy if a job for it is already running or queued
- Manual **"Take Backup Now"** available from both the portal and Horizon

---

## Auto Retention Enforcement

- Runs daily at **01:00 UTC** via Celery Beat
- Scans all successful backups and computes expiry as `completed_at + retention_days`
- Deletes expired backups from S3/MinIO **and** removes the database record
- Handles both S3-path and local-path backups
- Sends an email notification summary when deletions occur
- Freed storage is reported in logs and the notification email

---

## One-Click Restore

- Restore any available recovery point to a **new VM** — original is never touched
- Choose target VM name, flavor, and network at restore time
- Progress tracked in real-time: download → merge (incremental) → Glance upload → Nova boot
- Restore pipeline for incremental backups: download full base + download delta → `qemu-img` flatten → upload merged image → boot
- Restored VM is fully independent and immediately usable

---

## Recovery Points

Every backup job is a **recovery point** with the following states:

| Status | Meaning |
|---|---|
| Executing | Job is running or queued |
| Available | Backup succeeded and within retention window |
| Expired | Retention window passed — will be auto-deleted |
| Failed | Backup encountered an error |

- **Multi-select bulk delete** — select recovery points with checkboxes and delete in one action
- **Restore** button hidden for expired recovery points
- `expires_at` shown per row, highlighted red when expired
- Backup type badge (△ Inc / ● Full) and encryption badge (🔒 AES-256) shown per row

---

## Daily Backup Report

- Sent every day at **08:00 UTC** via Celery Beat
- Delivered by email and/or Slack (uses the same alert config as failure alerts)
- **Email report includes:**
  - Last 24 h: total / successful / failed / running job counts, success rate, GB backed up
  - Failed job details (VM name + error message)
  - Restore activity (last 24 h)
  - All-time statistics: total policies, all-time success rate, total stored GB
- **Slack summary:** single-line digest with emoji indicator (✅ all good / ⚠️ failures)

---

## Monitoring & Alerts

Configure under **Monitoring** in the React portal:

- **Email alerts** — SMTP host, port, TLS, username, password, recipient list
- **Slack alerts** — incoming webhook URL
- Alert triggers: backup failure, backup success (configurable independently)
- 7-day backup trend chart (success vs failure per day)
- Recent alert log with timestamp, severity, and delivery status
- Test-send button to verify SMTP/Slack config before relying on it

---

## Workload Snapshots

- Group-level snapshot — takes a backup of **every VM** in a policy in one operation
- Tracked as a single workload snapshot object linked to individual backup jobs
- Status rolls up: `running` while any job is in progress, `success` only when all succeed
- Available from the React portal Workloads page

---

## Multi-Tenancy

- Each OpenStack project can have its **own S3 bucket and credentials**
- Configure via **Admin → VaultStack → Tenant Storage** (Horizon) or the React portal
- Worker checks project-specific storage config before falling back to global S3 settings
- Backup paths are project-prefixed: `s3://bucket/<project-id-prefix>/<vm-id>/<job-id>.qcow2`
- Horizon Protection Groups are scoped per project — users only see their own policies and jobs

---

## React Operations Portal

- JWT-authenticated single-page app served at `/portal/`
- **Overview** — live stats: total policies, jobs today, success rate, storage used
- **Backup Jobs** — filterable job list with recovery status badges, bulk delete, restore trigger
- **Policies** — create / edit / pause / resume / delete policies with incremental config
- **Restores** — restore history with progress tracking
- **Workloads** — workload snapshot list and trigger
- **Monitoring** — alert config, trend charts, alert log
- **Tenant Storage** — per-project S3 configuration

---

## OpenStack Horizon Plugin

Native **Data Protection** panel added to every OpenStack project:

- **Protection Groups** — full policy management (create, edit, pause, resume, delete)
  - Backup Type card on policy detail: shows Full / Incremental + interval setting
- **Backup Jobs** — DataTable with recovery status, encryption, backup type, bulk delete
- **Policy Detail** — recovery points list with badges (type · encryption · status), bulk delete, per-row restore and delete
- **Restore Jobs** — restore history with progress
- **Workload Snapshots** — per-project workload view
- Project-scoped: Horizon passes `tenant_id` so users only see their own data
- Admin panel: **VaultStack → Storage Config** for global and per-tenant S3 setup

---

## Storage Backends

| Backend | Notes |
|---|---|
| MinIO (bundled) | Included in `docker-compose.yml`, S3-compatible, zero config |
| AWS S3 | Set `storage_type = s3` and supply bucket + credentials |
| Local disk | Default fallback; backups stored under `BACKUP_BASE_PATH` |

---

## Supported VM Types

| VM type | Snapshot method |
|---|---|
| Image-backed (ephemeral) | Nova snapshot → Glance image |
| Volume-backed (BFV) | Cinder snapshot → temp volume → Glance image |

Both paths produce a standard `.qcow2` file and clean up all cloud-side artifacts after upload.

---

## API

FastAPI REST API at port `8000`:

- `GET/POST /api/v1/backups/` — list all jobs, trigger ad-hoc backup
- `POST /api/v1/backups/bulk-delete` — delete multiple recovery points
- `GET/POST /api/v1/policies/` — list and create policies
- `PATCH /api/v1/policies/{id}` — update policy (name, schedule, VMs, retention, type)
- `POST /api/v1/policies/{id}/toggle` — pause / resume
- `GET/POST /api/v1/restores/` — list and trigger restores
- `GET /api/v1/backups/vms/list` — list available OpenStack VMs
- `GET /api/v1/dashboard/stats` — aggregate stats for the overview page
- `GET/POST /api/v1/monitoring/alerts` — alert config + alert log
- `GET/PUT /api/v1/settings/storage` — global S3 config
- `GET/POST /api/v1/tenant-storage/` — per-project S3 config

Interactive Swagger UI: `http://<host>:8000/docs`

---

## Security

- Portal access protected by **JWT tokens** (PyJWT)
- Horizon access uses OpenStack session — no additional credentials needed
- Backup files optionally encrypted with **AES-256-CTR** at rest before reaching S3
- Per-project storage isolation — backup paths include a project ID prefix
- Encryption key never stored in the database — supplied only via environment variable

---

## Verified End-to-End Test

1. Created `vaultstack-test-vm` (cirros), wrote test data to `/tmp/test-data.txt`
2. Took a full backup → stored encrypted in MinIO as `.qcow2`
3. Took an incremental backup → delta stored encrypted in MinIO
4. Restored full backup to `vaultstack-restore-vm` → SSH'd in → test file present with identical content ✓
5. Incremental restore merged delta + base → booted clean VM ✓
6. Encryption verified: `encrypted = true` in DB, purple badge in Horizon ✓
