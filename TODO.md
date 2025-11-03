# TODO / Future Enhancements

## Production Readiness

### Compiled Helper Binary
- [ ] Create small Rust/C helper binary to replace Python helper
- [ ] This avoids need for `setcap` on Python interpreter
- [ ] Easier to package and maintain
- [ ] Better security (smaller attack surface)
- [ ] Location: `backend/helper-rust/` or `backend/helper-c/`

## Features

### OUI Database
- [ ] Automate OUI database updates (cron job)
- [ ] Cache frequently looked-up vendors
- [ ] Add vendor icons/logos to UI

### Nmap Integration
- [ ] Allow custom port ranges in GUI
- [ ] Save Nmap scan results to database
- [ ] Show Nmap history per host
- [ ] Schedule periodic Nmap scans

### Network History & Diff
- [ ] Implement diff view between scans
- [ ] Highlight new/disappeared hosts
- [ ] Show host uptime/availability timeline
- [ ] Export scan history to JSON/CSV

### Performance
- [ ] Parallel ARP scanning for large networks
- [ ] Progress reporting during scans
- [ ] Cancel scan functionality

## UI Enhancements

- [ ] Dark mode support
- [ ] Host details dialog (click on host row)
- [ ] Scan history sidebar
- [ ] Export scan results
- [ ] Network topology visualization
- [ ] Filter/search hosts

## Testing

- [x] Mock scanner for fake network data (no root needed)
- [x] Fake network scripts for testing
- [ ] Unit tests for scanner functions with mocked scapy
- [ ] Mock OUI database for tests
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Test coverage reporting

## Documentation

- [ ] User manual
- [ ] API documentation
- [ ] Developer guide
- [ ] Packaging guide for other distros

## Security

- [ ] Rate limiting for scan requests
- [ ] Audit logging
- [ ] Input validation hardening
- [ ] Secure socket communication (optional encryption)


