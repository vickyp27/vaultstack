import json
from django.http import JsonResponse
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.shortcuts import redirect
from django.views import View
from django.views.generic.edit import FormView
from django.views.generic import TemplateView
from horizon import tables, forms, exceptions
from vaultstack_dashboard.backup import api
from vaultstack_dashboard.backup.tables import (
    BackupJobsTable, PoliciesTable, RestoreJobsTable,
    PolicyBackupJobsTable, WorkloadSnapshotsTable,
)
from vaultstack_dashboard.backup.forms import (
    TakeBackupForm, CreatePolicyForm, RestoreForm, StorageSettingsForm
)


class IndexView(TemplateView):
    template_name = "backup/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project_id = getattr(self.request.user, "tenant_id", None)
        try:
            context["policies"] = api.list_policies(project_id=project_id)
        except Exception:
            context["policies"] = []
        try:
            context["stats"] = api.get_stats(project_id=project_id)
        except Exception:
            context["stats"] = {}
        try:
            context["storage_settings"] = api.get_storage_settings()
        except Exception:
            context["storage_settings"] = {"storage_type": "local"}
        return context


class PoliciesView(tables.DataTableView):
    table_class = PoliciesTable
    template_name = "backup/policies.html"
    page_title = _("Backup Policies")

    def get_data(self):
        try:
            project_id = getattr(self.request.user, "tenant_id", None)
            return api.list_policies(project_id=project_id)
        except Exception:
            exceptions.handle(self.request, _("Unable to fetch policies."))
            return []


class BackupJobsView(tables.DataTableView):
    table_class = BackupJobsTable
    template_name = "backup/jobs.html"
    page_title = _("Backup Jobs")

    def get_data(self):
        try:
            return api.list_backups()
        except Exception:
            exceptions.handle(self.request, _("Unable to fetch backup jobs."))
            return []


class RestoresView(tables.DataTableView):
    table_class = RestoreJobsTable
    template_name = "backup/restores.html"
    page_title = _("Restore Jobs")

    def get_data(self):
        try:
            return api.list_restores()
        except Exception:
            exceptions.handle(self.request, _("Unable to fetch restore jobs."))
            return []


class TakeBackupView(forms.ModalFormView):
    form_class = TakeBackupForm
    template_name = "backup/take_backup.html"
    ajax_template_name = "backup/take_backup.html"
    success_url = reverse_lazy("horizon:project:backup:jobs")
    modal_header = _("Take Instant Backup")
    submit_label = _("Take Backup Now")
    page_title = _("Take Backup")


class CreatePolicyView(forms.ModalFormView):
    form_class = CreatePolicyForm
    template_name = "backup/create_policy.html"
    ajax_template_name = "backup/create_policy.html"
    success_url = reverse_lazy("horizon:project:backup:policies")
    modal_header = _("Create Backup Policy")
    submit_label = _("Create Policy")
    page_title = _("Create Backup Policy")


class RestoreView(forms.ModalFormView):
    form_class = RestoreForm
    template_name = "backup/restore.html"
    ajax_template_name = "backup/restore.html"
    success_url = reverse_lazy("horizon:project:backup:restores")
    modal_header = _("Restore VM from Backup")
    submit_label = _("Start Restore")
    page_title = _("Restore VM")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["backup_id"] = self.kwargs.get("backup_id")
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["backup_id"] = self.kwargs.get("backup_id")
        try:
            context["backup"] = api.get_backup(self.kwargs["backup_id"])
        except Exception:
            context["backup"] = {}
        return context


class TogglePolicyScheduleView(TemplateView):
    def get(self, request, policy_id):
        try:
            policy = api.get_policy(policy_id)
            new_state = not policy.get("is_active", True)
            api.toggle_policy(policy_id, new_state)
            if new_state:
                messages.success(request, _("Schedule enabled."))
            else:
                messages.success(request, _("Schedule disabled. Manual backups still work."))
        except Exception as e:
            messages.error(request, _("Failed to update schedule: %s") % str(e))
        return redirect(
            reverse("horizon:project:backup:policy_detail",
                    kwargs={"policy_id": policy_id})
        )


class BulkDeleteRecoveryPointsView(View):
    def post(self, request, *args, **kwargs):
        ids = request.POST.getlist("backup_ids")
        policy_id = request.POST.get("policy_id")
        deleted = 0
        for bid in ids:
            try:
                api.delete_backup(bid)
                deleted += 1
            except Exception:
                pass
        if deleted:
            messages.success(request, _("%d recovery point(s) deleted.") % deleted)
        else:
            messages.warning(request, _("No recovery points were deleted."))
        if policy_id:
            return redirect(
                reverse("horizon:project:backup:policy_detail",
                        kwargs={"policy_id": policy_id})
            )
        return redirect(reverse("horizon:project:backup:jobs"))


class DeleteRecoveryPointView(TemplateView):
    def get(self, request, backup_id):
        policy_id = request.GET.get("policy_id")
        try:
            api.delete_backup(backup_id)
            messages.success(request, _("Recovery point deleted successfully."))
        except Exception as e:
            messages.error(request, _("Delete failed: %s") % str(e))
        if policy_id:
            return redirect(
                reverse("horizon:project:backup:policy_detail",
                        kwargs={"policy_id": policy_id})
            )
        return redirect(reverse_lazy("horizon:project:backup:index"))


