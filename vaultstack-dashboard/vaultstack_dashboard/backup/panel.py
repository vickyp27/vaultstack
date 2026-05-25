from django.utils.translation import gettext_lazy as _
import horizon


class BackupPanel(horizon.Panel):
    name = _("Data Protection")
    slug = "backup"
