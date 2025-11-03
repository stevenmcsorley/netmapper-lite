#!/bin/bash
# Quick test script to verify helper is running and test a scan

SOCKET_PATH="/tmp/netmapper-helper.sock"

if [ ! -e "$SOCKET_PATH" ]; then
    echo "❌ Helper socket not found. Is the helper running?"
    echo "   Start it with: sudo python3 backend/netmapper_helper.py --dev"
    exit 1
fi

echo "✅ Helper socket found"
echo ""

# Get network CIDR from user or use default
if [ -z "$1" ]; then
    echo "Usage: $0 <CIDR>"
    echo "Example: $0 192.168.1.0/24"
    exit 1
fi

CIDR="$1"
echo "Testing scan on: $CIDR"
echo ""

python3 << EOF
import socket
import json
import time
import sys

socket_path = "$SOCKET_PATH"
cidr = "$CIDR"

try:
    # Send scan request
    print(f"📡 Sending scan request for {cidr}...")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(socket_path)
    
    scan_req = {"cmd": "scan", "cidr": cidr}
    s.sendall(json.dumps(scan_req).encode())
    
    response = s.recv(4096).decode()
    s.close()
    
    data = json.loads(response)
    if data.get('status') == 'started':
        scan_id = data.get('scan_id')
        print(f"✅ Scan started: {scan_id}")
        print(f"⏳ Waiting for results (scanning network)...")
        
        # Wait a bit for scan to complete
        time.sleep(10)
        
        # Get results
        s2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s2.settimeout(5)
        s2.connect(socket_path)
        s2.sendall(json.dumps({"cmd": "get_results", "scan_id": scan_id}).encode())
        resp2 = s2.recv(8192).decode()
        s2.close()
        
        results_data = json.loads(resp2)
        if results_data.get('status') == 'ok':
            hosts = results_data.get('results', [])
            print(f"\n📊 Scan Results:")
            print(f"   Hosts found: {len(hosts)}")
            
            if hosts:
                print(f"\n   Sample hosts:")
                for h in hosts[:5]:
                    vendor = h.get('vendor') or '-'
                    hostname = h.get('hostname') or '-'
                    print(f"   - {h.get('ip'):15s} | {h.get('mac'):17s} | {hostname:20s} | {vendor}")
                
                if len(hosts) > 5:
                    print(f"   ... and {len(hosts) - 5} more hosts")
            else:
                print("   ⚠ No hosts found. Check network permissions or CIDR.")
        else:
            print(f"   Error: {results_data.get('message')}")
    else:
        print(f"❌ Error: {data.get('message', 'Unknown error')}")
        sys.exit(1)

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
EOF

