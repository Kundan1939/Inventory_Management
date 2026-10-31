"""
Hardware and Barcode Auto-Detection Engine for IT Asset Manager
Extracts local host specs on Ubuntu / Linux and enriches barcode/serial information.
"""

import glob
import json
import os
import platform
import re
import socket
import subprocess
import urllib.request

CHASSIS_MAP = {
    '1': 'Other', '2': 'Unknown', '3': 'Desktop', '4': 'Low Profile Desktop',
    '5': 'Pizza Box', '6': 'Mini Tower', '7': 'Tower', '8': 'Portable',
    '9': 'Laptop', '10': 'Notebook', '11': 'Hand Held', '12': 'Docking Station',
    '13': 'All-in-One', '14': 'Sub Notebook', '15': 'Space-saving Desktop',
    '16': 'Lunch Box', '17': 'Main Server Chassis', '18': 'Expansion Chassis',
    '19': 'SubChassis', '20': 'Bus Expansion Chassis', '21': 'Peripheral Chassis',
    '22': 'RAID Chassis', '23': 'Rack Mount Chassis', '24': 'Sealed-case PC',
    '30': 'Tablet', '31': 'Convertible Laptop', '32': 'Detachable Laptop'
}

OUI_MAP = {
    '00:14:22': ('Dell Inc.', 'Computer / Network'),
    '00:1E:C9': ('Dell Inc.', 'Computer / Network'),
    '18:66:DA': ('Dell Inc.', 'Computer / Network'),
    '74:86:7A': ('Dell Inc.', 'Computer / Network'),
    'B0:4F:13': ('Dell Inc.', 'Computer / Network'),
    'B8:2A:72': ('Dell Inc.', 'Computer / Network'),
    'D4:BE:D9': ('Dell Inc.', 'Computer / Network'),
    'F8:DB:88': ('Dell Inc.', 'Computer / Network'),
    '00:1F:29': ('HP Inc.', 'Computer / Printer'),
    '3C:D9:2B': ('HP Inc.', 'Computer / Printer'),
    '70:5A:0F': ('HP Inc.', 'Computer / Printer'),
    '98:E7:43': ('HP Inc.', 'Computer / Printer'),
    '00:21:CC': ('Lenovo', 'Laptop / Desktop'),
    '54:EE:75': ('Lenovo', 'Laptop / Desktop'),
    '70:85:C2': ('Lenovo', 'Laptop / Desktop'),
    '80:2B:F9': ('Lenovo', 'Laptop / Desktop'),
    '00:17:88': ('Apple Inc.', 'Mac / iPhone / iPad'),
    '3C:06:30': ('Apple Inc.', 'Mac / iPhone / iPad'),
    'AC:BC:32': ('Apple Inc.', 'Mac / iPhone / iPad'),
    'F4:F1:5A': ('Apple Inc.', 'Mac / iPhone / iPad'),
    '00:00:0C': ('Cisco Systems', 'Switch / Router'),
    '00:27:0D': ('Cisco Systems', 'Switch / Router'),
    '74:8E:F8': ('Ubiquiti Networks', 'Access Point / Switch'),
    '24:5A:4C': ('Ubiquiti Networks', 'Access Point / Switch'),
    'B8:27:EB': ('Raspberry Pi Foundation', 'Single Board Computer'),
    'DC:A6:32': ('Raspberry Pi Foundation', 'Single Board Computer'),
    'E4:5F:01': ('Raspberry Pi Foundation', 'Single Board Computer'),
    '00:1A:79': ('TP-Link Technologies', 'Network Device'),
    '50:D4:F7': ('TP-Link Technologies', 'Network Device'),
}

