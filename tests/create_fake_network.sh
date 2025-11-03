#!/bin/bash
# Create a fake network with multiple nodes for testing NetMapper-Lite
# This creates virtual network interfaces with different IPs to simulate devices

set -e

TEST_NET="192.168.100.0/24"
TEST_GATEWAY="192.168.100.1"
NAMESPACE_PREFIX="netmapper-test"

echo "=========================================="
echo "Creating Fake Network for Testing"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ This script must be run as root (for creating network interfaces)"
    echo "Run: sudo $0"
    exit 1
fi

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Cleaning up fake network..."
    # Remove network namespaces
    for ns in $(ip netns list | grep "$NAMESPACE_PREFIX" 2>/dev/null | awk '{print $1}'); do
        echo "  Removing namespace: $ns"
        ip netns delete "$ns" 2>/dev/null || true
    done
    # Remove veth pairs (both ends)
    for iface in $(ip link show | grep -E "veth-.*-$NAMESPACE_PREFIX|veth-.*-host|veth-.*-device" | cut -d: -f2 | awk '{print $1}'); do
        echo "  Removing interface: $iface"
        ip link delete "$iface" 2>/dev/null || true
    done
    # Remove bridge if it exists
    if ip link show "$BRIDGE_NAME" &>/dev/null; then
        echo "  Removing bridge: $BRIDGE_NAME"
        ip link set "$BRIDGE_NAME" down 2>/dev/null || true
        ip link delete "$BRIDGE_NAME" 2>/dev/null || true
    fi
    echo "✅ Cleanup complete"
}

trap cleanup EXIT

echo "Creating network topology:"
echo "  Gateway: $TEST_GATEWAY"
echo "  Network: $TEST_NET"
echo ""

# Create a bridge for the fake network
BRIDGE_NAME="br-$NAMESPACE_PREFIX"
echo "📡 Creating bridge: $BRIDGE_NAME"

# Check if bridge exists
if ip link show "$BRIDGE_NAME" &>/dev/null; then
    echo "  Bridge already exists, cleaning up first..."
    ip link set "$BRIDGE_NAME" down 2>/dev/null || true
    ip link delete "$BRIDGE_NAME" 2>/dev/null || true
    sleep 1
fi

# Create fresh bridge
ip link add "$BRIDGE_NAME" type bridge
ip addr add "$TEST_GATEWAY/24" dev "$BRIDGE_NAME"
ip link set "$BRIDGE_NAME" up
echo "  ✅ Bridge created and started"

# Define fake devices with interesting topology
# Format: name,ip,hostname,vendor,role
declare -a DEVICES=(
    # Core infrastructure
    "gateway,$TEST_GATEWAY,router.local,Router-Tech,gateway"
    
    # Servers (different subnets/roles)
    "web-server,192.168.100.10,web1.local,ServerCorp,server"
    "db-server,192.168.100.11,db1.local,ServerCorp,server"
    "backup-server,192.168.100.12,backup.local,ServerCorp,server"
    
    # IoT devices
    "smart-tv,192.168.100.20,tv.living-room.local,IoT-Media,iot"
    "smart-light,192.168.100.21,light.kitchen.local,IoT-Home,iot"
    "camera-1,192.168.100.22,camera.front.local,Hikvision,iot"
    "camera-2,192.168.100.23,camera.back.local,Hikvision,iot"
    
    # Workstations
    "laptop-1,192.168.100.30,laptop-alice.local,Dell,workstation"
    "laptop-2,192.168.100.31,laptop-bob.local,HP,workstation"
    "desktop-1,192.168.100.32,desktop.local,CustomPC,workstation"
    
    # Mobile devices
    "phone-1,192.168.100.40,phone-alice.local,Apple,mobile"
    "phone-2,192.168.100.41,phone-bob.local,Samsung,mobile"
    "tablet-1,192.168.100.42,tablet.local,Apple,mobile"
    
    # Printers and peripherals
    "printer-1,192.168.100.50,printer.office.local,HP-Printer,printer"
    "printer-2,192.168.100.51,printer.home.local,Canon,printer"
    
    # Smart home hub
    "hub,192.168.100.60,smart-hub.local,HomeHub,iot"
    
    # Guest devices
    "guest-1,192.168.100.100,guest-phone.local,Unknown,guest"
    "guest-2,192.168.100.101,guest-laptop.local,Unknown,guest"
)

echo ""
echo "🔧 Creating ${#DEVICES[@]} virtual devices..."

DEVICE_COUNT=0
for device_info in "${DEVICES[@]}"; do
    IFS=',' read -r name ip hostname vendor role <<< "$device_info"
    DEVICE_COUNT=$((DEVICE_COUNT + 1))
    
    # Create namespace for this device (better isolation)
    ns_name="${NAMESPACE_PREFIX}-${name}"
    veth_host="veth-${name}-host"
    veth_device="veth-${name}-device"
    
    echo "  [$DEVICE_COUNT] Creating: $name ($ip)"
    
    # Create namespace
    ip netns add "$ns_name" 2>/dev/null || echo "    Namespace exists, reusing..."
    
    # Create veth pair
    ip link add "$veth_host" type veth peer name "$veth_device" 2>/dev/null || {
        echo "    Veth pair exists, cleaning up..."
        ip link delete "$veth_host" 2>/dev/null || true
        ip link add "$veth_host" type veth peer name "$veth_device" 2>/dev/null
    }
    
    # Move device end into namespace
    ip link set "$veth_device" netns "$ns_name"
    
    # Add host end to bridge
    ip link set "$veth_host" master "$BRIDGE_NAME"
    ip link set "$veth_host" up
    
    # Configure device in namespace
    ip -n "$ns_name" link set "$veth_device" up
    ip -n "$ns_name" addr add "${ip}/24" dev "$veth_device"
    ip -n "$ns_name" route add default via "$TEST_GATEWAY"
    
    # Set hostname in namespace
    ip netns exec "$ns_name" hostname "$hostname" 2>/dev/null || true
    
    # Add static ARP entry on bridge so scanner can see it
    # Generate a fake MAC based on IP for consistency
    mac=$(printf "02:00:%02x:%02x:%02x:%02x" \
        $(echo "$ip" | awk -F. '{print $2, $3, $4}'))
    ip neigh add "$ip" lladdr "$mac" dev "$BRIDGE_NAME" nud permanent 2>/dev/null || true
done

echo ""
echo "✅ Fake network created!"
echo ""
echo "📊 Network Summary:"
echo "   Network: $TEST_NET"
echo "   Gateway: $TEST_GATEWAY (bridge: $BRIDGE_NAME)"
echo "   Devices: ${#DEVICES[@]} virtual nodes"
echo ""
echo "🔍 To scan this network with NetMapper-Lite:"
echo "   1. Run: ./netmapper"
echo "   2. Enter CIDR: $TEST_NET"
echo "   3. Click 'Start Scan'"
echo ""
echo "🧹 To cleanup:"
echo "   Press Ctrl+C or run: sudo $0 --cleanup"
echo ""
echo "⚠️  Note: This fake network will be removed when this script exits"
echo "   To keep it running, keep this terminal open"
echo ""
echo "Waiting... (Ctrl+C to cleanup and exit)"

# Keep script running to maintain the fake network
sleep infinity

