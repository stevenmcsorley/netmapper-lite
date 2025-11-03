#!/usr/bin/env python3
"""
Subnet detection and analysis for network topology.
Groups hosts into logical subnetworks based on IP ranges.
"""
import ipaddress
from typing import List, Dict, Tuple

def detect_subnets(hosts: List[Dict], base_cidr: str) -> Dict:
    """
    Detect subnetworks within the scanned network.
    
    Args:
        hosts: List of host dicts with 'ip' key
        base_cidr: The CIDR that was scanned (e.g., "192.168.1.0/24")
    
    Returns:
        Dict with subnet information and grouped hosts
    """
    if not hosts:
        return {
            "subnets": [],
            "hosts_by_subnet": {},
            "base_network": base_cidr
        }
    
    # Parse base network
    try:
        base_network = ipaddress.ip_network(base_cidr, strict=False)
    except ValueError:
        return {
            "subnets": [],
            "hosts_by_subnet": {},
            "base_network": base_cidr
        }
    
    # Group hosts by common /24 subnet (most common case)
    subnet_groups = {}
    
    for host in hosts:
        ip = host.get('ip')
        if not ip:
            continue
        
        try:
            ip_obj = ipaddress.ip_address(ip)
            
            # Create /24 subnet for this IP
            subnet_24 = ipaddress.ip_network(f"{ip}/{24}", strict=False)
            subnet_key = str(subnet_24)
            
            if subnet_key not in subnet_groups:
                subnet_groups[subnet_key] = []
            
            subnet_groups[subnet_key].append(host)
        except ValueError:
            continue
    
    # If all hosts are in same /24, try detecting smaller subnets (/26, /28)
    if len(subnet_groups) == 1:
        # Try to detect smaller subnet divisions
        subnet_groups = _detect_smaller_subnets(hosts, base_network)
    
    # Format results
    subnets = []
    hosts_by_subnet = {}
    
    for subnet_str, subnet_hosts in subnet_groups.items():
        try:
            subnet_net = ipaddress.ip_network(subnet_str, strict=False)
            subnets.append({
                "cidr": subnet_str,
                "network": str(subnet_net.network_address),
                "broadcast": str(subnet_net.broadcast_address),
                "size": subnet_net.num_addresses,
                "host_count": len(subnet_hosts)
            })
            hosts_by_subnet[subnet_str] = subnet_hosts
        except ValueError:
            continue
    
    # Sort by host count (largest first)
    subnets.sort(key=lambda x: x['host_count'], reverse=True)
    
    return {
        "subnets": subnets,
        "hosts_by_subnet": hosts_by_subnet,
        "base_network": base_cidr,
        "total_subnets": len(subnets)
    }


def _detect_smaller_subnets(hosts: List[Dict], base_network: ipaddress.IPv4Network) -> Dict:
    """Detect if hosts cluster into smaller subnetworks (/26, /28)."""
    subnet_groups = {}
    
    # Try /26 subnets first (64 IPs each)
    if base_network.prefixlen <= 24:
        for host in hosts:
            ip = host.get('ip')
            if not ip:
                continue
            
            try:
                ip_obj = ipaddress.ip_address(ip)
                # Find which /26 subnet this IP belongs to
                subnet_26 = ipaddress.ip_network(f"{ip_obj}/{26}", strict=False)
                subnet_key = str(subnet_26)
                
                if subnet_key not in subnet_groups:
                    subnet_groups[subnet_key] = []
                
                subnet_groups[subnet_key].append(host)
            except ValueError:
                continue
        
        # Only use /26 if we have multiple distinct subnets
        if len(subnet_groups) > 1:
            return subnet_groups
    
    # Fall back to single /24
    subnet_key = str(ipaddress.ip_network(f"{base_network.network_address}/{24}", strict=False))
    return {subnet_key: hosts}


def get_subnet_info(ip: str) -> Dict:
    """Get subnet information for a specific IP."""
    try:
        ip_obj = ipaddress.ip_address(ip)
        
        # Determine subnet based on IP class
        if ip_obj.is_private:
            if ipaddress.IPv4Address('10.0.0.0') <= ip_obj <= ipaddress.IPv4Address('10.255.255.255'):
                # Class A private - likely /8 or /16
                return {
                    "likely_subnet": f"{ip}/16",
                    "subnet_type": "private_class_a"
                }
            elif ipaddress.IPv4Address('172.16.0.0') <= ip_obj <= ipaddress.IPv4Address('172.31.255.255'):
                # Class B private - likely /16
                return {
                    "likely_subnet": f"{ip}/16",
                    "subnet_type": "private_class_b"
                }
            elif ipaddress.IPv4Address('192.168.0.0') <= ip_obj <= ipaddress.IPv4Address('192.168.255.255'):
                # Class C private - likely /24
                return {
                    "likely_subnet": f"{ip}/24",
                    "subnet_type": "private_class_c"
                }
        
        # Default to /24
        return {
            "likely_subnet": f"{ip}/24",
            "subnet_type": "unknown"
        }
    except ValueError:
        return {
            "likely_subnet": None,
            "subnet_type": "invalid"
        }