class DeleteProtectionGroupView(TemplateView):
    def get(self, request, policy_id):
        try:
            all_backups = api.list_backups()
            has_backups = any(
                b.get("policy_id") == policy_id for b in all_backups
            )
            if has_backups:
                messages.error(
                    request,
                    _("Cannot delete: this Protection Group has existing backups. "
                      "Delete all backup jobs first.")
                )
                return redirect(
                    reverse("horizon:project:backup:policy_detail",
                            kwargs={"policy_id": policy_id})
                )
            api.delete_policy(policy_id)
            messages.success(request, _("Protection Group deleted successfully."))
        except Exception as e:
            messages.error(request, _("Delete failed: %s") % str(e))
        return redirect(reverse_lazy("horizon:project:backup:index"))


class RunWorkloadView(TemplateView):
    def get(self, request, policy_id):
        try:
            result = api.trigger_workload_backup(policy_id)
            messages.success(request, _("Workload backup started!"))
            return redirect(
                reverse_lazy("horizon:project:backup:workload_detail",
                             kwargs={"workload_id": result["workload_snapshot_id"]})
            )
        except Exception as e:
            messages.error(request, _("Failed to start workload: %s") % str(e))
            return redirect(reverse_lazy("horizon:project:backup:policies"))


class WorkloadSnapshotsView(tables.DataTableView):
    table_class = WorkloadSnapshotsTable
    template_name = "backup/workloads.html"
    page_title = _("Workload Snapshots")

    def get_data(self):
        try:
            return api.list_workloads()
        except Exception:
            exceptions.handle(self.request, _("Unable to fetch workload snapshots."))
            return []


class WorkloadDetailView(tables.DataTableView):
    table_class = PolicyBackupJobsTable
    template_name = "backup/workload_detail.html"
    page_title = _("Workload Snapshot Detail")

    def get_data(self):
        wid = self.kwargs.get("workload_id")
        try:
            ws = api.get_workload(wid)
            return ws.get("jobs", [])
        except Exception:
            exceptions.handle(self.request, _("Unable to fetch workload jobs."))
            return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wid = self.kwargs.get("workload_id")
        try:
            context["workload"] = api.get_workload(wid)
        except Exception:
            context["workload"] = {}
        return context


class PolicyDetailView(TemplateView):
    template_name = "backup/policy_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        policy_id = self.kwargs.get("policy_id")
        try:
            context["policy"] = api.get_policy(policy_id)
        except Exception:
            context["policy"] = {}
        try:
            project_id = getattr(self.request.user, "tenant_id", None)
            all_vms = {v["id"]: v for v in api.list_vms(project_id=project_id)}
            policy = context.get("policy", {})
            context["vm_details"] = [
                all_vms.get(vid, {"id": vid, "name": vid, "status": "UNKNOWN", "flavor": "—", "volumes": []})
                for vid in (policy.get("vm_ids") or [])
            ]
        except Exception:
            context["vm_details"] = []
        try:
            all_backups = api.list_backups()
            jobs = [b for b in all_backups if b.get("policy_id") == policy_id]
            # Also include workload-triggered backups for this policy
            workloads = api.list_workloads()
            wl_ids = {w["id"] for w in workloads if w.get("policy_id") == policy_id}
            extra = [b for b in all_backups if b.get("workload_snapshot_id") in wl_ids]
            seen = {j["id"] for j in jobs}
            jobs += [b for b in extra if b["id"] not in seen]
            jobs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
            context["backup_jobs"] = jobs
            context["has_running"] = any(
                j["status"] in ("running", "queued") for j in jobs
            )
            context["has_backups"] = len(jobs) > 0
        except Exception:
            context["backup_jobs"] = []
            context["has_running"] = False
            context["has_backups"] = False
        try:
            context["restore_jobs"] = api.list_restores(policy_id=policy_id)
            context["has_running_restore"] = any(
                r["status"] in ("running", "queued") for r in context["restore_jobs"]
            )
        except Exception:
            context["restore_jobs"] = []
            context["has_running_restore"] = False
        return context


class StorageSettingsView(FormView):
    template_name = "backup/settings.html"
    form_class = StorageSettingsForm
    success_url = reverse_lazy("horizon:admin:vaultstack_admin:index")

    def get_initial(self):
        try:
            data = api.get_storage_settings()
            # Don't pre-fill masked secrets in form fields
            data["s3_access_key"] = "" if data.get("s3_access_key") == "***" else data.get("s3_access_key", "")
            data["s3_secret_key"] = ""
            return data
        except Exception:
            return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = _("Storage Settings")
        try:
            context["current"] = api.get_storage_settings()
        except Exception:
            context["current"] = {"storage_type": "local"}
        return context

    def form_valid(self, form):
        try:
            api.update_storage_settings(form.cleaned_data)
            messages.success(self.request, _("Storage settings saved successfully."))
        except Exception as e:
            messages.error(self.request, _("Failed to save settings: %s") % str(e))
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)


class TestS3ConnectionView(View):
    def post(self, request, *args, **kwargs):
        try:
            result = api.test_s3_connection()
            return JsonResponse({"success": True, "message": result.get("message", "Connection successful!")})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})
