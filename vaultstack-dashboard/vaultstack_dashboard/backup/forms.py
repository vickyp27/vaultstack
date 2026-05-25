from horizon import forms
from django.utils.translation import gettext_lazy as _


class TakeBackupForm(forms.SelfHandlingForm):
    vm_id = forms.ChoiceField(
        label=_("Virtual Machine"),
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        from vaultstack_dashboard.backup import api
        try:
            vms = api.list_vms(project_id=getattr(request.user, "tenant_id", None))
            self.fields["vm_id"].choices = [
                (vm["id"], f"{vm['name']}  ({vm['status']})")
                for vm in vms
            ]
        except Exception:
            self.fields["vm_id"].choices = [("", _("— No VMs available —"))]

    def handle(self, request, data):
        from vaultstack_dashboard.backup import api
        return api.create_backup(vm_id=data["vm_id"])


class CreatePolicyForm(forms.SelfHandlingForm):
    name = forms.CharField(
        label=_("Policy Name"),
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": _("e.g. Daily Production Backup"),
        }),
    )
    vm_ids = forms.MultipleChoiceField(
        label=_("Virtual Machines"),
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Select one or more VMs to include in this policy."),
    )
    schedule = forms.ChoiceField(
        label=_("Schedule"),
        choices=[
            ("0 2 * * *",   _("Daily at 2:00 AM")),
            ("0 2 * * 0",   _("Weekly — Sunday at 2:00 AM")),
            ("0 2 1 * *",   _("Monthly — 1st day at 2:00 AM")),
            ("0 */6 * * *", _("Every 6 Hours")),
            ("0 * * * *",   _("Every Hour")),
        ],
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    retention_days = forms.IntegerField(
        label=_("Retention (Days)"),
        initial=30,
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text=_("Backups older than this will be automatically deleted."),
    )

    def __init__(self, request, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        from vaultstack_dashboard.backup import api
        try:
            vms = api.list_vms(project_id=getattr(request.user, "tenant_id", None))
            self.fields["vm_ids"].choices = [
                (vm["id"], f"{vm['name']}  ({vm['status']})")
                for vm in vms
            ]
        except Exception:
            self.fields["vm_ids"].choices = []

    def handle(self, request, data):
        from vaultstack_dashboard.backup import api
        return api.create_policy(
            name=data["name"],
            vm_ids=data["vm_ids"],
            schedule=data["schedule"],
            retention_days=data["retention_days"],
            project_id=getattr(request.user, "tenant_id", None),
        )


class RestoreForm(forms.SelfHandlingForm):
    backup_job_id = forms.CharField(widget=forms.HiddenInput())
    target_vm_name = forms.CharField(
        label=_("New VM Name"),
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": _("e.g. restored-web-server"),
        }),
    )
    flavor_id = forms.ChoiceField(
        label=_("Flavor"),
        choices=[],
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text=_("Select the compute flavor for the restored VM."),
    )
    target_network_id = forms.ChoiceField(
        label=_("Target Network"),
        choices=[],
        required=False,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    def __init__(self, request, *args, **kwargs):
        backup_id = kwargs.pop("backup_id", None)
        super().__init__(request, *args, **kwargs)
        if backup_id:
            self.fields["backup_job_id"].initial = backup_id
        # Load flavors
        try:
            from vaultstack_dashboard.backup import api
            flavors = api.list_flavors()
            self.fields["flavor_id"].choices = [
                (f["id"], f"{f['name']}  ({f['vcpus']} vCPU, {f['ram']} MB RAM)")
                for f in flavors
            ]
        except Exception:
            self.fields["flavor_id"].choices = [("", _("— No flavors available —"))]
        # Load networks
        try:
            from openstack_dashboard import api as os_api
            networks = os_api.neutron.network_list(request)
            self.fields["target_network_id"].choices = [
                ("", _("— Default Network —"))
            ] + [(n.id, n.name) for n in networks]
        except Exception:
            self.fields["target_network_id"].choices = [("", _("— Default Network —"))]

    def handle(self, request, data):
        from vaultstack_dashboard.backup import api
        return api.create_restore(
            backup_job_id=data["backup_job_id"],
            target_vm_name=data["target_vm_name"],
            flavor_id=data["flavor_id"] or None,
            target_network_id=data["target_network_id"] or None,
        )


class StorageSettingsForm(forms.Form):
    storage_type = forms.ChoiceField(
        label=_("Storage Backend"),
        choices=[
            ("local", _("Local Disk")),
            ("s3",    _("S3 / Object Storage")),
        ],
        widget=forms.RadioSelect(),
    )
    s3_endpoint_url = forms.CharField(
        label=_("S3 Endpoint URL"),
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "https://s3.amazonaws.com  (leave empty for AWS)",
        }),
        help_text=_("Use a custom endpoint for MinIO, Ceph RGW, or other S3-compatible stores."),
    )
    s3_access_key = forms.CharField(
        label=_("Access Key ID"),
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "AKIAIOSFODNN7EXAMPLE"}),
    )
    s3_secret_key = forms.CharField(
        label=_("Secret Access Key"),
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}, render_value=False),
        help_text=_("Leave blank to keep the existing secret key."),
    )
    s3_bucket_name = forms.CharField(
        label=_("Bucket Name"),
        required=False,
        initial="vaultstack-backups",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "vaultstack-backups"}),
    )
    s3_region = forms.CharField(
        label=_("Region"),
        required=False,
        initial="us-east-1",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "us-east-1"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("storage_type") == "s3" and not cleaned.get("s3_bucket_name"):
            self.add_error("s3_bucket_name", _("Bucket name is required when using S3 storage."))
        return cleaned
