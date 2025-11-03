# Quick Testing Guide

## Problem: "Operation not permitted" or "Found 0 hosts"

If your scan finds 0 hosts, check the helper logs:
```bash
tail -20 /tmp/helper.log
```

If you see `[ERROR] ARP scan error: [Errno 1] Operation not permitted`, the helper needs network privileges.

## Solution

### Method 1: Set Capabilities (Recommended - one-time setup)

```bash
cd /home/dev/projects/software/netmapper-lite
sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)
```

Then start helper normally:
```bash
python3 backend/netmapper_helper.py --dev
```

### Method 2: Run Helper with Sudo

```bash
sudo python3 backend/netmapper_helper.py --dev
```

**Note:** GUI should NOT run with sudo - only the helper needs privileges.

### Method 3: Use Fix Script

```bash
./fix_permissions.sh
```

## Verify It Works

After setting capabilities or starting with sudo:

```bash
# Quick test
python3 -c "
from backend.scanner import arp_scan
hosts = arp_scan('192.168.1.0/24', timeout=3)
print(f'Found {len(hosts)} hosts')
"
```

If it works, you should see hosts. If still 0, check:
- Correct CIDR network
- Network interface is active
- You're on the network you're scanning

