# VaultStack — Feature Reference

Complete feature list for VaultStack, the open-source VM backup & restore platform for OpenStack.

---

## Protection Groups (Backup Policies)

- Create named policies that group one or more VMs
- Per-policy **cron schedule** — hourly, daily, weekly, monthly, or custom cron expression
- Per-policy **retention** — configurable in days; expired recovery points are auto-deleted
- **Per-VM retention override** — override retention days per individual VM within a policy (JSONB map)
- **SLA threshold** — set `sla_max_age_hours`; breached VMs surface on the SLA Compliance dashboard
- **Test Restore Automation** — toggle auto-test restore on a schedule; records RTO in seconds
- **Pause / Resume** — suspend a policy without deleting it
- **Edit in-place** — change VMs, schedule, retention, backup type, SLA threshold at any time
- **Delete guard** — blocked if the policy has active (running/queued) jobs (409 error)

---

## Backup Engine

### Full Backup
- Nova snapshot (image-backed VMs) or Cinder snapshot → Glance image path (volume-backed VMs)
- Downloads the snapshot as a `.qcow2` file
- Uploads to configured storage backend (S3/MinIO, Swift, or local disk)
- All temporary Glance images and Cinder snapshots are cleaned up after each run

### Incremental Backup (VSDT)
- Toggle **Enable Incremental Backup** per policy
- Stores only changed blocks since the last full backup using `qemu-img rebase`
- Configurable **full backup interval** (2–30 runs)
- Incremental backups are typically **70–90% smaller** than full backups
- Restore automatically merges the delta + base before booting the VM

### CBT — Changed Block Tracking (Cinder Native)
- Uses **Cinder Backup API** for true block-level CBT — no full disk read needed
- Only changed blocks are transferred — far smaller than VSDT incremental
- Works on **volume-backed VMs only**; image-backed VMs fall back to VSDT automatically
- Marked with `⚡ CBT` badge in the portal

### Multi-Volume Backup
- Backs up VMs with multiple Cinder volumes attached
- All volumes packed into a single `.tar` archive (manifest + per-volume qcow2 files)
- App-consistent freeze/thaw via Nova guest agent before snapshot

### Backup Types at a Glance

| Type | Method | Storage impact |
|---|---|---|
| Full | Complete disk image | Baseline |
| Incremental (VSDT) | Changed blocks via qemu-img | 70–90% smaller |
| CBT | Cinder native block tracking | Smallest — only actual changes |

---

## AES-256 Encryption

- Backups encrypted with **AES-256-CTR** before upload to storage
- Streaming encryption — no full-file copy, works on large disks
- Each backup gets a unique random **16-byte IV** prepended to the file
- Key supplied via `BACKUP_ENCRYPTION_KEY` environment variable — never stored in DB
- `encrypted = true` flag stored per backup job
- Restore pipeline auto-decrypts before use (full restore, instant restore, FLR)
- **🔒 AES-256** badge shown in portal per recovery point

---

## WORM / Retention Lock

- Lock any backup against deletion for a configurable number of days
- Locked backups return **HTTP 423** on any delete attempt (single or bulk)
- Retention task skips locked backups — they are never auto-expired while locked
- Lock / unlock actions recorded in Audit Log
- **🔒 WORM** orange badge shown on locked recovery points
- Unlock button available for admin to remove lock early

---

## Scheduling

- Celery Beat scheduler ticks every **60 seconds**
- Supports standard cron expressions and human-readable presets
- Prevents duplicate jobs — skips policy if a job is already running/queued
- Manual **"Backup Now"** from portal policy detail or Horizon

---

## Auto Retention Enforcement

- Runs daily at **01:00 UTC** via Celery Beat
- Computes expiry as `completed_at + retention_days` (per-VM override respected)
- Deletes expired backups from storage backend **and** removes DB record
- Skips WORM-locked backups regardless of expiry
- Handles S3, Swift, and local-path backups

---

## Restore Options

