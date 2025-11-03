# Fake Network Testing

This directory contains tools to create a fake network with multiple devices for testing NetMapper-Lite.

## Quick Start

### Option 1: Mock Scanner (No Root Required)

Uses fake data - perfect for UI testing without network setup:

```bash
# Test the mock scanner
python3 tests/test_fake_network.py

# Or use mock mode in helper
NETMAPPER_MOCK_SCAN=1 python3 backend/netmapper_helper.py --dev
```

### Option 2: Real Fake Network (Requires Root)

Creates actual virtual network interfaces:

```bash
# In one terminal (as root):
sudo tests/create_fake_network.sh

# In another terminal:
./netmapper
# Then scan: 192.168.100.0/24
```

## Fake Network Topology

The fake network (`192.168.100.0/24`) includes:

### Gateway
- **192.168.100.1** - Router (Router-Tech)

### Servers (Cluster)
- **192.168.100.10** - web1.local (ServerCorp)
- **192.168.100.11** - db1.local (ServerCorp)
- **192.168.100.12** - backup.local (ServerCorp)

### IoT Devices
- **192.168.100.20** - tv.living-room.local (IoT-Media)
- **192.168.100.21** - light.kitchen.local (IoT-Home)
- **192.168.100.22** - camera.front.local (Hikvision)
- **192.168.100.23** - camera.back.local (Hikvision)
- **192.168.100.60** - smart-hub.local (HomeHub)

### Workstations
- **192.168.100.30** - laptop-alice.local (Dell)
- **192.168.100.31** - laptop-bob.local (HP)
- **192.168.100.32** - desktop.local (CustomPC)

### Mobile Devices
- **192.168.100.40** - phone-alice.local (Apple)
- **192.168.100.41** - phone-bob.local (Samsung)
- **192.168.100.42** - tablet.local (Apple)

### Printers
- **192.168.100.50** - printer.office.local (HP-Printer)
- **192.168.100.51** - printer.home.local (Canon)

### Guest Devices
- **192.168.100.100** - (no hostname, Unknown vendor)
- **192.168.100.101** - (no hostname, Unknown vendor)

**Total: 19 devices + 1 gateway = 20 nodes**

## Network Map Visualization

When you scan this network, you'll see:
- **Gateway** (192.168.100.1) at the center in blue
- **Servers** grouped together (10-12)
- **IoT devices** scattered (20-23, 60)
- **Workstations** (30-32)
- **Mobile devices** (40-42)
- **Printers** (50-51)
- **Guest devices** (100-101)

This creates an interesting topology perfect for testing the network map visualization!

## Usage Examples

### Test Mock Scanner
```bash
python3 tests/test_fake_network.py
```

### Test Real Fake Network
```bash
# Terminal 1: Start fake network
sudo tests/create_fake_network.sh

# Terminal 2: Test scanner
python3 tests/test_fake_network.py --real

# Terminal 3: Run NetMapper-Lite
./netmapper
# Then scan: 192.168.100.0/24
```

### Cleanup Fake Network

The fake network script automatically cleans up when you press Ctrl+C.

To manually cleanup:
```bash
# Remove all test namespaces
sudo ip netns list | grep netmapper-test | awk '{print $1}' | xargs -r -n1 sudo ip netns delete

# Remove bridge
sudo ip link delete br-netmapper-test 2>/dev/null || true

# Remove veth pairs
sudo ip link show | grep veth-netmapper-test | cut -d: -f2 | awk '{print $1}' | xargs -r -n1 sudo ip link delete
```

## Integration with Tests

The fake network can be used in integration tests:

```python
import os
os.environ["NETMAPPER_MOCK_SCAN"] = "1"
from backend.scanner import arp_scan
hosts = arp_scan("192.168.100.0/24")  # Returns fake data
```

## Customization

Edit `tests/create_fake_network.sh` to add/modify devices:

```bash
declare -a DEVICES=(
    "my-device,192.168.100.200,my-host.local,MyVendor,role"
    # Add more...
)
```

Or edit `tests/mock_scanner.py` to change the FAKE_NETWORK dictionary.

