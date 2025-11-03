#!/usr/bin/env python3
# scanner.py - ARP scan helper functions
from scapy.all import ARP, Ether, srp, conf
import socket
import subprocess
import logging
import os

# Suppress scapy warnings
conf.verb = 0
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)

def arp_scan(cidr, timeout=2, mock_mode=False):
    """
    Perform ARP scan on a CIDR network.
    
    Args:
        cidr: Network CIDR (e.g., "192.168.1.0/24")
        timeout: Timeout per host in seconds
        mock_mode: If True, return fake data for testing (192.168.100.0/24 only)
        
    Returns:
        List of dicts with keys: ip, mac, hostname
    """
    # Mock mode for testing fake networks
    if mock_mode or os.getenv("NETMAPPER_MOCK_SCAN") == "1":
        if "192.168.100" in cidr:
            import sys
            mock_path = os.path.join(os.path.dirname(__file__), "..", "tests", "mock_scanner.py")
            if os.path.exists(mock_path):
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
                from tests.mock_scanner import get_fake_hosts
                return get_fake_hosts(cidr)
    
    try:
        pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=cidr)
        ans, _ = srp(pkt, timeout=timeout, retry=1, verbose=False)
        hosts = []
        for s, r in ans:
            ip = r.psrc
            mac = r.hwsrc
            try:
                name = socket.gethostbyaddr(ip)[0]
            except (socket.herror, socket.gaierror, OSError):
                name = None
            hosts.append({"ip": ip, "mac": mac, "hostname": name})
        return hosts
    except Exception as e:
        logging.error(f"ARP scan error: {e}")
        return []


def nmap_scan(ip, ports="1-1024"):
    """
    Run nmap port scan on a single IP.
    
    Args:
        ip: Target IP address
        ports: Port range (default: "1-1024")
        
    Returns:
        XML output string from nmap
    """
    try:
        out = subprocess.run(
            ["nmap", "-Pn", "-sS", "-p", ports, ip, "-oX", "-"],
            capture_output=True,
            text=True,
            timeout=300
        )
        if out.returncode != 0:
            return f"<error>Nmap failed: {out.stderr}</error>"
        return out.stdout
    except FileNotFoundError:
        return "<error>Nmap not found. Please install nmap.</error>"
    except subprocess.TimeoutExpired:
        return "<error>Nmap scan timed out</error>"
    except Exception as e:
        return f"<error>Nmap error: {str(e)}</error>"


