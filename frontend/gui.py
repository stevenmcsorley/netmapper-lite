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
try:
    gi.require_version('Notify', '0.7')
    from gi.repository import Notify
    NOTIFY_AVAILABLE = True
except (ImportError, ValueError):
    NOTIFY_AVAILABLE = False
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
        # Window size will be set from preferences
        self.set_default_size(1200, 800)
        self.current_scan_id = None
        self._refresh_timeout_id = None  # For polling cleanup
        self._scan_cancelled = False  # Flag for cancel button
        
        # Detect socket path (prefer dev mode)
        self.socket_path = DEV_SOCKET_PATH if os.path.exists(DEV_SOCKET_PATH) else SOCKET_PATH
        self.db_path = DEV_DB_PATH if os.path.exists(DEV_DB_PATH) else DB_PATH
        
        # Initialize window preferences (must be before _build_ui)
        self._config_dir = os.path.expanduser("~/.config/netmapper-lite")
        os.makedirs(self._config_dir, exist_ok=True)
        self._config_file = os.path.join(self._config_dir, "preferences.json")
        self._window_prefs = {'width': 1200, 'height': 800, 'x': -1, 'y': -1}
        self._app_prefs = {'dark_mode': 'auto', 'network_profiles': []}
        self._load_window_prefs()
        
        # Initialize network map data
        self.network_nodes = []
        self.network_edges = []
        self.map_drawing_area = None
        self.map_zoom = 1.0  # Zoom level (1.0 = 100%)
        self.map_offset_x = 0.0  # Pan offset
        self.map_offset_y = 0.0
        
        # Initialize notifications
        self.notifications_available = False
        if NOTIFY_AVAILABLE:
            try:
                Notify.init("NetMapper-Lite")
                self.notifications_available = True
            except:
                pass
        
        # Build UI
        try:
            self._build_ui()
        except Exception as e:
            print(f"❌ Error building UI: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Apply dark mode
        self._apply_theme()
        
        # Restore window position/size (after window is shown)
        GLib.idle_add(self._restore_window_state)
        
        # Connect to window events for saving preferences
        self.connect("close-request", self._on_window_close)
        
        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
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
        
        # Load last used CIDR or profiles
        self._load_cidr_from_profiles()
        
        input_box.append(self.cidr_entry)
        
        # Network profiles dropdown
        self.profile_combo = Gtk.ComboBoxText()
        self.profile_combo.set_tooltip_text("Select saved network profile")
        self.profile_combo.connect("changed", self._on_profile_selected)
        self._refresh_profiles()
        input_box.append(self.profile_combo)
        
        # Save profile button
        save_profile_btn = Gtk.Button(label="💾")
        save_profile_btn.set_tooltip_text("Save current CIDR as profile")
        save_profile_btn.connect('clicked', self._save_profile)
        input_box.append(save_profile_btn)
        
        control_box.append(input_box)
        
        # Scan button
        self.scan_btn = Gtk.Button(label='Start Scan')
        self.scan_btn.connect('clicked', self.on_scan_clicked)
        self.scan_btn.add_css_class('suggested-action')
        control_box.append(self.scan_btn)
        
        # Cancel scan button (hidden initially)
        self.cancel_scan_btn = Gtk.Button(label='Cancel Scan')
        self.cancel_scan_btn.connect('clicked', self.on_cancel_scan_clicked)
        self.cancel_scan_btn.set_visible(False)
        self.cancel_scan_btn.add_css_class('destructive-action')
        control_box.append(self.cancel_scan_btn)
        
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
        
        # Scan Comparison tab
        compare_frame = self._build_compare_tab()
        self.notebook.append_page(compare_frame, Gtk.Label(label="Compare Scans"))
        
        # Bottom status bar
        status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        status_bar.set_margin_start(6)
        status_bar.set_margin_end(6)
        status_bar.set_margin_top(6)
        status_bar.set_margin_bottom(6)
        content_area.append(status_bar)
        
        self.host_count_label = Gtk.Label(label="Hosts: 0")
        status_bar.append(self.host_count_label)
        
        # Theme toggle button
        theme_btn = Gtk.Button(label="🌙 Theme")
        theme_btn.connect('clicked', lambda b: self._toggle_dark_mode())
        theme_btn.set_tooltip_text("Toggle dark/light theme (Auto/Dark/Light)")
        status_bar.append(theme_btn)
        
        # Progress bar (hidden initially)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_hexpand(False)
        self.progress_bar.set_visible(False)
        self.progress_bar.set_show_text(True)
        status_bar.append(self.progress_bar)
        
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
        
        # Main vertical box
        results_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        results_box.set_margin_start(12)
        results_box.set_margin_end(12)
        results_box.set_margin_top(12)
        results_box.set_margin_bottom(12)
        results_frame.set_child(results_box)
        
        # Search/filter box
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_label = Gtk.Label(label="Filter:")
        search_box.append(search_label)
        
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search by IP, hostname, MAC, or vendor...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        search_box.append(self.search_entry)
        
        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect('clicked', lambda b: self.search_entry.set_text(""))
        search_box.append(clear_btn)
        
        results_box.append(search_box)
        
        # Create list store: IP, MAC, Hostname, Vendor
        self.store = Gtk.ListStore(str, str, str, str)  # IP, MAC, Hostname, Vendor
        # Filter model for search
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._filter_func)
        
        # TreeView with filtered model
        self.tree_view = Gtk.TreeView(model=self.filter_model)
        self.tree_view.set_hexpand(True)
        self.tree_view.set_vexpand(True)
        
        # Columns (make them sortable)
        renderer = Gtk.CellRendererText()
        
        col = Gtk.TreeViewColumn(title="IP Address")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 0)
        col.set_sort_column_id(0)
        col.set_resizable(True)
        col.set_sort_indicator(True)
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
        results_box.append(scroll)
        
        # Store selected host
        self.selected_host = None
        
        return results_frame
    
    def _filter_func(self, model, tree_iter, data):
        """Filter function for search."""
        search_text = self.search_entry.get_text().lower()
        if not search_text:
            return True
        
        # Check all columns
        ip = model[tree_iter][0].lower()
        mac = model[tree_iter][1].lower()
        hostname = model[tree_iter][2].lower() if model[tree_iter][2] else ""
        vendor = model[tree_iter][3].lower() if model[tree_iter][3] else ""
        
        return (search_text in ip or 
                search_text in mac or 
                search_text in hostname or 
                search_text in vendor)
    
    def _on_search_changed(self, entry):
        """Handle search text change."""
        self.filter_model.refilter()
    
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
        self.map_drawing_area.set_content_width(1200)
        self.map_drawing_area.set_content_height(800)
        
        # Store network map data
        self.network_nodes = []  # List of {x, y, ip, mac, hostname, vendor, type, radius}
        self.network_edges = []  # List of connections (for future)
        self.hovered_node = None  # Currently hovered node
        
        # Connect draw signal
        self.map_drawing_area.set_draw_func(self._draw_network_map)
        
        # Mouse click handler
        click_controller = Gtk.GestureClick()
        click_controller.set_button(1)  # Left mouse button
        click_controller.connect("pressed", self._on_map_clicked)
        self.map_drawing_area.add_controller(click_controller)
        
        # Mouse motion handler for hover tooltips
        motion_controller = Gtk.EventControllerMotion()
        motion_controller.connect("motion", self._on_map_motion)
        motion_controller.connect("leave", self._on_map_leave)
        self.map_drawing_area.add_controller(motion_controller)
        
        # Scroll/zoom handler
        scroll_controller = Gtk.EventControllerScroll()
        scroll_controller.set_flags(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll_controller.connect("scroll", self._on_map_scroll)
        self.map_drawing_area.add_controller(scroll_controller)
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.map_drawing_area)
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        map_box.append(scroll)
        
        # Zoom controls
        zoom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        zoom_in_btn = Gtk.Button(label="Zoom In (+)")
        zoom_in_btn.connect('clicked', lambda b: self._zoom_map(1.2))
        zoom_out_btn = Gtk.Button(label="Zoom Out (-)")
        zoom_out_btn.connect('clicked', lambda b: self._zoom_map(0.8))
        reset_btn = Gtk.Button(label="Reset View")
        reset_btn.connect('clicked', lambda b: self._reset_map_view())
        zoom_box.append(zoom_in_btn)
        zoom_box.append(zoom_out_btn)
        zoom_box.append(reset_btn)
        map_box.append(zoom_box)
        
        # Refresh button
        refresh_btn = Gtk.Button(label="Refresh Map")
        refresh_btn.connect('clicked', self._refresh_network_map)
        map_box.append(refresh_btn)
        
        # Export map button
        export_map_btn = Gtk.Button(label="Export Map as Image")
        export_map_btn.connect('clicked', self._export_map_image)
        map_box.append(export_map_btn)
        
        return map_frame
    
    def _build_compare_tab(self):
        """Build scan comparison tab."""
        compare_frame = Gtk.Frame(label="Compare Scans")
        
        compare_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        compare_box.set_margin_start(12)
        compare_box.set_margin_end(12)
        compare_box.set_margin_top(12)
        compare_box.set_margin_bottom(12)
        compare_frame.set_child(compare_box)
        
        # Instructions
        info_label = Gtk.Label(label="Select two scans from history to compare. This will show new devices, disappeared devices, and changed hosts.")
        info_label.set_wrap(True)
        info_label.set_halign(Gtk.Align.START)
        compare_box.append(info_label)
        
        # Scan selection
        selection_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        compare_box.append(selection_box)
        
        scan1_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scan1_label = Gtk.Label(label="Scan 1 (Older):")
        scan1_label.set_halign(Gtk.Align.START)
        scan1_box.append(scan1_label)
        
        self.compare_scan1_combo = Gtk.ComboBoxText()
        self.compare_scan1_combo.set_hexpand(True)
        scan1_box.append(self.compare_scan1_combo)
        selection_box.append(scan1_box)
        
        scan2_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scan2_label = Gtk.Label(label="Scan 2 (Newer):")
        scan2_label.set_halign(Gtk.Align.START)
        scan2_box.append(scan2_label)
        
        self.compare_scan2_combo = Gtk.ComboBoxText()
        self.compare_scan2_combo.set_hexpand(True)
        scan2_box.append(self.compare_scan2_combo)
        selection_box.append(scan2_box)
        
        compare_btn = Gtk.Button(label="Compare Scans")
        compare_btn.connect('clicked', self._on_compare_scans)
        selection_box.append(compare_btn)
        
        # Results area
        results_notebook = Gtk.Notebook()
        results_notebook.set_hexpand(True)
        results_notebook.set_vexpand(True)
        compare_box.append(results_notebook)
        
        # New hosts tab
        new_store = Gtk.ListStore(str, str, str, str)
        self.compare_new_view = Gtk.TreeView(model=new_store)
        self._setup_compare_columns(self.compare_new_view)
        new_scroll = Gtk.ScrolledWindow()
        new_scroll.set_child(self.compare_new_view)
        results_notebook.append_page(new_scroll, Gtk.Label(label="New Hosts"))
        
        # Disappeared hosts tab
        disappeared_store = Gtk.ListStore(str, str, str, str)
        self.compare_disappeared_view = Gtk.TreeView(model=disappeared_store)
        self._setup_compare_columns(self.compare_disappeared_view)
        disappeared_scroll = Gtk.ScrolledWindow()
        disappeared_scroll.set_child(self.compare_disappeared_view)
        results_notebook.append_page(disappeared_scroll, Gtk.Label(label="Disappeared"))
        
        # Changed hosts tab
        changed_store = Gtk.ListStore(str, str, str, str, str)
        self.compare_changed_view = Gtk.TreeView(model=changed_store)
        self._setup_compare_columns(self.compare_changed_view, changed=True)
        changed_scroll = Gtk.ScrolledWindow()
        changed_scroll.set_child(self.compare_changed_view)
        results_notebook.append_page(changed_scroll, Gtk.Label(label="Changed"))
        
        return compare_frame
    
    def _setup_compare_columns(self, tree_view, changed=False):
        """Setup columns for comparison views."""
        renderer = Gtk.CellRendererText()
        
        col = Gtk.TreeViewColumn(title="IP")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 0)
        tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="MAC")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 1)
        tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Hostname")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 2)
        tree_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Vendor")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 3)
        tree_view.append_column(col)
        
        if changed:
            col = Gtk.TreeViewColumn(title="Changes")
            col.pack_start(renderer, True)
            col.add_attribute(renderer, "text", 4)
            col.set_resizable(True)
            tree_view.append_column(col)
    
    def _on_compare_scans(self, btn):
        """Handle compare scans button click."""
        scan_id1 = self.compare_scan1_combo.get_active_id()
        scan_id2 = self.compare_scan2_combo.get_active_id()
        
        if not scan_id1 or not scan_id2:
            self._show_info_dialog("Compare Scans", "Please select both scans to compare.")
            return
        
        if scan_id1 == scan_id2:
            self._show_info_dialog("Compare Scans", "Please select two different scans.")
            return
        
        result = self.send_request({
            "cmd": "compare_scans",
            "scan_id1": scan_id1,
            "scan_id2": scan_id2
        })
        
        if not result:
            self._show_error_dialog("Error", "Could not compare scans.")
            return
        
        try:
            j = json.loads(result)
            if j.get('status') == 'ok':
                comparison = j.get('comparison', {})
                self._display_comparison(comparison)
            else:
                self._show_error_dialog("Error", j.get('message', 'Unknown error'))
        except Exception as e:
            self._show_error_dialog("Error", f"Failed to parse comparison: {e}")
    
    def _display_comparison(self, comparison):
        """Display comparison results."""
        # New hosts
        new_store = Gtk.ListStore(str, str, str, str)
        for host in comparison.get('new', []):
            new_store.append([
                host.get('ip', ''),
                host.get('mac', ''),
                host.get('hostname') or '-',
                host.get('vendor') or '-'
            ])
        self.compare_new_view.set_model(new_store)
        
        # Disappeared hosts
        disappeared_store = Gtk.ListStore(str, str, str, str)
        for host in comparison.get('disappeared', []):
            disappeared_store.append([
                host.get('ip', ''),
                host.get('mac', ''),
                host.get('hostname') or '-',
                host.get('vendor') or '-'
            ])
        self.compare_disappeared_view.set_model(disappeared_store)
        
        # Changed hosts
        changed_store = Gtk.ListStore(str, str, str, str, str)
        for host in comparison.get('changed', []):
            changes = host.get('changes', {})
            changes_str = ', '.join([f"{k}: {v['old']} → {v['new']}" for k, v in changes.items()])
            changed_store.append([
                host.get('ip', ''),
                host.get('mac', ''),
                host.get('hostname') or '-',
                host.get('vendor') or '-',
                changes_str
            ])
        self.compare_changed_view.set_model(changed_store)
    
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
        """Generate network topology from hosts with subnet detection."""
        if not hosts:
            self.network_nodes = []
            return
        
        # Detect subnetworks
        try:
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from backend.subnet_detector import detect_subnets
            # Get base CIDR from current scan (if available)
            base_cidr = self.current_cidr if hasattr(self, 'current_cidr') and self.current_cidr else "192.168.100.0/24"
            print(f"🔍 Detecting subnets in {base_cidr} with {len(hosts)} hosts...")
            subnet_info = detect_subnets(hosts, base_cidr)
            subnets = subnet_info.get("subnets", [])
            hosts_by_subnet = subnet_info.get("hosts_by_subnet", {})
            
            print(f"✅ Found {len(subnets)} subnet(s)")
            if len(subnets) > 1:
                print(f"🗺️  Using subnet-aware map layout")
                # If multiple subnets detected, use subnet-aware layout
                self._generate_subnet_map(hosts, subnets, hosts_by_subnet)
                return
            else:
                print(f"📍 Single subnet detected, using standard layout")
        except Exception as e:
            print(f"Subnet detection error: {e}")
            import traceback
            traceback.print_exc()
            # Fall through to regular layout
        
        # Regular single-subnet layout
        import math
        import subprocess
        center_x, center_y = 400, 300
        radius = min(250, len(hosts) * 15)
        
        self.network_nodes = []
        
        # Detect actual gateway IP from system routing table
        actual_gateway_ip = None
        try:
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.split()
                for i, part in enumerate(parts):
                    if part == 'via':
                        actual_gateway_ip = parts[i+1] if i+1 < len(parts) else None
                        break
        except:
            pass
        
        # Find gateway host in scan results
        gateway = None
        if actual_gateway_ip:
            # Match by actual gateway IP
            for host in hosts:
                if host.get('ip') == actual_gateway_ip:
                    gateway = host
                    break
        
        # Fallback: try common gateway IPs (.1 or .254) if not found
        if not gateway:
            for host in hosts:
                ip_parts = host.get('ip', '').split('.')
                if len(ip_parts) == 4:
                    last_octet = ip_parts[-1]
                    if last_octet in ['1', '254']:
                        gateway = host
                        break
        
        # Position gateway in center if found
        if gateway:
            # Use better label for gateway
            gateway_label = gateway.get('hostname') or gateway.get('vendor') or 'Router'
            # If it's a vendor-specific device (like Hikvision), show that
            if gateway.get('vendor') and 'hikvision' in gateway.get('vendor', '').lower():
                gateway_label = gateway.get('vendor')  # Show it's Hikvision, but still mark as gateway
            elif not gateway.get('hostname') and not gateway.get('vendor'):
                gateway_label = 'Router'
            
            self.network_nodes.append({
                'x': center_x,
                'y': center_y,
                'ip': gateway.get('ip', ''),
                'mac': gateway.get('mac', ''),
                'hostname': gateway.get('hostname') or '',
                'vendor': gateway.get('vendor') or '',
                'label': gateway_label,
                'type': 'gateway',
                'radius': 25,
                'port_count': self._get_port_count(gateway.get('ip', ''))
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
            
            # Determine node type based on hostname and vendor
            node_type = 'device'
            hostname = (host.get('hostname') or '').lower()
            vendor = (host.get('vendor') or '').lower()
            
            # Enhanced classification
            if 'router' in hostname or 'gateway' in hostname or 'router' in vendor:
                node_type = 'gateway'
            elif 'server' in hostname or 'db' in hostname or 'backup' in hostname or 'web' in hostname:
                node_type = 'server'
            elif any(x in hostname for x in ['camera', 'tv', 'light', 'thermostat', 'sensor', 'hub', 'iot']):
                node_type = 'iot'
            elif any(x in hostname for x in ['phone', 'tablet', 'mobile']):
                node_type = 'mobile'
            elif 'printer' in hostname:
                node_type = 'printer'
            elif vendor == 'unknown' or not vendor or vendor == '-':
                node_type = 'unknown'
            
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
    
    def _generate_subnet_map(self, hosts, subnets, hosts_by_subnet):
        """Generate network map with subnet groupings."""
        import math
        import subprocess
        
        self.network_nodes = []
        
        # Main center for overall network
        center_x, center_y = 400, 300
        main_radius = 200
        
        # Detect actual gateway
        actual_gateway_ip = None
        try:
            result = subprocess.run(
                ['ip', 'route', 'show', 'default'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                parts = result.stdout.split()
                for i, part in enumerate(parts):
                    if part == 'via':
                        actual_gateway_ip = parts[i+1] if i+1 < len(parts) else None
                        break
        except:
            pass
        
        # Position main gateway in center
        gateway = None
        for host in hosts:
            if host.get('ip') == actual_gateway_ip or host.get('ip').endswith('.1') or host.get('ip').endswith('.254'):
                gateway = host
                break
        
        if gateway:
            self.network_nodes.append({
                'x': center_x,
                'y': center_y,
                'ip': gateway.get('ip', ''),
                'mac': gateway.get('mac', ''),
                'hostname': gateway.get('hostname') or '',
                'vendor': gateway.get('vendor') or '',
                'label': gateway.get('hostname') or gateway.get('vendor') or 'Gateway',
                'type': 'gateway',
                'radius': 30,
                'subnet': None,
                'port_count': self._get_port_count(gateway.get('ip', ''))
            })
        
        # Position each subnet in a circle around the center
        subnet_count = len(subnets)
        if subnet_count == 0:
            subnet_count = 1
        
        subnet_angle_step = (2 * math.pi) / subnet_count if subnet_count > 1 else 0
        subnet_radius = 180  # Distance from center to subnet center
        
        for idx, subnet in enumerate(subnets):
            subnet_cidr = subnet['cidr']
            subnet_hosts = hosts_by_subnet.get(subnet_cidr, [])
            
            if not subnet_hosts:
                continue
            
            # Calculate subnet center position
            if subnet_count == 1:
                subnet_center_x, subnet_center_y = center_x, center_y
            else:
                angle = idx * subnet_angle_step
                subnet_center_x = center_x + subnet_radius * math.cos(angle)
                subnet_center_y = center_y + subnet_radius * math.sin(angle)
            
            # Add subnet label node (invisible, for reference)
            subnet_label = subnet_cidr.split('/')[0].rsplit('.', 1)[0] + '.x/' + subnet_cidr.split('/')[1]
            
            # Position hosts in this subnet in a circle around subnet center
            host_count = len(subnet_hosts)
            if host_count == 0:
                continue
            
            host_radius = min(60, host_count * 8)
            host_angle_step = (2 * math.pi) / host_count if host_count > 1 else 0
            
            for host_idx, host in enumerate(subnet_hosts):
                if gateway and host.get('ip') == gateway.get('ip'):
                    continue  # Skip gateway, already placed
                
                host_angle = host_idx * host_angle_step
                node_x = subnet_center_x + host_radius * math.cos(host_angle)
                node_y = subnet_center_y + host_radius * math.sin(host_angle)
                
                # Determine node type
                node_type = 'host'
                hostname = host.get('hostname', '').lower() if host.get('hostname') else ''
                if 'server' in hostname or 'db' in hostname:
                    node_type = 'server'
                elif 'router' in hostname or 'gateway' in hostname:
                    node_type = 'gateway'
                
                self.network_nodes.append({
                    'x': node_x,
                    'y': node_y,
                    'ip': host.get('ip', ''),
                    'mac': host.get('mac', ''),
                    'hostname': host.get('hostname') or '',
                    'vendor': host.get('vendor') or '',
                    'label': subnet_label,  # Show subnet info
                    'type': node_type,
                    'radius': 12,
                    'subnet': subnet_cidr,
                    'port_count': self._get_port_count(host.get('ip', ''))
                })
        
        # Generate edges: hosts connect to gateway, subnets connect to gateway
        self.network_edges = []
        gateway_node = None
        for node in self.network_nodes:
            if node.get('type') == 'gateway':
                gateway_node = node
                break
        
        if gateway_node:
            gateway_ip = gateway_node.get('ip', '')
            for node in self.network_nodes:
                if node.get('ip') != gateway_ip:
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
        
        # Apply zoom and pan transform
        cr.translate(self.map_offset_x, self.map_offset_y)
        cr.scale(self.map_zoom, self.map_zoom)
        
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
            # Color by device type
            node_type = node.get('type', 'device')
            if node_type == 'gateway':
                cr.set_source_rgb(0.2, 0.6, 0.9)  # Blue for gateway
            elif node_type == 'server':
                cr.set_source_rgb(0.9, 0.6, 0.2)  # Orange for server
            elif node_type == 'iot':
                cr.set_source_rgb(0.7, 0.3, 0.9)  # Purple for IoT devices
            elif node_type == 'mobile':
                cr.set_source_rgb(0.9, 0.8, 0.2)  # Yellow for mobile
            elif node_type == 'printer':
                cr.set_source_rgb(0.3, 0.7, 0.9)  # Light blue for printers
            elif node_type == 'unknown':
                cr.set_source_rgb(0.6, 0.6, 0.6)  # Gray for unknown
            else:
                cr.set_source_rgb(0.4, 0.7, 0.4)  # Green for regular devices
            
            # Draw node circle
            cr.arc(node['x'], node['y'], node['radius'], 0, 2 * 3.14159)
            cr.fill()
            
            # Draw border
            cr.set_source_rgb(0.2, 0.2, 0.2)
            cr.set_line_width(2)
            cr.arc(node['x'], node['y'], node['radius'], 0, 2 * 3.14159)
            cr.stroke()
            
            # Highlight hovered node
            if self.hovered_node and node['ip'] == self.hovered_node['ip']:
                # Draw highlight ring
                cr.set_source_rgba(0.2, 0.6, 0.9, 0.5)
                cr.set_line_width(3)
                cr.arc(node['x'], node['y'], node['radius'] + 3, 0, 2 * 3.14159)
                cr.stroke()
                
                # Draw tooltip background (in map coordinates)
                tooltip_text = f"{node['ip']}"
                if node.get('hostname'):
                    tooltip_text += f"\n{node['hostname']}"
                if node.get('vendor'):
                    tooltip_text += f"\n{node['vendor']}"
                
                cr.select_font_face("Sans")
                cr.set_font_size(9)
                lines = tooltip_text.split('\n')
                max_width = 0
                total_height = 0
                line_heights = []
                for line in lines:
                    (x, y, text_width, text_height, dx, dy) = cr.text_extents(line)
                    line_heights.append(text_height)
                    max_width = max(max_width, text_width)
                    total_height += text_height + 2
                
                tooltip_x = node['x'] - max_width / 2 - 6
                tooltip_y = node['y'] - node['radius'] - total_height - 15
                
                # Background
                cr.set_source_rgba(0.95, 0.95, 0.95, 0.95)
                cr.rectangle(tooltip_x - 4, tooltip_y - 4, max_width + 12, total_height + 8)
                cr.fill()
                
                # Border
                cr.set_source_rgba(0.5, 0.5, 0.5, 0.8)
                cr.set_line_width(1)
                cr.rectangle(tooltip_x - 4, tooltip_y - 4, max_width + 12, total_height + 8)
                cr.stroke()
                
                # Text
                cr.set_source_rgb(0, 0, 0)
                y_offset = tooltip_y
                for i, line in enumerate(lines):
                    cr.move_to(tooltip_x, y_offset + line_heights[i])
                    cr.show_text(line)
                    y_offset += line_heights[i] + 2
            
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
            
            # Draw port count if available (small badge)
            port_count = node.get('port_count', 0)
            if port_count > 0:
                # Draw small badge with port count
                badge_radius = 8
                badge_x = node['x'] + node['radius'] - badge_radius - 2
                badge_y = node['y'] - node['radius'] + badge_radius + 2
                
                # Badge background (red/orange)
                cr.set_source_rgb(0.9, 0.3, 0.2)
                cr.arc(badge_x, badge_y, badge_radius, 0, 2 * 3.14159)
                cr.fill()
                
                # Badge border
                cr.set_source_rgb(0.7, 0.2, 0.1)
                cr.set_line_width(1)
                cr.arc(badge_x, badge_y, badge_radius, 0, 2 * 3.14159)
                cr.stroke()
                
                # Port count text
                cr.set_source_rgb(1, 1, 1)  # White text
                cr.select_font_face("Sans Bold")
                cr.set_font_size(8)
                port_text = str(port_count) if port_count < 100 else "99+"
                (x, y, text_width, text_height, dx, dy) = cr.text_extents(port_text)
                cr.move_to(badge_x - text_width / 2, badge_y + text_height / 2 - 2)
                cr.show_text(port_text)
        
        # Draw legend and zoom indicator
        cr.save()
        cr.identity_matrix()  # Reset to screen coordinates
        
        # Get drawing area size
        width = self.map_drawing_area.get_allocated_width()
        height = self.map_drawing_area.get_allocated_height()
        
        # Draw legend box
        legend_x = 10
        legend_y = 10
        legend_width = 180
        legend_height = 150
        
        # Legend background
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.rectangle(legend_x, legend_y, legend_width, legend_height)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.3)
        cr.set_line_width(1)
        cr.rectangle(legend_x, legend_y, legend_width, legend_height)
        cr.stroke()
        
        # Legend title
        cr.set_source_rgb(0, 0, 0)
        cr.select_font_face("Sans Bold")
        cr.set_font_size(11)
        cr.move_to(legend_x + 5, legend_y + 18)
        cr.show_text("Device Types")
        
        # Legend items
        legend_items = [
            ((0.2, 0.6, 0.9), "Gateway/Router"),
            ((0.9, 0.6, 0.2), "Server"),
            ((0.4, 0.7, 0.4), "Device"),
            ((0.7, 0.3, 0.9), "IoT"),
            ((0.9, 0.8, 0.2), "Mobile"),
            ((0.3, 0.7, 0.9), "Printer"),
            ((0.6, 0.6, 0.6), "Unknown"),
        ]
        
        cr.select_font_face("Sans")
        cr.set_font_size(9)
        y_offset = 35
        for color, label in legend_items:
            # Color dot
            cr.set_source_rgb(*color)
            cr.arc(legend_x + 12, legend_y + y_offset, 5, 0, 2 * 3.14159)
            cr.fill()
            # Label
            cr.set_source_rgb(0, 0, 0)
            cr.move_to(legend_x + 25, legend_y + y_offset + 4)
            cr.show_text(label)
            y_offset += 18
        
        # Zoom indicator
        cr.set_source_rgba(0, 0, 0, 0.5)
        cr.select_font_face("Sans")
        cr.set_font_size(10)
        zoom_text = f"Zoom: {int(self.map_zoom * 100)}%"
        cr.move_to(10, height - 10)
        cr.show_text(zoom_text)
        
        cr.restore()
    
    def _on_map_clicked(self, gesture, n_press, x, y):
        """Handle mouse click on network map."""
        if not self.network_nodes:
            return
        
        # Convert click coordinates to map coordinates (accounting for zoom and offset)
        map_x = (x - self.map_offset_x) / self.map_zoom
        map_y = (y - self.map_offset_y) / self.map_zoom
        
        # Find clicked node (check each node)
        clicked_node = None
        min_distance = float('inf')
        
        for node in self.network_nodes:
            distance = ((map_x - node['x'])**2 + (map_y - node['y'])**2)**0.5
            # Use larger hit radius for easier clicking
            hit_radius = node.get('radius', 20) * 1.5  # 50% larger hit area
            if distance <= hit_radius and distance < min_distance:
                clicked_node = node
                min_distance = distance
        
        if clicked_node:
            # Show details for this node
            self._show_host_details(
                clicked_node['ip'],
                clicked_node['mac'],
                clicked_node.get('hostname', ''),
                clicked_node.get('vendor', '')
            )
    
    def _on_map_motion(self, controller, x, y):
        """Handle mouse motion over network map for tooltips."""
        if not self.network_nodes:
            return
        
        # Convert to map coordinates
        map_x = (x - self.map_offset_x) / self.map_zoom
        map_y = (y - self.map_offset_y) / self.map_zoom
        
        # Find hovered node
        hovered = None
        min_distance = float('inf')
        
        for node in self.network_nodes:
            distance = ((map_x - node['x'])**2 + (map_y - node['y'])**2)**0.5
            hit_radius = node.get('radius', 20) * 1.5
            if distance <= hit_radius and distance < min_distance:
                hovered = node
                min_distance = distance
        
        if hovered != self.hovered_node:
            self.hovered_node = hovered
            self.map_drawing_area.queue_draw()  # Redraw to show tooltip
    
    def _on_map_leave(self, controller):
        """Handle mouse leaving the map area."""
        if self.hovered_node:
            self.hovered_node = None
            self.map_drawing_area.queue_draw()
    
    def _on_map_scroll(self, controller, dx, dy):
        """Handle scroll/zoom on network map."""
        # Check if Ctrl is pressed for zoom, otherwise pan
        modifiers = controller.get_current_event_state() if hasattr(controller, 'get_current_event_state') else 0
        is_ctrl = (modifiers & Gdk.ModifierType.CONTROL_MASK) if hasattr(Gdk, 'ModifierType') else False
        
        if is_ctrl or dy != 0:
            # Zoom (Ctrl+scroll or trackpad pinch)
            zoom_factor = 1.1 if dy < 0 else 0.9
            self._zoom_map(zoom_factor)
            return True
        return False
    
    def _zoom_map(self, factor):
        """Zoom the network map."""
        self.map_zoom *= factor
        # Limit zoom range
        self.map_zoom = max(0.1, min(5.0, self.map_zoom))
        self.map_drawing_area.queue_draw()
    
    def _reset_map_view(self):
        """Reset zoom and pan to default."""
        self.map_zoom = 1.0
        self.map_offset_x = 0.0
        self.map_offset_y = 0.0
        self.map_drawing_area.queue_draw()
    
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
    
    def _load_window_prefs(self):
        """Load window preferences from config file."""
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, 'r') as f:
                    prefs = json.load(f)
                    self._window_prefs.update(prefs.get('window', {}))
                    self._app_prefs.update(prefs.get('app', {}))
        except Exception as e:
            print(f"Error loading preferences: {e}")
    
    def _save_window_prefs(self):
        """Save window preferences to config file."""
        try:
            # Get current window position and size
            width = self.get_width()
            height = self.get_height()
            x, y = self.get_position()
            
            self._window_prefs.update({
                'width': width,
                'height': height,
                'x': x,
                'y': y
            })
            
            prefs = {
                'window': self._window_prefs,
                'app': self._app_prefs
            }
            
            with open(self._config_file, 'w') as f:
                json.dump(prefs, f, indent=2)
        except Exception as e:
            print(f"Error saving preferences: {e}")
    
    def _restore_window_state(self):
        """Restore window position and size after window is realized."""
        if self._window_prefs.get('x', -1) >= 0 and self._window_prefs.get('y', -1) >= 0:
            self.move(self._window_prefs['x'], self._window_prefs['y'])
        if self._window_prefs.get('width', 1200) != 1200 or self._window_prefs.get('height', 800) != 800:
            self.set_default_size(self._window_prefs['width'], self._window_prefs['height'])
        return False  # Don't repeat
    
    def _load_cidr_from_profiles(self):
        """Load last used CIDR or default."""
        profiles = self._app_prefs.get('network_profiles', [])
        if profiles:
            # Use last scanned CIDR
            last_cidr = self._app_prefs.get('last_cidr', '')
            if last_cidr:
                self.cidr_entry.set_text(last_cidr)
            else:
                # Use first profile
                self.cidr_entry.set_text(profiles[0].get('cidr', ''))
    
    def _refresh_profiles(self):
        """Refresh network profiles dropdown."""
        self.profile_combo.remove_all()
        self.profile_combo.append_text("-- Select Profile --")
        profiles = self._app_prefs.get('network_profiles', [])
        for profile in profiles:
            self.profile_combo.append_text(f"{profile.get('name', 'Unnamed')} ({profile.get('cidr', '')})")
        self.profile_combo.set_active(0)
    
    def _on_profile_selected(self, combo):
        """Handle profile selection."""
        active = combo.get_active()
        if active > 0:  # Skip "-- Select Profile --"
            profiles = self._app_prefs.get('network_profiles', [])
            if active - 1 < len(profiles):
                profile = profiles[active - 1]
                self.cidr_entry.set_text(profile.get('cidr', ''))
                self._app_prefs['last_cidr'] = profile.get('cidr', '')
    
    def _save_profile(self, btn):
        """Save current CIDR as a profile."""
        cidr = self.cidr_entry.get_text().strip()
        if not cidr:
            self._show_info_dialog("Save Profile", "Please enter a CIDR first.")
            return
        
        # Show dialog to get profile name
        dialog = Gtk.Dialog(title="Save Network Profile", transient_for=self, modal=True)
        dialog.set_default_size(300, 150)
        
        vbox = dialog.get_content_area()
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_spacing(12)
        
        label = Gtk.Label(label="Profile Name:")
        label.set_halign(Gtk.Align.START)
        vbox.append(label)
        
        name_entry = Gtk.Entry()
        name_entry.set_text(f"{cidr.replace('/', '_')}")
        name_entry.set_hexpand(True)
        vbox.append(name_entry)
        
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        save_btn = dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
        save_btn.add_css_class("suggested-action")
        
        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                name = name_entry.get_text().strip()
                if name:
                    profiles = self._app_prefs.get('network_profiles', [])
                    # Check if CIDR already exists
                    existing = [p for p in profiles if p.get('cidr') == cidr]
                    if existing:
                        existing[0]['name'] = name
                    else:
                        profiles.append({'name': name, 'cidr': cidr})
                    self._app_prefs['network_profiles'] = profiles
                    self._save_window_prefs()
                    self._refresh_profiles()
                    self.status_label.set_text(f"Profile '{name}' saved")
            dialog.close()
        
        dialog.connect("response", on_response)
        dialog.present()
    
    def _apply_theme(self):
        """Apply dark/light theme based on preferences."""
        settings = Gtk.Settings.get_default()
        dark_mode = self._app_prefs.get('dark_mode', 'auto')
        
        if dark_mode == 'auto':
            # Detect system preference
            try:
                # Try to detect from GTK settings
                system_dark = settings.get_property('gtk-application-prefer-dark-theme')
                settings.set_property('gtk-application-prefer-dark-theme', system_dark)
            except:
                # Fallback: check environment
                try:
                    import subprocess
                    result = subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'color-scheme'],
                                          capture_output=True, text=True, timeout=1)
                    if 'dark' in result.stdout.lower():
                        settings.set_property('gtk-application-prefer-dark-theme', True)
                    else:
                        settings.set_property('gtk-application-prefer-dark-theme', False)
                except:
                    pass
        elif dark_mode == 'dark':
            settings.set_property('gtk-application-prefer-dark-theme', True)
        else:  # 'light'
            settings.set_property('gtk-application-prefer-dark-theme', False)
    
    def _toggle_dark_mode(self):
        """Toggle dark mode on/off."""
        current = self._app_prefs.get('dark_mode', 'auto')
        if current == 'auto':
            self._app_prefs['dark_mode'] = 'dark'
        elif current == 'dark':
            self._app_prefs['dark_mode'] = 'light'
        else:
            self._app_prefs['dark_mode'] = 'auto'
        
        self._apply_theme()
        self._save_window_prefs()
        
        mode_name = {'auto': 'Auto (System)', 'dark': 'Dark', 'light': 'Light'}[self._app_prefs['dark_mode']]
        self.status_label.set_text(f"Theme: {mode_name}")
    
    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Create keyboard controller
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)
    
    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handle keyboard shortcuts."""
        # Check for Ctrl key
        ctrl = (state & Gtk.accelerator_get_default_mod_mask()) == Gdk.ModifierType.CONTROL_MASK
        
        # Ctrl+S: Start scan
        if ctrl and keyval == ord('s'):
            if hasattr(self, 'scan_btn') and self.scan_btn.get_sensitive():
                self.on_scan_clicked(self.scan_btn)
            return True
        
        # Ctrl+F: Focus search
        if ctrl and keyval == ord('f'):
            if hasattr(self, 'search_entry'):
                self.search_entry.grab_focus()
            return True
        
        # Ctrl+E: Export
        if ctrl and keyval == ord('e'):
            if hasattr(self, 'export_btn') and self.export_btn.get_sensitive():
                self.on_export_clicked(self.export_btn)
            return True
        
        # Esc: Cancel scan
        if keyval == 65307:  # Escape key code
            if hasattr(self, 'cancel_scan_btn') and self.cancel_scan_btn.get_visible():
                self.on_cancel_scan_clicked(self.cancel_scan_btn)
            return True
        
        return False
    
    def _get_port_count(self, ip):
        """Get port count for an IP from Nmap history."""
        if not ip:
            return 0
        try:
            result = self.send_request({
                "cmd": "get_nmap_history",
                "ip": ip,
                "limit": 1
            })
            if result:
                j = json.loads(result)
                if j.get('status') == 'ok' and j.get('history'):
                    latest = j.get('history')[0]
                    ports = latest.get('ports', '')
                    if ports:
                        # Count ports (format: "22/tcp, 80/tcp, 443/tcp")
                        return len([p for p in ports.split(',') if p.strip()])
        except:
            pass
        return 0
    
    def _on_window_close(self, window):
        """Handle window close event - save preferences."""
        self._save_window_prefs()
        return False  # Allow window to close
    
    def _load_scan_history(self):
        """Load recent scan history into sidebar."""
        result = self.send_request({"cmd": "list_history", "limit": 10})
        if result:
            try:
                j = json.loads(result)
                if j.get('status') == 'ok':
                    self.history_store.clear()
                    self.compare_scan1_combo.remove_all()
                    self.compare_scan2_combo.remove_all()
                    
                    for scan in j.get('history', []):
                        scan_id = scan.get('scan_id', '')
                        cidr = scan.get('cidr', '')
                        ts = scan.get('timestamp', 0)
                        time_str = time.strftime('%H:%M', time.localtime(ts)) if ts else '-'
                        display_str = f"{cidr} @ {time_str}"
                        
                        self.history_store.append([scan_id, cidr, time_str])
                        
                        # Add to comparison dropdowns
                        self.compare_scan1_combo.append(scan_id, display_str)
                        self.compare_scan2_combo.append(scan_id, display_str)
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
        self.cancel_scan_btn.set_visible(True)
        self.cancel_scan_btn.set_sensitive(True)
        self.status_label.set_text('Starting scan...')
        # Show progress bar
        self.progress_bar.set_visible(True)
        self.progress_bar.set_fraction(0.0)
        self.progress_bar.set_text("Starting scan...")
        self.current_cidr = cidr  # Store for subnet detection
        self._app_prefs['last_cidr'] = cidr  # Save as last used
        self._save_window_prefs()
        self._scan_cancelled = False  # Reset cancel flag
        # Clear store by creating new one (clear() deprecated in GTK4)
        self.store = Gtk.ListStore(str, str, str, str)
        if hasattr(self, 'filter_model'):
            self.filter_model = self.store.filter_new()
            self.filter_model.set_visible_func(self._filter_func)
            self.tree_view.set_model(self.filter_model)
        else:
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

    def on_cancel_scan_clicked(self, btn):
        """Handle cancel scan button click."""
        self._scan_cancelled = True
        self.status_label.set_text('Scan cancelled by user')
        self.progress_bar.set_visible(False)
        self.scan_btn.set_sensitive(True)
        self.export_btn.set_sensitive(True)
        self.cancel_scan_btn.set_visible(False)
        
        # Stop polling
        if hasattr(self, '_refresh_timeout_id') and self._refresh_timeout_id:
            GLib.source_remove(self._refresh_timeout_id)
            self._refresh_timeout_id = None
        
        # Send cancel request to helper (if supported)
        try:
            self.send_request({"cmd": "cancel_scan", "scan_id": self.current_scan_id})
        except:
            pass  # Helper may not support cancel yet

    def _start_polling(self):
        """Start polling for scan results."""
        if self._refresh_timeout_id:
            GLib.source_remove(self._refresh_timeout_id)
        
        self._poll_attempts = 0
        self._poll_start_time = time.time()
        self._poll_for_results()

    def _poll_for_results(self):
        """Poll database for scan results."""
        # Check if scan was cancelled
        if self._scan_cancelled:
            return False
        
        self._poll_attempts += 1
        
        if not self.current_scan_id:
            return False
        
        # Update progress bar (indeterminate for now, could be improved with real progress)
        elapsed = time.time() - getattr(self, '_poll_start_time', time.time())
        # Show progress with pulsing effect
        if self.progress_bar.get_visible():
            self.progress_bar.pulse()
            self.progress_bar.set_text(f"Scanning... ({int(elapsed)}s)")
        
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
                        self.cancel_scan_btn.set_visible(False)
                        # Hide progress bar
                        self.progress_bar.set_visible(False)
                        # Auto-generate and show network map
                        self._generate_network_map(hosts)
                        if self.map_drawing_area:
                            self.map_drawing_area.queue_draw()
                        self._load_scan_history()  # Refresh sidebar
                        # Show desktop notification
                        self._show_notification("Scan Complete", f"Found {len(hosts)} hosts")
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
                    self.cancel_scan_btn.set_visible(False)
                    self._load_scan_history()  # Refresh sidebar
                    # Auto-generate network map
                    self._generate_network_map(hosts)
                    if self.map_drawing_area:
                        self.map_drawing_area.queue_draw()
                    # Show desktop notification
                    self._show_notification("Scan Complete", f"Found {len(hosts)} hosts")
                    return False
        except Exception as e:
            print(f"Database access error: {e}")
        
        # Check if cancelled
        if self._scan_cancelled:
            return False
        
        # Keep polling if not done (max 60 attempts = 2 minutes)
        if self._poll_attempts < 60:
            elapsed = time.time() - getattr(self, '_poll_start_time', time.time())
            self.status_label.set_text(f"Scanning... ({int(elapsed)}s)")
            if self.progress_bar.get_visible():
                self.progress_bar.pulse()
                self.progress_bar.set_text(f"Scanning... ({int(elapsed)}s)")
            self._refresh_timeout_id = GLib.timeout_add_seconds(2, self._poll_for_results)
            return False
        else:
            self.status_label.set_text("Scan timeout - check helper logs")
            self.progress_bar.set_visible(False)
            self.scan_btn.set_sensitive(True)
            self.cancel_scan_btn.set_visible(False)
            return False

    def _update_results(self, hosts):
        """Update tree view with scan results."""
        # Clear store - create new one to avoid deprecation warning
        self.store = Gtk.ListStore(str, str, str, str)
        # Recreate filter model
        self.filter_model = self.store.filter_new()
        self.filter_model.set_visible_func(self._filter_func)
        self.tree_view.set_model(self.filter_model)
        
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
        
        # Nmap history section
        nmap_history_label = Gtk.Label(label="Nmap Scan History:")
        nmap_history_label.set_halign(Gtk.Align.START)
        nmap_history_label.set_margin_top(12)
        vbox.append(nmap_history_label)
        
        # Nmap history list
        nmap_store = Gtk.ListStore(int, str, str)  # timestamp, ports, services
        nmap_view = Gtk.TreeView(model=nmap_store)
        
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(title="Date/Time")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 1)
        nmap_view.append_column(col)
        
        col = Gtk.TreeViewColumn(title="Ports/Services")
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 2)
        col.set_resizable(True)
        nmap_view.append_column(col)
        
        nmap_scroll = Gtk.ScrolledWindow()
        nmap_scroll.set_child(nmap_view)
        nmap_scroll.set_min_content_height(120)
        nmap_scroll.set_max_content_height(200)
        vbox.append(nmap_scroll)
        
        # Load Nmap history
        self._load_nmap_history(ip, nmap_store)
        
        # Close button
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.connect("response", lambda d, r: d.close())
        
        dialog.present()
    
    def _load_nmap_history(self, ip, store):
        """Load Nmap scan history for a host."""
        result = self.send_request({
            "cmd": "get_nmap_history",
            "ip": ip,
            "limit": 20
        })
        if result:
            try:
                j = json.loads(result)
                if j.get('status') == 'ok':
                    history = j.get('history', [])
                    for entry in history:
                        ts = entry.get('timestamp', 0)
                        time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(ts)) if ts else '-'
                        ports = entry.get('ports', '')
                        services = entry.get('services', '')
                        display = ports if ports else services if services else 'No ports found'
                        store.append([ts, time_str, display])
            except:
                pass
    
    def on_nmap_clicked(self, btn):
        """Handle Nmap scan button click."""
        if not self.selected_host:
            return
        
        ip = self.selected_host['ip']
        # Show port range dialog
        dialog = Gtk.Dialog(title="Nmap Port Scan", transient_for=self, modal=True)
        dialog.set_default_size(350, 150)
        
        vbox = dialog.get_content_area()
        vbox.set_margin_start(20)
        vbox.set_margin_end(20)
        vbox.set_margin_top(20)
        vbox.set_margin_bottom(20)
        vbox.set_spacing(12)
        
        label = Gtk.Label(label=f"Scan ports on {ip}:")
        label.set_halign(Gtk.Align.START)
        vbox.append(label)
        
        port_entry = Gtk.Entry()
        port_entry.set_text("1-1024")
        port_entry.set_placeholder_text("e.g., 1-1024, 22,80,443, 8080-8090")
        port_entry.set_hexpand(True)
        vbox.append(port_entry)
        
        # Quick select buttons
        quick_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for ports, label_text in [("1-1024", "Common"), ("1-1000", "Fast"), ("1-65535", "All")]:
            btn = Gtk.Button(label=label_text)
            btn.connect('clicked', lambda b, p=ports: port_entry.set_text(p))
            quick_box.append(btn)
        vbox.append(quick_box)
        
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Scan", Gtk.ResponseType.ACCEPT)
        
        def on_response(d, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                ports = port_entry.get_text().strip()
                if not ports:
                    ports = "1-1024"
                self._run_nmap_scan(ip, ports)
            dialog.close()
        
        dialog.connect("response", on_response)
        dialog.present()
    
    def _run_nmap_scan(self, ip, ports, template="common"):
        """Actually run the Nmap scan with specified ports."""
        self.status_label.set_text(f"Running Nmap scan on {ip}:{ports}...")
        self.nmap_btn.set_sensitive(False)
        
        # Add version detection for service template
        args = {"cmd": "nmap", "ip": ip, "ports": ports}
        if template == "service":
            args["args"] = "-sV"  # Version detection
        
        # Send Nmap request
        result = self.send_request(args)
        
        self.nmap_btn.set_sensitive(True)
        
        if not result:
            self.status_label.set_text('Error: Nmap scan failed')
            return
        
        try:
            j = json.loads(result)
            if j.get('status') == 'ok':
                nmap_xml = j.get('nmap_xml', '')
                # Results are now saved automatically by helper
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

    def _export_map_image(self, btn):
        """Export network map as PNG image."""
        if not self.network_nodes:
            self._show_info_dialog("No Map", "Please run a scan first to generate the network map.")
            return
        
        # Create file chooser dialog
        dialog = Gtk.FileChooserDialog(
            title="Export Network Map",
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.SAVE
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Save", Gtk.ResponseType.ACCEPT)
        
        # Set default filename
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dialog.set_current_name(f"netmap_{timestamp}.png")
        
        # Add PNG filter
        png_filter = Gtk.FileFilter()
        png_filter.set_name("PNG Images")
        png_filter.add_pattern("*.png")
        dialog.add_filter(png_filter)
        
        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file:
                    filename = file.get_path()
                    dialog.close()
                    
                    try:
                        self._do_export_map(filename)
                    except Exception as e:
                        self._show_error_dialog("Export Error", f"Failed to export map: {e}")
                else:
                    dialog.close()
            else:
                dialog.close()
        
        dialog.connect("response", on_response)
        dialog.present()
    
    def _do_export_map(self, filename):
        """Actually perform the map export."""
        try:
            # Get drawing area dimensions
            width = self.map_drawing_area.get_allocated_width()
            height = self.map_drawing_area.get_allocated_height()
            if width == 0 or height == 0:
                width, height = 1200, 800  # Default size
            
            # Create surface for exporting
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
            cr = cairo.Context(surface)
            
            # Fill white background
            cr.set_source_rgb(1, 1, 1)
            cr.paint()
            
            # Draw the map (reuse drawing code)
            center_x, center_y = width / 2, height / 2
            cr.translate(center_x, center_y)
            cr.scale(self.map_zoom, self.map_zoom)
            
            # Draw connections
            gateway_node = None
            for node in self.network_nodes:
                if node.get('type') == 'gateway':
                    gateway_node = node
                    break
            
            if gateway_node:
                cr.set_source_rgba(0.7, 0.7, 0.7, 0.5)
                cr.set_line_width(1)
                for node in self.network_nodes:
                    if node['type'] != 'gateway':
                        cr.move_to(node['x'], node['y'])
                        cr.line_to(gateway_node['x'], gateway_node['y'])
                        cr.stroke()
            
            # Draw nodes
            for node in self.network_nodes:
                node_type = node.get('type', 'device')
                if node_type == 'gateway':
                    cr.set_source_rgb(0.2, 0.6, 0.9)
                elif node_type == 'server':
                    cr.set_source_rgb(0.9, 0.6, 0.2)
                elif node_type == 'iot':
                    cr.set_source_rgb(0.7, 0.3, 0.9)
                elif node_type == 'mobile':
                    cr.set_source_rgb(0.9, 0.8, 0.2)
                elif node_type == 'printer':
                    cr.set_source_rgb(0.3, 0.7, 0.9)
                elif node_type == 'unknown':
                    cr.set_source_rgb(0.6, 0.6, 0.6)
                else:
                    cr.set_source_rgb(0.4, 0.7, 0.4)
                
                cr.arc(node['x'], node['y'], node['radius'], 0, 2 * 3.14159)
                cr.fill()
                
                cr.set_source_rgb(0.2, 0.2, 0.2)
                cr.set_line_width(2)
                cr.arc(node['x'], node['y'], node['radius'], 0, 2 * 3.14159)
                cr.stroke()
                
                # Draw label
                cr.set_source_rgb(0, 0, 0)
                cr.select_font_face("Sans Bold")
                cr.set_font_size(10)
                label = node['ip'].split('.')[-1]
                (x, y, text_width, text_height, dx, dy) = cr.text_extents(label)
                cr.move_to(node['x'] - text_width / 2, node['y'] + node['radius'] + text_height + 5)
                cr.show_text(label)
            
            # Draw legend on exported image
            cr.identity_matrix()
            legend_x, legend_y = 10, 10
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.rectangle(legend_x, legend_y, 180, 150)
            cr.fill()
            cr.set_source_rgba(0, 0, 0, 0.3)
            cr.set_line_width(1)
            cr.rectangle(legend_x, legend_y, 180, 150)
            cr.stroke()
            
            cr.set_source_rgb(0, 0, 0)
            cr.select_font_face("Sans Bold")
            cr.set_font_size(11)
            cr.move_to(legend_x + 5, legend_y + 18)
            cr.show_text("Device Types")
            
            legend_items = [
                ((0.2, 0.6, 0.9), "Gateway/Router"),
                ((0.9, 0.6, 0.2), "Server"),
                ((0.4, 0.7, 0.4), "Device"),
                ((0.7, 0.3, 0.9), "IoT"),
                ((0.9, 0.8, 0.2), "Mobile"),
                ((0.3, 0.7, 0.9), "Printer"),
                ((0.6, 0.6, 0.6), "Unknown"),
            ]
            
            cr.select_font_face("Sans")
            cr.set_font_size(9)
            y_offset = 35
            for color, label in legend_items:
                cr.set_source_rgb(*color)
                cr.arc(legend_x + 12, legend_y + y_offset, 5, 0, 2 * 3.14159)
                cr.fill()
                cr.set_source_rgb(0, 0, 0)
                cr.move_to(legend_x + 25, legend_y + y_offset + 4)
                cr.show_text(label)
                y_offset += 18
            
            # Write to file
            surface.write_to_png(filename)
            self.status_label.set_text(f"Map exported to {filename}")
            self._show_info_dialog("Export Successful", f"Network map saved to:\n{filename}")
            
        except Exception as e:
            self._show_error_dialog("Export Error", f"Failed to export map: {e}")
            raise
    
    def _show_notification(self, title, message):
        """Show desktop notification."""
        if not self.notifications_available or not NOTIFY_AVAILABLE:
            return
        
        try:
            notification = Notify.Notification.new(title, message, "network-wired")
            notification.set_timeout(5000)  # 5 seconds
            notification.show()
        except Exception as e:
            print(f"Notification error: {e}")
    
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
