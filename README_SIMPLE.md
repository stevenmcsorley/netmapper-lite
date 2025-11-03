# NetMapper-Lite - Simple Setup (Just Make It Work)

## The Problem
The app needs network permissions to scan. Here's the simplest way to make it work.

## Solution (2 Steps)

### Step 1: Start Helper (Terminal 1)
```bash
cd ~/projects/software/netmapper-lite
sudo python3 backend/netmapper_helper.py --dev
```
Leave this terminal running.

### Step 2: Start GUI (Terminal 2)
```bash
cd ~/projects/software/netmapper-lite
python3 frontend/gui.py
```

### Step 3: Scan
- Enter your network: `192.168.1.0/24`
- Click "Start Scan"
- Wait 10-30 seconds
- See results!

## That's It!

If you see 0 hosts, check:
1. Helper is running (Step 1)
2. You're on the right network
3. There are devices on the network

## Alternative: One-Time Setup (No Sudo Each Time)

If you don't want to use sudo every time:

```bash
# One-time setup (requires sudo once)
sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)

# Then run helper normally (no sudo needed)
python3 backend/netmapper_helper.py --dev
```

## Troubleshooting

**"Connection refused"**
- Helper isn't running. Start it (Step 1)

**"Found 0 hosts" but helper logs show "Operation not permitted"**
- Helper needs sudo or capabilities (see above)

**GUI won't open**
- Check GTK4 is installed: `sudo apt-get install python3-gi gir1.2-gtk-4.0`

**Still not working?**
- Check helper logs: `tail -f /tmp/helper.log`
- Make sure you're on a real network (not isolated VM)
- Verify network: `ip addr show`

