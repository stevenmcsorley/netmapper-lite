#!/usr/bin/env python3
"""
NetMapper Helper Service - Privileged backend for network scanning.
Runs as systemd service or standalone with elevated privileges.
"""
import socket
import os
import json
import uuid
import sqlite3
import threading
import time
import logging
from pathlib import Path
from scanner import arp_scan, nmap_scan

# Configuration
SOCKET_PATH = "/var/run/netmapper-helper.sock"  # Production path
# Dev mode: use /tmp for non-root testing
DEV_SOCKET_PATH = "/tmp/netmapper-helper.sock"

DB_PATH = "/var/lib/netmapper/netmapper.db"
DEV_DB_PATH = os.path.expanduser("~/.local/share/netmapper/netmapper.db")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class NetMapperHelper:
    def __init__(self, socket_path=None, db_path=None, dev_mode=False):
        self.dev_mode = dev_mode
        self.socket_path = socket_path or (DEV_SOCKET_PATH if dev_mode else SOCKET_PATH)
        self.db_path = db_path or (DEV_DB_PATH if dev_mode else DB_PATH)
        
        # Rate limiting: track requests per client
        self.rate_limits = {}  # {client_id: {'count': int, 'window_start': float}}
        self.rate_limit_max = 10  # Max requests per window
        self.rate_limit_window = 60  # Time window in seconds
        
        # Audit logging
        self.audit_log_path = os.path.join(os.path.dirname(self.db_path), "audit.log")
        
        # Ensure database directory exists
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        
        # Initialize database
        self._init_db()
        
        # Setup socket
        self._setup_socket()
        
        # Start auto-cleanup thread
        self._start_cleanup_thread()

    def _init_db(self):
        """Initialize SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY,
            cidr TEXT,
            ts INTEGER,
            host_count INTEGER
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS hosts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id TEXT,
            ip TEXT,
            mac TEXT,
            hostname TEXT,
            vendor TEXT,
            FOREIGN KEY(scan_id) REFERENCES scans(id)
        )''')
        # Nmap scan results table
        c.execute('''CREATE TABLE IF NOT EXISTS nmap_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            scan_timestamp INTEGER,
            ports TEXT,
            services TEXT,
            nmap_xml TEXT
        )''')
        # Index for quick lookups
        c.execute('''CREATE INDEX IF NOT EXISTS idx_nmap_ip ON nmap_scans(ip)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_nmap_timestamp ON nmap_scans(scan_timestamp DESC)''')
        
        # Device tags table
        c.execute('''CREATE TABLE IF NOT EXISTS device_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT,
            tag TEXT,
            created_at INTEGER
        )''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_device_tags_ip ON device_tags(ip)''')
        
        # Audit log table
        c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,
            action TEXT,
            details TEXT,
            client_id TEXT
        )''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC)''')
        
        # Scan schedules table
        c.execute('''CREATE TABLE IF NOT EXISTS scan_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cidr TEXT,
            schedule TEXT,
            enabled INTEGER,
            last_run INTEGER,
            created_at INTEGER
        )''')
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def _setup_socket(self):
        """Setup UNIX domain socket."""
        # Remove existing socket if it exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.socket_path)
        
        # Set permissions for group access (in production)
        if not self.dev_mode:
            try:
                os.chmod(self.socket_path, 0o660)
            except PermissionError:
                logger.warning("Could not set socket permissions (may need root)")
        else:
            os.chmod(self.socket_path, 0o666)  # Dev mode: permissive
        
        self.sock.listen(4)
        logger.info(f"Socket listening on {self.socket_path}")
    
    def _validate_request(self, req):
        """Validate request parameters."""
        if not isinstance(req, dict):
            return False
        
        cmd = req.get('cmd')
        if not cmd or not isinstance(cmd, str):
            return False
        
        # Validate CIDR format for scan commands
        if cmd == 'scan':
            cidr = req.get('cidr', '')
            if not cidr or '/' not in cidr:
                return False
            # Basic CIDR validation
            try:
                parts = cidr.split('/')
                if len(parts) != 2:
                    return False
                ip_parts = parts[0].split('.')
                if len(ip_parts) != 4:
                    return False
                prefix = int(parts[1])
                if prefix < 0 or prefix > 32:
                    return False
            except:
                return False
        
        # Validate IP for nmap commands
        if cmd == 'nmap':
            ip = req.get('ip', '')
            if not ip:
                return False
            # Basic IP validation
            try:
                parts = ip.split('.')
                if len(parts) != 4:
                    return False
                for part in parts:
                    num = int(part)
                    if num < 0 or num > 255:
                        return False
            except:
                return False
        
        return True
    
    def _audit_log(self, action, details, client_id=None):
        """Log action to audit log."""
        try:
            timestamp = int(time.time())
            log_entry = {
                'timestamp': timestamp,
                'action': action,
                'details': details,
                'client_id': client_id or 'unknown'
            }
            
            # Write to database
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO audit_log (timestamp, action, details, client_id)
                         VALUES (?, ?, ?, ?)''',
                     (timestamp, action, json.dumps(details), client_id or 'unknown'))
            conn.commit()
            conn.close()
            
            # Also write to log file
            with open(self.audit_log_path, 'a') as f:
                f.write(f"{timestamp} | {action} | {client_id or 'unknown'} | {json.dumps(details)}\n")
        except Exception as e:
            logger.error(f"Audit log error: {e}")
    
    def _check_rate_limit(self, client_id):
        """Check if client exceeds rate limit."""
        now = time.time()
        if client_id not in self.rate_limits:
            self.rate_limits[client_id] = {'count': 0, 'window_start': now}
            return True
        
        limit_info = self.rate_limits[client_id]
        
        # Reset window if expired
        if now - limit_info['window_start'] > self.rate_limit_window:
            limit_info['count'] = 0
            limit_info['window_start'] = now
        
        # Check limit
        if limit_info['count'] >= self.rate_limit_max:
            return False
        
        limit_info['count'] += 1
        return True
    
    def _start_cleanup_thread(self):
        """Start background thread for auto-cleanup."""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(3600)  # Run every hour
                    self._auto_cleanup_scans()
                except Exception as e:
                    logger.error(f"Cleanup thread error: {e}")
        
        thread = threading.Thread(target=cleanup_worker, daemon=True)
        thread.start()
        logger.info("Auto-cleanup thread started")
    
    def _auto_cleanup_scans(self, days_to_keep=30):
        """Automatically clean up old scans."""
        try:
            cutoff_time = int(time.time()) - (days_to_keep * 24 * 60 * 60)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Find old scans
            c.execute('SELECT id FROM scans WHERE ts < ?', (cutoff_time,))
            old_scan_ids = [row[0] for row in c.fetchall()]
            
            if old_scan_ids:
                # Delete old hosts
                placeholders = ','.join('?' * len(old_scan_ids))
                c.execute(f'DELETE FROM hosts WHERE scan_id IN ({placeholders})', old_scan_ids)
                
                # Delete old scans
                c.execute(f'DELETE FROM scans WHERE id IN ({placeholders})', old_scan_ids)
                
                conn.commit()
                deleted_count = len(old_scan_ids)
                logger.info(f"Auto-cleanup: Deleted {deleted_count} scans older than {days_to_keep} days")
                self._audit_log('auto_cleanup', {'deleted_scans': deleted_count, 'cutoff_days': days_to_keep})
            
            conn.close()
        except Exception as e:
            logger.error(f"Auto-cleanup error: {e}")

    def serve_forever(self):
        """Main server loop."""
        logger.info("NetMapper Helper Service started")
        try:
            while True:
                conn, addr = self.sock.accept()
                logger.debug(f"New connection from {addr}")
                threading.Thread(
                    target=self.handle,
                    args=(conn,),
                    daemon=True
                ).start()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)

    def handle(self, conn):
        """Handle client connection."""
        client_id = str(conn.getpeername()) if hasattr(conn, 'getpeername') else 'local'
        try:
            data = conn.recv(65536).decode('utf-8')
            if not data:
                return
            
            req = json.loads(data)
            cmd = req.get('cmd')
            
            # Rate limiting check
            if not self._check_rate_limit(client_id):
                self._audit_log('rate_limit_exceeded', {'cmd': cmd, 'client': client_id}, client_id)
                conn.sendall(json.dumps({
                    "status": "error",
                    "message": "Rate limit exceeded. Please wait before making more requests."
                }).encode('utf-8'))
                return
            
            # Audit log request
            self._audit_log('request', {'cmd': cmd, 'params': {k: v for k, v in req.items() if k != 'cmd'}}, client_id)
            
            # Input validation
            if not self._validate_request(req):
                self._audit_log('validation_failed', {'cmd': cmd, 'req': req}, client_id)
                conn.sendall(json.dumps({
                    "status": "error",
                    "message": "Invalid request parameters"
                }).encode('utf-8'))
                return
            
            if cmd == 'scan':
                cidr = req.get('cidr')
                if not cidr:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing CIDR parameter"
                    }).encode('utf-8'))
                    return
                
                scan_id = str(uuid.uuid4())
                # Send immediate acknowledgment
                conn.sendall(json.dumps({
                    "status": "started",
                    "scan_id": scan_id
                }).encode('utf-8'))
                
                # Run scan in background thread
                threading.Thread(
                    target=self.run_scan_and_store,
                    args=(scan_id, cidr),
                    daemon=True
                ).start()
                
            elif cmd == 'nmap':
                ip = req.get('ip')
                if not ip:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing IP parameter"
                    }).encode('utf-8'))
                    return
                
                ports = req.get('ports', '1-1024')
                logger.info(f"Nmap scan requested for {ip}:{ports}")
                res = nmap_scan(ip, ports)
                
                # Save Nmap results to database
                self._save_nmap_results(ip, ports, res)
                
                conn.sendall(json.dumps({
                    "status": "ok",
                    "nmap_xml": res
                }).encode('utf-8'))
                
            elif cmd == 'get_results':
                scan_id = req.get('scan_id')
                if not scan_id:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing scan_id parameter"
                    }).encode('utf-8'))
                    return
                
                results = self._get_scan_results(scan_id)
                conn.sendall(json.dumps({
                    "status": "ok",
                    "results": results
                }).encode('utf-8'))
                
            elif cmd == 'get_nmap_history':
                ip = req.get('ip')
                if not ip:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing IP parameter"
                    }).encode('utf-8'))
                    return
                
                limit = req.get('limit', 10)
                db_conn = sqlite3.connect(self.db_path)
                c = db_conn.cursor()
                c.execute('''SELECT scan_timestamp, ports, services 
                             FROM nmap_scans 
                             WHERE ip = ? 
                             ORDER BY scan_timestamp DESC 
                             LIMIT ?''',
                          (ip, limit))
                results = []
                for row in c.fetchall():
                    results.append({
                        'timestamp': row[0],
                        'ports': row[1] or '',
                        'services': row[2] or ''
                    })
                db_conn.close()
                
                conn.sendall(json.dumps({
                    "status": "ok",
                    "history": results
                }).encode('utf-8'))
            
            elif cmd == 'compare_scans':
                scan_id1 = req.get('scan_id1')
                scan_id2 = req.get('scan_id2')
                if not scan_id1 or not scan_id2:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing scan_id parameters"
                    }).encode('utf-8'))
                    return
                
                comparison = self._compare_scans(scan_id1, scan_id2)
                conn.sendall(json.dumps({
                    "status": "ok",
                    "comparison": comparison
                }).encode('utf-8'))
            
            elif cmd == 'list_history':
                limit = req.get('limit', 10)
                history = self._get_scan_history(limit)
                conn.sendall(json.dumps({
                    "status": "ok",
                    "history": history
                }).encode('utf-8'))
            
            elif cmd == 'get_stats':
                stats = self._get_database_stats()
                conn.sendall(json.dumps({
                    "status": "ok",
                    "stats": stats
                }).encode('utf-8'))
            
            elif cmd == 'get_timeline':
                ip = req.get('ip')
                days = req.get('days', 7)
                timeline = self._get_device_timeline(ip, days)
                conn.sendall(json.dumps({
                    "status": "ok",
                    "timeline": timeline
                }).encode('utf-8'))
            
            elif cmd == 'add_device_tag':
                ip = req.get('ip')
                tag = req.get('tag')
                if ip and tag:
                    self._add_device_tag(ip, tag)
                    conn.sendall(json.dumps({"status": "ok"}).encode('utf-8'))
                else:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing ip or tag"
                    }).encode('utf-8'))
            
            elif cmd == 'get_device_tags':
                ip = req.get('ip')
                tags = self._get_device_tags(ip)
                conn.sendall(json.dumps({
                    "status": "ok",
                    "tags": tags
                }).encode('utf-8'))
            
            elif cmd == 'scan_multiple':
                cidrs = req.get('cidrs', [])
                if not cidrs:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "No CIDRs provided"
                    }).encode('utf-8'))
                    return
                
                scan_id = str(uuid.uuid4())
                conn.sendall(json.dumps({
                    "status": "started",
                    "scan_id": scan_id
                }).encode('utf-8'))
                
                # Start multi-network scan in background
                threading.Thread(target=self._scan_multiple_networks, args=(scan_id, cidrs), daemon=True).start()
            
            elif cmd == 'schedule_scan':
                cidr = req.get('cidr')
                schedule = req.get('schedule')  # cron-like: "0 2 * * *" for daily at 2am
                if cidr and schedule:
                    self._add_scan_schedule(cidr, schedule)
                    conn.sendall(json.dumps({"status": "ok"}).encode('utf-8'))
                else:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing cidr or schedule"
                    }).encode('utf-8'))
            
            elif cmd == 'wake_on_lan':
                mac = req.get('mac')
                if mac:
                    result = self._wake_on_lan(mac)
                    conn.sendall(json.dumps({
                        "status": "ok" if result else "error",
                        "message": "WoL packet sent" if result else "WoL failed"
                    }).encode('utf-8'))
                else:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing MAC address"
                    }).encode('utf-8'))
            
            elif cmd == 'backup_database':
                backup_path = req.get('path')
                if backup_path:
                    result = self._backup_database(backup_path)
                    conn.sendall(json.dumps({
                        "status": "ok" if result else "error",
                        "message": f"Backup saved to {backup_path}" if result else "Backup failed"
                    }).encode('utf-8'))
                else:
                    conn.sendall(json.dumps({
                        "status": "error",
                        "message": "Missing backup path"
                    }).encode('utf-8'))
                
            else:
                conn.sendall(json.dumps({
                    "status": "error",
                    "message": f"Unknown command: {cmd}"
                }).encode('utf-8'))
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            conn.sendall(json.dumps({
                "status": "error",
                "message": "Invalid JSON"
            }).encode('utf-8'))
        except Exception as e:
            logger.error(f"Handle error: {e}", exc_info=True)
            conn.sendall(json.dumps({
                "status": "error",
                "message": str(e)
            }).encode('utf-8'))
        finally:
            conn.close()

    def run_scan_and_store(self, scan_id, cidr):
        """Run ARP scan and store results in database."""
        logger.info(f"Starting scan {scan_id} for {cidr}")
        try:
            # Detect if this is a large network that needs parallel scanning
            import ipaddress
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                use_parallel = network.prefixlen < 24  # Use parallel for /16, /8, etc.
            except:
                use_parallel = False
            
            if use_parallel:
                logger.info(f"Using parallel scanning for large network {cidr}")
                hosts = arp_scan(cidr, parallel=True)
            else:
                hosts = arp_scan(cidr)
            logger.info(f"Scan {scan_id} found {len(hosts)} hosts")
            
            # Store to database
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute(
                'INSERT INTO scans (id, cidr, ts, host_count) VALUES (?, ?, ?, ?)',
                (scan_id, cidr, int(time.time()), len(hosts))
            )
            
            for h in hosts:
                # Simple vendor lookup (can be enhanced with OUI database)
                vendor = self._lookup_vendor(h.get('mac', ''))
                c.execute(
                    'INSERT INTO hosts (scan_id, ip, mac, hostname, vendor) VALUES (?, ?, ?, ?, ?)',
                    (scan_id, h['ip'], h['mac'], h.get('hostname'), vendor)
                )
            
            conn.commit()
            conn.close()
            logger.info(f"Scan {scan_id} completed and stored")
            
        except Exception as e:
            logger.error(f"Scan error for {scan_id}: {e}", exc_info=True)

    def _save_nmap_results(self, ip, ports, nmap_xml):
        """Save Nmap scan results to database."""
        try:
            # Parse XML to extract ports and services
            ports_list = []
            services_list = []
            
            if nmap_xml:
                import xml.etree.ElementTree as ET
                try:
                    root = ET.fromstring(nmap_xml)
                    for host in root.findall('host'):
                        for port in host.findall('.//port'):
                            port_id = port.get('portid')
                            protocol = port.get('protocol', 'tcp')
                            state = port.find('state')
                            service = port.find('service')
                            
                            if state is not None and state.get('state') == 'open':
                                ports_list.append(f"{port_id}/{protocol}")
                                if service is not None:
                                    name = service.get('name', '')
                                    product = service.get('product', '')
                                    version = service.get('version', '')
                                    if product or name:
                                        svc_str = f"{name}"
                                        if product:
                                            svc_str += f" ({product}"
                                            if version:
                                                svc_str += f" {version}"
                                            svc_str += ")"
                                        services_list.append(f"{port_id}/{protocol}: {svc_str}")
                except ET.ParseError:
                    pass  # Invalid XML, just store raw
            
            ports_str = ', '.join(ports_list)
            services_str = ', '.join(services_list)
            
            # Save to database
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO nmap_scans (ip, scan_timestamp, ports, services, nmap_xml)
                         VALUES (?, ?, ?, ?, ?)''',
                      (ip, int(time.time()), ports_str, services_str, nmap_xml))
            conn.commit()
            conn.close()
            logger.info(f"Nmap results saved for {ip}: {len(ports_list)} open ports")
        except Exception as e:
            logger.error(f"Error saving Nmap results: {e}", exc_info=True)
    
    def _compare_scans(self, scan_id1, scan_id2):
        """Compare two scans and return differences."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        # Get hosts from both scans
        c.execute('SELECT ip, mac, hostname, vendor FROM hosts WHERE scan_id=?', (scan_id1,))
        hosts1 = {row[0]: {'ip': row[0], 'mac': row[1], 'hostname': row[2], 'vendor': row[3]} 
                  for row in c.fetchall()}
        
        c.execute('SELECT ip, mac, hostname, vendor FROM hosts WHERE scan_id=?', (scan_id2,))
        hosts2 = {row[0]: {'ip': row[0], 'mac': row[1], 'hostname': row[2], 'vendor': row[3]} 
                  for row in c.fetchall()}
        
        # Find differences
        new_hosts = [hosts2[ip] for ip in hosts2 if ip not in hosts1]
        disappeared_hosts = [hosts1[ip] for ip in hosts1 if ip not in hosts2]
        
        # Find changed hosts (same IP, different MAC/hostname)
        changed_hosts = []
        for ip in hosts1:
            if ip in hosts2:
                h1 = hosts1[ip]
                h2 = hosts2[ip]
                changes = {}
                if h1['mac'] != h2['mac']:
                    changes['mac'] = {'old': h1['mac'], 'new': h2['mac']}
                if h1['hostname'] != h2['hostname']:
                    changes['hostname'] = {'old': h1['hostname'], 'new': h2['hostname']}
                if h1['vendor'] != h2['vendor']:
                    changes['vendor'] = {'old': h1['vendor'], 'new': h2['vendor']}
                if changes:
                    changed_hosts.append({'ip': ip, **h2, 'changes': changes})
        
        conn.close()
        
        return {
            'new': new_hosts,
            'disappeared': disappeared_hosts,
            'changed': changed_hosts,
            'unchanged': [hosts1[ip] for ip in hosts1 if ip in hosts2 and ip not in [h['ip'] for h in changed_hosts]]
        }
    
    def _get_database_stats(self):
        """Get database statistics."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Total scans
            c.execute('SELECT COUNT(*) FROM scans')
            total_scans = c.fetchone()[0]
            
            # Total hosts
            c.execute('SELECT COUNT(DISTINCT ip) FROM hosts')
            unique_hosts = c.fetchone()[0]
            
            # Total Nmap scans
            c.execute('SELECT COUNT(*) FROM nmap_scans')
            total_nmap_scans = c.fetchone()[0]
            
            # Oldest scan
            c.execute('SELECT MIN(ts) FROM scans')
            oldest = c.fetchone()[0]
            
            # Newest scan
            c.execute('SELECT MAX(ts) FROM scans')
            newest = c.fetchone()[0]
            
            # Hosts by vendor
            c.execute('''SELECT vendor, COUNT(DISTINCT ip) as count 
                        FROM hosts 
                        WHERE vendor IS NOT NULL AND vendor != ''
                        GROUP BY vendor 
                        ORDER BY count DESC 
                        LIMIT 10''')
            top_vendors = [{'vendor': row[0], 'count': row[1]} for row in c.fetchall()]
            
            conn.close()
            
            return {
                'total_scans': total_scans,
                'unique_hosts': unique_hosts,
                'total_nmap_scans': total_nmap_scans,
                'oldest_scan': oldest,
                'newest_scan': newest,
                'top_vendors': top_vendors
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
    
    def _get_device_timeline(self, ip, days=7):
        """Get device availability timeline."""
        try:
            cutoff_time = int(time.time()) - (days * 24 * 60 * 60)
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Get all scans where this IP appeared
            c.execute('''SELECT s.ts, s.id, h.mac, h.hostname, h.vendor
                       FROM scans s
                       JOIN hosts h ON s.id = h.scan_id
                       WHERE h.ip = ? AND s.ts >= ?
                       ORDER BY s.ts ASC''',
                    (ip, cutoff_time))
            
            timeline = []
            for row in c.fetchall():
                timeline.append({
                    'timestamp': row[0],
                    'scan_id': row[1],
                    'mac': row[2],
                    'hostname': row[3],
                    'vendor': row[4]
                })
            
            conn.close()
            return timeline
        except Exception as e:
            logger.error(f"Error getting timeline: {e}")
            return []
    
    def _add_device_tag(self, ip, tag):
        """Add a custom tag to a device."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO device_tags (ip, tag, created_at)
                        VALUES (?, ?, ?)''',
                     (ip, tag, int(time.time())))
            conn.commit()
            conn.close()
            self._audit_log('add_tag', {'ip': ip, 'tag': tag})
        except Exception as e:
            logger.error(f"Error adding tag: {e}")
    
    def _get_device_tags(self, ip):
        """Get tags for a device."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('SELECT tag FROM device_tags WHERE ip = ?', (ip,))
            tags = [row[0] for row in c.fetchall()]
            conn.close()
            return tags
        except Exception as e:
            logger.error(f"Error getting tags: {e}")
            return []
    
    def _scan_multiple_networks(self, scan_id, cidrs):
        """Scan multiple networks in parallel."""
        import concurrent.futures
        
        logger.info(f"Starting multi-network scan {scan_id} for {len(cidrs)} networks")
        
        all_hosts = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(arp_scan, cidr): cidr for cidr in cidrs}
            
            for future in concurrent.futures.as_completed(futures):
                cidr = futures[future]
                try:
                    hosts = future.result()
                    all_hosts.extend(hosts)
                    logger.info(f"Completed scan for {cidr}: {len(hosts)} hosts")
                except Exception as e:
                    logger.error(f"Error scanning {cidr}: {e}")
        
        # Store combined results
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('INSERT INTO scans (id, cidr, ts, host_count) VALUES (?, ?, ?, ?)',
                 (scan_id, f"multi:{','.join(cidrs)}", int(time.time()), len(all_hosts)))
        
        for h in all_hosts:
            vendor = self._lookup_vendor(h.get('mac', ''))
            c.execute('INSERT INTO hosts (scan_id, ip, mac, hostname, vendor) VALUES (?, ?, ?, ?, ?)',
                     (scan_id, h['ip'], h['mac'], h.get('hostname'), vendor))
        
        conn.commit()
        conn.close()
        logger.info(f"Multi-network scan {scan_id} completed: {len(all_hosts)} total hosts")
    
    def _add_scan_schedule(self, cidr, schedule):
        """Add a scheduled scan."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute('''INSERT INTO scan_schedules (cidr, schedule, enabled, created_at)
                        VALUES (?, ?, ?, ?)''',
                     (cidr, schedule, 1, int(time.time())))
            conn.commit()
            conn.close()
            self._audit_log('add_schedule', {'cidr': cidr, 'schedule': schedule})
            logger.info(f"Added scheduled scan: {cidr} - {schedule}")
        except Exception as e:
            logger.error(f"Error adding schedule: {e}")
    
    def _wake_on_lan(self, mac):
        """Send Wake-on-LAN magic packet."""
        try:
            from scapy.all import sendp, Ether
            # Create magic packet
            mac_bytes = bytes.fromhex(mac.replace(':', '').replace('-', ''))
            magic_packet = b'\xff' * 6 + mac_bytes * 16
            
            # Send broadcast
            packet = Ether(dst='ff:ff:ff:ff:ff:ff') / magic_packet
            sendp(packet, verbose=False)
            logger.info(f"Wake-on-LAN packet sent to {mac}")
            return True
        except Exception as e:
            logger.error(f"WoL error: {e}")
            return False
    
    def _backup_database(self, backup_path):
        """Backup database to specified path."""
        try:
            import shutil
            shutil.copy2(self.db_path, backup_path)
            self._audit_log('backup', {'path': backup_path})
            logger.info(f"Database backed up to {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Backup error: {e}")
            return False

    def _lookup_vendor(self, mac):
        """Lookup vendor from MAC address using OUI database."""
        if not mac:
            return None
        
        # Try dev mode OUI DB first, then production
        oui_db_paths = [
            os.path.expanduser("~/.local/share/netmapper/oui.db"),
            "/usr/lib/netmapper/oui.db",
            os.path.join(os.path.dirname(__file__), "oui.db")
        ]
        
        for db_path in oui_db_paths:
            if os.path.exists(db_path):
                vendor = self._lookup_vendor_from_db(mac, db_path)
                if vendor:
                    return vendor
        
        return None
    
    def _lookup_vendor_from_db(self, mac, db_path):
        """Lookup vendor from OUI SQLite database."""
        try:
            # Extract first 6 hex chars (OUI prefix) from MAC
            mac_clean = mac.upper().replace('-', ':').replace(' ', '')
            parts = mac_clean.split(':')
            
            if len(parts) < 3:
                return None
            
            oui_prefix = f"{parts[0]}{parts[1]}{parts[2]}"
            
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute('SELECT vendor FROM oui WHERE oui_prefix = ?', (oui_prefix,))
            result = c.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.debug(f"OUI lookup error: {e}")
            return None

    def _get_scan_results(self, scan_id):
        """Retrieve scan results from database."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'SELECT ip, mac, hostname, vendor FROM hosts WHERE scan_id=?',
            (scan_id,)
        )
        rows = c.fetchall()
        conn.close()
        
        return [
            {
                "ip": row[0],
                "mac": row[1],
                "hostname": row[2],
                "vendor": row[3]
            }
            for row in rows
        ]

    def _get_scan_history(self, limit):
        """Get recent scan history."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            'SELECT id, cidr, ts, host_count FROM scans ORDER BY ts DESC LIMIT ?',
            (limit,)
        )
        rows = c.fetchall()
        conn.close()
        
        return [
            {
                "scan_id": row[0],
                "cidr": row[1],
                "timestamp": row[2],
                "host_count": row[3]
            }
            for row in rows
        ]


if __name__ == '__main__':
    import sys
    
    # Check for dev mode flag
    dev_mode = '--dev' in sys.argv or os.getenv('NETMAPPER_DEV', '').lower() == 'true'
    
    if dev_mode:
        logger.info("Running in DEV mode (using /tmp socket and user database)")
    
    helper = NetMapperHelper(dev_mode=dev_mode)
    try:
        helper.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down helper service")

