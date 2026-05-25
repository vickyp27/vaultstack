  #!/bin/bash
# Install VaultStack Horizon plugin on an RDO/TripleO/Packstack deployment
# Run this on the controller node as root

set -e

PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
API_URL="${VAULTSTACK_API_URL:-http://localhost:8000}"

# Horizon paths on RDO (RHEL/CentOS/Rocky)
HORIZON_DIR="/usr/share/openstack-dashboard"
HORIZON_PYTHON="/usr/bin/python3"
ENABLED_DIR="$HORIZON_DIR/openstack_dashboard/enabled"
LOCAL_SETTINGS="$HORIZON_DIR/openstack_dashboard/local/local_settings.py"

echo "============================================"
echo " Installing VaultStack Plugin (RDO)"
echo "============================================"

# 1. Install plugin into system Python / Horizon venv
echo "[1/4] Installing Python package..."
if [ -f "/usr/share/openstack-dashboard/bin/pip" ]; then
    /usr/share/openstack-dashboard/bin/pip install "$PLUGIN_DIR"
elif [ -f "/usr/bin/pip3" ]; then
    pip3 install "$PLUGIN_DIR"
else
    python3 -m pip install "$PLUGIN_DIR"
fi

# 2. Copy enabled files (fallback if entry_points auto-discovery doesn't work)
echo "[2/4] Copying enabled files to Horizon..."
cp "$PLUGIN_DIR"/vaultstack_dashboard/enabled/_9*.py "$ENABLED_DIR/"

# 3. Add VAULTSTACK_API_URL to local_settings.py
if [ -f "$LOCAL_SETTINGS" ] && ! grep -q "VAULTSTACK_API_URL" "$LOCAL_SETTINGS"; then
    echo "" >> "$LOCAL_SETTINGS"
    echo "# VaultStack Backup Plugin" >> "$LOCAL_SETTINGS"
    echo "VAULTSTACK_API_URL = '$API_URL'" >> "$LOCAL_SETTINGS"
    echo "Added VAULTSTACK_API_URL to $LOCAL_SETTINGS"
fi

# 4. Collect static + restart Apache
echo "[4/4] Collecting static files and restarting Apache..."
cd "$HORIZON_DIR"
python3 manage.py collectstatic --noinput 2>/dev/null || true
systemctl restart httpd || service httpd restart

echo ""
echo "============================================"
echo " Done! Open Horizon:"
echo "  Project -> Data Protection"
echo "  Admin   -> VaultStack -> Storage Config"
echo "============================================"
