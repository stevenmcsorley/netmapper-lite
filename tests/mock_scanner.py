#!/usr/bin/env python3
"""
Mock scanner that returns predefined network topology for testing.
This simulates an interesting network with multiple device types.
"""
import json
import sys
import time

# Fake network devices with interesting topology
FAKE_NETWORK = {
    "gateway": {
        "ip": "192.168.100.1",
        "mac": "00:00:00:00:00:01",
        "hostname": "router.local",
        "vendor": "Router-Tech",
        "role": "gateway"
    },
    "devices": [
        # Servers cluster
        {"ip": "192.168.100.10", "mac": "00:00:00:00:00:10", "hostname": "web1.local", "vendor": "ServerCorp", "role": "server"},
        {"ip": "192.168.100.11", "mac": "00:00:00:00:00:11", "hostname": "db1.local", "vendor": "ServerCorp", "role": "server"},
        {"ip": "192.168.100.12", "mac": "00:00:00:00:00:12", "hostname": "backup.local", "vendor": "ServerCorp", "role": "server"},
        
        # IoT devices
        {"ip": "192.168.100.20", "mac": "00:00:00:00:00:20", "hostname": "tv.living-room.local", "vendor": "IoT-Media", "role": "iot"},
        {"ip": "192.168.100.21", "mac": "00:00:00:00:00:21", "hostname": "light.kitchen.local", "vendor": "IoT-Home", "role": "iot"},
        {"ip": "192.168.100.22", "mac": "00:00:00:00:00:22", "hostname": "camera.front.local", "vendor": "Hikvision", "role": "iot"},
        {"ip": "192.168.100.23", "mac": "00:00:00:00:00:23", "hostname": "camera.back.local", "vendor": "Hikvision", "role": "iot"},
        
        # Workstations
        {"ip": "192.168.100.30", "mac": "00:00:00:00:00:30", "hostname": "laptop-alice.local", "vendor": "Dell", "role": "workstation"},
        {"ip": "192.168.100.31", "mac": "00:00:00:00:00:31", "hostname": "laptop-bob.local", "vendor": "HP", "role": "workstation"},
        {"ip": "192.168.100.32", "mac": "00:00:00:00:00:32", "hostname": "desktop.local", "vendor": "CustomPC", "role": "workstation"},
        
    # Mobile devices
    {"ip": "192.168.100.40", "mac": "00:00:00:00:00:40", "hostname": "phone-alice.local", "vendor": "Apple", "role": "mobile"},
    {"ip": "192.168.100.41", "mac": "00:00:00:00:00:41", "hostname": "phone-bob.local", "vendor": "Samsung", "role": "mobile"},
    {"ip": "192.168.100.42", "mac": "00:00:00:00:00:42", "hostname": "tablet.local", "vendor": "Apple", "role": "mobile"},
    
    # Printers
    {"ip": "192.168.100.50", "mac": "00:00:00:00:00:50", "hostname": "printer.office.local", "vendor": "HP-Printer", "role": "printer"},
    {"ip": "192.168.100.51", "mac": "00:00:00:00:00:51", "hostname": "printer.home.local", "vendor": "Canon", "role": "printer"},
    
    # Subnet 1: IoT devices (192.168.101.0/24) - nested subnet
    {"ip": "192.168.101.10", "mac": "00:00:00:00:01:10", "hostname": "iot-gateway.local", "vendor": "IoT-Hub", "role": "gateway"},
    {"ip": "192.168.101.20", "mac": "00:00:00:00:01:20", "hostname": "sensor-1.local", "vendor": "IoT-Sensors", "role": "iot"},
    {"ip": "192.168.101.21", "mac": "00:00:00:00:01:21", "hostname": "sensor-2.local", "vendor": "IoT-Sensors", "role": "iot"},
    {"ip": "192.168.101.22", "mac": "00:00:00:00:01:22", "hostname": "thermostat.local", "vendor": "SmartHome", "role": "iot"},
    
    # Subnet 2: Guest network (192.168.102.0/24) - nested subnet
    {"ip": "192.168.102.50", "mac": "00:00:00:00:02:50", "hostname": "guest-router.local", "vendor": "Router-Tech", "role": "gateway"},
    {"ip": "192.168.102.100", "mac": "00:00:00:00:02:01", "hostname": None, "vendor": "Unknown", "role": "guest"},
    {"ip": "192.168.102.101", "mac": "00:00:00:00:02:02", "hostname": None, "vendor": "Unknown", "role": "guest"},
    
    # Smart hub
    {"ip": "192.168.100.60", "mac": "00:00:00:00:00:60", "hostname": "smart-hub.local", "vendor": "HomeHub", "role": "iot"},
        
        # Guest devices
        {"ip": "192.168.100.100", "mac": "00:00:00:00:01:00", "hostname": None, "vendor": "Unknown", "role": "guest"},
        {"ip": "192.168.100.101", "mac": "00:00:00:00:01:01", "hostname": None, "vendor": "Unknown", "role": "guest"},
    ]
}

def get_fake_hosts(cidr):
    """Return fake hosts for testing."""
    hosts = []
    
    # Add gateway
    hosts.append({
        "ip": FAKE_NETWORK["gateway"]["ip"],
        "mac": FAKE_NETWORK["gateway"]["mac"],
        "hostname": FAKE_NETWORK["gateway"]["hostname"],
        "vendor": FAKE_NETWORK["gateway"]["vendor"]
    })
    
    # Add all devices
    for device in FAKE_NETWORK["devices"]:
        hosts.append({
            "ip": device["ip"],
            "mac": device["mac"],
            "hostname": device["hostname"],
            "vendor": device["vendor"]
        })
    
    return hosts

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        hosts = get_fake_hosts("192.168.100.0/24")
        print(json.dumps(hosts, indent=2))
    else:
        print("Mock scanner for testing")
        print("Usage: python3 mock_scanner.py --list")
        print(f"Simulates {len(FAKE_NETWORK['devices']) + 1} devices")

