#!/usr/bin/env python3
"""
NetMapper-Lite GTK4 Frontend
Desktop GUI for network mapping and scanning.
"""
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio
import json
import socket
import os
import time
import sqlite3
from pathlib import Path

# Socket paths (try dev mode first, then production)
DEV_SOCKET_PATH = "/tmp/netmapper-helper.sock"
SOCKET_PATH = "/var/run/netmapper-helper.sock"

DEV_DB_PATH = os.path.expanduser("~/.local/share/netmapper/netmapper.db")
DB_PATH = "/var/lib/netmapper/netmapper.db"


class MainWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(application=app, title='NetMapper-Lite')
        self.set_default_size(1000, 700)
        self.current_scan_id = None
        
        # Detect socket path (prefer dev mode)
        self.socket_path = DEV_SOCKET_PATH if os.path.exists(DEV_SOCKET_PATH) else SOCKET_PATH
        self.db_path = DEV_DB_PATH if os.path.exists(DEV_DB_PATH) else DB_PATH
        
        # Build UI
        self._build_ui()
        
        # Setup auto-refresh
        self._refresh_timeout_id = None

    def _build_ui(self):
        """Build the GTK4 UI."""
        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=12)
        self.set_child(vbox)
        
        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        self.set_titlebar(header)
        
        # Control panel
        control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vbox.append(control_box)
        
        # CIDR input
        cidr_label = Gtk.Label(label="Network CIDR:")
        control_box.append(cidr_label)
        
        self.cidr_entry = Gtk.Entry()
        self.cidr_entry.set_text('192.168.1.0/24')
        self.cidr_entry.set_placeholder_text('192.168.1.0/24')
        self.cidr_entry.set_hexpand(True)
        control_box.append(self.cidr_entry)
        
        # Scan button
        self.scan_btn = Gtk.Button(label='Start Scan')
        self.scan_btn.connect('clicked', self.on_scan_clicked)
        self.scan_btn.add_css_class('suggested-action')
        control_box.append(self.scan_btn)
        
        # Status label
        self.status_label = Gtk.Label(label='Ready')
        self.status_label.set_halign(Gtk.Align.START)
        control_box.append(self.status_label)
        
        # Separator
        vbox.append(Gtk.Separator())
        
        # Results area - TreeView
        results_frame = Gtk.Frame(label="Scan Results")
        vbox.append(results_frame)
        
        # Create list store: IP, MAC, Hostname, Vendor
        self.store = Gtk.ListStore(str, str, str, str)  # IP, MAC, Hostname, Vendor
        
        # TreeView
        self.tree_view = Gtk.TreeView(model=self.store)
        self.tree_view.set_hexpand(True)
        self.tree_view.set_vexpand(True)
        
        # Columns
        renderer = Gtk.CellRendererText()
        
        col = Gtk.TreeViewColumn(title="IP Address")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 0)
        col.set_sort_column_id(0)
        self.tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="MAC Address")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 1)
        col.set_sort_column_id(1)
        self.tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Hostname")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 2)
        col.set_sort_column_id(2)
        self.tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Vendor")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 3)
        col.set_sort_column_id(3)
        self.tree_view.append_column(col)
        
        # Scrolled window
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.tree_view)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        results_frame.set_child(scroll)
        
        # Bottom status bar
        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin=6)
        vbox.append(status_bar)
        
        self.host_count_label = Gtk.Label(label="Hosts: 0")
        status_bar.append(self.host_count_label)
        
        # Connection status
        conn_status = "🔴 Helper not available" if not os.path.exists(self.socket_path) else "🟢 Helper connected"
        self.conn_label = Gtk.Label(label=conn_status)
        status_bar.append(self.conn_label)

    def on_scan_clicked(self, btn):
        """Handle scan button click."""
        cidr = self.cidr_entry.get_text().strip()
        if not cidr:
            self.status_label.set_text('Please enter a CIDR network')
            return
        
        # Validate CIDR format (basic)
        if '/' not in cidr:
            self.status_label.set_text('Invalid CIDR format (use: 192.168.1.0/24)')
            return
        
        self.scan_btn.set_sensitive(False)
        self.status_label.set_text('Starting scan...')
        self.store.clear()
        
        # Send scan request
        result = self.send_request({"cmd": "scan", "cidr": cidr})
        
        if not result:
            self.status_label.set_text('Error: Helper service not available')
            self.scan_btn.set_sensitive(True)
            return
        
        try:
            j = json.loads(result)
            if j.get('status') == 'started':
                self.current_scan_id = j.get('scan_id')
                self.status_label.set_text(f"Scan started: {self.current_scan_id[:8]}...")
                # Start polling for results
                self._start_polling()
            else:
                self.status_label.set_text(f"Error: {j.get('message', 'Unknown error')}")
                self.scan_btn.set_sensitive(True)
        except json.JSONDecodeError as e:
            self.status_label.set_text(f"Error parsing response: {e}")
            self.scan_btn.set_sensitive(True)
        except Exception as e:
            self.status_label.set_text(f"Error: {e}")
            self.scan_btn.set_sensitive(True)

    def _start_polling(self):
        """Start polling for scan results."""
        if self._refresh_timeout_id:
            GLib.source_remove(self._refresh_timeout_id)
        
        self._poll_attempts = 0
        self._poll_for_results()

    def _poll_for_results(self):
        """Poll database for scan results."""
        self._poll_attempts += 1
        
        if not self.current_scan_id:
            return False
        
        # Try to get results via helper API first
        result = self.send_request({
            "cmd": "get_results",
            "scan_id": self.current_scan_id
        })
        
        if result:
            try:
                j = json.loads(result)
                if j.get('status') == 'ok' and j.get('results'):
                    hosts = j.get('results', [])
                    if hosts:
                        self._update_results(hosts)
                        self.status_label.set_text(f"Scan complete: {len(hosts)} hosts found")
                        self.scan_btn.set_sensitive(True)
                        return False
            except:
                pass
        
        # Fallback: direct database access
        try:
            if os.path.exists(self.db_path):
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute(
                    'SELECT ip, mac, hostname, vendor FROM hosts WHERE scan_id=?',
                    (self.current_scan_id,)
                )
                rows = c.fetchall()
                conn.close()
                
                if rows:
                    hosts = [
                        {"ip": r[0], "mac": r[1], "hostname": r[2], "vendor": r[3] or ""}
                        for r in rows
                    ]
                    self._update_results(hosts)
                    self.status_label.set_text(f"Scan complete: {len(hosts)} hosts found")
                    self.scan_btn.set_sensitive(True)
                    return False
        except Exception as e:
            print(f"Database access error: {e}")
        
        # Keep polling if not done (max 60 attempts = 2 minutes)
        if self._poll_attempts < 60:
            self.status_label.set_text(f"Scanning... ({self._poll_attempts * 2}s)")
            self._refresh_timeout_id = GLib.timeout_add_seconds(2, self._poll_for_results)
            return False
        else:
            self.status_label.set_text("Scan timeout - check helper logs")
            self.scan_btn.set_sensitive(True)
            return False

    def _update_results(self, hosts):
        """Update tree view with scan results."""
        self.store.clear()
        for host in hosts:
            self.store.append([
                host.get('ip', ''),
                host.get('mac', ''),
                host.get('hostname') or '-',
                host.get('vendor') or '-'
            ])
        self.host_count_label.set_text(f"Hosts: {len(hosts)}")

    def send_request(self, obj):
        """Send JSON request to helper via UNIX socket."""
        if not os.path.exists(self.socket_path):
            return None
        
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect(self.socket_path)
            s.sendall(json.dumps(obj).encode('utf-8'))
            data = s.recv(65536).decode('utf-8')
            s.close()
            return data
        except (ConnectionRefusedError, FileNotFoundError, socket.error) as e:
            print(f"Socket error: {e}")
            return None
        except Exception as e:
            print(f"Request error: {e}")
            return None


class NetMapperApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.netmapper.lite')
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = MainWindow(self)
        self.window.present()


if __name__ == '__main__':
    app = NetMapperApp()
    app.run(None)

