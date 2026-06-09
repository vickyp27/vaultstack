from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy
from django.utils.safestring import mark_safe
from horizon import tables


def _recovery_status_badge(datum):
    if not isinstance(datum, dict):
        return "—"
    status = datum.get("recovery_status") or datum.get("status", "")
    config = {
        "executing": ("#3498db", "EXECUTING"),
        "available": ("#27ae60", "AVAILABLE"),
        "expired":   ("#95a5a6", "EXPIRED"),
        "failed":    ("#e74c3c", "FAILED"),
    }
    color, label = config.get(status, ("#95a5a6", status.upper()))
    return mark_safe(
        f'<span style="background:{color};color:#fff;padding:2px 10px;'
        f'border-radius:10px;font-size:.82em;font-weight:600;">{label}</span>'
    )


def _encrypted_badge(datum):
    if not isinstance(datum, dict):
        return "—"
    if datum.get("encrypted"):
        return mark_safe(
            '<span style="background:#8e44ad;color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:.82em;font-weight:600;">'
            '<i class="fa fa-lock" style="margin-right:4px;"></i>AES-256</span>'
        )
    return mark_safe('<span style="color:#aaa;font-size:.82em;">—</span>')


def _backup_type_badge(datum):
    if not isinstance(datum, dict):
        return "—"
    btype = datum.get("backup_type", "full")
    if btype == "incremental":
        return mark_safe(
            '<span style="background:#f39c12;color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:.82em;font-weight:600;">△ INC</span>'
        )
    return mark_safe(
        '<span style="background:#2980b9;color:#fff;padding:2px 8px;'
        'border-radius:10px;font-size:.82em;font-weight:600;">● FULL</span>'
    )


class RestoreBackupAction(tables.LinkAction):
    name = "restore"
    verbose_name = _("Restore")
    url = "horizon:project:backup:restore"
    classes = ("ajax-modal",)
    icon = "fa fa-undo"

    def allowed(self, request, datum):
        return datum.get("status") == "success"


class DeleteBackupAction(tables.DeleteAction):
    name = "delete"
    icon = "fa fa-trash"

    @staticmethod
    def action_present(count):
        return ngettext_lazy("Delete Backup", "Delete Backups", count)

    @staticmethod
    def action_past(count):
        return ngettext_lazy("Deleted Backup", "Deleted Backups", count)

    def delete(self, request, obj_id):
        from vaultstack_dashboard.backup import api
        api.delete_backup(obj_id)


class TakeBackupAction(tables.LinkAction):
    name = "take_backup"
    verbose_name = _("Take Backup")
    url = "horizon:project:backup:take_backup"
    classes = ("ajax-modal",)
    icon = "fa fa-plus"


class BackupJobsTable(tables.DataTable):
    vm_name = tables.Column("vm_name", verbose_name=_("VM Name"))
    backup_type = tables.Column(
        _backup_type_badge,
        verbose_name=_("Type"),
    )
    status = tables.Column(
        "status",
        verbose_name=_("Job Status"),
        status=True,
        status_choices=(
            ("success", True),
            ("failed", False),
            ("running", None),
            ("queued", None),
        ),
    )
    recovery_status = tables.Column(
        _recovery_status_badge,
        verbose_name=_("Recovery"),
    )
    encrypted = tables.Column(
        _encrypted_badge,
        verbose_name=_("Encryption"),
    )
    expires_at = tables.Column("expires_at", verbose_name=_("Expires At"))
    size_gb = tables.Column("size_gb", verbose_name=_("Size (GB)"))
    started_at = tables.Column("started_at", verbose_name=_("Started At"))
    completed_at = tables.Column("completed_at", verbose_name=_("Completed At"))

    def get_object_id(self, datum):
        return datum["id"] if isinstance(datum, dict) else datum.id

    class Meta:
        name = "backup_jobs"
        verbose_name = _("Backup Jobs")
        table_actions = (TakeBackupAction, DeleteBackupAction)
        row_actions = (RestoreBackupAction, DeleteBackupAction)


