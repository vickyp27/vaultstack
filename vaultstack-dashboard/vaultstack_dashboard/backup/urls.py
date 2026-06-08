from django.urls import re_path
from vaultstack_dashboard.backup import views

urlpatterns = [
    re_path(r"^$",                               views.IndexView.as_view(),          name="index"),
    re_path(r"^policies/$",                                   views.PoliciesView.as_view(),      name="policies"),
    re_path(r"^policies/create/$",                           views.CreatePolicyView.as_view(),   name="create_policy"),
    re_path(r"^policies/(?P<policy_id>[^/]+)/$",             views.PolicyDetailView.as_view(),   name="policy_detail"),
    re_path(r"^jobs/$",                          views.BackupJobsView.as_view(),      name="jobs"),
    re_path(r"^jobs/take/$",                     views.TakeBackupView.as_view(),      name="take_backup"),
    re_path(r"^restores/$",                      views.RestoresView.as_view(),        name="restores"),
    re_path(r"^restore/(?P<backup_id>[^/]+)/$",  views.RestoreView.as_view(),        name="restore"),
    re_path(r"^workloads/$",                                           views.WorkloadSnapshotsView.as_view(),  name="workloads"),
    re_path(r"^workloads/(?P<workload_id>[^/]+)/$",                   views.WorkloadDetailView.as_view(),     name="workload_detail"),
    re_path(r"^workloads/run/(?P<policy_id>[^/]+)/$",                 views.RunWorkloadView.as_view(),        name="run_workload"),
    re_path(r"^protection-group/(?P<policy_id>[^/]+)/delete/$",       views.DeleteProtectionGroupView.as_view(), name="delete_protection_group"),
    re_path(r"^recovery-point/(?P<backup_id>[^/]+)/delete/$",         views.DeleteRecoveryPointView.as_view(),    name="delete_recovery_point"),
    re_path(r"^recovery-points/bulk-delete/$",                        views.BulkDeleteRecoveryPointsView.as_view(), name="bulk_delete_recovery_points"),
    re_path(r"^protection-group/(?P<policy_id>[^/]+)/toggle/$",       views.TogglePolicyScheduleView.as_view(),   name="toggle_policy_schedule"),
]
