#!/bin/bash
# Quick script to start helper service

cd "$(dirname "$0")"

echo "Starting NetMapper Helper..."
echo ""

# Check if already running
if [ -e /tmp/netmapper-helper.sock ]; then
    echo "⚠️  Helper socket already exists. Stopping old instance..."
    pkill -f netmapper_helper.py
    sleep 2
    rm -f /tmp/netmapper-helper.sock
fi

# Start helper
NETMAPPER_DEV=true python3 backend/netmapper_helper.py --dev > /tmp/helper.log 2>&1 &
HELPER_PID=$!

sleep 3

if [ -e /tmp/netmapper-helper.sock ]; then
    echo "✅ Helper started successfully!"
    echo "   PID: $HELPER_PID"
    echo "   Logs: tail -f /tmp/helper.log"
    echo ""
    echo "Now you can run the GUI:"
    echo "   python3 frontend/gui.py"
else
    echo "❌ Helper failed to start"
    echo ""
    echo "Check logs:"
    tail -10 /tmp/helper.log
    echo ""
    echo "Common issues:"
    echo "  - Network permissions needed (run with sudo or set capabilities)"
    echo "  - Port conflict (check if another instance is running)"
fi


