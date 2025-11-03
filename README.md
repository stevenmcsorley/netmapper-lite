# NetMapper-Lite

A native Linux desktop network mapper application for discovering devices on your local network using ARP scanning and optional Nmap port scans.

## Overview

NetMapper-Lite is a two-process native Linux application:

1. **Privileged Scanner Service (Backend Helper)**
   - Performs ARP scans, optional Nmap port probes, and OUI vendor lookup
   - Runs as a systemd service or standalone helper with elevated privileges
   - Exposes a local IPC (UNIX domain socket) for communication

2. **GTK Desktop Frontend**
   - User interface for triggering scans, viewing results, and browsing history
   - Runs as normal user; communicates with helper over UNIX socket

## Features

- ARP network scanning with hostname resolution
- SQLite-based scan history
- GTK4 native Linux UI
- Secure privilege separation (helper runs with minimal capabilities)
- Development and production modes

## Requirements

- Python 3.11+ (3.10 acceptable but 3.11 preferred)
- GTK4 development libraries (`gir1.2-gtk-4.0` on Debian/Ubuntu)
- scapy library (for ARP scanning)
- Optional: nmap (for port scanning)
- sudo/root access for installing and running the helper service

### Installing GTK4 dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-4.0 python3-pip
```

**Fedora:**
```bash
sudo dnf install python3-gobject python3-gobject-devel gtk4
```

**Arch Linux:**
```bash
sudo pacman -S python-gobject gtk4
```

## Quick Start

### Single Command Launch

```bash
cd netmapper-lite
./netmapper
```

That's it! This starts the helper and GUI together. You may be prompted for sudo password once for network permissions.

**Optional:** Install to PATH so you can run from anywhere:
```bash
./netmapper.sh  # Installs launcher to ~/.local/bin
netmapper       # Then run from anywhere
```

---

## Quick Start (Development Mode - Manual)

### 1. Clone and Setup

```bash
git clone <repo-url>
cd netmapper-lite
```

### 2. Install Backend Dependencies

```bash
make install-backend
# Or manually:
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Install Frontend Dependencies

```bash
make install-frontend
# Or manually:
cd frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Run Helper (Development Mode)

In a terminal, start the helper service in development mode:

```bash
# Development mode uses /tmp socket (no root needed for socket, but may need for scanning)
make run-helper-dev

# Or with sudo if you get permission errors:
make run-helper-dev-sudo
```

**Note:** ARP scanning requires network capabilities. In development mode without systemd, you may need:
```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)
```

### 5. Run GUI

In another terminal:

```bash
make run-gui-dev
# Or:
python3 frontend/gui.py
```

### 6. Test Scan

1. Enter a CIDR network (e.g., `192.168.1.0/24`)
2. Click "Start Scan"
3. Wait for results to appear

## Production Installation

### Option 1: Manual Installation

1. Copy files to system locations:
```bash
sudo cp -r backend/* /usr/lib/netmapper/
sudo cp frontend/gui.py /usr/local/bin/netmapper-gui
sudo chmod +x /usr/local/bin/netmapper-gui
```

2. Install systemd service:
```bash
sudo cp packaging/netmapper-helper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable netmapper-helper.service
sudo systemctl start netmapper-helper.service
```

3. Create netmapper group and add your user:
```bash
sudo groupadd netmapper
sudo usermod -aG netmapper $USER
# Log out and back in for group changes to take effect
```

4. Set socket permissions:
```bash
sudo chown root:netmapper /var/run/netmapper-helper.sock
sudo chmod 660 /var/run/netmapper-helper.sock
```

### Option 2: Using Install Script

```bash
sudo bash packaging/install.sh
sudo systemctl start netmapper-helper.service
```

## Usage

1. **Start the helper service** (if not running as systemd):
   ```bash
   sudo python3 /usr/lib/netmapper/netmapper_helper.py
   ```

2. **Launch the GUI**:
   ```bash
   python3 frontend/gui.py
   # Or if installed: netmapper-gui
   ```

3. **Perform a scan**:
   - Enter CIDR network (e.g., `192.168.1.0/24`)
   - Click "Start Scan"
   - Results appear automatically when scan completes

## Architecture

### IPC Communication

The frontend and backend communicate via UNIX domain socket using JSON messages:

**Request:**
```json
{"cmd": "scan", "cidr": "192.168.1.0/24"}
```

**Response:**
```json
{"status": "started", "scan_id": "uuid-here"}
```

Results are stored in SQLite and can be retrieved via:
```json
{"cmd": "get_results", "scan_id": "uuid-here"}
```

### Database Schema

Scans are stored in SQLite with the following structure:
- `scans` table: scan_id, cidr, timestamp, host_count
- `hosts` table: scan_id, ip, mac, hostname, vendor

## Development

### Project Structure

```
netmapper-lite/
├── backend/
│   ├── scanner.py              # ARP/Nmap scanning functions
│   ├── netmapper_helper.py     # Helper service (UNIX socket server)
│   └── requirements.txt
├── frontend/
│   ├── gui.py                  # GTK4 application
│   ├── app/                    # UI modules (if modularized)
│   └── requirements.txt
├── packaging/
│   ├── netmapper-helper.service
│   └── install.sh
├── Makefile
└── README.md
```

### Running Tests

```bash
make test
```

### Clean Build Artifacts

```bash
make clean
```

## Troubleshooting

### Connection Refused

**Problem:** GUI shows "Connection refused"  
**Solution:** Helper isn't running. Use the launcher:
```bash
./netmapper
```

### Permission Denied / Found 0 Hosts

**Problem:** Scan completes but finds 0 hosts, helper logs show "Operation not permitted"  
**Solution:** Helper needs network permissions. Options:

1. **Use the launcher** (handles this automatically):
   ```bash
   ./netmapper  # Prompts for sudo if needed
   ```

2. **Set capabilities** (one-time setup):
   ```bash
   sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)
   ```

3. **Run helper with sudo manually:**
   ```bash
   sudo python3 backend/netmapper_helper.py --dev
   ```

### GTK Import Errors

**Problem:** `ImportError: No module named 'gi'`  
**Solution:** Install GTK4 packages:
```bash
sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-4.0
```

### Helper Logs

Check helper status and logs:
```bash
# Development mode
tail -f /tmp/helper.log

# Production mode (systemd)
sudo journalctl -u netmapper-helper.service -f
```

## Security Notes

- Helper service requires elevated privileges for raw socket access
- Use `setcap` to grant minimal capabilities instead of full root where possible
- Socket is protected by group permissions (`netmapper` group)
- Rate-limit port scans (Nmap) to avoid network flooding
- Helper service runs isolated from GUI for privilege separation

## License

[Specify your license here]

## Contributing

[Contributing guidelines]


