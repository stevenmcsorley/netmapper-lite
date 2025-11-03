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

def arp_scan(cidr, timeout=2, mock_mode=False, parallel=False):
    """
    Perform ARP scan on a CIDR network.
    
    Args:
        cidr: Network CIDR (e.g., "192.168.1.0/24")
        timeout: Timeout per host in seconds
        mock_mode: If True, return fake data for testing (192.168.100.0/24 only)
        parallel: If True, use parallel scanning for large networks
        
    Returns:
        List of dicts with keys: ip, mac, hostname
    """
    # Mock mode for testing fake networks
    if mock_mode or os.getenv("NETMAPPER_MOCK_SCAN") == "1":
        # Mock mode works for any CIDR - returns fake network data
        import sys
        mock_path = os.path.join(os.path.dirname(__file__), "..", "tests", "mock_scanner.py")
        if os.path.exists(mock_path):
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from tests.mock_scanner import get_fake_hosts
            # Mock scanner returns same fake data regardless of CIDR
            return get_fake_hosts(cidr)
    
    try:
        # For large networks, use parallel scanning
        if parallel:
            return _arp_scan_parallel(cidr, timeout)
        
        # Check if we're scanning a subnet we're not on (ARP won't work)
        import ipaddress
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            # Get local IP addresses
            import socket
            local_ips = []
            hostname = socket.gethostname()
            local_ips.extend([ip for ip in socket.gethostbyname_ex(hostname)[2] if not ip.startswith("127.")])
            # Also check interface IPs
            try:
                import subprocess
                result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    local_ips.extend([ip.split('/')[0] for ip in result.stdout.strip().split()])
            except:
                pass
            
            # Check if any local IP is in the network being scanned
            on_same_subnet = False
            for local_ip in local_ips:
                try:
                    if ipaddress.ip_address(local_ip) in network:
                        on_same_subnet = True
                        break
                except:
                    pass
            
            if not on_same_subnet and network.prefixlen <= 24:
                logging.warning(f"⚠️  Scanning {cidr} but local IPs {local_ips} are not in this network. ARP may not work across subnets!")
        except:
            pass  # Skip subnet check if it fails
        
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


def _arp_scan_parallel(cidr, timeout=2):
    """Perform parallel ARP scan for large networks."""
    try:
        import ipaddress
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        network = ipaddress.ip_network(cidr, strict=False)
        
        # For /24 or smaller, use regular scan
        if network.prefixlen >= 24:
            return arp_scan(cidr, timeout, parallel=False)
        
        # For larger networks, split into /24 subnets and scan in parallel
        subnets = list(network.subnets(new_prefix=24))
        logging.info(f"Parallel scanning {len(subnets)} /24 subnets for {cidr}")
        
        hosts = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(arp_scan, str(subnet), timeout, False, False): subnet 
                      for subnet in subnets}
            
            completed = 0
            failed = 0
            for future in as_completed(futures):
                subnet = futures[future]
                try:
                    subnet_hosts = future.result()
                    if subnet_hosts:
                        hosts.extend(subnet_hosts)
                        logging.info(f"Subnet {subnet}: found {len(subnet_hosts)} hosts")
                    completed += 1
                    if completed % 10 == 0:
                        logging.info(f"Progress: {completed}/{len(subnets)} subnets, {len(hosts)} total hosts found")
                except Exception as e:
                    failed += 1
                    logging.error(f"Parallel scan error for {subnet}: {e}")
        
        if failed > 0:
            logging.warning(f"Failed to scan {failed} subnets (may be on different network segments)")
        
        logging.info(f"Parallel scan complete: found {len(hosts)} total hosts across {len(subnets)} subnets")
        return hosts
    except Exception as e:
        logging.error(f"Parallel ARP scan error: {e}")
        import traceback
        traceback.print_exc()
        return arp_scan(cidr, timeout, parallel=False)  # Fallback to regular scan


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


