#!/bin/bash
# Simpler fake network setup using dummy interfaces (no bridge needed)
# This creates dummy interfaces that respond to ARP requests

set -e

TEST_NET="192.168.100.0/24"
TEST_GATEWAY="192.168.100.1"
NAMESPACE_PREFIX="netmapper-test"

echo "=========================================="
echo "Creating Simple Fake Network for Testing"
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
    # Remove dummy interfaces
    for iface in $(ip link show | grep -E "dummy-$NAMESPACE_PREFIX" | cut -d: -f2 | awk '{print $1}'); do
        echo "  Removing interface: $iface"
        ip link delete "$iface" 2>/dev/null || true
    done
    echo "✅ Cleanup complete"
}

trap cleanup EXIT

echo "Creating network topology (using dummy interfaces):"
echo "  Gateway: $TEST_GATEWAY"
echo "  Network: $TEST_NET"
echo ""
echo "⚠️  IMPORTANT: Your system may block network interface creation."
echo "   If this fails, use MOCK MODE instead (recommended):"
echo ""
echo "   NETMAPPER_MOCK_SCAN=1 ./netmapper"
echo ""
echo "   Mock mode works instantly and doesn't need network interfaces!"
echo ""

# Define fake devices
declare -a DEVICES=(
    "gateway,$TEST_GATEWAY,router.local,Router-Tech,gateway"
    "web-server,192.168.100.10,web1.local,ServerCorp,server"
    "db-server,192.168.100.11,db1.local,ServerCorp,server"
    "backup-server,192.168.100.12,backup.local,ServerCorp,server"
    "smart-tv,192.168.100.20,tv.living-room.local,IoT-Media,iot"
    "smart-light,192.168.100.21,light.kitchen.local,IoT-Home,iot"
    "camera-1,192.168.100.22,camera.front.local,Hikvision,iot"
    "camera-2,192.168.100.23,camera.back.local,Hikvision,iot"
    "laptop-1,192.168.100.30,laptop-alice.local,Dell,workstation"
    "laptop-2,192.168.100.31,laptop-bob.local,HP,workstation"
    "desktop-1,192.168.100.32,desktop.local,CustomPC,workstation"
    "phone-1,192.168.100.40,phone-alice.local,Apple,mobile"
    "phone-2,192.168.100.41,phone-bob.local,Samsung,mobile"
    "tablet-1,192.168.100.42,tablet.local,Apple,mobile"
    "printer-1,192.168.100.50,printer.office.local,HP-Printer,printer"
    "printer-2,192.168.100.51,printer.home.local,Canon,printer"
    "hub,192.168.100.60,smart-hub.local,HomeHub,iot"
    "guest-1,192.168.100.100,guest-phone.local,Unknown,guest"
    "guest-2,192.168.100.101,guest-laptop.local,Unknown,guest"
)

echo "🔧 Creating ${#DEVICES[@]} virtual devices using namespaces..."

DEVICE_COUNT=0
for device_info in "${DEVICES[@]}"; do
    IFS=',' read -r name ip hostname vendor role <<< "$device_info"
    DEVICE_COUNT=$((DEVICE_COUNT + 1))
    
    ns_name="${NAMESPACE_PREFIX}-${name}"
    dummy_iface="dummy-${name}"
    
    echo "  [$DEVICE_COUNT] Creating: $name ($ip)"
    
    # Create namespace
    ip netns add "$ns_name" 2>/dev/null && echo "    ✅ Namespace created" || echo "    ⚠️  Namespace exists"
    
    # Try to create dummy interface - handle policy validation errors
    if ! ip link add "$dummy_iface" type dummy 2>/dev/null; then
        # If it exists, try to remove and recreate
        if ip link show "$dummy_iface" &>/dev/null; then
            echo "    ⚠️  Dummy interface exists, removing first..."
            ip link delete "$dummy_iface" 2>/dev/null || true
            sleep 0.5
        fi
        
        # Try again, if still fails, it's a policy issue
        if ! ip link add "$dummy_iface" type dummy 2>/dev/null; then
            echo ""
            echo "  ❌ Cannot create network interfaces (kernel security policy restriction)"
            echo ""
            echo "  💡 This system blocks network interface creation."
            echo "     Use MOCK MODE instead (no interfaces needed):"
            echo ""
            echo "     NETMAPPER_MOCK_SCAN=1 ./netmapper"
            echo "     Then scan: $TEST_NET"
            echo ""
            echo "  Mock mode provides the same fake network data without"
            echo "  needing to create actual network interfaces."
            echo ""
            exit 1
        fi
    fi
    
    # Move dummy interface into namespace
    ip link set "$dummy_iface" netns "$ns_name"
    
    # Configure interface in namespace
    ip -n "$ns_name" link set "$dummy_iface" up
    ip -n "$ns_name" addr add "${ip}/24" dev "$dummy_iface"
    
    # Generate MAC address based on IP
    mac=$(printf "02:00:%02x:%02x:%02x:%02x" \
        $(echo "$ip" | awk -F. '{print $2, $3, $4}'))
    
    # Set MAC address
    ip -n "$ns_name" link set "$dummy_iface" address "$mac"
    
    echo "    ✅ Interface configured: $ip ($mac)"
done

echo ""
echo "✅ Fake network created with ${#DEVICES[@]} devices!"
echo ""
echo "📊 Network Summary:"
echo "   Network: $TEST_NET"
echo "   Gateway: $TEST_GATEWAY"
echo "   Devices: ${#DEVICES[@]} virtual nodes"
echo ""
echo "⚠️  Important: Dummy interfaces may not respond to ARP requests"
echo "   from outside their namespace. For testing NetMapper-Lite,"
echo "   we recommend using mock mode instead:"
echo ""
echo "   NETMAPPER_MOCK_SCAN=1 ./netmapper"
echo "   Then scan: $TEST_NET"
echo ""
echo "🧹 To cleanup: Press Ctrl+C"
echo ""
echo "Waiting... (Ctrl+C to cleanup and exit)"

# Keep script running to maintain the fake network
sleep infinity