HARDWARE_CATALOG = [
    # Dell Laptops
    {"keywords": ["vostro 3510", "vostro 15 3510"], "manufacturer": "Dell Inc.", "model": "Vostro 15 3510", "asset_type": "Laptop", "cpu": "11th Gen Intel Core i5-1135G7", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["vostro 3520", "vostro 15 3520"], "manufacturer": "Dell Inc.", "model": "Vostro 15 3520", "asset_type": "Laptop", "cpu": "12th Gen Intel Core i5-1235U", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["vostro 3400", "vostro 14 3400"], "manufacturer": "Dell Inc.", "model": "Vostro 14 3400", "asset_type": "Laptop", "cpu": "11th Gen Intel Core i5-1135G7", "ram": "8 GB DDR4", "storage": "256 GB SSD"},
    {"keywords": ["latitude 3420"], "manufacturer": "Dell Inc.", "model": "Latitude 3420", "asset_type": "Laptop", "cpu": "11th Gen Intel Core i5-1135G7", "ram": "16 GB DDR4", "storage": "256 GB NVMe SSD"},
    {"keywords": ["latitude 5420"], "manufacturer": "Dell Inc.", "model": "Latitude 5420", "asset_type": "Laptop", "cpu": "11th Gen Intel Core i5-1145G7", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["latitude 5430"], "manufacturer": "Dell Inc.", "model": "Latitude 5430", "asset_type": "Laptop", "cpu": "12th Gen Intel Core i5-1245U", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["latitude 5520"], "manufacturer": "Dell Inc.", "model": "Latitude 5520", "asset_type": "Laptop", "cpu": "11th Gen Intel Core i7-1185G7", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["latitude 7420"], "manufacturer": "Dell Inc.", "model": "Latitude 7420", "asset_type": "Laptop", "cpu": "11th Gen Intel Core i7-1185G7", "ram": "16 GB LPDDR4x", "storage": "512 GB NVMe SSD"},
    {"keywords": ["latitude 7430"], "manufacturer": "Dell Inc.", "model": "Latitude 7430", "asset_type": "Laptop", "cpu": "12th Gen Intel Core i7-1265U", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["xps 13 9310", "xps 13"], "manufacturer": "Dell Inc.", "model": "XPS 13", "asset_type": "Laptop", "cpu": "Intel Core i7-1185G7", "ram": "16 GB LPDDR4x", "storage": "512 GB NVMe SSD"},
    {"keywords": ["xps 15 9510", "xps 15"], "manufacturer": "Dell Inc.", "model": "XPS 15", "asset_type": "Laptop", "cpu": "Intel Core i7-11800H", "ram": "32 GB DDR4", "storage": "1 TB NVMe SSD"},
    # Dell Desktops & Workstations
    {"keywords": ["optiplex 3080"], "manufacturer": "Dell Inc.", "model": "OptiPlex 3080", "asset_type": "Desktop", "cpu": "Intel Core i5-10500", "ram": "16 GB DDR4", "storage": "512 GB SSD"},
    {"keywords": ["optiplex 7080"], "manufacturer": "Dell Inc.", "model": "OptiPlex 7080", "asset_type": "Desktop", "cpu": "Intel Core i7-10700", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["optiplex 7090"], "manufacturer": "Dell Inc.", "model": "OptiPlex 7090", "asset_type": "Desktop", "cpu": "11th Gen Intel Core i7-11700", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["optiplex 3000", "optiplex 7000"], "manufacturer": "Dell Inc.", "model": "OptiPlex 7000 Micro", "asset_type": "Desktop", "cpu": "12th Gen Intel Core i7-12700", "ram": "16 GB DDR5", "storage": "512 GB NVMe SSD"},
    {"keywords": ["precision 3560", "precision 3570"], "manufacturer": "Dell Inc.", "model": "Precision 3560 Workstation", "asset_type": "Laptop", "cpu": "Intel Core i7-1185G7", "ram": "32 GB DDR4", "storage": "1 TB NVMe SSD"},
    {"keywords": ["poweredge r640", "poweredge r740"], "manufacturer": "Dell Inc.", "model": "PowerEdge R740 Server", "asset_type": "Server", "cpu": "Dual Intel Xeon Silver 4210R", "ram": "64 GB ECC DDR4", "storage": "4x 1.2TB SAS 10K RAID"},
    
    # Lenovo
    {"keywords": ["thinkpad t14 gen 1", "thinkpad t14 gen 2", "thinkpad t14"], "manufacturer": "Lenovo", "model": "ThinkPad T14", "asset_type": "Laptop", "cpu": "Intel Core i5-1135G7 / AMD Ryzen 5 Pro", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["thinkpad t14s"], "manufacturer": "Lenovo", "model": "ThinkPad T14s", "asset_type": "Laptop", "cpu": "Intel Core i7-1165G7", "ram": "16 GB LPDDR4x", "storage": "512 GB NVMe SSD"},
    {"keywords": ["thinkpad t15"], "manufacturer": "Lenovo", "model": "ThinkPad T15", "asset_type": "Laptop", "cpu": "Intel Core i7-1165G7", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["thinkpad x1 carbon"], "manufacturer": "Lenovo", "model": "ThinkPad X1 Carbon", "asset_type": "Laptop", "cpu": "Intel Core i7-1165G7", "ram": "16 GB LPDDR4x", "storage": "512 GB NVMe SSD"},
    {"keywords": ["thinkpad e14"], "manufacturer": "Lenovo", "model": "ThinkPad E14", "asset_type": "Laptop", "cpu": "AMD Ryzen 5 5500U", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["thinkpad l14"], "manufacturer": "Lenovo", "model": "ThinkPad L14", "asset_type": "Laptop", "cpu": "Intel Core i5-1135G7", "ram": "16 GB DDR4", "storage": "256 GB NVMe SSD"},
    {"keywords": ["thinkcentre m70q"], "manufacturer": "Lenovo", "model": "ThinkCentre M70q Tiny", "asset_type": "Desktop", "cpu": "Intel Core i5-10400T", "ram": "16 GB DDR4", "storage": "512 GB SSD"},
    {"keywords": ["thinkcentre m90q"], "manufacturer": "Lenovo", "model": "ThinkCentre M90q Tiny", "asset_type": "Desktop", "cpu": "Intel Core i7-11700T", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},

    # HP
    {"keywords": ["elitebook 840 g7", "elitebook 840 g8", "elitebook 840"], "manufacturer": "HP", "model": "EliteBook 840 G8", "asset_type": "Laptop", "cpu": "Intel Core i5-1135G7", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["elitebook 850 g8", "elitebook 850"], "manufacturer": "HP", "model": "EliteBook 850 G8", "asset_type": "Laptop", "cpu": "Intel Core i7-1165G7", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["probook 440 g8", "probook 440"], "manufacturer": "HP", "model": "ProBook 440 G8", "asset_type": "Laptop", "cpu": "Intel Core i5-1135G7", "ram": "8 GB DDR4", "storage": "256 GB NVMe SSD"},
    {"keywords": ["probook 450 g8", "probook 450"], "manufacturer": "HP", "model": "ProBook 450 G8", "asset_type": "Laptop", "cpu": "Intel Core i5-1135G7", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["prodesk 400 g7", "prodesk 400"], "manufacturer": "HP", "model": "ProDesk 400 G7 SFF", "asset_type": "Desktop", "cpu": "Intel Core i5-10500", "ram": "16 GB DDR4", "storage": "512 GB SSD"},
    {"keywords": ["elitedesk 800 g6", "elitedesk 800"], "manufacturer": "HP", "model": "EliteDesk 800 G6 Mini", "asset_type": "Desktop", "cpu": "Intel Core i7-10700", "ram": "16 GB DDR4", "storage": "512 GB NVMe SSD"},
    {"keywords": ["zbook firefly 14", "zbook"], "manufacturer": "HP", "model": "ZBook Firefly 14 G8", "asset_type": "Laptop", "cpu": "Intel Core i7-1165G7 + NVIDIA T500", "ram": "32 GB DDR4", "storage": "1 TB NVMe SSD"},
    {"keywords": ["laserjet pro m404", "laserjet"], "manufacturer": "HP", "model": "LaserJet Pro M404dn", "asset_type": "Printer", "cpu": "1200 MHz Embedded", "ram": "256 MB", "storage": "Internal Flash"},

    # Apple
    {"keywords": ["macbook air m1"], "manufacturer": "Apple", "model": "MacBook Air (M1, 2020)", "asset_type": "Laptop", "cpu": "Apple M1 (8-core)", "ram": "8 GB Unified", "storage": "256 GB SSD"},
    {"keywords": ["macbook air m2"], "manufacturer": "Apple", "model": "MacBook Air (M2, 2022)", "asset_type": "Laptop", "cpu": "Apple M2 (8-core)", "ram": "16 GB Unified", "storage": "512 GB SSD"},
    {"keywords": ["macbook pro 14 m1", "macbook pro 14"], "manufacturer": "Apple", "model": "MacBook Pro 14-inch (M1 Pro)", "asset_type": "Laptop", "cpu": "Apple M1 Pro (10-core)", "ram": "16 GB Unified", "storage": "512 GB SSD"},
    {"keywords": ["macbook pro 16 m1", "macbook pro 16"], "manufacturer": "Apple", "model": "MacBook Pro 16-inch (M1 Pro)", "asset_type": "Laptop", "cpu": "Apple M1 Pro (10-core)", "ram": "32 GB Unified", "storage": "1 TB SSD"},
    {"keywords": ["mac mini m1", "mac mini"], "manufacturer": "Apple", "model": "Mac mini (M1)", "asset_type": "Desktop", "cpu": "Apple M1 (8-core)", "ram": "16 GB Unified", "storage": "512 GB SSD"},

    # Displays & Network
    {"keywords": ["p2419h", "p2422h", "dell p2419h", "dell p2422h"], "manufacturer": "Dell Inc.", "model": "Dell 24 Monitor (P2422H)", "asset_type": "Monitor", "cpu": "Display Controller", "ram": "N/A", "storage": "N/A"},
    {"keywords": ["p2720d", "dell p2720d"], "manufacturer": "Dell Inc.", "model": "Dell 27 1440p Monitor (P2720D)", "asset_type": "Monitor", "cpu": "Display Controller", "ram": "N/A", "storage": "N/A"},
    {"keywords": ["u2720q", "ultrasharp"], "manufacturer": "Dell Inc.", "model": "Dell UltraSharp 27 4K (U2720Q)", "asset_type": "Monitor", "cpu": "Display Controller", "ram": "N/A", "storage": "N/A"},
    {"keywords": ["catalyst 2960", "catalyst 9200", "ws-c2960"], "manufacturer": "Cisco Systems", "model": "Cisco Catalyst Switch", "asset_type": "Network", "cpu": "Cisco Dual Core", "ram": "2 GB", "storage": "4 GB Flash"},
    {"keywords": ["unifi", "u6-pro", "udm-pro"], "manufacturer": "Ubiquiti Networks", "model": "UniFi Network Hardware", "asset_type": "Network", "cpu": "ARM Cortex Quad-Core", "ram": "4 GB", "storage": "16 GB eMMC"}
]

