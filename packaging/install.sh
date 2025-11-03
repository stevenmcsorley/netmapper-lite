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

# Set capabilities on helper binary (better than setting on Python itself)
# Note: For production, prefer compiled helper with capabilities
echo "Setting network capabilities..."
if command -v setcap > /dev/null; then
    HELPER_BINARY="/usr/lib/netmapper/netmapper_helper.py"
    # Try to set capabilities on the helper script (requires Python interpreter path in shebang)
    # Alternative: set on a wrapper binary or use systemd capabilities
    PYTHON_PATH=$(which python3)
    if [ -n "$PYTHON_PATH" ]; then
        # Try setting capabilities on Python interpreter (if allowed)
        if setcap cap_net_raw,cap_net_admin+eip "$PYTHON_PATH" 2>/dev/null; then
            echo "✓ Network capabilities set on Python interpreter"
        else
            echo "⚠ Warning: Could not set capabilities on Python (may require root or different approach)"
            echo "  The helper will run as root via systemd (which is acceptable for this service)"
            echo "  For better security, consider compiling a small helper binary with capabilities"
        fi
    else
        echo "⚠ Warning: Could not find python3. Helper will run as root."
    fi
else
    echo "⚠ Warning: setcap not found. Helper will run as root via systemd."
fi

# Install Python dependencies if needed
echo "Checking Python dependencies..."
if command -v pip3 > /dev/null; then
    echo "  Installing backend dependencies..."
    # Try pip3 install, fallback to python3 -m pip
    if pip3 install --quiet --user scapy pyyaml 2>/dev/null; then
        echo "✓ Backend dependencies installed"
    elif python3 -m pip install --quiet --user scapy pyyaml 2>/dev/null; then
        echo "✓ Backend dependencies installed (via python3 -m pip)"
    else
        echo "  ⚠ Warning: Could not install dependencies automatically"
        echo "  Please install manually: pip3 install scapy pyyaml"
        echo "  Or use system package manager: sudo apt-get install python3-scapy python3-yaml"
    fi
elif python3 -m pip --version >/dev/null 2>&1; then
    echo "  Installing backend dependencies (via python3 -m pip)..."
    if python3 -m pip install --quiet --user scapy pyyaml 2>/dev/null; then
        echo "✓ Backend dependencies installed"
    else
        echo "  ⚠ Warning: Could not install dependencies automatically"
        echo "  Please install manually: python3 -m pip install scapy pyyaml"
    fi
else
    echo "  ⚠ Warning: pip3 not found. Please install dependencies manually:"
    echo "    sudo apt-get install python3-scapy python3-yaml"
    echo "    or: pip3 install scapy pyyaml"
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