class DeletePolicyAction(tables.DeleteAction):
    name = "delete"
    icon = "fa fa-trash"

    @staticmethod
    def action_present(count):
        return ngettext_lazy("Delete Policy", "Delete Policies", count)

    @staticmethod
    def action_past(count):
        return ngettext_lazy("Deleted Policy", "Deleted Policies", count)

    def delete(self, request, obj_id):
        from vaultstack_dashboard.backup import api
        api.delete_policy(obj_id)


class CreatePolicyAction(tables.LinkAction):
    name = "create_policy"
    verbose_name = _("Create Policy")
    url = "horizon:project:backup:create_policy"
    classes = ("ajax-modal",)
    icon = "fa fa-plus"


class PoliciesTable(tables.DataTable):
    name = tables.Column(
        "name",
        verbose_name=_("Policy Name"),
        link="horizon:project:backup:policy_detail",
    )
    schedule = tables.Column("schedule", verbose_name=_("Schedule (Cron)"))
    retention_days = tables.Column("retention_days", verbose_name=_("Retention (Days)"))
    vm_count = tables.Column(
        lambda d: len(d.get("vm_ids", [])) if isinstance(d, dict) else 0,
        verbose_name=_("VMs Protected"),
    )
    is_active = tables.Column("is_active", verbose_name=_("Active"))

    def get_object_id(self, datum):
        return datum["id"] if isinstance(datum, dict) else datum.id

    class Meta:
        name = "policies"
        verbose_name = _("Backup Policies")
        table_actions = (CreatePolicyAction,)
        row_actions = (DeletePolicyAction,)


class PolicyBackupJobsTable(tables.DataTable):
    """Backup jobs table used inside the policy detail page."""
    vm_name = tables.Column("vm_name", verbose_name=_("VM Name"))
    backup_type = tables.Column(
        _backup_type_badge,
        verbose_name=_("Type"),
    )
    status = tables.Column(
        "status",
        verbose_name=_("Job Status"),
        status=True,
        status_choices=(
            ("success", True),
            ("failed", False),
            ("running", None),
            ("queued", None),
        ),
    )
    recovery_status = tables.Column(
        _recovery_status_badge,
        verbose_name=_("Recovery"),
    )
    encrypted = tables.Column(
        _encrypted_badge,
        verbose_name=_("Encryption"),
    )
    expires_at = tables.Column("expires_at", verbose_name=_("Expires At"))
    size_gb = tables.Column("size_gb", verbose_name=_("Size (GB)"))
    started_at = tables.Column("started_at", verbose_name=_("Started At"))
    completed_at = tables.Column("completed_at", verbose_name=_("Completed At"))

    def get_object_id(self, datum):
        return datum["id"] if isinstance(datum, dict) else datum.id

    class Meta:
        name = "policy_backup_jobs"
        verbose_name = _("Recovery Points")
        table_actions = (DeleteBackupAction,)
        row_actions = (RestoreBackupAction, DeleteBackupAction)


class RunWorkloadAction(tables.LinkAction):
    name = "run_workload"
    verbose_name = _("Run Workload Backup")
    url = "horizon:project:backup:workloads"
    icon = "fa fa-play"


class DeleteWorkloadAction(tables.DeleteAction):
    name = "delete_workload"
    icon = "fa fa-trash"

    @staticmethod
    def action_present(count):
        return ngettext_lazy("Delete Snapshot", "Delete Snapshots", count)

    @staticmethod
    def action_past(count):
        return ngettext_lazy("Deleted Snapshot", "Deleted Snapshots", count)

    def delete(self, request, obj_id):
        from vaultstack_dashboard.backup import api
        api.delete_workload(obj_id)