### Full Restore
- Restore any recovery point to a **new VM** — original never touched
- Choose target VM name, flavor, and network at restore time
- Progress tracked in real-time: download → decrypt → merge (incremental) → Glance upload → Nova boot

### Instant Restore
- Boots VM **directly from Glance image** — no Cinder volume needed
- VM accessible in **~1–2 minutes** (ephemeral disk)
- Useful for quick verification or emergency access

### Restore to Original VM
- Toggle **Restore to Original VM** in the restore modal
- Worker stops and deletes the original VM after successful restore completes
- New VM takes over the original VM's identity

### Single Disk Restore
- For multi-volume (tar) backups — restore only selected volume indices
- Specify indices as comma-separated list: `0` (boot), `1` (first data disk), etc.
- Unselected volumes are skipped; only chosen disks are restored

### File-Level Restore (FLR)
- Browse backup contents without spinning up a VM
- Uses **libguestfs** (`virt-ls` / `virt-copy-out`) to inspect the backup image
- Select individual files or folders from the portal file browser
- Download selected files as a **ZIP** directly to the browser
- Works on both encrypted and unencrypted backups

---

## Recovery Point States

| Status | Meaning |
|---|---|
| Executing | Job running or queued |
| Available | Succeeded and within retention window |
| Expired | Past retention window — scheduled for auto-delete |
| Failed | Backup encountered an error |

---

## Test Restore Automation

- Per-policy toggle — automatically runs a test restore on a configurable schedule
- Celery task: triggers instant restore → waits for VM boot → auto-deletes test VM → records RTO
- Results stored in `test_restore_results` table with `status` (passed/failed) and `rto_seconds`
- Manual trigger available from Policy Detail → **⚡ Test Restore** button
- Results table shown in-panel: started_at, status badge, RTO, error message

---

## SLA Compliance Dashboard

- Per-policy `sla_max_age_hours` threshold
- Compliance computed from last successful backup per VM:
  - **Compliant** — last backup age ≤ 80% of threshold
  - **At Risk** — 80–100% of threshold
  - **Breach** — age exceeds threshold
- Summary cards: Total / Compliant / At Risk / Breach counts
- Per-VM table: VM name, policy, last backup time, age, threshold, status badge
- API: `GET /api/v1/sla/compliance` and `GET /api/v1/sla/summary`

---

## Audit Log

- Every write action recorded: `lock_backup`, `unlock_backup`, `delete_backup`, `create_restore`, etc.
- Fields: timestamp, action, entity_type, entity_id, actor, details
- Filterable by action type and entity type in the portal
- API: `GET /api/v1/audit/`

---

## Multi-Provider OpenStack

- Add multiple OpenStack endpoints (clouds) as **Providers**
- Each provider has its own credentials (auth URL, username, password, project)
- VM list aggregates across all providers with deduplication
- Backup triggered to correct provider automatically
- Provider name shown per VM in policy modal VM picker

---

## Storage Backends

| Backend | Notes |
|---|---|
| MinIO (bundled) | Included in docker-compose, S3-compatible, zero config |
| AWS S3 / any S3 | Set endpoint, bucket, access key, secret key |
| OpenStack Swift | python-swiftclient; auth URL, username, password, tenant, container |
| Local disk | Default fallback; `BACKUP_BASE_PATH` |

### Tenant Storage Isolation
- Each OpenStack project can have its own S3 bucket and credentials
- Worker checks project-specific config before falling back to global settings
- Backup paths are project-prefixed for full data isolation

---

## Monitoring & Alerts

- **Email** — SMTP host, port, TLS, username, password, recipient list
- **Slack** — incoming webhook URL
- Alert triggers: backup failure, backup success (configurable)
- 7-day backup trend chart
- Daily backup report at **08:00 UTC** (email + Slack digest)
- Test-send button to verify config

---

## React Operations Portal

JWT-authenticated SPA at port `3000`:

