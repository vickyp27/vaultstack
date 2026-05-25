from django.urls import re_path
from vaultstack_dashboard.backup import views

urlpatterns = [
    re_path(r"^$", views.StorageSettingsView.as_view(), name="index"),
    re_path(r"^test-connection/$", views.TestS3ConnectionView.as_view(), name="test_connection"),
]
