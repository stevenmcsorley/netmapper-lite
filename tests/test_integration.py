#!/usr/bin/env python3
"""
Integration tests for NetMapper-Lite.
Tests helper service, IPC communication, and database operations.
"""
import unittest
import os
import sys
import json
import socket
import sqlite3
import time
import threading
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.netmapper_helper import NetMapperHelper
from backend.scanner import arp_scan


class TestNetMapperIntegration(unittest.TestCase):
    """Integration tests for NetMapper helper and IPC."""
    
    def setUp(self):
        """Set up test environment."""
        # Use temporary directories
        self.temp_dir = tempfile.mkdtemp()
        self.test_socket = os.path.join(self.temp_dir, "test-helper.sock")
        self.test_db = os.path.join(self.temp_dir, "test-netmapper.db")
        
        # Start helper in test mode
        self.helper = NetMapperHelper(
            socket_path=self.test_socket,
            db_path=self.test_db,
            dev_mode=True
        )
        
        # Start helper in background thread
        self.helper_thread = threading.Thread(
            target=self.helper.serve_forever,
            daemon=True
        )
        self.helper_thread.start()
        
        # Wait for socket to be ready
        timeout = 5
        elapsed = 0
        while not os.path.exists(self.test_socket) and elapsed < timeout:
            time.sleep(0.1)
            elapsed += 0.1
        
        if not os.path.exists(self.test_socket):
            raise RuntimeError("Helper socket not created in time")
    
    def tearDown(self):
        """Clean up test environment."""
        # Helper will exit when socket is closed
        if os.path.exists(self.test_socket):
            try:
                os.remove(self.test_socket)
            except:
                pass
        
        # Clean up temp directory
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def send_request(self, request_dict):
        """Helper to send request to helper service."""
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(self.test_socket)
        s.sendall(json.dumps(request_dict).encode('utf-8'))
        data = s.recv(8192).decode('utf-8')
        s.close()
        return json.loads(data)
    
    def test_helper_connection(self):
        """Test that helper accepts connections."""
        self.assertTrue(os.path.exists(self.test_socket))
    
    def test_scan_command(self):
        """Test scan command initiates a scan."""
        # Use a small non-routable network for testing
        # This won't actually scan, but tests the command flow
        response = self.send_request({
            "cmd": "scan",
            "cidr": "192.0.2.0/30"  # TEST-NET from RFC 5737
        })
        
        self.assertEqual(response.get('status'), 'started')
        self.assertIn('scan_id', response)
        scan_id = response['scan_id']
        self.assertIsNotNone(scan_id)
        self.assertEqual(len(scan_id), 36)  # UUID length
    
    def test_get_results_command(self):
        """Test get_results command."""
        # First create a scan
        scan_resp = self.send_request({
            "cmd": "scan",
            "cidr": "192.0.2.0/30"
        })
        scan_id = scan_resp['scan_id']
        
        # Wait a bit for scan to complete
        time.sleep(2)
        
        # Get results
        results_resp = self.send_request({
            "cmd": "get_results",
            "scan_id": scan_id
        })
        
        self.assertEqual(results_resp.get('status'), 'ok')
        self.assertIn('results', results_resp)
        self.assertIsInstance(results_resp['results'], list)
    
    def test_list_history_command(self):
        """Test list_history command."""
        response = self.send_request({
            "cmd": "list_history",
            "limit": 5
        })
        
        self.assertEqual(response.get('status'), 'ok')
        self.assertIn('history', response)
        self.assertIsInstance(response['history'], list)
    
    def test_nmap_command(self):
        """Test nmap command (will fail if nmap not installed, but tests command)."""
        response = self.send_request({
            "cmd": "nmap",
            "ip": "127.0.0.1",
            "ports": "22"
        })
        
        # Command should succeed even if nmap not found (returns error in XML)
        self.assertIn('status', response)
        # May be 'ok' or 'error' depending on nmap availability
    
    def test_invalid_command(self):
        """Test invalid command handling."""
        response = self.send_request({
            "cmd": "invalid_command"
        })
        
        self.assertEqual(response.get('status'), 'error')
        self.assertIn('message', response)
    
    def test_database_storage(self):
        """Test that scan results are stored in database."""
        # Create a scan
        scan_resp = self.send_request({
            "cmd": "scan",
            "cidr": "192.0.2.0/30"
        })
        scan_id = scan_resp['scan_id']
        
        # Wait for scan to complete
        time.sleep(3)
        
        # Check database directly
        conn = sqlite3.connect(self.test_db)
        c = conn.cursor()
        
        # Check scan record
        c.execute('SELECT id, cidr FROM scans WHERE id = ?', (scan_id,))
        scan_row = c.fetchone()
        self.assertIsNotNone(scan_row)
        self.assertEqual(scan_row[1], '192.0.2.0/30')
        
        # Check hosts table
        c.execute('SELECT COUNT(*) FROM hosts WHERE scan_id = ?', (scan_id,))
        host_count = c.fetchone()[0]
        self.assertIsInstance(host_count, int)
        
        conn.close()


class TestScannerFunctions(unittest.TestCase):
    """Unit tests for scanner functions."""
    
    def test_arp_scan_invalid_cidr(self):
        """Test ARP scan with invalid CIDR."""
        # This should not crash, but return empty list
        hosts = arp_scan("invalid.cidr")
        self.assertIsInstance(hosts, list)
    
    def test_arp_scan_non_routable(self):
        """Test ARP scan on non-routable test network."""
        # Use TEST-NET (won't find anything, but shouldn't crash)
        hosts = arp_scan("192.0.2.0/30", timeout=1)
        self.assertIsInstance(hosts, list)


if __name__ == '__main__':
    unittest.main()