| Page | Features |
|---|---|
| Overview | Live stats: policies, jobs today, success rate, storage used |
| Backup Jobs | Filter by status, search by VM/policy, recovery badges, WORM lock/unlock, per-row delete, bulk delete, restore trigger, FLR |
| Policies | Create/edit/pause/resume/delete, incremental config, CBT toggle, GFS, SLA threshold, test restore, per-VM retention |
| Policy Detail | Recovery points table, Backup Now, Test Restore button + results panel, Restore History |
| Restores | Restore history with progress |
| SLA Compliance | Summary cards + per-VM compliance table |
| Audit Log | Action log with filters |
| Workloads | Workload snapshot list and trigger |
| Monitoring | Alert config, trend charts, alert log |
| Tenant Storage | Per-project S3 configuration |
| Settings | Global storage, providers, auth |

---

## OpenStack Horizon Plugin

Native **Data Protection** panel per OpenStack project:

- Protection Groups — full policy management
- Backup Jobs — DataTable with recovery status, encryption badge, CBT badge, bulk delete
- Policy Detail — recovery points with badges, bulk delete, per-row restore
- Restore Jobs — history with progress
- Workload Snapshots
- Admin panel: **VaultStack → Storage Config**

---

## GFS Retention (Grandfather-Father-Son)

- Keep separate tiers: **daily** (N days), **weekly** (N weeks), **monthly** (N months)
- Retention task applies GFS logic before standard expiry
- Configurable per policy

---

## API

FastAPI REST API at port `8000` — full Swagger UI at `/docs`:

| Endpoint | Description |
|---|---|
| `GET/POST /api/v1/backups/` | List jobs, trigger ad-hoc backup |
| `DELETE /api/v1/backups/{id}` | Delete backup (WORM check, S3 cleanup) |
| `POST /api/v1/backups/bulk-delete` | Bulk delete (WORM check, S3 cleanup) |
| `POST /api/v1/backups/{id}/lock` | WORM lock |
| `DELETE /api/v1/backups/{id}/lock` | WORM unlock |
| `GET /api/v1/backups/vms/list` | List VMs across all providers |
| `GET/POST /api/v1/policies/` | List, create policies |
| `PUT /api/v1/policies/{id}` | Update policy |
| `DELETE /api/v1/policies/{id}` | Delete policy (active job guard) |
| `GET/POST /api/v1/restores/` | List, trigger restores |
| `GET /api/v1/sla/compliance` | Per-VM SLA status |
| `GET /api/v1/sla/summary` | SLA summary counts |
| `GET /api/v1/audit/` | Audit log |
| `POST /api/v1/test-restores/{id}/run` | Trigger test restore |
| `GET /api/v1/test-restores/{id}/results` | Test restore results |
| `GET /api/v1/dashboard/stats` | Overview stats |
| `GET/PUT /api/v1/settings/storage` | Global storage config |
| `GET/POST /api/v1/settings/tenants/` | Tenant storage |
| `GET/POST /api/v1/providers/` | Multi-provider management |
| `POST /api/v1/file-restore/{id}/browse` | FLR — browse backup |
| `POST /api/v1/file-restore/{id}/download` | FLR — download files as ZIP |

---

## Security

- Portal access protected by **JWT tokens** (PyJWT, 12hr expiry)
- Backup files optionally encrypted with **AES-256-CTR** at rest
- WORM lock prevents deletion even by admin until expiry
- Per-project storage isolation — backup paths include project ID prefix
- Encryption key never stored in DB — env var only
- Audit log records all write actions

---

## Supported VM Types

| VM type | Snapshot method |
|---|---|
| Image-backed (ephemeral) | Nova snapshot → Glance image |
| Volume-backed (BFV), single volume | Cinder snapshot → Glance image |
| Volume-backed (BFV), multi-volume | Cinder snapshots → tar archive (per-volume qcow2 + manifest) |
| Volume-backed + CBT enabled | Cinder Backup API (block-level, smallest backup size) |
