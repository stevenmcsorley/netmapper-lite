# Suggested Improvements for NetMapper-Lite

## High Priority

### 1. **Scan Progress & Cancel**
- Show progress bar during scans
- Display "Scanning... X% complete" with estimated time
- "Cancel Scan" button to stop ongoing scans
- Real-time host count as devices are discovered

### 2. **Filter & Search**
- Search/filter hosts in results table by IP, hostname, or vendor
- Sortable columns (click headers to sort)
- Filter by device type (servers, IoT, mobile, etc.)
- Highlight specific hosts

### 3. **Scan Comparisons (Diff View)**
- Compare two scans side-by-side
- Highlight new devices (green)
- Highlight disappeared devices (red)
- Show which devices changed (MAC, hostname)
- Visual diff in network map

### 4. **Network Map Enhancements**
- Color-code nodes by device type:
  - Blue: Gateway/router
  - Orange: Servers
  - Green: Regular devices
  - Purple: IoT devices
  - Yellow: Mobile devices
  - Gray: Unknown/guest devices
- Legend/key showing what colors mean
- Hover tooltips showing device info
- Drag to pan (currently only zoom)
- Better layout algorithm (force-directed graph)

### 5. **Performance Improvements**
- Parallel ARP scanning for large networks (/16, /8)
- Progress reporting during long scans
- Caching of vendor lookups
- Lazy loading of scan history

## Medium Priority

### 6. **Nmap Integration Enhancements**
- Save Nmap results to database
- Show Nmap history per host
- Schedule periodic Nmap scans
- Custom port ranges in GUI
- Nmap scan templates (quick scan, full scan, etc.)
- Show open ports directly on network map nodes

### 7. **Export & Reporting**
- Export network map as image (PNG/SVG)
- Export full scan history (not just current scan)
- Generate network report (PDF/HTML)
- Export subnet information
- Scheduled reports

### 8. **Notifications & Alerts**
- Desktop notification when scan completes
- Alert on new devices detected
- Alert on devices that disappeared
- Configurable alert rules

### 9. **Device Classification**
- Auto-classify devices by vendor/type
- Group devices by category in results
- Device icons/logos (if vendor info available)
- Custom tags/labels for devices

### 10. **Multi-Network Support**
- Scan multiple networks at once
- Combine results from different networks
- Network profiles (save CIDR presets)
- Quick scan buttons for common networks

## Lower Priority

### 11. **Advanced Visualization**
- Timeline view showing device availability over time
- Heat map showing most active devices
- Connection strength/thickness based on traffic
- 3D network map (optional)

### 12. **Security Features**
- Rate limiting for scans
- Audit logging
- Input validation hardening
- Optional encryption for socket communication

### 13. **User Experience**
- Dark mode theme
- Customizable UI colors
- Keyboard shortcuts
- Window size/position persistence
- Recent scans quick access

### 14. **Advanced Scanning**
- Ping sweep before ARP (for remote subnets)
- Multi-threaded scanning
- Configurable timeout/retry settings
- Scan scheduling (cron-like)
- Wake-on-LAN support

### 15. **Database Features**
- Cleanup old scans automatically
- Database statistics/dashboard
- Backup/restore scan history
- Export/import database

## Implementation Complexity

**Easy (1-2 hours):**
- Filter/search in results table
- Sortable columns
- Progress indicator
- Device type colors on map
- Legend/key

**Medium (4-8 hours):**
- Scan progress & cancel
- Scan comparisons/diff
- Save Nmap results
- Export network map as image
- Notifications

**Hard (1-2 days):**
- Multi-network scanning
- Timeline/availability view
- Force-directed graph layout
- Parallel scanning optimization
- CI/CD pipeline

## Recommended Next Steps

1. **Quick wins** (do these first):
   - Add filter/search in results table
   - Color-code map nodes by device type
   - Add legend/key
   - Progress indicator during scans

2. **User-requested features**:
   - Scan cancel functionality
   - Scan comparisons/diff view
   - Export map as image

3. **Polish & UX**:
   - Dark mode
   - Better error messages
   - Keyboard shortcuts
   - Tooltips and help text

