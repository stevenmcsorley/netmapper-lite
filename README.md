# NetMapper-Lite

A native Linux desktop network mapper application for discovering devices on your local network using ARP scanning and optional Nmap port scans.

## Overview

NetMapper-Lite is a two-process native Linux application:

1. **Privileged Scanner Service (Backend Helper)**
   - Performs ARP scans, optional Nmap port probes, and OUI vendor lookup
   - Runs as a systemd service or standalone helper with elevated privileges
   - Exposes a local IPC (UNIX domain socket) for communication

2. **GTK Desktop Frontend**
   - User interface with four main tabs:
     - **Scan Results**: View discovered hosts with IP, MAC, hostname, and vendor
     - **History**: Browse past scan results
     - **Network Map**: Visual topology with hover tooltips and interactive nodes
     - **Compare Scans**: Compare two scans to see network changes
   - Features: Nmap port scanning (auto-saved), export to JSON/CSV, host details dialog
   - Runs as normal user; communicates with helper over UNIX socket

## Features

### Core Scanning
- **ARP network scanning** with hostname resolution
- **OUI vendor lookup** - identify device manufacturers from MAC addresses
- **Optional Nmap port scanning** - per-host port scans with service detection
- **Subnet detection** - automatically groups devices by subnetworks for better visualization
- **Auto-detection** - automatically detects your network CIDR and gateway/router
- **Scan cancel** - stop ongoing scans with a cancel button

### Network Visualization
- **Interactive network topology map** with zoom, pan, and clickable nodes
- **Color-coded device types** - Gateway (blue), Servers (orange), IoT (purple), Mobile (yellow), Printers (light blue), Unknown (gray)
- **Port count badges** - shows open port count on map nodes (after Nmap scans)
- **Hover tooltips** - display device info when hovering over map nodes
- **Visual legend** - shows device type colors on the map
- **Subnet clustering** - devices grouped by subnet for complex networks
- **Export map as PNG** - save network topology as an image file

### User Interface
- **Dark mode theme** - Auto/Manual/Dark/Light theme support with system detection
- **Keyboard shortcuts** - Ctrl+S (scan), Ctrl+F (search), Ctrl+E (export), Esc (cancel)
- **Filter/search box** - real-time filtering by IP, hostname, MAC, or vendor
- **Sortable columns** - click column headers to sort results
- **Progress indicator** - shows scan progress with elapsed time
- **Desktop notifications** - alerts when scans complete
- **Window persistence** - remembers window size and position across sessions
- **Network profiles** - save and quickly switch between common CIDRs
- **GTK4 native Linux UI** - modern, responsive desktop interface
- **Scan history** - browse past scans and results in sidebar
- **Host details dialog** - double-click hosts for detailed information with Nmap history

### Data Management
- **SQLite-based scan history** - persistent storage of all scans
- **Nmap results storage** - automatically saves port scans to database
- **Nmap history per host** - view past port scans for any device in host details
- **Nmap scan templates** - Quick, Common, Full, and Service scan presets
- **Scan comparison/diff** - compare two scans to see what changed
- **Export functionality** - save scan results as JSON or CSV
- **Nmap results display** - view open ports and services per host
- **Custom Nmap port ranges** - choose specific ports or ranges to scan

### Security & Operations
- **Secure privilege separation** - helper runs with minimal capabilities
- **Development and production modes** - easy testing and deployment

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
     - The GUI auto-detects your network CIDR on startup
   - Click "Start Scan"
   - Results appear automatically when scan completes

4. **View network map**:
   - After a scan completes, the map auto-generates (or click "Refresh Map")
   - See your network topology with:
     - Gateway/router at the center (blue)
     - Devices arranged by subnet with color coding:
       - Blue: Gateway/Router
       - Orange: Servers
       - Green: Regular devices
       - Purple: IoT devices
       - Yellow: Mobile devices
       - Light Blue: Printers
       - Gray: Unknown devices
     - Connection lines showing network topology
     - Subnet clusters when multiple subnets detected
     - Legend in top-left corner showing device types
   - **Interact with the map:**
     - Click any device node to see detailed information
     - Use "Zoom In" / "Zoom Out" buttons or mouse wheel (Ctrl+scroll)
     - Click "Reset View" to restore default zoom
     - Use "Export Map as Image" to save as PNG
   - The map auto-detects your actual gateway/router from the routing table

