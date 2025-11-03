#!/usr/bin/env python3
"""
NetMapper-Lite GTK4 Frontend
Desktop GUI for network mapping and scanning.
"""
import warnings
# Suppress GTK4 deprecation warnings for TreeView (still functional)
warnings.filterwarnings('ignore', category=DeprecationWarning, module='gi')

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio, Gdk
import cairo
import sys
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
        self.set_default_size(1200, 800)
        self.current_scan_id = None
        
        # Detect socket path (prefer dev mode)
        self.socket_path = DEV_SOCKET_PATH if os.path.exists(DEV_SOCKET_PATH) else SOCKET_PATH
        self.db_path = DEV_DB_PATH if os.path.exists(DEV_DB_PATH) else DB_PATH
        
        # Initialize network map data
        self.network_nodes = []
        self.network_edges = []
        self.map_drawing_area = None
        
        # Build UI
        try:
            self._build_ui()
        except Exception as e:
            print(f"❌ Error building UI: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Setup auto-refresh
        self._refresh_timeout_id = None

    def _build_ui(self):
        """Build the GTK4 UI."""
        # Main container with improved layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.set_child(main_box)
        
        # Left sidebar for history
        sidebar = self._build_sidebar()
        main_box.append(sidebar)
        
        # Main content area
        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_area.set_margin_start(12)
        content_area.set_margin_end(12)
        content_area.set_margin_top(12)
        content_area.set_margin_bottom(12)
        main_box.append(content_area)
        
        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)
        self.set_titlebar(header)
        
        # Control panel
        control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        content_area.append(control_box)
        
        # CIDR input with label
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cidr_label = Gtk.Label(label="Network CIDR:")
        input_box.append(cidr_label)
        
        self.cidr_entry = Gtk.Entry()
        # Auto-detect network for default CIDR
        try:
            import subprocess
            result = subprocess.run(['ip', '-4', 'route', 'show', 'default'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                parts = result.stdout.split()
                for i, part in enumerate(parts):
                    if part == 'src':
                        ip = parts[i+1] if i+1 < len(parts) else None
                        if ip:
                            net = '.'.join(ip.split('.')[:-1])
                            default_cidr = f"{net}.0/24"
                            self.cidr_entry.set_text(default_cidr)
                            break
        except:
            pass
        
        if not self.cidr_entry.get_text():
            self.cidr_entry.set_text('192.168.1.0/24')
        self.cidr_entry.set_placeholder_text('e.g., 192.168.1.0/24')
        self.cidr_entry.set_hexpand(True)
        input_box.append(self.cidr_entry)
        control_box.append(input_box)
        
        # Scan button
        self.scan_btn = Gtk.Button(label='Start Scan')
        self.scan_btn.connect('clicked', self.on_scan_clicked)
        self.scan_btn.add_css_class('suggested-action')
        control_box.append(self.scan_btn)
        
        # Nmap scan button (for selected host)
        self.nmap_btn = Gtk.Button(label='Scan Ports (Nmap)')
        self.nmap_btn.connect('clicked', self.on_nmap_clicked)
        self.nmap_btn.set_sensitive(False)
        control_box.append(self.nmap_btn)
        
        # Export button
        self.export_btn = Gtk.Button(label='Export Results')
        self.export_btn.connect('clicked', self.on_export_clicked)
        self.export_btn.set_sensitive(False)
        control_box.append(self.export_btn)
        
        # Status label
        self.status_label = Gtk.Label(label='Ready')
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.set_margin_start(6)
        control_box.append(self.status_label)
        
        # Separator
        content_area.append(Gtk.Separator())
        
        # Results area - Notebook for tabs
        self.notebook = Gtk.Notebook()
        self.notebook.set_hexpand(True)
        self.notebook.set_vexpand(True)
        content_area.append(self.notebook)
        
        # Scan Results tab
        results_frame = self._build_results_tab()
        self.notebook.append_page(results_frame, Gtk.Label(label="Scan Results"))
        
        # History tab
        history_frame = self._build_history_tab()
        self.notebook.append_page(history_frame, Gtk.Label(label="History"))
        
        # Network Map tab
        map_frame = self._build_network_map_tab()
        self.notebook.append_page(map_frame, Gtk.Label(label="Network Map"))
        
        # Bottom status bar
        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_bar.set_margin_start(6)
        status_bar.set_margin_end(6)
        status_bar.set_margin_top(6)
        status_bar.set_margin_bottom(6)
        content_area.append(status_bar)
        
        self.host_count_label = Gtk.Label(label="Hosts: 0")
        status_bar.append(self.host_count_label)
        
        # Connection status
        conn_status = "🔴 Helper not available" if not os.path.exists(self.socket_path) else "🟢 Helper connected"
        self.conn_label = Gtk.Label(label=conn_status)
        status_bar.append(self.conn_label)
        
        # Start helper button (if not available)
        self.start_helper_btn = Gtk.Button(label="Start Helper")
        self.start_helper_btn.connect('clicked', self._start_helper_clicked)
        if not os.path.exists(self.socket_path):
            self.start_helper_btn.set_visible(True)
        else:
            self.start_helper_btn.set_visible(False)
        status_bar.append(self.start_helper_btn)
        
        # Refresh connection status periodically
        GLib.timeout_add_seconds(5, self._update_connection_status)
    
    def _build_sidebar(self):
        """Build left sidebar with scan history."""
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sidebar.set_size_request(200, -1)
        sidebar.set_margin_start(6)
        sidebar.set_margin_end(6)
        sidebar.set_margin_top(6)
        sidebar.set_margin_bottom(6)
        
        # Sidebar frame
        frame = Gtk.Frame(label="Recent Scans")
        sidebar.append(frame)
        
        # History list
        self.history_store = Gtk.ListStore(str, str, str)  # scan_id, cidr, timestamp
        self.history_view = Gtk.TreeView(model=self.history_store)
        
        # Columns
        renderer = Gtk.CellRendererText()
        
        col = Gtk.TreeViewColumn(title="CIDR")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 1)
        self.history_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Time")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 2)
        self.history_view.append_column(col)
        
        # Selection
        selection = self.history_view.get_selection()
        selection.connect("changed", self.on_history_selected)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.history_view)
        frame.set_child(scroll)
        
        # Load history
        self._load_scan_history()
        
        return sidebar
    
    def _build_results_tab(self):
        """Build scan results tab."""
        results_frame = Gtk.Frame(label="Scan Results")
        
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
        col.set_resizable(True)
        self.tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="MAC Address")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 1)
        col.set_sort_column_id(1)
        col.set_resizable(True)
        self.tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Hostname")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 2)
        col.set_sort_column_id(2)
        col.set_resizable(True)
        self.tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Vendor")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 3)
        col.set_sort_column_id(3)
        col.set_resizable(True)
        self.tree_view.append_column(col)
        
        # Connect selection changed
        selection = self.tree_view.get_selection()
        selection.connect("changed", self.on_host_selected)
        
        # Double-click to show details
        self.tree_view.connect("row-activated", self.on_host_activated)
        
        # Scrolled window
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.tree_view)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        results_frame.set_child(scroll)
        
        # Store selected host
        self.selected_host = None
        
        return results_frame
    
    def _build_history_tab(self):
        """Build history tab."""
        history_frame = Gtk.Frame(label="Scan History")
        
        # History list store
        history_store = Gtk.ListStore(str, str, str, str)  # scan_id, cidr, timestamp, host_count
        
        history_view = Gtk.TreeView(model=history_store)
        
        renderer = Gtk.CellRendererText()
        
        col = Gtk.TreeViewColumn(title="CIDR")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 1)
        history_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Date/Time")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 2)
        history_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Hosts")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 3)
        history_view.append_column(col)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(history_view)
        history_frame.set_child(scroll)
        
        # Load history into this view
        self._load_full_history(history_store)
        
        return history_frame
    
    def _build_network_map_tab(self):
        """Build network topology map tab."""
        map_frame = Gtk.Frame(label="Network Topology Map")
        
        # Main box for map
        map_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        map_box.set_margin_start(12)
        map_box.set_margin_end(12)
        map_box.set_margin_top(12)
        map_box.set_margin_bottom(12)
        map_frame.set_child(map_box)
        
        # Info label
        info_label = Gtk.Label(label="Network topology visualization - click nodes for details")
        info_label.set_halign(Gtk.Align.START)
        map_box.append(info_label)
        
        # Drawing area for network map
        self.map_drawing_area = Gtk.DrawingArea()
        self.map_drawing_area.set_hexpand(True)
        self.map_drawing_area.set_vexpand(True)
        self.map_drawing_area.set_content_width(800)
        self.map_drawing_area.set_content_height(600)
        
        # Store network map data
        self.network_nodes = []  # List of {x, y, ip, mac, hostname, vendor, type, radius}
        self.network_edges = []  # List of connections (for future)
        
        # Connect draw signal
        self.map_drawing_area.set_draw_func(self._draw_network_map)
        
        # Mouse click handler
        click_controller = Gtk.GestureClick()
        click_controller.connect("pressed", self._on_map_clicked)
        self.map_drawing_area.add_controller(click_controller)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.map_drawing_area)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        map_box.append(scroll)
        
        # Refresh button
        refresh_btn = Gtk.Button(label="Refresh Map")
        refresh_btn.connect('clicked', self._refresh_network_map)
        map_box.append(refresh_btn)
        
        return map_frame
    
    def _refresh_network_map(self, btn):
        """Refresh the network map with current scan results."""
        if not self.current_scan_id:
            self._show_info_dialog("Network Map", "Run a scan first to generate the network map.")
            return
        
        # Get current results
        result = self.send_request({
            "cmd": "get_results",
            "scan_id": self.current_scan_id
        })
        
        if result:
            try:
                j = json.loads(result)
                if j.get('status') == 'ok':
                    hosts = j.get('results', [])
                    self._generate_network_map(hosts)
                    self.map_drawing_area.queue_draw()
            except:
                pass
    
    def _generate_network_map(self, hosts):
        """Generate network topology from hosts."""
        if not hosts:
            self.network_nodes = []
            return
        
        # Simple circular layout
        import math
        center_x, center_y = 400, 300
        radius = min(250, len(hosts) * 15)
        
        self.network_nodes = []
        
        # Identify gateway (usually .1 or .254)
        gateway = None
        for host in hosts:
            ip_parts = host.get('ip', '').split('.')
            if len(ip_parts) == 4:
                last_octet = ip_parts[-1]
                if last_octet in ['1', '254']:
                    gateway = host
                    break
        
        # Position gateway in center if found
        if gateway:
            self.network_nodes.append({
                'x': center_x,
                'y': center_y,
                'ip': gateway.get('ip', ''),
                'mac': gateway.get('mac', ''),
                'hostname': gateway.get('hostname') or 'Router',
                'vendor': gateway.get('vendor') or '',
                'type': 'gateway',
                'radius': 25
            })
            other_hosts = [h for h in hosts if h.get('ip') != gateway.get('ip')]
        else:
            other_hosts = hosts
        
        # Position other hosts in circle
        angle_step = (2 * math.pi) / len(other_hosts) if other_hosts else 0
        
        for i, host in enumerate(other_hosts):
            angle = i * angle_step
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            
            # Determine node type
            node_type = 'device'
            hostname = host.get('hostname') or ''
            vendor = host.get('vendor') or ''
            
            # Classify by vendor/type
            if 'router' in hostname.lower() or 'gateway' in hostname.lower():
                node_type = 'gateway'
            elif 'server' in hostname.lower():
                node_type = 'server'
            
            self.network_nodes.append({
                'x': x,
                'y': y,
                'ip': host.get('ip', ''),
                'mac': host.get('mac', ''),
                'hostname': hostname or host.get('ip', ''),
                'vendor': vendor,
                'type': node_type,
                'radius': 20
            })
        
        # Generate edges (connections to gateway)
        self.network_edges = []
        if gateway:
            gateway_ip = gateway.get('ip', '')
            for node in self.network_nodes:
                if node['ip'] != gateway_ip:
                    self.network_edges.append((node, gateway_ip))
    
    def _draw_network_map(self, widget, cr, width, height):
        """Draw the network topology map."""
        # Clear background
        cr.set_source_rgb(0.95, 0.95, 0.95)
        cr.paint()
        
        if not self.network_nodes:
            # Draw placeholder text
            cr.set_source_rgb(0.5, 0.5, 0.5)
            cr.select_font_face("Sans")
            cr.set_font_size(24)
            text = "Run a scan and click 'Refresh Map' to view network topology"
            (x, y, text_width, text_height, dx, dy) = cr.text_extents(text)
            cr.move_to((width - text_width) / 2, height / 2)
            cr.show_text(text)
            return
        
        # Draw edges (connections) first
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.set_line_width(2)
        
        gateway_node = None
        for node in self.network_nodes:
            if node['type'] == 'gateway':
                gateway_node = node
                break
        
        if gateway_node:
            for node in self.network_nodes:
                if node['type'] != 'gateway':
                    cr.move_to(node['x'], node['y'])
                    cr.line_to(gateway_node['x'], gateway_node['y'])
                    cr.stroke()
        
        # Draw nodes
        for node in self.network_nodes:
            # Color by type
            if node['type'] == 'gateway':
                cr.set_source_rgb(0.2, 0.6, 0.9)  # Blue for gateway
            elif node['type'] == 'server':
                cr.set_source_rgb(0.9, 0.6, 0.2)  # Orange for server
            else:
                cr.set_source_rgb(0.4, 0.7, 0.4)  # Green for devices
            
            # Draw node circle
            cr.arc(node['x'], node['y'], node['radius'], 0, 2 * 3.14159)
            cr.fill()
            
            # Draw border
            cr.set_source_rgb(0.2, 0.2, 0.2)
            cr.set_line_width(2)
            cr.arc(node['x'], node['y'], node['radius'], 0, 2 * 3.14159)
            cr.stroke()
            
            # Draw label (IP address)
            cr.set_source_rgb(0, 0, 0)
            cr.select_font_face("Sans Bold")
            cr.set_font_size(10)
            
            label = node['ip'].split('.')[-1]  # Last octet
            (x, y, text_width, text_height, dx, dy) = cr.text_extents(label)
            cr.move_to(node['x'] - text_width / 2, node['y'] + node['radius'] + text_height + 5)
            cr.show_text(label)
            
            # Draw hostname if short
            if node['hostname'] and len(node['hostname']) < 15:
                cr.set_font_size(8)
                hostname = node['hostname']
                (x, y, text_width, text_height, dx, dy) = cr.text_extents(hostname)
                cr.move_to(node['x'] - text_width / 2, node['y'] - node['radius'] - 5)
                cr.show_text(hostname)
    
    def _on_map_clicked(self, gesture, n_press, x, y):
        """Handle mouse click on network map."""
        # Get actual click coordinates in drawing area
        allocation = self.map_drawing_area.get_allocation()
        scale_x = self.map_drawing_area.get_content_width() / allocation.width if allocation.width > 0 else 1
        scale_y = self.map_drawing_area.get_content_height() / allocation.height if allocation.height > 0 else 1
        map_x = x * scale_x
        map_y = y * scale_y
        
        # Find clicked node
        for node in self.network_nodes:
            distance = ((map_x - node['x'])**2 + (map_y - node['y'])**2)**0.5
            if distance <= node['radius']:
                # Show details for this node
                self._show_host_details(
                    node['ip'],
                    node['mac'],
                    node['hostname'],
                    node['vendor']
                )
                break
    
    def _update_connection_status(self):
        """Update connection status indicator."""
        if os.path.exists(self.socket_path):
            self.conn_label.set_text("🟢 Helper connected")
            self.start_helper_btn.set_visible(False)
        else:
            self.conn_label.set_text("🔴 Helper not available")
            self.start_helper_btn.set_visible(True)
        return True  # Continue periodic updates
    
    def _start_helper_clicked(self, btn):
        """Handle start helper button click."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Start Helper Service"
        )
        dialog.set_secondary_text(
            "The helper service needs to be started with sudo.\n\n"
            "Please run this in a terminal:\n"
            "sudo python3 backend/netmapper_helper.py --dev\n\n"
            "Or use the launcher script:\n"
            "./netmapper"
        )
        response = dialog.show()
        dialog.destroy()
        
        if response == Gtk.ResponseType.OK:
            # Try to start helper via subprocess (will prompt for sudo)
            try:
                import subprocess
                import sys
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                helper_path = os.path.join(script_dir, "backend", "netmapper_helper.py")
                subprocess.Popen(
                    ["sudo", "python3", helper_path, "--dev"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self.status_label.set_text("Helper starting... (check terminal for sudo prompt)")
            except Exception as e:
                self._show_error_dialog("Error", f"Could not start helper automatically:\n{e}\n\nPlease start it manually.")
    
    def _load_scan_history(self):
        """Load recent scan history into sidebar."""
        result = self.send_request({"cmd": "list_history", "limit": 10})
        if result:
            try:
                j = json.loads(result)
                if j.get('status') == 'ok':
                    self.history_store.clear()
                    for scan in j.get('history', []):
                        scan_id = scan.get('scan_id', '')
                        cidr = scan.get('cidr', '')
                        ts = scan.get('timestamp', 0)
                        time_str = time.strftime('%H:%M', time.localtime(ts)) if ts else '-'
                        self.history_store.append([scan_id, cidr, time_str])
            except:
                pass
    
    def _load_full_history(self, store):
        """Load full history into history tab."""
        result = self.send_request({"cmd": "list_history", "limit": 50})
        if result:
            try:
                j = json.loads(result)
                if j.get('status') == 'ok':
                    for scan in j.get('history', []):
                        scan_id = scan.get('scan_id', '')
                        cidr = scan.get('cidr', '')
                        ts = scan.get('timestamp', 0)
                        host_count = scan.get('host_count', 0)
                        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts)) if ts else '-'
                        store.append([scan_id, cidr, time_str, str(host_count)])
            except:
                pass
    
    def on_history_selected(self, selection):
        """Handle history item selection."""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            scan_id = model[tree_iter][0]
            # Load and display this scan's results
            self._load_scan_results(scan_id)
    
    def _load_scan_results(self, scan_id):
        """Load results for a specific scan."""
        result = self.send_request({
            "cmd": "get_results",
            "scan_id": scan_id
        })
        if result:
            try:
                j = json.loads(result)
                if j.get('status') == 'ok':
                    hosts = j.get('results', [])
                    self._update_results(hosts)
                    self.current_scan_id = scan_id
            except:
                pass

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
        self.export_btn.set_sensitive(False)
        self.status_label.set_text('Starting scan...')
        # Clear store by creating new one (clear() deprecated in GTK4)
        self.store = Gtk.ListStore(str, str, str, str)
        self.tree_view.set_model(self.store)
        
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
                        self.export_btn.set_sensitive(True)
                        self._load_scan_history()  # Refresh sidebar
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
                    self.export_btn.set_sensitive(True)
                    self._load_scan_history()  # Refresh sidebar
                    # Auto-generate network map
                    self._generate_network_map(hosts)
                    self.map_drawing_area.queue_draw()
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
        # Clear store - create new one to avoid deprecation warning
        self.store = Gtk.ListStore(str, str, str, str)
        self.tree_view.set_model(self.store)
        for host in hosts:
            self.store.append([
                host.get('ip', ''),
                host.get('mac', ''),
                host.get('hostname') or '-',
                host.get('vendor') or '-'
            ])
        self.host_count_label.set_text(f"Hosts: {len(hosts)}")

    def on_host_selected(self, selection):
        """Handle host selection in tree view."""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            ip = model[tree_iter][0]
            mac = model[tree_iter][1]
            hostname = model[tree_iter][2]
            self.selected_host = {"ip": ip, "mac": mac, "hostname": hostname}
            self.nmap_btn.set_sensitive(True)
        else:
            self.selected_host = None
            self.nmap_btn.set_sensitive(False)
    
    def on_host_activated(self, tree_view, path, column):
        """Handle host double-click - show details."""
        model = tree_view.get_model()
        tree_iter = model.get_iter(path)
        if tree_iter:
            ip = model[tree_iter][0]
            mac = model[tree_iter][1]
            hostname = model[tree_iter][2]
            vendor = model[tree_iter][3]
            self._show_host_details(ip, mac, hostname, vendor)
    
    def _show_host_details(self, ip, mac, hostname, vendor):
        """Show detailed host information dialog."""
        dialog = Gtk.Dialog(title=f"Host Details: {ip}", transient_for=self, modal=True)
        dialog.set_default_size(400, 300)
        
        vbox = dialog.get_content_area()
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_spacing(12)
        
        # Host information
        info_grid = Gtk.Grid()
        info_grid.set_column_spacing(12)
        info_grid.set_row_spacing(6)
        
        info_grid.attach(Gtk.Label(label="IP Address:", halign=Gtk.Align.START), 0, 0, 1, 1)
        info_grid.attach(Gtk.Label(label=ip, halign=Gtk.Align.START), 1, 0, 1, 1)
        
        info_grid.attach(Gtk.Label(label="MAC Address:", halign=Gtk.Align.START), 0, 1, 1, 1)
        info_grid.attach(Gtk.Label(label=mac, halign=Gtk.Align.START), 1, 1, 1, 1)
        
        info_grid.attach(Gtk.Label(label="Hostname:", halign=Gtk.Align.START), 0, 2, 1, 1)
        info_grid.attach(Gtk.Label(label=hostname if hostname != '-' else "Unknown", halign=Gtk.Align.START), 1, 2, 1, 1)
        
        info_grid.attach(Gtk.Label(label="Vendor:", halign=Gtk.Align.START), 0, 3, 1, 1)
        info_grid.attach(Gtk.Label(label=vendor if vendor != '-' else "Unknown", halign=Gtk.Align.START), 1, 3, 1, 1)
        
        vbox.append(info_grid)
        
        # Close button
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.connect("response", lambda d, r: d.close())
        
        dialog.present()
    
    def on_nmap_clicked(self, btn):
        """Handle Nmap scan button click."""
        if not self.selected_host:
            return
        
        ip = self.selected_host['ip']
        self.status_label.set_text(f"Running Nmap scan on {ip}...")
        self.nmap_btn.set_sensitive(False)
        
        # Send Nmap request
        result = self.send_request({
            "cmd": "nmap",
            "ip": ip,
            "ports": "1-1024"
        })
        
        self.nmap_btn.set_sensitive(True)
        
        if not result:
            self.status_label.set_text('Error: Nmap scan failed')
            return
        
        try:
            j = json.loads(result)
            if j.get('status') == 'ok':
                nmap_xml = j.get('nmap_xml', '')
                self._show_nmap_results(ip, nmap_xml)
            else:
                self.status_label.set_text(f"Error: {j.get('message', 'Unknown error')}")
        except Exception as e:
            self.status_label.set_text(f"Error parsing Nmap results: {e}")
    
    def on_export_clicked(self, btn):
        """Handle export button click."""
        if not self.current_scan_id:
            self._show_info_dialog("Export", "No scan results to export. Run a scan first.")
            return
        
        # Get current results
        result = self.send_request({
            "cmd": "get_results",
            "scan_id": self.current_scan_id
        })
        
        if not result:
            self._show_error_dialog("Export Error", "Could not retrieve scan results.")
            return
        
        try:
            j = json.loads(result)
            if j.get('status') == 'ok':
                hosts = j.get('results', [])
                self._export_results(hosts)
            else:
                self._show_error_dialog("Export Error", "No results available to export.")
        except Exception as e:
            self._show_error_dialog("Export Error", str(e))
    
    def _export_results(self, hosts):
        """Export scan results to file."""
        dialog = Gtk.FileChooserDialog(
            title="Export Scan Results",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
        
        # Set default filename
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        dialog.set_current_name(f"netmapper_scan_{timestamp}")
        
        # Add filters
        json_filter = Gtk.FileFilter()
        json_filter.set_name("JSON files")
        json_filter.add_pattern("*.json")
        dialog.add_filter(json_filter)
        
        csv_filter = Gtk.FileFilter()
        csv_filter.set_name("CSV files")
        csv_filter.add_pattern("*.csv")
        dialog.add_filter(csv_filter)
        
        response = dialog.show()
        if response == Gtk.ResponseType.ACCEPT:
            filename = dialog.get_filename()
            dialog.destroy()
            
            # Determine format from extension
            if filename.endswith('.json'):
                self._export_json(hosts, filename)
            elif filename.endswith('.csv'):
                self._export_csv(hosts, filename)
            else:
                # Default to JSON
                self._export_json(hosts, filename + '.json')
        else:
            dialog.destroy()
    
    def _export_json(self, hosts, filename):
        """Export results as JSON."""
        try:
            import json as json_lib
            data = {
                "scan_id": self.current_scan_id,
                "timestamp": int(time.time()),
                "hosts": hosts
            }
            with open(filename, 'w') as f:
                json_lib.dump(data, f, indent=2)
            self._show_info_dialog("Export Complete", f"Results exported to:\n{filename}")
        except Exception as e:
            self._show_error_dialog("Export Error", f"Failed to export JSON: {e}")
    
    def _export_csv(self, hosts, filename):
        """Export results as CSV."""
        try:
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['IP Address', 'MAC Address', 'Hostname', 'Vendor'])
                for host in hosts:
                    writer.writerow([
                        host.get('ip', ''),
                        host.get('mac', ''),
                        host.get('hostname') or '',
                        host.get('vendor') or ''
                    ])
            self._show_info_dialog("Export Complete", f"Results exported to:\n{filename}")
        except Exception as e:
            self._show_error_dialog("Export Error", f"Failed to export CSV: {e}")
    
    def _show_nmap_results(self, ip, nmap_xml):
        """Parse and display Nmap results in a dialog."""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(nmap_xml)
            
            # Check for errors
            if 'error' in nmap_xml.lower():
                self._show_error_dialog("Nmap Error", nmap_xml)
                return
            
            # Parse ports
            ports = []
            for host in root.findall('host'):
                for ports_elem in host.findall('ports'):
                    for port in ports_elem.findall('port'):
                        port_id = port.get('portid')
                        protocol = port.get('protocol')
                        state = port.find('state')
                        service = port.find('service')
                        
                        state_text = state.get('state') if state is not None else 'unknown'
                        service_name = service.get('name') if service is not None else '-'
                        service_product = service.get('product', '')
                        service_version = service.get('version', '')
                        
                        ports.append({
                            'port': f"{port_id}/{protocol}",
                            'state': state_text,
                            'service': service_name,
                            'product': service_product,
                            'version': service_version
                        })
            
            if not ports:
                self._show_info_dialog("Nmap Results", f"No open ports found on {ip}")
                return
            
            # Create results dialog
            dialog = Gtk.Dialog(title=f"Nmap Results: {ip}", transient_for=self, modal=True)
            dialog.set_default_size(600, 400)
            
            vbox = dialog.get_content_area()
            label = Gtk.Label(label=f"Open ports on {ip}:")
            label.set_halign(Gtk.Align.START)
            label.set_margin_bottom(10)
            vbox.append(label)
            
            # Create tree view for ports
            store = Gtk.ListStore(str, str, str, str)  # Port, State, Service, Product/Version
            
            tree_view = Gtk.TreeView(model=store)
            tree_view.set_hexpand(True)
            tree_view.set_vexpand(True)
            
            renderer = Gtk.CellRendererText()
            
            col = Gtk.TreeViewColumn(title="Port")
            col.pack_start(renderer, True)
            col.add_attribute(renderer, "text", 0)
            tree_view.append_column(col)
            
            col = Gtk.TreeViewColumn(title="State")
            col.pack_start(renderer, True)
            col.add_attribute(renderer, "text", 1)
            tree_view.append_column(col)
            
            col = Gtk.TreeViewColumn(title="Service")
            col.pack_start(renderer, True)
            col.add_attribute(renderer, "text", 2)
            tree_view.append_column(col)
            
            col = Gtk.TreeViewColumn(title="Product/Version")
            col.pack_start(renderer, True)
            col.add_attribute(renderer, "text", 3)
            tree_view.append_column(col)
            
            # Add ports to store
            for p in ports:
                product_info = f"{p['product']} {p['version']}".strip()
                if not product_info:
                    product_info = '-'
                store.append([p['port'], p['state'], p['service'], product_info])
            
            scroll = Gtk.ScrolledWindow()
            scroll.set_child(tree_view)
            scroll.set_hexpand(True)
            scroll.set_vexpand(True)
            vbox.append(scroll)
            
            # Close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)
            dialog.connect("response", lambda d, r: d.close())
            
            dialog.present()
            
            self.status_label.set_text(f"Nmap scan complete: {len(ports)} ports found")
            
        except ET.ParseError as e:
            self._show_error_dialog("Parse Error", f"Failed to parse Nmap XML: {e}")
        except Exception as e:
            self._show_error_dialog("Error", f"Failed to display Nmap results: {e}")
    
    def _show_info_dialog(self, title, message):
        """Show info dialog."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.set_secondary_text(message)
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()
    
    def _show_error_dialog(self, title, message):
        """Show error dialog."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.set_secondary_text(message)
        dialog.connect("response", lambda d, r: d.close())
        dialog.present()

    def send_request(self, obj):
        """Send JSON request to helper via UNIX socket."""
        if not os.path.exists(self.socket_path):
            return None
        
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(30)  # Longer timeout for Nmap
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
            try:
                print("Creating MainWindow...")
                self.window = MainWindow(self)
                print("MainWindow created successfully")
            except Exception as e:
                print(f"Error creating window: {e}")
                import traceback
                traceback.print_exc()
                return
        
        print("Presenting window...")
        self.window.present()
        print("Window presented. GUI should be visible now.")
        # Force window to front
        self.window.set_visible(True)
        if hasattr(self.window, 'activate'):
            self.window.activate()


if __name__ == '__main__':
    import os
    if 'DISPLAY' not in os.environ:
        print("Error: DISPLAY environment variable not set")
        print("GUI applications require X11 or Wayland display")
        sys.exit(1)
    
    try:
        app = NetMapperApp()
        app.run(None)
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