def _workload_status_badge(datum):
    if not isinstance(datum, dict):
        return "—"
    status = datum.get("status", "")
    colors = {
        "success": "#27ae60",
        "failed": "#e74c3c",
        "partial": "#e67e22",
        "running": "#3498db",
        "queued": "#95a5a6",
    }
    color = colors.get(status, "#95a5a6")
    return mark_safe(
        f'<span style="background:{color};color:#fff;padding:2px 10px;'
        f'border-radius:10px;font-size:.82em;font-weight:600;">{status.upper()}</span>'
    )


def _vm_progress(datum):
    if not isinstance(datum, dict):
        return "—"
    total = datum.get("vm_count", 0) or 0
    done = datum.get("completed_count", 0) or 0
    failed = datum.get("failed_count", 0) or 0
    if not total:
        return "—"
    pct = round(done / total * 100)
    color = "#27ae60" if failed == 0 else "#e67e22"
    return mark_safe(
        f'<div style="min-width:120px;">'
        f'<div style="background:#e9ecef;border-radius:4px;height:10px;overflow:hidden;margin-bottom:3px;">'
        f'<div style="width:{pct}%;background:{color};height:100%;"></div>'
        f'</div>'
        f'<small style="color:#555;">{done}/{total} VMs'
        f'{(" &bull; <span style=color:#e74c3c>" + str(failed) + " failed</span>") if failed else ""}'
        f'</small></div>'
    )


class WorkloadSnapshotsTable(tables.DataTable):
    policy_name = tables.Column(
        "policy_name",
        verbose_name=_("Policy / Workload"),
        link="horizon:project:backup:workload_detail",
    )
    status = tables.Column(
        _workload_status_badge,
        verbose_name=_("Status"),
    )
    vm_progress = tables.Column(
        _vm_progress,
        verbose_name=_("VMs"),
    )
    total_size_gb = tables.Column("total_size_gb", verbose_name=_("Total Size (GB)"))
    started_at = tables.Column("started_at", verbose_name=_("Started At"))
    completed_at = tables.Column("completed_at", verbose_name=_("Completed At"))

    def get_object_id(self, datum):
        return datum["id"] if isinstance(datum, dict) else datum.id

    class Meta:
        name = "workload_snapshots"
        verbose_name = _("Workload Snapshots")
        row_actions = (DeleteWorkloadAction,)


def _progress_bar(datum):
    if not isinstance(datum, dict):
        return "—"
    pct = datum.get("progress", 0) or 0
    msg = datum.get("progress_msg", "") or ""
    status = datum.get("status", "")
    if status == "success":
        color = "#27ae60"
    elif status == "failed":
        color = "#e74c3c"
    else:
        color = "#3498db"
    return mark_safe(
        f'<div style="min-width:160px;">'
        f'<div style="background:#e9ecef;border-radius:4px;height:14px;overflow:hidden;">'
        f'<div style="width:{pct}%;background:{color};height:100%;transition:width .4s;"></div>'
        f'</div>'
        f'<small style="color:#666;">{pct}% &mdash; {msg}</small>'
        f'</div>'
    )


class RestoreJobsTable(tables.DataTable):
    target_vm_name = tables.Column("target_vm_name", verbose_name=_("New VM Name"))
    status = tables.Column(
        "status",
        verbose_name=_("Status"),
        status=True,
        status_choices=(
            ("success", True),
            ("failed", False),
            ("running", None),
            ("queued", None),
        ),
    )
    progress = tables.Column(
        _progress_bar,
        verbose_name=_("Progress"),
        classes=("nowrap-col",),
    )
    new_vm_id = tables.Column("new_vm_id", verbose_name=_("New VM ID"))
    started_at = tables.Column("started_at", verbose_name=_("Started At"))

    def get_object_id(self, datum):
        return datum["id"] if isinstance(datum, dict) else datum.id

    class Meta:
        name = "restore_jobs"
        verbose_name = _("Restore Jobs")
