#!/usr/bin/env python3
"""
IT Asset Manager — Automated Hardware Discovery Agent
Auto-detects Motherboard, Processor, RAM, Storage (SSD/NVMe), Serial Number,
Device Name (Hostname), and Logged-in User Name, and stores directly in the IT Asset Manager database.
Supports Ubuntu / Debian / RHEL / Linux, Windows, and macOS.
"""

import sys
import os
import json
import socket
import argparse
import urllib.request
import urllib.error
import re
import glob
import subprocess
import platform

def read_file(path):
    try:
        with open(path, 'r', errors='ignore') as f:
            return f.read().strip()
    except Exception:
        return ''

def normalize_ram(gb_raw):
    # Standard commercial RAM module capacities
    for standard in [2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256]:
        if abs(gb_raw - standard) <= 1.2:
            return standard
    return gb_raw

def get_real_user():
    """Detects the real desktop/laptop logged-in user, avoiding 'root' when run via sudo."""
    user = os.environ.get('SUDO_USER') or os.environ.get('USER') or os.environ.get('LOGNAME') or ''
    if not user or user == 'root':
        try:
            who = subprocess.check_output(['logname'], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
            if who and who != 'root':
                user = who
        except Exception:
            pass
    if not user or user == 'root':
        try:
            # Active GUI session user on Linux
            out = subprocess.check_output(['who'], stderr=subprocess.DEVNULL, timeout=2).decode()
            for line in out.strip().splitlines():
                u = line.split()[0]
                if u and u != 'root':
                    user = u
                    break
        except Exception:
            pass
    if not user or user == 'root':
        try:
            # First non-root home folder
            homes = [d for d in os.listdir('/home') if os.path.isdir(os.path.join('/home', d)) and not d.startswith('.')]
            if homes:
                user = homes[0]
        except Exception:
            pass
    return user or socket.gethostname()

def resolve_disk_vendor(vendor, model):
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

def get_linux_storage():
    """Detects physical disk drives, vendors, models, serial numbers, and capacities."""
    first_disk = None
    disks = []
    try:
        out = subprocess.check_output(
            ['lsblk', '-J', '-b', '-d', '-o', 'NAME,SIZE,MODEL,SERIAL,VENDOR,ROTA,TYPE,TRAN'],
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode()
        data = json.loads(out)
        for dev in data.get('blockdevices', []):
            name = dev.get('name', '')
            dtype = dev.get('type', '')
            if dtype != 'disk' or name.startswith(('loop', 'ram', 'sr', 'zd', 'zram', 'dm-')):
                continue
            size_bytes = int(dev.get('size') or 0)
            if size_bytes < 1000**3:
                continue
            size_gb = round(size_bytes / (1000**3))
            model = (dev.get('model') or '').strip()
            serial = (dev.get('serial') or '').strip()
            raw_vendor = (dev.get('vendor') or '').strip()
            vendor = resolve_disk_vendor(raw_vendor, model)
            
            is_nvme = (dev.get('tran') == 'nvme' or 'nvme' in name.lower())
            is_ssd = (not dev.get('rota', True))
            drive_type = 'NVMe SSD' if is_nvme else ('SSD' if is_ssd else 'HDD')
            display_cap = f"{size_gb} GB" if size_gb < 1000 else f"{round(size_gb/1000, 1)} TB"
            
            disp = f"{display_cap} {drive_type}" + (f" ({model})" if model else "")
            disks.append(disp)
            if not first_disk:
                first_disk = {
                    'vendor': vendor,
                    'model': model or disp,
                    'serial': serial or 'N/A',
                    'size': display_cap
                }
    except Exception:
        pass

    if not first_disk:
        first_disk = {'vendor': 'Micron / Samsung', 'model': '512 GB NVMe SSD', 'serial': 'N/A', 'size': '512 GB'}
    
    first_disk['display'] = ' + '.join(disks) if disks else '512 GB SSD'
    return first_disk

def get_linux_motherboard():
    """Reads motherboard vendor, product model, board serial, and BIOS version."""
    vendor = read_file('/sys/class/dmi/id/board_vendor')
    name = read_file('/sys/class/dmi/id/board_name')
    version = read_file('/sys/class/dmi/id/board_version')
    serial = read_file('/sys/class/dmi/id/board_serial')
    bios_ver = read_file('/sys/class/dmi/id/bios_version')

    if not vendor or not name or not serial:
        for cmd in [['dmidecode', '-t', '2'], ['sudo', '-n', 'dmidecode', '-t', '2']]:
            try:
                out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2).decode()
                m_v = re.search(r'Manufacturer:\s+(.+)', out)
                m_p = re.search(r'Product Name:\s+(.+)', out)
                m_s = re.search(r'Serial Number:\s+(.+)', out)
                if m_v and not vendor: vendor = m_v.group(1).strip()
                if m_p and not name: name = m_p.group(1).strip()
                if m_s and not serial: serial = m_s.group(1).strip()
                if vendor and name: break
            except Exception:
                pass

    if not serial or serial.lower() in ['to be filled by o.e.m.', 'default string', 'none']:
        serial = read_file('/sys/class/dmi/id/product_serial') or 'N/A'

    vendor = vendor or 'Dell Inc.'
    name = name or 'Motherboard'
    disp = f"{vendor} {name}"
    if bios_ver: disp += f" (BIOS {bios_ver})"
    if serial and serial != 'N/A': disp += f" (S/N: {serial})"

    return {
        'mfg': vendor,
        'product': name,
        'serial': serial,
        'display': disp
    }

def get_linux_cpu():
    """Detects CPU model name, physical cores, and logical threads."""
    cpu_name = ''
    threads = 0
    cores = 0
    try:
        with open('/proc/cpuinfo') as f:
            for line in f:
                if 'model name' in line and not cpu_name:
                    cpu_name = line.split(':', 1)[1].strip()
                if line.startswith('processor'):
                    threads += 1
                if 'cpu cores' in line and not cores:
                    m = re.search(r'\d+', line)
                    if m: cores = int(m.group(0))
    except Exception:
        pass

    if not cpu_name:
        try:
            out = subprocess.check_output(['lscpu'], stderr=subprocess.DEVNULL, timeout=3).decode()
            for line in out.splitlines():
                if 'Model name:' in line:
                    cpu_name = line.split(':', 1)[1].strip()
                    break
        except Exception:
            pass

    cpu_name = re.sub(r'\s+', ' ', cpu_name or 'Multi-Core Processor')
    details = []
    if cores: details.append(f"{cores} Cores")
    if threads and threads != cores: details.append(f"{threads} Threads")
    elif threads and not cores: details.append(f"{threads} Cores")
    
    disp = f"{cpu_name} ({', '.join(details)})" if details else cpu_name
    return {
        'model': cpu_name,
        'display': disp
    }

def get_linux_ram():
    """Detects total memory capacity, module vendors, and serial numbers."""
    kb = 0
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if 'MemTotal' in line:
                    kb = int(re.search(r'\d+', line).group(0))
                    break
    except Exception:
        pass

    gb_raw = (kb / (1024 * 1024)) if kb else 16
    gb_norm = normalize_ram(round(gb_raw, 1))

    vendors = []
    serials = []
    sizes = []
    types = set()
    speeds = []

    for cmd in [['dmidecode', '-t', '17'], ['sudo', '-n', 'dmidecode', '-t', '17']]:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2).decode()
            if 'Memory Device' in out:
                for block in out.split('Memory Device'):
                    sz_m = re.search(r'Size:\s+(\d+\s*(?:GB|MB))', block)
                    if not sz_m or 'no module' in block.lower():
                        continue
                    sizes.append(sz_m.group(1).strip())
                    
                    mfg_m = re.search(r'Manufacturer:\s+([^\n\r]+)', block)
                    if mfg_m:
                        v = mfg_m.group(1).strip()
                        if v and 'unknown' not in v.lower() and 'not' not in v.lower():
                            vendors.append(v)
                            
                    sn_m = re.search(r'Serial Number:\s+([^\n\r]+)', block)
                    if sn_m:
                        s = sn_m.group(1).strip()
                        if s and 'unknown' not in s.lower() and 'not' not in s.lower():
                            serials.append(s)
                types = set(re.findall(r'Type:\s+(DDR\d|LPDDR\d)', out))
                speeds = re.findall(r'Speed:\s+(\d+)\s+MT/s', out)
                break
        except Exception:
            pass

    # Fallback to udevadm info --export-db if dmidecode is unavailable (non-root access)
    if not serials:
        try:
            u_out = subprocess.check_output(['udevadm', 'info', '--export-db'], stderr=subprocess.DEVNULL, timeout=4).decode()
            for line in u_out.splitlines():
                m_sn = re.search(r'MEMORY_DEVICE_\d+_SERIAL_NUMBER=([^\s]+)', line)
                if m_sn:
                    val = m_sn.group(1).strip()
                    if val and val.lower() not in ['unknown', 'none', 'n/a', 'not specified', '00000000', '0']:
                        serials.append(val)
                m_mfg = re.search(r'MEMORY_DEVICE_\d+_(?:MANUFACTURER|MODULE_MANUFACTURER_ID)=([^\s]+)', line)
                if m_mfg:
                    val = m_mfg.group(1).strip()
                    if '0xAD' in val or '80AD' in val:
                        vendors.append('SK Hynix')
                    elif '0x2C' in val or '802C' in val:
                        vendors.append('Micron')
                    elif '0xCE' in val or 'Samsung' in val:
                        vendors.append('Samsung')
                    elif '0x98' in val or 'Kingston' in val:
                        vendors.append('Kingston')
                m_type = re.search(r'MEMORY_DEVICE_\d+_TYPE=([^\s]+)', line)
                if m_type:
                    types.add(m_type.group(1).strip())
                m_sz = re.search(r'MEMORY_DEVICE_\d+_SIZE=(\d+)', line)
                if m_sz:
                    bytes_val = int(m_sz.group(1))
                    gb = round(bytes_val / (1024**3))
                    if gb > 0:
                        sizes.append(f'{gb} GB')
        except Exception:
            pass

    r_vendor = ' / '.join(dict.fromkeys(vendors)) if vendors else 'Micron / Samsung'
    r_serial = ' / '.join(dict.fromkeys(serials)) if serials else 'N/A'
    r_size = f"{gb_norm} GB"

    type_info = ''
    if types:
        type_str = list(types)[0]
        sp_str = f"-{speeds[0]}" if speeds else ""
        type_info = f" {type_str}{sp_str}"

    disp = f"{gb_norm} GB{type_info} RAM"
    return {
        'vendor': r_vendor,
        'size': r_size,
        'serial': r_serial,
        'display': disp
    }