def _read_file(path):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read().strip()
    except Exception:
        return ''

def resolve_disk_vendor(vendor: str, model: str) -> str:
    m = f"{vendor} {model}".upper()
    if any(k in m for k in ['SAMSUNG', 'MZVL', 'MZNT', 'MZ7', 'MZ8', '980 PRO', '970 EVO', '990 PRO']):
        return "Samsung"
    if any(k in m for k in ['WDC', 'WD ', 'WESTERN DIGITAL', 'SN520', 'SN530', 'SN550', 'SN570', 'SN740', 'SN750', 'SN770', 'SN850']):
        return "Western Digital"
    if any(k in m for k in ['CRUCIAL', 'MICRON', 'MTFD', 'CT500', 'CT1000', 'CT2000']) or re.search(r'\bCT\d{3,4}\b', m):
        return "Crucial / Micron"
    if any(k in m for k in ['KINGSTON', 'SA400', 'SKC', 'OM8P', 'SNV2', 'SNV3']):
        return "Kingston"
    if any(k in m for k in ['KIOXIA', 'TOSHIBA', 'KBG', 'THNS']):
        return "Kioxia / Toshiba"
    if any(k in m for k in ['SKHYNIX', 'SK HYNIX', 'HYNIX', 'HFM', 'HFS', 'PC711', 'BC711', 'BC511']):
        return "SK Hynix"
    if any(k in m for k in ['SEAGATE', 'BARRACUDA', 'FIRECUDA']) or re.search(r'\bST\d{3,4}\b', m):
        return "Seagate"
    if any(k in m for k in ['SANDISK', 'SDSS']):
        return "SanDisk"
    if any(k in m for k in ['INTEL', 'MEMPEK', 'SSDPE']):
        return "Intel"
    if any(k in m for k in ['ADATA', 'SX8200', 'SU650', 'SU800']):
        return "ADATA"
    if any(k in m for k in ['CORSAIR', 'FORCE MP']):
        return "Corsair"
    if 'SOLIDIGM' in m:
        return "Solidigm"
    if 'LEXAR' in m:
        return "Lexar"
    if 'TRANSCEND' in m:
        return "Transcend"
    if 'PNY' in m:
        return "PNY"
    if 'TEAMGROUP' in m or 'TEAM ' in m:
        return "TeamGroup"

    clean = vendor.strip() if vendor and not any(g in vendor.lower() for g in ['standard', 'generic', 'unknown', 'none', 'nvme ssd', 'ata']) else ''
    if clean:
        return clean
    parts = model.split()
    if parts and len(parts[0]) > 2 and not parts[0].isdigit() and parts[0].upper() not in ['NVME', 'SSD', 'SCSI', 'DISK']:
        return parts[0]
    return "NVMe / SSD"

