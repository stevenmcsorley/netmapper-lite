#!/bin/bash
# NetMapper-Lite Installation Script
# Run with sudo

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Installing NetMapper-Lite..."
echo "Project root: $PROJECT_ROOT"

# Create netmapper group if it doesn't exist
if ! getent group netmapper > /dev/null 2>&1; then
    groupadd netmapper
    echo "✓ Created 'netmapper' group"
else
    echo "✓ 'netmapper' group already exists"
fi

# Add current user (or $SUDO_USER) to netmapper group
if [ -n "$SUDO_USER" ]; then
    if groups "$SUDO_USER" | grep -q "\bnetmapper\b"; then
        echo "✓ $SUDO_USER already in netmapper group"
    else
        usermod -aG netmapper "$SUDO_USER"
        echo "✓ Added $SUDO_USER to netmapper group"
    fi
else
    echo "Warning: SUDO_USER not set, skipping user group addition"
fi

# Create directories
echo "Creating directories..."
mkdir -p /usr/lib/netmapper
mkdir -p /var/lib/netmapper
mkdir -p /run/netmapper
echo "✓ Directories created"

# Copy helper files to system location
echo "Copying helper files..."
cp "$PROJECT_ROOT/backend/netmapper_helper.py" /usr/lib/netmapper/
cp "$PROJECT_ROOT/backend/scanner.py" /usr/lib/netmapper/
chmod +x /usr/lib/netmapper/netmapper_helper.py
chmod 644 /usr/lib/netmapper/scanner.py
echo "✓ Helper files installed"

# Copy OUI database if it exists
if [ -f "$PROJECT_ROOT/backend/oui.db" ]; then
    cp "$PROJECT_ROOT/backend/oui.db" /usr/lib/netmapper/
    chmod 644 /usr/lib/netmapper/oui.db
    echo "✓ OUI database copied"
fi

# Install systemd service
echo "Installing systemd service..."
cp "$PROJECT_ROOT/packaging/netmapper-helper.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable netmapper-helper.service
echo "✓ Systemd service installed and enabled"

# Set permissions on database directory
chown root:netmapper /var/lib/netmapper
chmod 775 /var/lib/netmapper
echo "✓ Database directory permissions set"

# Set socket directory permissions
chown root:netmapper /run/netmapper
chmod 775 /run/netmapper
echo "✓ Socket directory permissions set"

# Set socket path permissions (helper will create, but ensure parent dir is correct)
SOCKET_PATH="/var/run/netmapper-helper.sock"
if [ -e "$SOCKET_PATH" ]; then
    chown root:netmapper "$SOCKET_PATH"
    chmod 660 "$SOCKET_PATH"
    echo "✓ Existing socket permissions updated"
fi

# Set capabilities on Python (or use compiled helper)
# Note: For production, prefer compiled helper with capabilities
echo "Setting network capabilities..."
if command -v setcap > /dev/null; then
    if setcap cap_net_raw,cap_net_admin+eip /usr/bin/python3 2>/dev/null; then
        echo "✓ Network capabilities set on Python"
    else
        echo "⚠ Warning: Could not set capabilities. Helper will run as root."
        echo "  Consider compiling a small helper binary for production use."
    fi
else
    echo "⚠ Warning: setcap not found. Helper will run as root."
fi

# Install Python dependencies if needed
echo "Checking Python dependencies..."
if command -v pip3 > /dev/null; then
    echo "  Installing backend dependencies..."
    pip3 install --quiet scapy pyyaml 2>/dev/null || echo "  ⚠ Warning: Could not install dependencies via pip3"
else
    echo "  ⚠ Warning: pip3 not found. Please install dependencies manually."
fi

echo ""
echo "========================================="
echo "Installation complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Start the service:"
echo "     sudo systemctl start netmapper-helper.service"
echo ""
echo "  2. Check service status:"
echo "     sudo systemctl status netmapper-helper.service"
echo ""
echo "  3. View service logs:"
echo "     sudo journalctl -u netmapper-helper.service -f"
echo ""
echo "  4. Run the GUI:"
echo "     python3 $PROJECT_ROOT/frontend/gui.py"
echo ""
echo "  5. Update OUI database (optional):"
echo "     python3 $PROJECT_ROOT/backend/scripts/update_oui_db.py"
echo ""
echo "⚠ Note: You may need to log out and back in for group changes to take effect."
echo ""
echo "⚠ TODO: For production, consider compiling a small helper binary (Rust/C)"
echo "   instead of using Python with setcap. See TODO.md in repository."