def collect_linux_specs():
    hostname = socket.gethostname()
    user = get_real_user()
    
    # Serial number
    INVALID_SERIALS = {
        '', 'none', 'to be filled by o.e.m.', 'default string', 'system serial number',
        'chassis serial number', 'type2 - board serial number', '00000000', '123456789',
        'not specified', 'null', 'n/a', 'unknown', 'system manufacturer'
    }
    def _clean(val):
        if not val: return ''
        v = str(val).strip()
        return '' if v.lower() in INVALID_SERIALS else v

    # 1. Product serial
    serial = _clean(read_file('/sys/class/dmi/id/product_serial'))
    
    # 2. Chassis serial
    if not serial:
        serial = _clean(read_file('/sys/class/dmi/id/chassis_serial'))

    # 3. Board serial (Dell format: /3BZL6Q3/CNCMC001C6087C/)
    if not serial:
        b_sn = read_file('/sys/class/dmi/id/board_serial')
        if b_sn:
            m_dell = re.search(r'/([A-Za-z0-9]{7})/', b_sn)
            if m_dell and _clean(m_dell.group(1)):
                serial = m_dell.group(1).upper()
            else:
                serial = _clean(b_sn)

    # 4. systemd-hostnamed D-Bus interface (works unprivileged on Ubuntu / modern Linux)
    if not serial:
        try:
            out = subprocess.check_output(
                ['busctl', '--timeout=5', 'call', 'org.freedesktop.hostname1', '/org/freedesktop/hostname1', 'org.freedesktop.hostname1', 'GetHardwareSerial'],
                stderr=subprocess.DEVNULL, timeout=6
            ).decode()
            m = re.search(r's\s+"([^"]+)"', out)
            if m:
                serial = _clean(m.group(1))
        except Exception:
            pass

    # 5. dmidecode tools (both unprivileged & sudo)
    if not serial:
        for flag in ['system-serial-number', 'chassis-serial-number', 'baseboard-serial-number']:
            try:
                out = subprocess.check_output(['dmidecode', '-s', flag], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
                if _clean(out):
                    serial = _clean(out)
                    break
            except Exception:
                pass
            try:
                out = subprocess.check_output(['sudo', '-n', 'dmidecode', '-s', flag], stderr=subprocess.DEVNULL, timeout=2).decode().strip()
                if _clean(out):
                    serial = _clean(out)
                    break
            except Exception:
                pass

    # 6. Fallback to machine-id token only if no hardware serial exists
    if not serial:
        m_id = read_file('/etc/machine-id')
        serial = f"UB-{m_id[:8].upper()}" if m_id else f"HOST-{hostname.upper()}"

    # Chassis type
    asset_type = 'Laptop'
    chassis = read_file('/sys/class/dmi/id/chassis_type')
    if chassis in ['8', '9', '10', '11', '14', '30', '31', '32']:
        asset_type = 'Laptop'
    elif chassis in ['3', '4', '6', '7', '13', '15', '24']:
        asset_type = 'Desktop'
    elif chassis in ['17', '23', '28']:
        asset_type = 'Server'

    # OS Name
    os_name = 'Ubuntu Linux'
    try:
        with open('/etc/os-release') as f:
            for line in f:
                if line.startswith('PRETTY_NAME='):
                    os_name = line.split('=', 1)[1].strip().strip('"')
                    break
    except Exception:
        pass

    # Network IP & MAC
    ip_addr = '127.0.0.1'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip_addr = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    mac_addr = ''
    try:
        for dev in sorted(glob.glob('/sys/class/net/*')):
            if not os.path.basename(dev).startswith(('lo', 'docker', 'veth', 'br-', 'virbr')):
                mac = read_file(os.path.join(dev, 'address'))
                if mac and mac != '00:00:00:00:00:00':
                    mac_addr = mac.upper()
                    break
    except Exception:
        pass

    mfg = read_file('/sys/class/dmi/id/sys_vendor') or 'Dell Inc.'
    model = read_file('/sys/class/dmi/id/product_name') or hostname
    sku = read_file('/sys/class/dmi/id/product_sku') or ''
    
    mb_info = get_linux_motherboard()
    cpu_info = get_linux_cpu()
    ram_info = get_linux_ram()
    disk_info = get_linux_storage()

    notes = f"Auto-enrolled on {hostname} | MB: {mb_info['mfg']} {mb_info['product']} (S/N: {mb_info['serial']}) | Disk: {disk_info['display']} | RAM: {ram_info['display']} | User: {user}"

    return {
        'asset_type': asset_type,
        'manufacturer': mfg,
        'model': model,
        'serial_number': serial,
        'barcode': serial,
        'barcode_format': 'CODE128',
        'product_code': sku,
        'hostname': hostname,
        'device_name': hostname,
        'cpu_model': cpu_info['model'],
        'cpu': cpu_info['display'],
        'ram_vendor': ram_info['vendor'],
        'ram_size': ram_info['size'],
        'ram_serial': ram_info['serial'],
        'ram': ram_info['display'],
        'storage_vendor': disk_info['vendor'],
        'storage_model': disk_info['model'],
        'storage_serial': disk_info['serial'],
        'storage_size': disk_info['size'],
        'storage': disk_info['display'],
        'motherboard_mfg': mb_info['mfg'],
        'motherboard_product': mb_info['product'],
        'motherboard_serial': mb_info['serial'],
        'motherboard': mb_info['display'],
        'os_name': os_name,
        'assigned_to': user,
        'ip_address': ip_addr,
        'mac_address': mac_addr,
        'status': 'Assigned' if user and user != 'root' else 'Available',
        'department': 'IT',
        'location': 'Office',
        'notes': notes
    }

def collect_windows_specs():
    """Hardware extraction for Windows laptops and desktops using PowerShell / WMI."""
    hostname = socket.gethostname()
    user = os.environ.get('USERNAME') or socket.gethostname()
    
    def run_ps(cmd):
        try:
            return subprocess.check_output(['powershell', '-Command', cmd], stderr=subprocess.DEVNULL, timeout=5).decode().strip()
        except Exception:
            return ''

    serial = run_ps("(Get-CimInstance Win32_BIOS).SerialNumber") or f"WIN-{hostname}"
    mfg = run_ps("(Get-CimInstance Win32_ComputerSystem).Manufacturer") or "PC"
    model = run_ps("(Get-CimInstance Win32_ComputerSystem).Model") or hostname
    board_mfg = run_ps("(Get-CimInstance Win32_BaseBoard).Manufacturer") or "OEM"
    board_prod = run_ps("(Get-CimInstance Win32_BaseBoard).Product") or "Mainboard"
    board_serial = run_ps("(Get-CimInstance Win32_BaseBoard).SerialNumber") or "N/A"
    bios_ver = run_ps("(Get-CimInstance Win32_BIOS).SMBIOSBIOSVersion")

    motherboard = f"{board_mfg} {board_prod}".strip()
    if bios_ver: motherboard += f" (BIOS {bios_ver})"
    if board_serial and board_serial != 'N/A': motherboard += f" (S/N: {board_serial})"

    cpu_model = run_ps("(Get-CimInstance Win32_Processor).Name") or "Processor"
    cores = run_ps("(Get-CimInstance Win32_Processor).NumberOfCores")
    threads = run_ps("(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors")
    cpu_disp = cpu_model
    if cores and threads:
        cpu_disp += f" ({cores} Cores, {threads} Threads)"

    # RAM Details
    ram_raw = run_ps("[math]::Round(((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB))")
    ram_gb = normalize_ram(int(ram_raw)) if ram_raw and ram_raw.isdigit() else 16
    ram_size = f"{ram_gb} GB"
    ram_vendor = run_ps("((Get-CimInstance Win32_PhysicalMemory).Manufacturer | Select-Object -Unique) -join ', '") or "Crucial / Micron"
    ram_serial = run_ps("((Get-CimInstance Win32_PhysicalMemory).SerialNumber | Select-Object -Unique) -join ', '") or "N/A"
    ram_disp = f"{ram_size} RAM"

    # Storage Details
    storage_model = run_ps("((Get-CimInstance Win32_DiskDrive).Model | Select-Object -First 1)") or "SSD"
    storage_serial = run_ps("((Get-CimInstance Win32_DiskDrive).SerialNumber | Select-Object -First 1)") or "N/A"
    storage_size_raw = run_ps("[math]::Round((Get-CimInstance Win32_DiskDrive | Select-Object -First 1).Size / 1GB)")
    storage_size = f"{storage_size_raw} GB" if storage_size_raw and storage_size_raw.isdigit() else "512 GB"
    storage_vendor = run_ps("((Get-CimInstance Win32_DiskDrive).Manufacturer | Select-Object -First 1)") or (storage_model.split()[0] if storage_model.split() else "SSD")
    storage_disp = f"{storage_size} ({storage_model})"

    os_name = run_ps("(Get-CimInstance Win32_OperatingSystem).Caption") or "Windows"
    ip_addr = run_ps("(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike '*Loopback*' -and $_.IPAddress -notlike '169.254*' } | Select-Object -First 1).IPAddress") or "127.0.0.1"

    return {
        'asset_type': 'Laptop',
        'manufacturer': mfg,
        'model': model,
        'serial_number': serial,
        'barcode': serial,
        'barcode_format': 'CODE128',
        'product_code': '',
        'hostname': hostname,
        'device_name': hostname,
        'cpu_model': cpu_model,
        'cpu': cpu_disp,
        'ram_vendor': ram_vendor,
        'ram_size': ram_size,
        'ram_serial': ram_serial,
        'ram': ram_disp,
        'storage_vendor': storage_vendor,
        'storage_model': storage_model,
        'storage_serial': storage_serial,
        'storage_size': storage_size,
        'storage': storage_disp,
        'motherboard_mfg': board_mfg,
        'motherboard_product': board_prod,
        'motherboard_serial': board_serial,
        'motherboard': motherboard,
        'os_name': os_name,
        'assigned_to': user,
        'ip_address': ip_addr,
        'mac_address': '',
        'status': 'Assigned',
        'department': 'IT',
        'location': 'Office',
        'notes': f"Auto-enrolled on {hostname} | MB: {board_mfg} {board_prod} | Disk: {storage_disp} | RAM: {ram_disp} | User: {user}"
    }

MACOS_CODENAMES = {
    '15': 'Sequoia',
    '14': 'Sonoma',
    '13': 'Ventura',
    '12': 'Monterey',
    '11': 'Big Sur',
    '10.16': 'Big Sur',
    '10.15': 'Catalina',
    '10.14': 'Mojave',
    '10.13': 'High Sierra',
    '10.12': 'Sierra',
}

def run_cmd(cmd_list, timeout=5):
    try:
        return subprocess.check_output(cmd_list, stderr=subprocess.DEVNULL, timeout=timeout).decode('utf-8', errors='ignore').strip()
    except Exception:
        return ''

def get_macos_serial():
    # 1. ioreg IOPlatformSerialNumber (most accurate and fast on Apple Silicon & Intel)
    out = run_cmd(['ioreg', '-c', 'IOPlatformExpertDevice', '-d', '2'])
    if out:
        m = re.search(r'"IOPlatformSerialNumber"\s*=\s*"([^"]+)"', out)
        if m and m.group(1).strip():
            return m.group(1).strip().upper()

    # 2. system_profiler SPHardwareDataType
    out = run_cmd(['system_profiler', 'SPHardwareDataType'])
    if out:
        m = re.search(r'Serial Number.*:\s+([A-Za-z0-9]+)', out)
        if m and m.group(1).strip():
            return m.group(1).strip().upper()

    # 3. ioreg -l fallback
    out = run_cmd(['ioreg', '-l'])
    if out:
        m = re.search(r'"IOPlatformSerialNumber"\s*=\s*"([^"]+)"', out)
        if m and m.group(1).strip():
            return m.group(1).strip().upper()
    return ''

def get_macos_model_and_type():
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

    return {
        'model': display_model,
        'model_identifier': hw_model,
        'asset_type': asset_type,
        'chip': chip
    }

def get_macos_cpu():
    brand = run_cmd(['sysctl', '-n', 'machdep.cpu.brand_string'])
    sp = run_cmd(['system_profiler', 'SPHardwareDataType'])
    if not brand and sp:
        m = re.search(r'Chip:\s+([^\n\r]+)', sp)
        if m:
            brand = m.group(1).strip()
        else:
            m2 = re.search(r'Processor Name:\s+([^\n\r]+)', sp)
            if m2:
                brand = m2.group(1).strip()
    if not brand:
        brand = "Apple Silicon Processor"

    core_breakdown = ""
    if sp:
        m = re.search(r'Total Number of Cores:\s+([^\n\r]+)', sp)
        if m:
            core_breakdown = m.group(1).strip()

    ncpu = run_cmd(['sysctl', '-n', 'hw.ncpu']) or run_cmd(['sysctl', '-n', 'hw.physicalcpu'])
    if core_breakdown:
        display = f"{brand} ({core_breakdown} Cores)" if 'core' not in core_breakdown.lower() else f"{brand} ({core_breakdown})"
    elif ncpu:
        display = f"{brand} ({ncpu} Cores)"
    else:
        display = brand

    return {
        'model': brand,
        'display': display
    }

def get_macos_ram():
    memsize_str = run_cmd(['sysctl', '-n', 'hw.memsize'])
    gb_norm = 16
    if memsize_str and memsize_str.isdigit():
        bytes_val = int(memsize_str)
        gb_raw = bytes_val / (1024 ** 3)
        gb_norm = normalize_ram(round(gb_raw, 1))

    cpu_brand = run_cmd(['sysctl', '-n', 'machdep.cpu.brand_string']).lower()
    is_apple_silicon = any(k in cpu_brand for k in ['apple', 'm1', 'm2', 'm3', 'm4'])
    vendor = "Apple Inc." if is_apple_silicon else "Crucial / Micron / Apple"
    serial = "On-Die Unified Memory" if is_apple_silicon else "N/A"
    mem_type = "Unified Memory" if is_apple_silicon else "RAM"

    sp_mem = run_cmd(['system_profiler', 'SPMemoryDataType'])
    if sp_mem:
        m_mfg = re.findall(r'Manufacturer:\s+([^\n\r]+)', sp_mem)
        if m_mfg:
            clean_mfg = [m.strip() for m in m_mfg if 'unknown' not in m.lower() and '0x' not in m.lower()]
            if clean_mfg:
                vendor = ', '.join(dict.fromkeys(clean_mfg))
        m_sn = re.findall(r'Serial Number:\s+([^\n\r]+)', sp_mem)
        if m_sn:
            clean_sn = [s.strip() for s in m_sn if s.strip() and s.strip() != '0x00000000' and 'unknown' not in s.lower()]
            if clean_sn:
                serial = ', '.join(dict.fromkeys(clean_sn))

    return {
        'vendor': vendor,
        'size': f"{gb_norm} GB",
        'serial': serial,
        'display': f"{gb_norm} GB {mem_type}"
    }

def get_macos_storage():
    du = run_cmd(['diskutil', 'info', '/'])
    size_str = "512 GB"
    device_name = "Apple SSD"
    vendor = "Apple"
    serial = "N/A"

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
            serial = m_ser.group(1).strip()

    if 'apple' in device_name.lower():
        vendor = "Apple"
    elif 'samsung' in device_name.lower():
        vendor = "Samsung"
    else:
        vendor = resolve_disk_vendor(device_name, "")

    return {
        'vendor': vendor,
        'model': device_name,
        'serial': serial,
        'size': size_str,
        'display': f"{size_str} ({device_name})"
    }

def get_macos_os():
    name = run_cmd(['sw_vers', '-productName']) or "macOS"
    ver = run_cmd(['sw_vers', '-productVersion']) or ""
    build = run_cmd(['sw_vers', '-buildVersion']) or ""

    codename = ""
    if ver:
        major = ver.split('.')[0]
        codename = MACOS_CODENAMES.get(major, '')
        if not codename and major == '10':
            two_parts = '.'.join(ver.split('.')[:2])
            codename = MACOS_CODENAMES.get(two_parts, '')

    res = name
    if codename:
        res += f" {codename}"
    if ver:
        res += f" {ver}"
    if build:
        res += f" (Build {build})"
    return res

def get_macos_network():
    route_out = run_cmd(['route', '-n', 'get', 'default'])
    iface = "en0"
    if route_out:
        m = re.search(r'interface:\s+([^\s]+)', route_out)
        if m:
            iface = m.group(1).strip()

    ip_addr = run_cmd(['ipconfig', 'getifaddr', iface])
    if not ip_addr:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_addr = s.getsockname()[0]
            s.close()
        except Exception:
            ip_addr = "127.0.0.1"

    mac_addr = ""
    ifconfig_out = run_cmd(['ifconfig', iface])
    if ifconfig_out:
        m = re.search(r'ether\s+([0-9a-fA-F:]{17})', ifconfig_out)
        if m:
            mac_addr = m.group(1).upper()

    return ip_addr, mac_addr

def get_macos_user():
    out = run_cmd(['stat', '-f', '%Su', '/dev/console'])
    if out and out not in ('root', 'daemon', ''):
        return out
    out2 = run_cmd(['scutil', '--get', 'ConsoleUser'])
    if out2 and out2 not in ('root', 'daemon', ''):
        return out2
    user = os.environ.get('SUDO_USER') or os.environ.get('USER') or os.environ.get('LOGNAME') or ''
    if user and user != 'root':
        return user
    return socket.gethostname()

def collect_macos_specs():
    """Hardware and OS extraction for macOS (Apple Silicon M1/M2/M3/M4 & Intel Macs)."""
    hostname = socket.gethostname()
    user = get_macos_user()
    serial = get_macos_serial() or f"MAC-{hostname}"
    model_info = get_macos_model_and_type()
    cpu_info = get_macos_cpu()
    ram_info = get_macos_ram()
    storage_info = get_macos_storage()
    os_name = get_macos_os()
    ip_addr, mac_addr = get_macos_network()

    mb_mfg = "Apple Inc."
    mb_product = f"{model_info['model']} Logic Board"
    mb_serial = serial
    mb_display = f"Apple Inc. Logic Board (S/N: {serial})"

    notes = (
        f"Auto-enrolled on {hostname} | Model: {model_info['model']} | "
        f"CPU: {cpu_info['display']} | RAM: {ram_info['display']} | "
        f"Storage: {storage_info['display']} | OS: {os_name} | User: {user}"
    )

    return {
        'asset_type': model_info['asset_type'],
        'manufacturer': 'Apple Inc.',
        'model': model_info['model'],
        'serial_number': serial,
        'barcode': serial,
        'barcode_format': 'CODE128',
        'product_code': model_info['model_identifier'],
        'hostname': hostname,
        'device_name': hostname,
        'cpu_model': cpu_info['model'],
        'cpu': cpu_info['display'],
        'ram_vendor': ram_info['vendor'],
        'ram_size': ram_info['size'],
        'ram_serial': ram_info['serial'],
        'ram': ram_info['display'],
        'storage_vendor': storage_info['vendor'],
        'storage_model': storage_info['model'],
        'storage_serial': storage_info['serial'],
        'storage_size': storage_info['size'],
        'storage': storage_info['display'],
        'motherboard_mfg': mb_mfg,
        'motherboard_product': mb_product,
        'motherboard_serial': mb_serial,
        'motherboard': mb_display,
        'os_name': os_name,
        'assigned_to': user,
        'ip_address': ip_addr,
        'mac_address': mac_addr,
        'status': 'Assigned' if user and user != 'root' else 'Available',
        'department': 'IT',
        'location': 'Office',
        'notes': notes
    }

def collect_specs():
    system = platform.system().lower()
    if system == 'windows':
        return collect_windows_specs()
    elif system == 'darwin':
        return collect_macos_specs()
    else:
        return collect_linux_specs()

def main():
    parser = argparse.ArgumentParser(description="IT Asset Manager Automated Hardware Discovery Agent")
    parser.add_argument('--server', default="http://127.0.0.1:5000", help="URL of IT Asset Manager server")
    parser.add_argument('--key', default="", help="ASSET_API_KEY for authorization")
    parser.add_argument('--barcode', help="Custom barcode/sticker value (defaults to detected serial number)")
    parser.add_argument('--assigned', help="Employee name asset is assigned to")
    parser.add_argument('--department', help="Department name")
    parser.add_argument('--location', help="Location or office name")
    parser.add_argument('--status', choices=['Available', 'Assigned', 'In Repair', 'Retired'])
    parser.add_argument('--dry-run', action='store_true', help="Print detected specs without sending")

    args = parser.parse_args()

    print("🔍 Discovering full system hardware specifications...")
    data = collect_specs()

    if args.barcode:
        data['barcode'] = args.barcode
        data['serial_number'] = args.barcode
    if args.assigned:
        data['assigned_to'] = args.assigned
        data['status'] = 'Assigned'
    if args.department:
        data['department'] = args.department
    if args.location:
        data['location'] = args.location
    if args.status:
        data['status'] = args.status

    print("\n================ DETECTED DEVICE HARDWARE TELEMETRY ================")
    print(f"  Hostname                 : {data.get('hostname') or data.get('device_name', '')}")
    print(f"  CPU Model                : {data.get('cpu_model') or data.get('cpu', '')}")
    print(f"  RAM Vendor               : {data.get('ram_vendor', '')}")
    print(f"  RAM Size                 : {data.get('ram_size', '')}")
    print(f"  RAM Serial No.           : {data.get('ram_serial', '')}")
    print(f"  Storage Vendor           : {data.get('storage_vendor', '')}")
    print(f"  Storage Model            : {data.get('storage_model', '')}")
    print(f"  Storage Serial No.       : {data.get('storage_serial', '')}")
    print(f"  Storage Size             : {data.get('storage_size', '')}")
    print(f"  Motherboard Manufacturer : {data.get('motherboard_mfg', '')}")
    print(f"  Motherboard Product      : {data.get('motherboard_product', '')}")
    print(f"  Motherboard Serial No.   : {data.get('motherboard_serial', '')}")
    print(f"  IP Address               : {data.get('ip_address', '')}")
    print(f"  Logged-in User           : {data.get('assigned_to', '')}")
    print(f"  Serial / Service Tag     : {data.get('serial_number', '')}")
    print("===================================================================\n")

    if args.dry_run:
        print("Dry run complete. No network request sent.")
        return

    url = f"{args.server.rstrip('/')}/api/autodiscover"
    req_data = json.dumps(data).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'ITAssetManagerAgent/2.2'
    }
    if args.key:
        headers['X-Asset-Key'] = args.key

    req = urllib.request.Request(url, data=req_data, headers=headers)

    try:
        with urllib.request.urlopen(req) as resp:
            res_json = json.loads(resp.read().decode())
            action = res_json.get('action', 'registered')
            asset_id = res_json.get('id', '')
            print(f"✅ Success! Asset #{asset_id} ({data.get('manufacturer')} {data.get('model')}) has been {action} in the inventory database.")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode()
        try:
            err_msg = json.loads(err_msg).get('error', err_msg)
        except Exception:
            pass
        print(f"❌ Failed to register asset ({e.code}): {err_msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Connection error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
