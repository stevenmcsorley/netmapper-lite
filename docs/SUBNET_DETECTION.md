# Subnet Detection and Network Topology

## How Subnet Detection Works

NetMapper-Lite can detect and visualize **logical subnetworks** within your scanned network.

### ARP Scanning Limitations

**Important:** ARP (Address Resolution Protocol) operates at **Layer 2 (Ethernet)**. This means:

✅ **What ARP CAN find:**
- All devices on the **same broadcast domain** (same switch/LAN)
- Devices in different IP subnets if they're on the same physical network
- Example: If you scan `192.168.0.0/16`, you'll find devices with IPs like:
  - `192.168.1.50` (subnet 1)
  - `192.168.2.100` (subnet 2)
  - `192.168.3.25` (subnet 3)
  - All discovered via ARP on the same LAN!

❌ **What ARP CANNOT find:**
- Devices behind a **router** (different broadcast domain)
- Devices on separate VLANs without proper routing
- Devices that require Layer 3 routing to reach

### How It Works

1. **ARP Scan Phase:**
   ```
   Scan: 192.168.0.0/16
   ↓
   ARP discovers all devices on same LAN
   Finds: 192.168.1.10, 192.168.2.20, 192.168.3.30, etc.
   ```

2. **Subnet Detection Phase:**
   ```
   Analyzes discovered IPs
   Groups by /24 subnets (default):
   - 192.168.1.0/24: 5 hosts
   - 192.168.2.0/24: 3 hosts
   - 192.168.3.0/24: 8 hosts
   ```

3. **Network Map Visualization:**
   ```
   Gateway (center)
     ↓
   Subnet clusters (circles around gateway)
     ↓
   Individual devices (within each subnet cluster)
   ```

## Example: Nested Subnetworks

When you scan a large network like `192.168.0.0/16`, the scanner will:

1. **Discover all devices** on the same LAN (via ARP)
2. **Group them by subnet** (automatically detects /24 boundaries)
3. **Visualize as clusters** in the network map

### Mock Network Example

The fake network includes 3 nested subnets:

- **192.168.100.0/24** (Main network): 19 hosts
- **192.168.101.0/24** (IoT subnet): 4 hosts  
- **192.168.102.0/24** (Guest subnet): 3 hosts

**To test:**
```bash
NETMAPPER_MOCK_SCAN=1 ./netmapper
# Scan: 192.168.0.0/16 (or 192.168.100.0/24)
```

The network map will show:
- Main gateway at center
- IoT subnet as a cluster (if multiple hosts found)
- Guest subnet as a cluster (if multiple hosts found)

## Scanning Remote Subnets

To scan subnetworks behind routers, you have options:

### Option 1: Scan Each Subnet Separately
```bash
# Scan main network
192.168.1.0/24  → Finds: 192.168.1.10, 192.168.1.20...

# Scan IoT subnet (if on separate VLAN)
192.168.101.0/24 → Finds: 192.168.101.10, 192.168.101.20...

# Scan guest network
192.168.102.0/24 → Finds: 192.168.102.50, ...
```

### Option 2: Use Router's Proxy ARP (if enabled)
Some routers support proxy ARP, allowing ARP requests to cross subnet boundaries. This is router-dependent.

### Option 3: Scan from Different Network Interfaces
If your machine has access to multiple subnets:
```bash
# On interface eth0 (main network)
Scan 192.168.1.0/24

# On interface eth1 (IoT network)
Scan 192.168.101.0/24
```

## Visualizing Subnets in Network Map

The network map automatically detects subnets when:

1. **Multiple /24 subnets detected** in scan results
2. **Visualizes as:**
   - Gateway/router at center (blue)
   - Subnet clusters arranged in circle around gateway
   - Devices within each subnet cluster
   - Connection lines from devices to gateway

## Limitations

- **ARP only finds devices on same L2 network**
- **Subnet detection is logical grouping** - it analyzes IP ranges, not actual routing topology
- **For true multi-subnet scanning**, scan each subnet separately and combine results

## Future Enhancements

Potential improvements:
- Scan multiple CIDRs and combine results
- Detect VLANs (if switch supports LLDP/CDP)
- Router detection via traceroute/ping
- Automatic multi-subnet scanning

