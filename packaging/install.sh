#!/bin/bash
# NetMapper-Lite Installation Script
# Run with sudo

set -e

echo "Installing NetMapper-Lite..."

# Create netmapper group if it doesn't exist
if ! getent group netmapper > /dev/null 2>&1; then
    groupadd netmapper
    echo "Created 'netmapper' group"
fi

# Add current user (or $SUDO_USER) to netmapper group
if [ -n "$SUDO_USER" ]; then
    usermod -aG netmapper "$SUDO_USER"
    echo "Added $SUDO_USER to netmapper group"
fi

# Create directories
mkdir -p /usr/lib/netmapper
mkdir -p /var/lib/netmapper
mkdir -p /run/netmapper

# Copy helper to system location
cp backend/netmapper_helper.py /usr/lib/netmapper/
cp backend/scanner.py /usr/lib/netmapper/
chmod +x /usr/lib/netmapper/netmapper_helper.py

# Install systemd service
cp packaging/netmapper-helper.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable netmapper-helper.service

# Set permissions on database directory
chown root:netmapper /var/lib/netmapper
chmod 775 /var/lib/netmapper

# Set socket permissions (will be set by helper, but ensure directory exists)
chown root:netmapper /run/netmapper
chmod 775 /run/netmapper

# Set capabilities on Python (or use compiled helper)
# Note: For production, prefer compiled helper with capabilities
if command -v setcap > /dev/null; then
    setcap cap_net_raw,cap_net_admin+eip /usr/bin/python3 2>/dev/null || \
        echo "Warning: Could not set capabilities. Helper may need root privileges."
fi

echo ""
echo "Installation complete!"
echo ""
echo "To start the service, run:"
echo "  sudo systemctl start netmapper-helper.service"
echo ""
echo "To check status:"
echo "  sudo systemctl status netmapper-helper.service"
echo ""
echo "Note: You may need to log out and back in for group changes to take effect."