5. **Filter and search results**:
   - Use the search box above the results table
   - Type to filter by IP, hostname, MAC address, or vendor
   - Click "Clear" to reset the filter
   - Click column headers to sort results

6. **Cancel scans**:
   - Click "Cancel Scan" button that appears during active scans
   - Immediately stops the scan and restores the UI

7. **Export results**:
   - Click "Export Results" to save scan data as JSON or CSV
   - Click "Export Map as Image" in the Network Map tab to save the visualization

8. **Compare scans**:
   - Go to the "Compare Scans" tab
   - Select two scans from the dropdown menus
   - Click "Compare Scans" to see:
     - **New Hosts**: Devices that appeared in the newer scan
     - **Disappeared**: Devices that vanished between scans
     - **Changed**: Devices with different MAC, hostname, or vendor

9. **Hover tooltips on map**:
   - Hover your mouse over any device node on the network map
   - See a tooltip with IP, hostname, and vendor information
   - The node highlights when hovered

10. **Window persistence**:
    - The app remembers your window size and position
    - Preferences are saved automatically when you close the window
    - Settings stored in ~/.config/netmapper-lite/preferences.json

11. **Dark mode theme**:
    - Click the "🌙 Theme" button in the status bar
    - Toggles between Auto (system), Dark, and Light modes
    - Theme preference is saved automatically

12. **Keyboard shortcuts**:
    - **Ctrl+S**: Start scan
    - **Ctrl+F**: Focus search box
    - **Ctrl+E**: Export results
    - **Esc**: Cancel ongoing scan

13. **Network profiles**:
    - Save common CIDRs as named profiles using the 💾 button
    - Select from dropdown to quickly switch between networks
    - App remembers last scanned CIDR
    - Profiles stored in preferences.json

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
- `nmap_scans` table: ip, scan_timestamp, ports, services, nmap_xml (stores port scan history)

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
├── tests/
│   ├── mock_scanner.py          # Fake network data for testing
│   ├── create_fake_network.sh   # Creates virtual network interfaces
│   └── README_FAKE_NETWORK.md   # Fake network testing guide
├── docs/
│   └── SUBNET_DETECTION.md      # Subnet detection documentation
├── Makefile
└── README.md
```

### Running Tests

```bash
make test
```

### Testing with Fake Network

For testing and development without scanning real networks, you can use the mock scanner:

```bash
# Use mock mode (no root needed, instant results)
NETMAPPER_MOCK_SCAN=1 ./netmapper

# Then scan: 192.168.0.0/16 or 192.168.100.0/24
# You'll get 26 fake devices across 3 subnets:
#   - 192.168.100.0/24 (main network): 21 hosts
#   - 192.168.101.0/24 (IoT subnet): 4 hosts  
#   - 192.168.102.0/24 (guest subnet): 3 hosts
```

**Mock network includes:**
- Gateway/router
- Servers (web, database, backup)
- IoT devices (smart TV, lights, cameras, hub)
- Workstations (laptops, desktop)
- Mobile devices (phones, tablet)
- Printers
- Guest devices

Perfect for testing the network map visualization and UI features!

See `tests/README_FAKE_NETWORK.md` for more details.

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

### Export Map Not Working

**Problem:** Export map dialog shows warning or doesn't save file  
**Solution:** Ensure you've run a scan first to generate the map. The export feature creates a PNG file with the current map view including all nodes, connections, and the legend.

### Search/Filter Not Working

**Problem:** Search box doesn't filter results  
**Solution:** Make sure you have scan results loaded. The filter searches across IP, hostname, MAC address, and vendor columns.

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


