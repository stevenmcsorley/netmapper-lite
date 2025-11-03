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
        
        # Ensure database directory exists
        db_dir = os.path.dirname(self.db_path)
        os.makedirs(db_dir, exist_ok=True)
        
        # Initialize database
        self._init_db()
        
        # Setup socket
        self._setup_socket()

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
        try:
            data = conn.recv(65536).decode('utf-8')
            if not data:
                return
            
            req = json.loads(data)
            cmd = req.get('cmd')
            
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
                
            elif cmd == 'list_history':
                limit = req.get('limit', 10)
                history = self._get_scan_history(limit)
                conn.sendall(json.dumps({
                    "status": "ok",
                    "history": history
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

