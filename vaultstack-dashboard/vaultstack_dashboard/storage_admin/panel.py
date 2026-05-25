from django.utils.translation import gettext_lazy as _
import horizon


class VaultStackAdminPanel(horizon.Panel):
    name = _("Storage Config")
    slug = "vaultstack_admin"