INVALID_SERIALS = {
    '', 'none', 'to be filled by o.e.m.', 'default string', 'system serial number',
    'chassis serial number', 'type2 - board serial number', '00000000', '123456789',
    'not specified', 'null', 'n/a', 'unknown', 'system manufacturer'
}

def clean_serial(s):
    if not s:
        return ''
    s = str(s).strip()
    if s.lower() in INVALID_SERIALS:
        return ''
    return s

def extract_system_serial():
    """
    Exhaustively extracts authentic physical hardware serial number / service tag.
    Checks DMI product_serial, chassis_serial, board_serial, systemd hostnamed dbus, and dmidecode.
    """
    # 1. Direct DMI product_serial
    s = clean_serial(_read_file('/sys/class/dmi/id/product_serial'))
    if s:
        return s

    # 2. Direct DMI chassis_serial
    s = clean_serial(_read_file('/sys/class/dmi/id/chassis_serial'))
    if s:
        return s

    # 3. Direct DMI board_serial (Dell format: /3BZL6Q3/CNCMC001C6087C/)
    b_sn = _read_file('/sys/class/dmi/id/board_serial')
    if b_sn:
        m_dell = re.search(r'/([A-Za-z0-9]{7})/', b_sn)
        if m_dell:
            cand = clean_serial(m_dell.group(1))
            if cand:
                return cand.upper()
        s = clean_serial(b_sn)
        if s:
            return s

    # 4. systemd-hostnamed D-Bus interface (works unprivileged on Ubuntu / modern Linux)
    try:
        out = subprocess.check_output(
            ['busctl', '--timeout=5', 'call', 'org.freedesktop.hostname1', '/org/freedesktop/hostname1', 'org.freedesktop.hostname1', 'GetHardwareSerial'],
            stderr=subprocess.DEVNULL, timeout=6
        ).decode()
        m = re.search(r's\s+"([^"]+)"', out)
        if m:
            s = clean_serial(m.group(1))
            if s:
                return s
    except Exception:
        pass

    # 5. dmidecode tools (both unprivileged & sudo)
    for flag in ['system-serial-number', 'chassis-serial-number', 'baseboard-serial-number']:
        try:
            out = subprocess.check_output(['dmidecode', '-s', flag], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            s = clean_serial(out)
            if s:
                return s
        except Exception:
            pass
        try:
            out = subprocess.check_output(['sudo', '-n', 'dmidecode', '-s', flag], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            s = clean_serial(out)
            if s:
                return s
        except Exception:
            pass

    # 6. Fallback to machine-id token only if no physical serial can be found
    machine_id = _read_file('/etc/machine-id')
    if machine_id:
        return f"UB-{machine_id[:8].upper()}"

    return ''

def get_primary_ip() -> str:
    """Dynamically detects active LAN/WiFi IP address of this machine whenever network changes."""
    env_ip = os.environ.get('HOST_LAN_IP') or os.environ.get('LAN_IP')
    if env_ip and env_ip.strip() and env_ip.strip().lower() != 'auto':
        clean_env = env_ip.strip()
        if not (clean_env.startswith('172.') or clean_env.startswith('127.')):
            return clean_env

    # 1. Dynamic kernel routing check (queries active default gateway interface)
    for target in [('8.8.8.8', 80), ('1.1.1.1', 80), ('10.255.255.255', 80), ('192.168.255.255', 80)]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(target)
            ip = s.getsockname()[0]
            s.close()
            if ip and not (ip.startswith('172.') or ip.startswith('127.')):
                return ip
        except Exception:
            pass

    # 2. Try ioctl on active network interfaces (skipping virtual/bridge/docker adapters)
    try:
        import fcntl
        import struct
        for iface_path in sorted(glob.glob('/sys/class/net/*')):
            iface = os.path.basename(iface_path)
            if iface.startswith(('lo', 'docker', 'br-', 'veth', 'virbr')):
                continue
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                ip = socket.inet_ntoa(fcntl.ioctl(
                    s.fileno(),
                    0x8915,  # SIOCGIFADDR
                    struct.pack('256s', iface[:15].encode('utf-8'))
                )[20:24])
                s.close()
                if ip and not (ip.startswith('127.') or ip.startswith('172.')):
                    return ip
            except Exception:
                pass
    except Exception:
        pass

    # 3. Hostname resolution
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            candidate = info[4][0]
            if not (candidate.startswith('127.') or candidate.startswith('172.')):
                return candidate
    except Exception:
        pass

    return '127.0.0.1'

def detect_macos_hardware() -> dict:
    """Extracts hardware and OS details natively on macOS (Apple Silicon M1/M2/M3/M4 & Intel Macs)."""
    hostname = socket.gethostname()

    def run_cmd(cmd_list, timeout=4):
        try:
            return subprocess.check_output(cmd_list, stderr=subprocess.DEVNULL, timeout=timeout).decode('utf-8', errors='ignore').strip()
        except Exception:
            return ''

    # 1. Serial number
    serial = ''
    out = run_cmd(['ioreg', '-c', 'IOPlatformExpertDevice', '-d', '2'])
    if out:
        m = re.search(r'"IOPlatformSerialNumber"\s*=\s*"([^"]+)"', out)
        if m and m.group(1).strip():
            serial = m.group(1).strip().upper()
    if not serial:
        out = run_cmd(['system_profiler', 'SPHardwareDataType'])
        if out:
            m = re.search(r'Serial Number.*:\s+([A-Za-z0-9]+)', out)
            if m and m.group(1).strip():
                serial = m.group(1).strip().upper()
    if not serial:
        serial = f"MAC-{hostname}"

    # 2. Model & Asset Type
    hw_model = run_cmd(['sysctl', '-n', 'hw.model'])
    sp = run_cmd(['system_profiler', 'SPHardwareDataType'])
    m_name = ""
    chip = ""
    if sp:
        m1 = re.search(r'Model Name:\s+([^\n\r]+)', sp)
        if m1:
            m_name = m1.group(1).strip()
        m2 = re.search(r'Chip:\s+([^\n\r]+)', sp)
        if m2:
            chip = m2.group(1).strip()
        if not chip:
            m3 = re.search(r'Processor Name:\s+([^\n\r]+)', sp)
            if m3:
                chip = m3.group(1).strip()

    lower_ident = (hw_model + " " + m_name).lower()
    if 'book' in lower_ident or 'air' in lower_ident or ('pro' in lower_ident and 'mac' in lower_ident and not any(k in lower_ident for k in ['imac', 'mini', 'studio'])):
        asset_type = 'Laptop'
    elif any(k in lower_ident for k in ['mini', 'studio', 'imac', 'macpro', 'desktop']):
        asset_type = 'Desktop'
    elif 'xserve' in lower_ident or 'server' in lower_ident:
        asset_type = 'Server'
    else:
        asset_type = 'Laptop'

    display_model = m_name or hw_model or "Apple Mac"
    if hw_model and hw_model.lower() not in display_model.lower():
        display_model = f"{display_model} ({hw_model})"

    # 3. CPU
    brand = run_cmd(['sysctl', '-n', 'machdep.cpu.brand_string'])
    if not brand and chip:
        brand = chip
    if not brand:
        brand = "Apple Silicon Processor"

    core_breakdown = ""
    if sp:
        m = re.search(r'Total Number of Cores:\s+([^\n\r]+)', sp)
        if m:
            core_breakdown = m.group(1).strip()
    ncpu = run_cmd(['sysctl', '-n', 'hw.ncpu']) or run_cmd(['sysctl', '-n', 'hw.physicalcpu'])
    if core_breakdown:
        cpu_disp = f"{brand} ({core_breakdown} Cores)" if 'core' not in core_breakdown.lower() else f"{brand} ({core_breakdown})"
    elif ncpu:
        cpu_disp = f"{brand} ({ncpu} Cores)"
    else:
        cpu_disp = brand

    # 4. RAM
    memsize_str = run_cmd(['sysctl', '-n', 'hw.memsize'])
    gb_norm = 16
    if memsize_str and memsize_str.isdigit():
        gb_raw = int(memsize_str) / (1024 ** 3)
        gb_norm = round(gb_raw)

    is_apple_silicon = any(k in brand.lower() for k in ['apple', 'm1', 'm2', 'm3', 'm4'])
    ram_vendor = "Apple Inc." if is_apple_silicon else "Crucial / Micron / Apple"
    ram_serial = "On-Die Unified Memory" if is_apple_silicon else "N/A"
    mem_type = "Unified Memory" if is_apple_silicon else "RAM"

    # 5. Storage
    du = run_cmd(['diskutil', 'info', '/'])
    size_str = "512 GB"
    device_name = "Apple SSD"
    storage_serial = "N/A"
    if du:
        m_sz = re.search(r'Disk Size:\s+([^\n\r]+)', du)
        if m_sz:
            size_clean = m_sz.group(1).split('(')[0].strip()
            if size_clean:
                size_str = size_clean
        m_name = re.search(r'Device / Media Name:\s+([^\n\r]+)', du)
        if m_name:
            device_name = m_name.group(1).strip()

    sp_nvme = run_cmd(['system_profiler', 'SPNVMeDataType'])
    if sp_nvme:
        m_mod = re.search(r'Device Model:\s+([^\n\r]+)', sp_nvme)
        if m_mod:
            device_name = m_mod.group(1).strip()
        m_ser = re.search(r'Serial Number:\s+([^\n\r]+)', sp_nvme)
        if m_ser:
            storage_serial = m_ser.group(1).strip()

    # 6. OS Name
    sw_name = run_cmd(['sw_vers', '-productName']) or "macOS"
    sw_ver = run_cmd(['sw_vers', '-productVersion']) or ""
    sw_build = run_cmd(['sw_vers', '-buildVersion']) or ""
    codenames = {'15': 'Sequoia', '14': 'Sonoma', '13': 'Ventura', '12': 'Monterey', '11': 'Big Sur', '10.15': 'Catalina', '10.14': 'Mojave'}
    code = codenames.get(sw_ver.split('.')[0] if sw_ver else '', '')
    os_name = f"{sw_name} {code} {sw_ver}".strip()
    if sw_build:
        os_name += f" (Build {sw_build})"

    # 7. Network (IP & MAC)
    route_out = run_cmd(['route', '-n', 'get', 'default'])
    iface = "en0"
    if route_out:
        m = re.search(r'interface:\s+([^\s]+)', route_out)
        if m:
            iface = m.group(1).strip()
    ip_addr = run_cmd(['ipconfig', 'getifaddr', iface]) or get_primary_ip()
    mac_addr = ""
    ifconfig_out = run_cmd(['ifconfig', iface])
    if ifconfig_out:
        m = re.search(r'ether\s+([0-9a-fA-F:]{17})', ifconfig_out)
        if m:
            mac_addr = m.group(1).upper()

    # 8. User
    out_user = run_cmd(['stat', '-f', '%Su', '/dev/console'])
    user = out_user if (out_user and out_user not in ('root', 'daemon')) else (os.environ.get('USER') or '')

    motherboard = f"Apple Inc. Logic Board (S/N: {serial})"

    return {
        'asset_type': asset_type,
        'manufacturer': 'Apple Inc.',
        'model': display_model,
        'serial_number': serial,
        'product_code': hw_model,
        'cpu': cpu_disp,
        'cpu_model': brand,
        'ram': f"{gb_norm} GB {mem_type}",
        'ram_vendor': ram_vendor,
        'ram_size': f"{gb_norm} GB",
        'ram_serial': ram_serial,
        'storage': f"{size_str} ({device_name})",
        'storage_vendor': 'Apple',
        'storage_model': device_name,
        'storage_serial': storage_serial,
        'storage_size': size_str,
        'motherboard': motherboard,
        'motherboard_mfg': 'Apple Inc.',
        'motherboard_product': f"{display_model} Logic Board",
        'motherboard_serial': serial,
        'os_name': os_name,
        'hostname': hostname,
        'device_name': hostname,
        'assigned_to': user,
        'ip_address': ip_addr,
        'mac_address': mac_addr,
        'barcode': serial,
        'barcode_format': 'CODE128',
        'source': 'macOS Native Auto-Detection (ioreg, sysctl & system_profiler)'
    }

def get_host_specs():
    """
    Detects hardware specifications of the current host machine (Ubuntu/Linux/macOS).
    Extracts CPU, RAM, disk, DMI manufacturer/model, chassis type, OS, IP, MAC.
    """
    if platform.system().lower() == 'darwin':
        return detect_macos_hardware()

    specs = {
        'asset_type': 'Laptop',
        'manufacturer': '',
        'model': '',
        'serial_number': '',
        'product_code': '',
        'cpu': '',
        'ram': '',
        'storage': '',
        'os_name': '',
        'hostname': socket.gethostname(),
        'ip_address': '',
        'mac_address': '',
        'barcode': '',
        'barcode_format': 'CODE128',
        'source': 'Ubuntu Local System Auto-Detection (/sys/class/dmi & /proc)'
    }

    # 1. DMI Hardware info
    vendor = _read_file('/sys/class/dmi/id/sys_vendor')
    product = _read_file('/sys/class/dmi/id/product_name')
    serial = extract_system_serial()
    sku = _read_file('/sys/class/dmi/id/product_sku')
    chassis = _read_file('/sys/class/dmi/id/chassis_type')

    specs['manufacturer'] = vendor or 'Dell Inc.'
    specs['model'] = product or 'Ubuntu Workstation'
    specs['serial_number'] = serial
    specs['product_code'] = sku or product

    # Chassis to Asset Type
    chassis_desc = CHASSIS_MAP.get(chassis, '')
    if any(k in chassis_desc.lower() for k in ['laptop', 'notebook', 'portable']):
        specs['asset_type'] = 'Laptop'
    elif any(k in chassis_desc.lower() for k in ['desktop', 'tower', 'all-in-one', 'space-saving']):
        specs['asset_type'] = 'Desktop'
    elif any(k in chassis_desc.lower() for k in ['server', 'rack']):
        specs['asset_type'] = 'Server'
    elif 'tablet' in chassis_desc.lower():
        specs['asset_type'] = 'Tablet'

    # 2. CPU
    cpu_model = ''
    core_count = 0
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if 'model name' in line and not cpu_model:
                    cpu_model = line.split(':', 1)[1].strip()
                if line.startswith('processor'):
                    core_count += 1
    except Exception:
        pass

    if cpu_model:
        # Clean redundant spaces
        cpu_clean = re.sub(r'\s+', ' ', cpu_model)
        specs['cpu'] = f"{cpu_clean} ({core_count} Cores)" if core_count > 1 else cpu_clean
    else:
        specs['cpu'] = 'Intel/AMD Multi-core Processor'

    # 3. RAM
    ram_gb = 16
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if 'MemTotal' in line:
                    kb = int(re.search(r'\d+', line).group(0))
                    ram_gb = round(kb / (1024 * 1024))
                    break
    except Exception:
        pass
    
    # Check dmidecode for RAM vendor and serial
    ram_vendor = "Crucial / Micron"
    ram_serial = "N/A"
    try:
        out = subprocess.check_output(['sudo', '-n', 'dmidecode', '-t', '17'], stderr=subprocess.DEVNULL, timeout=5).decode()
        mfg = re.findall(r'Manufacturer:\s+([^\n\r]+)', out)
        sn = re.findall(r'Serial Number:\s+([^\n\r]+)', out)
        if mfg:
            v_list = [m.strip() for m in mfg if 'unknown' not in m.lower() and 'not' not in m.lower()]
            if v_list: ram_vendor = ', '.join(dict.fromkeys(v_list))
        if sn:
            s_list = [s.strip() for s in sn if 'unknown' not in s.lower() and 'not' not in s.lower()]
            if s_list: ram_serial = ', '.join(dict.fromkeys(s_list))
    except Exception:
        pass

    if ram_serial == "N/A":
        try:
            u_out = subprocess.check_output(['udevadm', 'info', '--export-db'], stderr=subprocess.DEVNULL, timeout=5).decode()
            u_serials = []
            u_vendors = []
            for line in u_out.splitlines():
                m_sn = re.search(r'MEMORY_DEVICE_\d+_SERIAL_NUMBER=([^\s]+)', line)
                if m_sn:
                    val = m_sn.group(1).strip()
                    if val and val.lower() not in ['unknown', 'none', 'n/a', 'not specified', '00000000', '0']:
                        u_serials.append(val)
                m_mfg = re.search(r'MEMORY_DEVICE_\d+_(?:MANUFACTURER|MODULE_MANUFACTURER_ID)=([^\s]+)', line)
                if m_mfg:
                    val = m_mfg.group(1).strip()
                    if '0xAD' in val or '80AD' in val:
                        u_vendors.append('SK Hynix')
                    elif '0x2C' in val or '802C' in val:
                        u_vendors.append('Micron')
                    elif '0xCE' in val or 'Samsung' in val:
                        u_vendors.append('Samsung')
                    elif '0x98' in val or 'Kingston' in val:
                        u_vendors.append('Kingston')
            if u_serials:
                ram_serial = ' / '.join(dict.fromkeys(u_serials))
            if u_vendors:
                ram_vendor = ' / '.join(dict.fromkeys(u_vendors))
        except Exception:
            pass

    specs['ram'] = f"{ram_gb} GB RAM"
    specs['ram_vendor'] = ram_vendor
    specs['ram_size'] = f"{ram_gb} GB"
    specs['ram_serial'] = ram_serial

    # Motherboard / Baseboard
    board_vendor = _read_file('/sys/class/dmi/id/board_vendor') or vendor or 'Dell Inc.'
    board_name = _read_file('/sys/class/dmi/id/board_name') or 'Mainboard'
    board_serial = clean_serial(_read_file('/sys/class/dmi/id/board_serial')) or clean_serial(_read_file('/sys/class/dmi/id/product_serial')) or serial or 'N/A'
    bios_ver = _read_file('/sys/class/dmi/id/bios_version')
    board_parts = [p for p in [board_vendor, board_name] if p and p.lower() not in ['to be filled by o.e.m.', 'default string', 'none']]
    motherboard = ' '.join(board_parts) if board_parts else 'Motherboard'
    if bios_ver:
        motherboard += f" (BIOS {bios_ver})"
    if board_serial and board_serial != 'N/A':
        motherboard += f" (S/N: {board_serial})"

    specs['motherboard'] = motherboard
    specs['motherboard_mfg'] = board_vendor
    specs['motherboard_product'] = board_name
    specs['motherboard_serial'] = board_serial
    specs['device_name'] = socket.gethostname()
    specs['hostname'] = socket.gethostname()
    specs['cpu_model'] = cpu_model or specs['cpu']

    # User detection
    user = os.environ.get('SUDO_USER') or os.environ.get('USER') or os.environ.get('LOGNAME') or ''
    if not user or user == 'root':
        try:
            who = subprocess.check_output(['logname'], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            if who and who != 'root': user = who
        except Exception:
            pass
    if not user or user == 'root':
        try:
            homes = [d for d in os.listdir('/home') if os.path.isdir(os.path.join('/home', d)) and not d.startswith('.')]
            if homes: user = homes[0]
        except Exception:
            pass
    specs['assigned_to'] = user or socket.gethostname()

    # 4. Storage (Physical Drive Detection via lsblk)
    disks = []
    first_disk = None
    try:
        out = subprocess.check_output(['lsblk', '-J', '-b', '-d', '-o', 'NAME,SIZE,MODEL,SERIAL,VENDOR,ROTA,TYPE,TRAN'], stderr=subprocess.DEVNULL, timeout=5).decode()
        data = json.loads(out)
        for dev in data.get('blockdevices', []):
            name = dev.get('name', '')
            dtype = dev.get('type', '')
            if dtype != 'disk' or name.startswith(('loop', 'ram', 'sr', 'zd', 'zram', 'dm-')): continue
            size_bytes = int(dev.get('size') or 0)
            if size_bytes < 1000**3: continue
            size_gb = round(size_bytes / (1000**3))
            model = (dev.get('model') or '').strip()
            raw_vendor = (dev.get('vendor') or '').strip()
            vendor = resolve_disk_vendor(raw_vendor, model)
            is_nvme = (dev.get('tran') == 'nvme' or 'nvme' in name.lower())
            is_ssd = (not dev.get('rota', True))
            drive_type = 'NVMe SSD' if is_nvme else ('SSD' if is_ssd else 'HDD')
            display_cap = f"{size_gb} GB" if size_gb < 1000 else f"{round(size_gb/1000, 1)} TB"
            dstr = f"{display_cap} {drive_type}" + (f" ({model})" if model else "")
            disks.append(dstr)
            disk_serial = (dev.get('serial') or '').strip()
            if not disk_serial and is_nvme:
                disk_serial = _read_file(f'/sys/block/{name}/device/serial')
            if not first_disk:
                first_disk = {'vendor': vendor, 'model': model or dstr, 'serial': disk_serial or 'N/A', 'size': display_cap}
    except Exception:
        pass

    if first_disk:
        specs['storage'] = ' + '.join(disks)
        specs['storage_vendor'] = first_disk['vendor']
        specs['storage_model'] = first_disk['model']
        specs['storage_serial'] = first_disk['serial']
        specs['storage_size'] = first_disk['size']
    else:
        specs['storage'] = '512 GB SSD'
        specs['storage_vendor'] = 'Micron / Samsung'
        specs['storage_model'] = 'SSD 512GB'
        specs['storage_serial'] = 'N/A'
        specs['storage_size'] = '512 GB'

    # 5. OS Name
    os_name = ''
    try:
        with open('/etc/os-release', 'r') as f:
            for line in f:
                if line.startswith('PRETTY_NAME='):
                    os_name = line.split('=', 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
    specs['os_name'] = os_name or 'Ubuntu Linux'

    # 6. Network (IP & MAC)
    specs['ip_address'] = get_primary_ip()

    # Primary MAC
    try:
        net_devs = glob.glob('/sys/class/net/*')
        for dev in sorted(net_devs):
            if not os.path.basename(dev).startswith(('lo', 'docker', 'veth', 'br-', 'virbr')):
                mac = _read_file(os.path.join(dev, 'address'))
                if mac and mac != '00:00:00:00:00:00':
                    specs['mac_address'] = mac.upper()
                    break
    except Exception:
        pass

    # Suggest Barcode
    if specs['serial_number']:
        specs['barcode'] = specs['serial_number']
    elif specs['mac_address']:
        specs['barcode'] = specs['mac_address'].replace(':', '')
    else:
        specs['barcode'] = f"UB-{specs['hostname'].upper()}"

    return specs

def decode_dell_service_tag(tag):
    """
    Dell service tag is a 7-character alphanumeric string.
    Express Service Code is the base 36 integer representation.
    """
    clean_tag = tag.strip().upper()
    if re.fullmatch(r'[A-Z0-9]{7}', clean_tag):
        try:
            express_code = int(clean_tag, 36)
            return {
                'is_dell': True,
                'service_tag': clean_tag,
                'express_service_code': str(express_code),
                'manufacturer': 'Dell Inc.'
            }
        except Exception:
            pass
    return None

def lookup_mac_vendor(mac_raw):
    """
    Checks if a string is a MAC address barcode and resolves the OUI vendor.
    """
    clean_mac = re.sub(r'[^A-Fa-f0-9]', '', mac_raw).upper()
    if len(clean_mac) == 12:
        formatted = ':'.join(clean_mac[i:i+2] for i in range(0, 12, 2))
        prefix = formatted[:8]
        if prefix in OUI_MAP:
            vendor, dev_type = OUI_MAP[prefix]
            return {
                'is_mac': True,
                'mac_address': formatted,
                'manufacturer': vendor,
                'suggested_type': dev_type
            }
    return None

def match_catalog(text):
    """
    Searches our built-in hardware dictionary for matching computer/device models.
    """
    if not text:
        return None
    lower = text.lower()
    for item in HARDWARE_CATALOG:
        for kw in item['keywords']:
            if kw in lower:
                return item
    return None

def query_open_upc(code):
    """
    Queries open GTIN/UPC registry with short timeout for commercial barcodes.
    """
    if not re.fullmatch(r'\d{8,14}', code):
        return None
    url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={code}"
    req = urllib.request.Request(url, headers={'User-Agent': 'ITAssetManager/2.0'})
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                items = data.get('items', [])
                if items:
                    it = items[0]
                    return {
                        'title': it.get('title', ''),
                        'brand': it.get('brand', ''),
                        'model': it.get('model', ''),
                        'description': it.get('description', '')
                    }
    except Exception:
        pass
    return None

def enrich_barcode_details(raw_barcode, fmt='', manual_model=''):
    """
    Comprehensive auto-enrichment engine.
    Analyzes scanned barcode, serial number, GS1 standards, Dell tags, MACs,
    hardware catalog, and online registries to fill device specifications automatically.
    """
    raw = (raw_barcode or '').strip()
    fmt = (fmt or '').strip()
    out = {
        'barcode': raw,
        'barcode_format': fmt,
        'asset_type': 'Laptop',
        'manufacturer': '',
        'model': manual_model,
        'serial_number': '',
        'product_code': '',
        'cpu': '',
        'ram': '',
        'storage': '',
        'notes': '',
        'source': 'Barcode Auto-Discovery Engine'
    }

    if not raw:
        return out

    # 1. GS1 Application Identifiers: (01) GTIN and (21) serial
    m_gtin = re.search(r'\(01\)(\d{14})', raw)
    if m_gtin:
        out['product_code'] = m_gtin.group(1)
    m_ser = re.search(r'\(21\)([A-Za-z0-9_-]{1,30})', raw)
    if m_ser:
        out['serial_number'] = m_ser.group(1)

    # If raw is a plain serial / tag
    if not out['serial_number'] and re.fullmatch(r'[A-Za-z0-9_-]{5,40}', raw):
        out['serial_number'] = raw

    # 2. Check Dell Service Tag
    dell_info = decode_dell_service_tag(out['serial_number'] or raw)
    if dell_info:
        out['manufacturer'] = dell_info['manufacturer']
        out['serial_number'] = dell_info['service_tag']
        out['product_code'] = f"Dell Express Code: {dell_info['express_service_code']}"
        out['source'] = 'Dell Service Tag Decoder (Calculated Express Service Code)'

    # 3. Check Lenovo Serial / MTM format (e.g. 20W0..., 21AH..., PF2...)
    clean_raw = raw.upper()
    if re.match(r'^(PF[0-9A-Z]{6}|1S[0-9A-Z]{8,})', clean_raw) or 'THINKPAD' in clean_raw:
        out['manufacturer'] = 'Lenovo'
        out['source'] = 'Lenovo ThinkPad Serial Pattern'

    # 4. Check HP Serial format (e.g. CND..., 5CD..., CZ...)
    if re.match(r'^(CND|5CD|5CG|CZC|CNU|2CE)[0-9A-Z]{7}', clean_raw):
        out['manufacturer'] = 'HP'
        out['source'] = 'HP Enterprise Serial Pattern'

    # 5. Check MAC address
    mac_info = lookup_mac_vendor(raw)
    if mac_info:
        out['manufacturer'] = mac_info['manufacturer']
        out['notes'] = f"Scanned MAC: {mac_info['mac_address']}"
        out['source'] = f"IEEE OUI MAC Lookup ({mac_info['manufacturer']})"

    # 6. Catalog lookup (check model, raw barcode, or notes)
    lookup_str = f"{raw} {manual_model} {out['model']} {out['manufacturer']}"
    cat = match_catalog(lookup_str)
    if cat:
        if not out['manufacturer']:
            out['manufacturer'] = cat['manufacturer']
        if not out['model'] or out['model'] == manual_model:
            out['model'] = cat['model']
        out['asset_type'] = cat['asset_type']
        out['cpu'] = cat['cpu']
        out['ram'] = cat['ram']
        out['storage'] = cat['storage']
        out['source'] += f" + Hardware Catalog Match ({cat['model']})"

    # 7. Online GTIN/UPC lookup if 8-14 numeric digits
    if re.fullmatch(r'\d{8,14}', raw):
        out['product_code'] = raw
        upc_data = query_open_upc(raw)
        if upc_data:
            if upc_data.get('brand'):
                out['manufacturer'] = upc_data['brand']
            if upc_data.get('title'):
                out['model'] = upc_data['title'][:100]
                out['notes'] = f"Product: {upc_data['title']}"
            out['source'] += " + Global UPC Database Lookup"

    return out
