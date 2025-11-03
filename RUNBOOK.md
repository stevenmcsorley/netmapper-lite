# NetMapper-Lite Live Network Test Runbook

This document contains step-by-step instructions for testing NetMapper-Lite on a live LAN.

## Prerequisites

- Linux machine on a live LAN (not isolated VM)
- Python 3.11+ installed
- GTK4 libraries installed
- `scapy` Python package installed
- Optional: `nmap` installed for port scanning
- Root/sudo access for network scanning capabilities

## Test Environment Setup

### 1. Install Dependencies

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-4.0 nmap

# Install Python packages
pip3 install scapy pyyaml PyGObject
```

### 2. Clone/Download Repository

```bash
cd ~/projects
git clone <repository-url> netmapper-lite
cd netmapper-lite
```

Or extract from release archive:
```bash
tar -xzf netmapper-lite.tar.gz
cd netmapper-lite
```

### 3. Update OUI Database (Optional but Recommended)

```bash
python3 backend/scripts/update_oui_db.py --dev
```

This downloads the latest IEEE OUI database for vendor lookup.

## Running the Test

### Step 1: Determine Your Network CIDR

```bash
# Find your network interface and CIDR
ip -4 addr show | grep -E 'inet '

# Example output:
# inet 192.168.1.100/24 scope global wlan0
# This means your network is 192.168.1.0/24
```

### Step 2: Start Helper Service in Dev Mode

**Terminal 1:**
```bash
cd netmapper-lite

# Option A: Run with sudo (required for network capabilities)
sudo python3 backend/netmapper_helper.py --dev

# Option B: Set capabilities on Python first
sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)
python3 backend/netmapper_helper.py --dev
```

Expected output:
```
2025-11-03 15:36:56,129 [INFO] Running in DEV mode (using /tmp socket and user database)
2025-11-03 15:36:56,129 [INFO] Database initialized at /home/user/.local/share/netmapper/netmapper.db
2025-11-03 15:36:56,130 [INFO] Socket listening on /tmp/netmapper-helper.sock
2025-11-03 15:36:56,130 [INFO] NetMapper Helper Service started
```

### Step 3: Start GTK Frontend

**Terminal 2:**
```bash
cd netmapper-lite
python3 frontend/gui.py
```

The GUI window should open.

### Step 4: Perform Network Scan

1. In the GUI, enter your network CIDR (e.g., `192.168.1.0/24`)
2. Click "Start Scan"
3. Wait for scan to complete (typically 10-30 seconds for /24 network)
4. Results should appear in the table with:
   - IP Address
   - MAC Address
   - Hostname (if resolvable)
   - Vendor (if OUI database is present)

### Step 5: Test Nmap Port Scanning

1. Select a host from the scan results
2. Click "Scan Ports (Nmap)" button
3. Wait for Nmap scan to complete (may take 30-60 seconds)
4. Results dialog should show open ports, services, and versions

### Step 6: Verify Results in Database

```bash
# Check SQLite database
sqlite3 ~/.local/share/netmapper/netmapper.db

# View recent scans
sqlite> SELECT id, cidr, ts, host_count FROM scans ORDER BY ts DESC LIMIT 5;

# View hosts from latest scan (replace SCAN_ID)
sqlite> SELECT ip, mac, hostname, vendor FROM hosts WHERE scan_id='<SCAN_ID>';

# Exit
sqlite> .quit
```

## Expected Results

### Successful Scan Output

**Helper Logs (Terminal 1):**
```
[INFO] Starting scan <scan-id> for 192.168.1.0/24
[INFO] Scan <scan-id> found 15 hosts
[INFO] Scan <scan-id> completed and stored
```

**GUI Status:**
```
Scan complete: 15 hosts found
```

**Database Records:**
- One entry in `scans` table
- Multiple entries in `hosts` table (one per discovered host)
- Vendor information populated if OUI database exists

### Example Test Results

```
Scan ID: 97af116c-8139-4cdb-945b-9f091a38c9e3
CIDR: 192.168.1.0/24
Timestamp: 1699034567
Hosts Found: 15

Sample Hosts:
- 192.168.1.1 | aa:bb:cc:dd:ee:01 | router.local | Cisco Systems
- 192.168.1.100 | aa:bb:cc:dd:ee:64 | desktop.local | Intel Corporation
- 192.168.1.101 | aa:bb:cc:dd:ee:65 | - | Apple Inc.
```

## Troubleshooting

### Helper Not Starting

**Issue:** Permission denied for raw sockets
**Solution:**
```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)
# Or run helper with sudo
```

### GUI Cannot Connect

**Issue:** Socket connection refused
**Solution:**
- Verify helper is running: `ps aux | grep netmapper_helper`
- Check socket exists: `ls -l /tmp/netmapper-helper.sock`
- Check socket permissions: should be readable by your user

### No Hosts Found

**Issue:** Scan returns 0 hosts
**Possible causes:**
- Wrong CIDR network (verify with `ip addr`)
- Network interface doesn't have proper permissions
- Firewall blocking ARP packets
- No devices on network (unlikely)

**Solution:**
- Verify network: `ip route | grep default`
- Check interface: `ip link show`
- Try scanning with `nmap` directly to verify network access

### Nmap Not Working

**Issue:** Nmap scan fails or returns no ports
**Solution:**
- Verify nmap is installed: `which nmap`
- Check if target host is reachable: `ping <ip>`
- Some hosts may have no open ports (firewall)

### OUI Vendor Not Showing

**Issue:** Vendor column shows "-" for all hosts
**Solution:**
- Update OUI database: `python3 backend/scripts/update_oui_db.py --dev`
- Verify database exists: `ls -l ~/.local/share/netmapper/oui.db`

## Cleanup

After testing:

```bash
# Stop helper service (Ctrl+C in Terminal 1)
# Close GUI (Terminal 2)

# Optional: Clean up test data
rm -f /tmp/netmapper-helper.sock
rm -f ~/.local/share/netmapper/netmapper.db
rm -f ~/.local/share/netmapper/oui.db
```

## Production Installation

For production use, use the installation script:

```bash
sudo bash packaging/install.sh
sudo systemctl start netmapper-helper.service
```

See `README.md` for full production installation instructions.

