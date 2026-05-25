#!/bin/bash
# Run this script ON the DevStack VM to install VaultStack Horizon plugin

set -e

HORIZON_DIR="/opt/stack/horizon"
PLUGIN_DIR="$(dirname "$0")"

echo "============================================"
echo " Installing VaultStack Horizon Plugin"
echo "============================================"

# Add VAULTSTACK_API_URL to Horizon local_settings
SETTINGS_FILE="$HORIZON_DIR/openstack_dashboard/local/local_settings.py"
if ! grep -q "VAULTSTACK_API_URL" "$SETTINGS_FILE"; then
    echo "" >> "$SETTINGS_FILE"
    echo "# VaultStack API" >> "$SETTINGS_FILE"
    echo "VAULTSTACK_API_URL = 'http://localhost:8000'" >> "$SETTINGS_FILE"
    echo "Added VAULTSTACK_API_URL to local_settings.py"
fi

# Install plugin in Horizon's venv
HORIZON_VENV="/opt/stack/data/venv"
if [ -f "$HORIZON_VENV/bin/pip" ]; then
    sudo "$HORIZON_VENV/bin/pip" install -e "$PLUGIN_DIR"
else
    sudo pip3 install -e "$PLUGIN_DIR"
fi

# Copy enabled file to Horizon
sudo cp "$PLUGIN_DIR/vaultstack_dashboard/enabled/_90_vaultstack.py" \
    "$HORIZON_DIR/openstack_dashboard/enabled/"

# Collect static files
cd "$HORIZON_DIR"
sudo python3 manage.py collectstatic --noinput 2>/dev/null || true
sudo python3 manage.py compress --force 2>/dev/null || true

# Restart Apache
sudo service apache2 restart || sudo systemctl restart apache2

echo ""
echo "============================================"
echo " VaultStack Plugin Installed!"
echo " Open Horizon and look for 'VaultStack' in sidebar"
echo "============================================"
