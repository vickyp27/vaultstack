#!/bin/bash
# Install VaultStack Horizon plugin on a Kolla-Ansible deployment
# Run this on the node where Horizon container is running

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
HORIZON_CONTAINER="horizon"
API_URL="${VAULTSTACK_API_URL:-http://localhost:8000}"

echo "============================================"
echo " Installing VaultStack Plugin (Kolla)"
echo "============================================"

# 1. Install the plugin package inside the Horizon container
echo "[1/4] Installing Python package inside Horizon container..."
docker exec "$HORIZON_CONTAINER" pip install "$PLUGIN_DIR"

# 2. Add VAULTSTACK_API_URL to Kolla's Horizon local_settings customization
#    Edit /etc/kolla/config/horizon/custom_local_settings (create if not exists)
KOLLA_HORIZON_CFG="/etc/kolla/config/horizon"
mkdir -p "$KOLLA_HORIZON_CFG"
CUSTOM_SETTINGS="$KOLLA_HORIZON_CFG/custom_local_settings"

if ! grep -q "VAULTSTACK_API_URL" "$CUSTOM_SETTINGS" 2>/dev/null; then
    echo "" >> "$CUSTOM_SETTINGS"
    echo "# VaultStack Backup Plugin" >> "$CUSTOM_SETTINGS"
    echo "VAULTSTACK_API_URL = '$API_URL'" >> "$CUSTOM_SETTINGS"
    echo "Added VAULTSTACK_API_URL to $CUSTOM_SETTINGS"
fi

# 3. Collect static files inside container
echo "[3/4] Collecting static files..."
docker exec "$HORIZON_CONTAINER" python manage.py collectstatic --noinput 2>/dev/null || true

# 4. Restart the Horizon container
echo "[4/4] Restarting Horizon container..."
docker restart "$HORIZON_CONTAINER"

echo ""
echo "============================================"
echo " Done! Open Horizon:"
echo "  Project -> Data Protection"
echo "  Admin   -> VaultStack -> Storage Config"
echo "============================================"
echo ""
echo "NOTE: If enabled files are not auto-discovered, copy them manually:"
echo "  docker exec $HORIZON_CONTAINER sh -c \\"
echo "    'cp /usr/local/lib/python*/dist-packages/vaultstack_dashboard/enabled/_9*.py"
echo "        /usr/share/openstack-dashboard/openstack_dashboard/enabled/'"
echo "  docker restart $HORIZON_CONTAINER"
