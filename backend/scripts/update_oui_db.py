#!/usr/bin/env python3
"""
Update OUI (Organizationally Unique Identifier) database from IEEE.
Downloads the latest OUI database and stores it in SQLite for fast lookups.
"""
import sqlite3
import urllib.request
import csv
import os
import sys
from pathlib import Path

OUI_URL = "https://standards-oui.ieee.org/oui/oui.csv"
OUI_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "oui.db")
DEV_OUI_DB_PATH = os.path.expanduser("~/.local/share/netmapper/oui.db")


def download_oui_database():
    """Download OUI database from IEEE."""
    print(f"Downloading OUI database from {OUI_URL}...")
    try:
        with urllib.request.urlopen(OUI_URL, timeout=30) as response:
            data = response.read().decode('utf-8')
        print(f"Downloaded {len(data)} bytes")
        return data
    except Exception as e:
        print(f"Error downloading OUI database: {e}")
        return None


def parse_oui_csv(csv_data):
    """Parse OUI CSV data and extract MAC -> Vendor mappings."""
    import io
    reader = csv.DictReader(io.StringIO(csv_data))
    oui_map = {}
    
    print("Parsing OUI entries...")
    count = 0
    for row in reader:
        oui = row.get('Assignment', '').strip().upper()
        org = row.get('Organization', '').strip()
        
        # Format: XX-XX-XX (with dashes) or XXXXXX (without)
        # Convert to standard format: XX:XX:XX
        oui = oui.replace('-', ':').replace(' ', '')
        if len(oui) == 6:  # Should be 6 hex chars
            oui_map[oui] = org
            count += 1
    
    print(f"Parsed {count} OUI entries")
    return oui_map


def store_oui_db(oui_map, db_path):
    """Store OUI mappings in SQLite database."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Create table
    c.execute('''CREATE TABLE IF NOT EXISTS oui (
        oui_prefix TEXT PRIMARY KEY,
        vendor TEXT
    )''')
    
    # Clear existing data
    c.execute('DELETE FROM oui')
    
    # Insert new data
    print(f"Storing {len(oui_map)} entries in database...")
    for oui, vendor in oui_map.items():
        c.execute('INSERT INTO oui (oui_prefix, vendor) VALUES (?, ?)', (oui, vendor))
    
    conn.commit()
    conn.close()
    print(f"OUI database stored at {db_path}")


def lookup_vendor_from_db(mac, db_path):
    """Lookup vendor from MAC address using OUI database."""
    if not os.path.exists(db_path):
        return None
    
    # Extract first 6 hex chars (OUI prefix) from MAC
    # MAC format: XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
    mac_clean = mac.upper().replace('-', ':').replace(' ', '')
    parts = mac_clean.split(':')
    
    if len(parts) < 3:
        return None
    
    oui_prefix = f"{parts[0]}{parts[1]}{parts[2]}"
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('SELECT vendor FROM oui WHERE oui_prefix = ?', (oui_prefix,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception:
        return None


def main():
    """Main function to update OUI database."""
    dev_mode = '--dev' in sys.argv
    
    db_path = DEV_OUI_DB_PATH if dev_mode else OUI_DB_PATH
    
    if dev_mode:
        print("Running in DEV mode")
    
    print(f"OUI database will be stored at: {db_path}")
    
    # Download OUI database
    csv_data = download_oui_database()
    if not csv_data:
        print("Failed to download OUI database")
        sys.exit(1)
    
    # Parse CSV
    oui_map = parse_oui_csv(csv_data)
    if not oui_map:
        print("Failed to parse OUI database")
        sys.exit(1)
    
    # Store in database
    store_oui_db(oui_map, db_path)
    
    print("OUI database update complete!")
    print(f"\nTo test lookup:")
    print(f"  python3 -c \"from scripts.update_oui_db import lookup_vendor_from_db; print(lookup_vendor_from_db('AA:BB:CC:DD:EE:FF', '{db_path}'))\"")


if __name__ == '__main__':
    main()


