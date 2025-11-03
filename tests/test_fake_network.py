#!/usr/bin/env python3
"""
Test script to verify fake network setup works.
Can be used with either real fake network interfaces or mock data.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.scanner import arp_scan
from tests.mock_scanner import get_fake_hosts

def test_mock_network():
    """Test with mock scanner data."""
    print("Testing with mock scanner data...")
    hosts = get_fake_hosts("192.168.100.0/24")
    
    print(f"\n✅ Found {len(hosts)} devices:")
    print(f"  Gateway: {hosts[0]['ip']} ({hosts[0]['hostname']})")
    print(f"  Devices: {len(hosts) - 1}")
    
    print("\n📊 Device breakdown:")
    roles = {}
    for host in hosts[1:]:
        role = "unknown"
        hostname = (host.get("hostname") or "").lower()
        if "server" in hostname or "db" in hostname:
            role = "server"
        elif "camera" in hostname or "tv" in hostname or "light" in hostname or "hub" in hostname:
            role = "iot"
        elif "phone" in hostname or "tablet" in hostname:
            role = "mobile"
        elif "printer" in hostname:
            role = "printer"
        elif "laptop" in hostname or "desktop" in hostname:
            role = "workstation"
        
        roles[role] = roles.get(role, 0) + 1
    
    for role, count in sorted(roles.items()):
        print(f"  {role.capitalize()}: {count}")
    
    print("\n🔍 Sample devices:")
    for host in hosts[:5]:
        print(f"  {host['ip']:15} {host['hostname'] or '-':30} {host['vendor'] or '-'}")
    
    return hosts

def test_real_scan(cidr="192.168.100.0/24"):
    """Test with real ARP scan (requires fake network to be set up)."""
    print(f"\nTesting real ARP scan on {cidr}...")
    print("(Make sure fake network is running: sudo tests/create_fake_network.sh)")
    
    try:
        hosts = arp_scan(cidr, timeout=3)
        if hosts:
            print(f"✅ Found {len(hosts)} devices via ARP scan")
            for host in hosts[:10]:
                print(f"  {host.get('ip', 'N/A'):15} {host.get('hostname', '-') or '-':30}")
            return hosts
        else:
            print("⚠️  No hosts found. Is the fake network running?")
            return []
    except Exception as e:
        print(f"❌ Scan failed: {e}")
        return []

if __name__ == "__main__":
    print("=" * 50)
    print("Fake Network Test")
    print("=" * 50)
    
    # Test with mock data
    mock_hosts = test_mock_network()
    
    # Test with real scan if requested
    if len(sys.argv) > 1 and sys.argv[1] == "--real":
        real_hosts = test_real_scan()
        if real_hosts:
            print(f"\n✅ Real scan found {len(real_hosts)} devices")
        else:
            print("\n💡 To test with real fake network:")
            print("   1. Run: sudo tests/create_fake_network.sh")
            print("   2. In another terminal: python3 tests/test_fake_network.py --real")
    else:
        print("\n💡 To test with real network interfaces:")
        print("   python3 tests/test_fake_network.py --real")

