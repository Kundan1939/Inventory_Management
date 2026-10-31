import base64
import hmac
import io
import logging
import os
import secrets
import urllib.parse
from datetime import UTC, datetime, timedelta
from functools import wraps
import ipaddress
import numpy as np
import pymysql
import pymysql.cursors
from pymysql.err import IntegrityError as MySqlIntegrityError
from pymysql.err import OperationalError as MySqlOperationalError
import xlsxwriter
import zxingcpp
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    send_file,
    send_from_directory,
    session,
)
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

logger = logging.getLogger(__name__)

DB_INTEGRITY_ERRORS = (MySqlIntegrityError,)

import ai_engine as ai
import hardware_detector as hd

BASE = os.path.dirname(os.path.abspath(__file__))

# OCR engine instance for server-side label & barcode processing
ocr_engine = None

def get_ocr_engine():
    global ocr_engine
    if ocr_engine is None:
        ocr_engine = RapidOCR()
    return ocr_engine

# Load .env if present and environment variable not already set
env_path = os.path.join(BASE, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit for high-res phone camera photos
app.secret_key = os.getenv('SECRET_KEY') or os.getenv('FLASK_SECRET_KEY') or 'kundan_secure_prod_session_key_9f8c6d4e2b0a1f7e'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

def get_admin_credentials():
    username = os.getenv('ADMIN_USERNAME') or os.getenv('ADMIN_USER') or 'admin'
    password = os.getenv('ADMIN_PASSWORD') or 'Kundan@@1231'
    return username.strip(), password.strip()

def verify_admin_login(username, password) -> bool:
    admin_user, admin_pass = get_admin_credentials()
    if not username or not password:
        return False
    user_ok = secrets.compare_digest(username.strip().lower(), admin_user.lower())
    pass_ok = secrets.compare_digest(password.strip(), admin_pass)
    return user_ok and pass_ok

def is_admin_authenticated() -> bool:
    return session.get('authenticated') is True

def is_local_ip(ip_str: str) -> bool:
    """Checks whether an IP or hostname belongs to local, private, or loopback networks."""
    if not ip_str:
        return False
    host_only = ip_str.split(':')[0].strip().strip('[]').lower()
    if host_only in ('localhost', '127.0.0.1', '::1', '0.0.0.0', 'testserver'):
        return True
    try:
        ip = ipaddress.ip_address(host_only)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        # Check for standard local domain suffixes
        if host_only.endswith(('.local', '.lan', '.internal', '.home', '.corp')):
            return True
        return False

def is_public_ip(ip_str: str) -> bool:
    """Checks whether a string is a publicly routable or external IP address."""
    if not ip_str:
        return False
    host_only = ip_str.split(':')[0].strip().strip('[]')
    try:
        ip = ipaddress.ip_address(host_only)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return False

def is_secure_connection() -> bool:
    """Detects if request is served over HTTPS directly or behind reverse proxy/load-balancer."""
    if request.is_secure:
        return True
    if request.headers.get('X-Forwarded-Proto', '').lower() == 'https':
        return True
    if request.headers.get('X-Forwarded-Ssl', '').lower() == 'on':
        return True
    if request.headers.get('Front-End-Https', '').lower() == 'on':
        return True
    if request.scheme == 'https':
        return True
    return False

def get_client_ip() -> str:
    """Extracts client real IP, respecting standard reverse proxy headers."""
    for header in ('CF-Connecting-IP', 'X-Real-IP'):
        val = request.headers.get(header)
        if val:
            return val.split(',')[0].strip()
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'

def enforce_https_or_local_ip():
    """
    Enforces network access security:
    - Direct access via public IP and port over HTTP is strictly FORBIDDEN (403).
    - Access is only permitted via HTTPS URL or from private Local Network IPs.
    - Public domain requests over plain HTTP are automatically upgraded/redirected to HTTPS (301).
    - Configured via RESTRICT_PUBLIC_HTTP and ALLOW_LOCAL_IP in Dockerfile / environment.
    """
    restrict_public = os.getenv('RESTRICT_PUBLIC_HTTP', 'true').lower() in ('true', '1', 'yes')
    if not restrict_public:
        return None

    # Exclude internal Docker/k8s healthchecks from blocking
    if request.path == '/api/health':
        return None

    # 1. Allow if request is already encrypted over HTTPS
    if is_secure_connection():
        return None

    # 2. Allow if request host is a local/private IP (127.0.0.1, 192.168.x.x, 10.x.x.x, localhost)
    req_host = request.host.split(':')[0] if request.host else ''
    client_ip = get_client_ip()

    allow_local = os.getenv('ALLOW_LOCAL_IP', 'true').lower() in ('true', '1', 'yes')
    if allow_local and is_local_ip(req_host):
        return None

    # 3. If accessed directly via public IP and port without HTTPS -> Block immediately with 403
    if is_public_ip(req_host):
        logger.warning(f"Blocked unauthorized direct public IP HTTP access from {client_ip} to host {request.host}")
        if request.path.startswith('/api/'):
            return jsonify(
                error="Access Restricted: Direct HTTP access via public IP and port is not permitted. Please access via a secure HTTPS URL or connect from the local network.",
                ok=False
            ), 403
        return render_template_string(
            """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>403 Forbidden — Access Restricted</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0F172A; color: #F8FAFC; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; }
    .card { background: #1E293B; border: 1px solid #334155; border-radius: 14px; padding: 36px; max-width: 500px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.5); }
    .icon { font-size: 40px; margin-bottom: 16px; }
    h1 { color: #F43F5E; font-size: 22px; margin: 0 0 12px 0; font-weight: 600; }
    p { color: #94A3B8; font-size: 14px; line-height: 1.6; margin: 0 0 12px 0; }
    .allowed-box { background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 12px; margin-top: 18px; text-align: left; font-size: 13px; color: #E2E8F0; }
    .allowed-box ul { margin: 6px 0 0 0; padding-left: 20px; }
    .badge { display: inline-block; background: #334155; color: #94A3B8; padding: 4px 10px; border-radius: 6px; font-family: monospace; font-size: 11px; margin-top: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🔒</div>
    <h1>Direct IP &amp; Port Access Restricted</h1>
    <p>Opening this application directly via public IP and port over unencrypted HTTP is not permitted for security reasons.</p>
    <div class="allowed-box">
      <strong>Authorized Access Methods:</strong>
      <ul>
        <li>Secure <strong>HTTPS URL</strong> (e.g. <code>https://assets.yourcompany.com</code>)</li>
        <li>Authorized <strong>Local Network IP</strong> (e.g. <code>192.168.x.x</code> or <code>10.x.x.x</code>)</li>
      </ul>
    </div>
    <div class="badge">HTTP 403 &bull; SSL/TLS or Local IP Required</div>
  </div>
</body>
</html>"""
        ), 403

    # 4. If accessed via a public domain name over HTTP -> Automatically redirect to HTTPS
    secure_url = f"https://{request.host}{request.full_path}"
    return redirect(secure_url, code=301)

@app.before_request
def enforce_security_and_auth():
    # 1. Enforce HTTPS or Local IP network restriction first
    resp = enforce_https_or_local_ip()
    if resp is not None:
        return resp

    # 2. Whitelisted endpoints that never require login:
    # - Internal Docker healthcheck
    # - Login & logout routes
    # - Static assets (CSS, JS, logos, icons)
    # - Remote workstation enrollment scripts
    whitelist_prefixes = (
        '/api/health',
        '/login',
        '/logout',
        '/static/',
        '/agent.sh',
        '/agent.py',
        '/agent.ps1',
        '/favicon.ico',
    )
    if any(request.path.startswith(prefix) or request.path == prefix for prefix in whitelist_prefixes):
        return None

    # 3. If accessing API endpoints (/api/*):
    if request.path.startswith('/api/'):
        # Allow if authenticated admin session exists
        if is_admin_authenticated():
            return None
        # Allow if valid API key is supplied (for agents / curl)
        token = request.headers.get('X-Asset-Key', '')
        if not token:
            auth_hdr = request.headers.get('Authorization', '')
            if auth_hdr.lower().startswith('bearer '):
                token = auth_hdr[7:].strip()
        if not token:
            token = request.args.get('key', '')
        if token and verify_token(token):
            return None
        return jsonify(error='Unauthorized: Admin login or valid ASSET_API_KEY required', ok=False), 401

    # 4. For HTML pages (/ and any other UI route):
    if not is_admin_authenticated():
        return redirect('/login')

    return None

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://fonts.gstatic.com data: blob:;"
    )
    if is_secure_connection():
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    return response

@app.errorhandler(400)
def handle_bad_request(e):
    if request.path.startswith('/api/'):
        msg = getattr(e, 'description', 'Bad Request')
        return jsonify(error=str(msg), ok=False), 400
    return e

@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify(error='Resource not found', ok=False), 404
    return e

@app.errorhandler(405)
def handle_method_not_allowed(e):
    if request.path.startswith('/api/'):
        return jsonify(error='Method not allowed', ok=False), 405
    return e

@app.errorhandler(413)
def handle_payload_too_large(e):
    return jsonify(error='Request payload exceeds maximum allowed size (16MB)', ok=False), 413

@app.errorhandler(500)
def handle_internal_error(e):
    logger.error(f"Internal server error: {e}", exc_info=True)
    if request.path.startswith('/api/'):
        return jsonify(error='Internal server error', ok=False), 500
    return "An internal server error occurred.", 500

FIELDS = [
    'barcode', 'barcode_format', 'asset_type', 'manufacturer', 'model',
    'serial_number', 'product_code', 'cpu', 'cpu_model', 'ram', 'storage',
    'os_name', 'ip_address', 'mac_address', 'motherboard', 'device_name', 'hostname',
    'ram_vendor', 'ram_size', 'ram_serial',
    'storage_vendor', 'storage_model', 'storage_serial', 'storage_size',
    'motherboard_mfg', 'motherboard_product', 'motherboard_serial',
    'assigned_to', 'department', 'location', 'status', 'notes'
]

VALID_STATUSES = ['Available', 'Assigned', 'In Repair', 'Retired']

class RowWrapper(dict):
    """Provides compatibility with dict-based and index-based column access."""
    def __init__(self, d):
        super().__init__(d)
        self._values = list(d.values())

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._values[item]
        return super().__getitem__(item)

    def keys(self):
        return super().keys()

class CursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = getattr(cursor, 'lastrowid', None)

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return RowWrapper(row)

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [RowWrapper(r) for r in rows]

class DBWrapper:
    def __init__(self, conn=None):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                pass
        else:
            try:
                self.rollback()
            except Exception:
                pass
        try:
            self.close()
        except Exception:
            pass

    def execute(self, sql, params=None):
        sql_mysql = sql.replace('?', '%s')
        cur = self.conn.cursor()
        cur.execute(sql_mysql, tuple(params) if params is not None else ())
        return CursorWrapper(cur)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

def connect():
    """Connect directly to production MySQL server with connection retry across known host aliases."""
    hosts_to_try = [
        os.environ.get('MYSQL_HOST', '127.0.0.1'),
        'mysql',
        '127.0.0.1',
        'host.docker.internal'
    ]
    seen = set()
    hosts = [h for h in hosts_to_try if h and not (h in seen or seen.add(h))]
    last_err = None
    for h in hosts:
        try:
            conn = pymysql.connect(
                host=h,
                port=int(os.environ.get('MYSQL_PORT', 3306)),
                user=os.environ.get('MYSQL_USER', 'asset_user'),
                password=os.environ.get('MYSQL_PASSWORD', 'kundan@@1231'),
                database=os.environ.get('MYSQL_DATABASE', 'it_asset_manager'),
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=5,
                read_timeout=15,
                write_timeout=15
            )
            return DBWrapper(conn=conn)
        except Exception as e:
            last_err = e
    logger.error(f"Failed to connect to MySQL across hosts {hosts}: {last_err}")
    raise RuntimeError(f"Database error: unable to connect to MySQL: {last_err}")

def init_db():
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS assets (
          id INT AUTO_INCREMENT PRIMARY KEY,
          barcode VARCHAR(255) NOT NULL UNIQUE,
          barcode_format VARCHAR(100),
          asset_type VARCHAR(100),
          manufacturer VARCHAR(255),
          model VARCHAR(255),
          serial_number VARCHAR(255),
          product_code VARCHAR(255),
          cpu TEXT,
          cpu_model TEXT,
          ram VARCHAR(255),
          storage TEXT,
          os_name VARCHAR(255),
          ip_address VARCHAR(100),
          mac_address VARCHAR(100),
          motherboard TEXT,
          device_name VARCHAR(255),
          hostname VARCHAR(255),
          ram_vendor VARCHAR(255),
          ram_size VARCHAR(100),
          ram_serial VARCHAR(255),
          storage_vendor VARCHAR(255),
          storage_model VARCHAR(255),
          storage_serial VARCHAR(255),
          storage_size VARCHAR(100),
          motherboard_mfg VARCHAR(255),
          motherboard_product VARCHAR(255),
          motherboard_serial VARCHAR(255),
          assigned_to VARCHAR(255),
          department VARCHAR(255),
          location VARCHAR(255),
          status VARCHAR(50),
          notes TEXT,
          created_at VARCHAR(100) NOT NULL,
          updated_at VARCHAR(100) NOT NULL,
          INDEX idx_serial (serial_number),
          INDEX idx_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;''')

try:
    init_db()
except Exception as e:
    logger.warning(f"Initial MySQL table verification: {e}")

def get_configured_key():
    return os.environ.get('ASSET_API_KEY', '')

def verify_token(provided_key):
    server_token = get_configured_key()
    if not server_token or not provided_key:
        return False
    return hmac.compare_digest(provided_key.strip(), server_token.strip())

def protected(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # 1. Allow if authenticated admin session exists
        if is_admin_authenticated():
            return fn(*args, **kwargs)

        # 2. Allow if valid API key token provided (remote agents, scripts, curl)
        token = request.headers.get('X-Asset-Key', '')
        if not token:
            auth_hdr = request.headers.get('Authorization', '')
            if auth_hdr.lower().startswith('bearer '):
                token = auth_hdr[7:].strip()
        if not token:
            token = request.args.get('key', '')

        if token and verify_token(token):
            return fn(*args, **kwargs)

        return jsonify(error='Unauthorized: Admin login or valid ASSET_API_KEY required', ok=False), 401
    return wrapper

def clean(value, limit=255):
    return str(value or '').strip()[:limit]

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method in ('GET', 'HEAD'):
        if is_admin_authenticated():
            return redirect('/')
        admin_user, _ = get_admin_credentials()
        return render_template('login.html', error=None, username=admin_user)

    # POST authentication
    if request.is_json:
        data = request.get_json(silent=True) or {}
        username = data.get('username', '')
        password = data.get('password', '')
    else:
        username = request.form.get('username', '')
        password = request.form.get('password', '')

    if verify_admin_login(username, password):
        session.clear()
        admin_user, _ = get_admin_credentials()
        session['user'] = admin_user
        session['authenticated'] = True
        session.permanent = True
        logger.info(f"Admin '{admin_user}' logged in successfully from {get_client_ip()}")
        if request.is_json:
            return jsonify(ok=True, redirect='/')
        return redirect('/')

    logger.warning(f"Failed admin login attempt for user '{username}' from {get_client_ip()}")
    if request.is_json:
        return jsonify(error='Invalid username or password', ok=False), 401
    return render_template('login.html', error='Invalid username or password', username=username), 401

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    user = session.get('user', 'admin')
    session.clear()
    logger.info(f"User '{user}' logged out from {get_client_ip()}")
    return redirect('/login')

@app.get('/')
def index():
    if not is_admin_authenticated():
        return redirect('/login')
    env_ip = os.environ.get('HOST_LAN_IP') or os.environ.get('LAN_IP')
    req_host = request.host.split(':')[0] if request.host else ''
    if env_ip and env_ip.strip() and env_ip.strip().lower() != 'auto':
        lan_ip = env_ip.strip()
    elif req_host and req_host not in ('127.0.0.1', 'localhost') and not req_host.startswith('172.'):
        lan_ip = req_host
    else:
        lan_ip = hd.get_primary_ip()
    port = request.host.split(':')[1] if ':' in request.host else os.environ.get('PORT', '5000')
    lan_url = f"http://{lan_ip}:{port}"
    admin_user = session.get('user', 'admin')
    return render_template('index.html', lan_ip=lan_ip, lan_url=lan_url, admin_user=admin_user)

@app.get('/api/health')
def health_check():
    try:
        with connect() as db:
            db.execute('SELECT 1')
        return jsonify(status='healthy', ok=True, database='connected')
    except Exception as e:
        logger.error(f"Health check probe failed: {e}")
        return jsonify(status='unhealthy', ok=False, error=str(e)), 503

@app.get('/api/network-ip')
def get_network_ip():
    """Returns the dynamically detected active LAN IP of this server."""
    env_ip = os.environ.get('HOST_LAN_IP') or os.environ.get('LAN_IP')
    req_host = request.host.split(':')[0] if request.host else ''
    if env_ip and env_ip.strip() and env_ip.strip().lower() != 'auto':
        detected_ip = env_ip.strip()
    elif req_host and req_host not in ('127.0.0.1', 'localhost') and not req_host.startswith('172.'):
        detected_ip = req_host
    else:
        detected_ip = hd.get_primary_ip()
    port = request.host.split(':')[1] if ':' in request.host else os.environ.get('PORT', '5000')
    return jsonify({
        'ip': detected_ip,
        'url': f"http://{detected_ip}:{port}"
    })

@app.get('/agent.py')
def serve_agent_py():
    return send_from_directory('static', 'agent.py', mimetype='text/x-python')

@app.get('/agent.sh')
def serve_agent_sh():
    server_url = request.host_url.rstrip('/')
    api_key = get_configured_key()
    script = f"""#!/usr/bin/env bash
# IT Asset Manager — Automated Hardware Discovery Agent (macOS / Ubuntu / Linux)
# Pre-configured for server: {server_url}

set -e

SERVER="{server_url}"
KEY="{api_key}"
EXTRA_ARGS=()

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --key) KEY="$2"; shift ;;
        --server) SERVER="$2"; shift ;;
        *) EXTRA_ARGS+=("$1") ;;
    esac
    shift
done

PYTHON_BIN=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Error: Python 3 was not found on this system."
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "💡 On macOS, run: xcode-select --install (or install python3 via brew)"
    else
        echo "💡 On Ubuntu/Linux, run: sudo apt update && sudo apt install -y python3"
    fi
    exit 1
fi

TMP_SCRIPT=$(mktemp /tmp/asset_agent_XXXXXX.py)
trap 'rm -f "$TMP_SCRIPT"' EXIT

echo "📥 Fetching hardware discovery agent from $SERVER..."
curl -sSL "$SERVER/agent.py" -o "$TMP_SCRIPT"

echo "⚡ Inspecting Motherboard/Logic Board, CPU, RAM, Storage (SSD/NVMe), Serial, Device Name & User..."
"$PYTHON_BIN" "$TMP_SCRIPT" --server "$SERVER" --key "$KEY" "${{EXTRA_ARGS[@]}}"
"""
    return script, 200, {'Content-Type': 'text/x-shellscript'}

@app.get('/agent.ps1')
def serve_agent_ps1():
    server_url = request.host_url.rstrip('/')
    api_key = get_configured_key()
    script = f"""# IT Asset Manager — Automated Hardware Discovery Agent (Windows PowerShell)
# Pre-configured for server: {server_url}
param(
    [string]$Server = "{server_url}",
    [string]$Key = "{api_key}",
    [string]$Assigned = "",
    [string]$Department = "IT",
    [string]$Location = "Office"
)

$ErrorActionPreference = "Stop"
Write-Host "⚡ Inspecting Motherboard, CPU, RAM, Storage (SSD/NVMe), Serial, Device Name & User..." -ForegroundColor Cyan

try {{
    $hostname = $env:COMPUTERNAME
    $currentUser = $env:USERNAME
    if (-not $Assigned) {{ $Assigned = $currentUser }}

    # Serial Number / Service Tag
    $bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue
    $serial = $bios.SerialNumber
    if (-not $serial -or $serial -match "To be filled|Default|None") {{
        $board = Get-CimInstance Win32_BaseBoard -ErrorAction SilentlyContinue
        $serial = $board.SerialNumber
    }}
    if (-not $serial -or $serial -match "To be filled|Default|None") {{
        $serial = "WIN-$hostname"
    }}

    # Manufacturer & Model
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
    $mfg = if ($cs.Manufacturer) {{ $cs.Manufacturer.Trim() }} else {{ "PC" }}
    $model = if ($cs.Model) {{ $cs.Model.Trim() }} else {{ $hostname }}

    # Chassis / Asset Type
    $assetType = "Laptop"
    $chassis = (Get-CimInstance Win32_SystemEnclosure -ErrorAction SilentlyContinue).ChassisTypes
    if ($chassis -contains 3 -or $chassis -contains 4 -or $chassis -contains 6 -or $chassis -contains 7) {{
        $assetType = "Desktop"
    }} elseif ($chassis -contains 17 -or $chassis -contains 23) {{
        $assetType = "Server"
    }}

    # Motherboard
    $board = Get-CimInstance Win32_BaseBoard -ErrorAction SilentlyContinue
    $boardMfg = if ($board.Manufacturer) {{ $board.Manufacturer.Trim() }} else {{ "" }}
    $boardProd = if ($board.Product) {{ $board.Product.Trim() }} else {{ "" }}
    $boardSerial = if ($board.SerialNumber) {{ $board.SerialNumber.Trim() }} else {{ "" }}
    $biosVer = if ($bios.SMBIOSBIOSVersion) {{ $bios.SMBIOSBIOSVersion.Trim() }} else {{ "" }}

    $mb = "$boardMfg $boardProd".Trim()
    if (-not $mb) {{ $mb = "Motherboard" }}
    if ($biosVer) {{ $mb += " (BIOS $biosVer)" }}
    if ($boardSerial -and $boardSerial -notmatch "To be filled|Default") {{ $mb += " (S/N: $boardSerial)" }}

    # Processor (CPU)
    $proc = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1
    $cpu = if ($proc.Name) {{ ($proc.Name -replace '\\s+', ' ').Trim() }} else {{ "Multi-Core Processor" }}
    $cores = $proc.NumberOfCores
    $threads = $proc.NumberOfLogicalProcessors
    if ($cores -and $threads) {{
        $cpu += " ($cores Cores, $threads Threads)"
    }}

    # Memory (RAM)
    $totalRamBytes = [double]($cs.TotalPhysicalMemory)
    $rawGb = [math]::Round($totalRamBytes / 1GB, 1)
    $normGb = 16
    $standards = @(2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128)
    $minDiff = 9999
    foreach ($s in $standards) {{
        $diff = [math]::Abs($rawGb - $s)
        if ($diff -lt $minDiff) {{
            $minDiff = $diff
            $normGb = $s
        }}
    }}
    $ram = "$normGb GB RAM"
    $memModules = Get-CimInstance Win32_PhysicalMemory -ErrorAction SilentlyContinue
    $ramVendors = @()
    $ramSerials = @()
    if ($memModules) {{
        foreach ($m in $memModules) {{
            if ($m.Manufacturer -and $m.Manufacturer -notmatch "Unknown|None|To be filled") {{ $ramVendors += $m.Manufacturer.Trim() }}
            if ($m.SerialNumber -and $m.SerialNumber -notmatch "Unknown|None|00000000|To be filled") {{ $ramSerials += $m.SerialNumber.Trim() }}
        }}
    }}
    $ramVendor = if ($ramVendors.Count -gt 0) {{ ($ramVendors | Select-Object -Unique) -join " / " }} else {{ "Crucial / Micron" }}
    $ramSerial = if ($ramSerials.Count -gt 0) {{ ($ramSerials | Select-Object -Unique) -join " / " }} else {{ "N/A" }}

    # Storage (Physical SSD / NVMe / HDD) - Support Single and Multi-Disk setups
    $disks = @(Get-CimInstance Win32_DiskDrive -ErrorAction SilentlyContinue)
    $physDisks = @(Get-PhysicalDisk -ErrorAction SilentlyContinue)

    $diskList = @()
    $vendorList = @()
    $modelList = @()
    $serialList = @()
    $sizeList = @()

    foreach ($d in $disks) {{
        $rawModel = if ($d.Model) {{ ($d.Model -replace '\\s+', ' ').Trim() }} else {{ "Disk" }}
        $rawMfg = if ($d.Manufacturer) {{ $d.Manufacturer.Trim() }} else {{ "" }}
        $rawSn = if ($d.SerialNumber) {{ $d.SerialNumber.Trim() }} else {{ "" }}

        # Match with PhysicalDisk for media type (SSD/HDD) and hardware serial
        $pd = $physDisks | Where-Object {{
            ($_.DeviceId -and $d.DeviceID -match "$($_.DeviceId)$") -or
            ($_.SerialNumber -and $rawSn -and $_.SerialNumber.Trim() -eq $rawSn) -or
            ($_.FriendlyName -and $_.FriendlyName.Trim() -eq $rawModel)
        }} | Select-Object -First 1

        if ($pd) {{
            if ($pd.Manufacturer -and $pd.Manufacturer -notmatch "\\(Standard|Generic|Unknown|None|To be filled") {{
                $rawMfg = $pd.Manufacturer.Trim()
            }}
            if (-not $rawSn -and $pd.SerialNumber) {{
                $rawSn = $pd.SerialNumber.Trim()
            }}
        }}

        # Size calculation
        $rawBytes = [double]($d.Size)
        $sizeGb = [math]::Round($rawBytes / 1GB)
        $sizeStr = if ($sizeGb -ge 900 -and $sizeGb -le 1050) {{ "1 TB" }} elseif ($sizeGb -gt 1800 -and $sizeGb -le 2100) {{ "2 TB" }} else {{ "$sizeGb GB" }}

        # Media type (SSD vs HDD)
        $media = "Disk"
        if ($pd -and $pd.MediaType) {{
            $mType = "$($pd.MediaType)".ToUpper()
            if ($mType -eq "SSD") {{ $media = "SSD" }}
            elseif ($mType -eq "HDD") {{ $media = "HDD" }}
        }}
        if ($media -eq "Disk") {{
            $dmUpper = "$rawMfg $rawModel".ToUpper()
            if ($dmUpper -match "SSD|NVME|FAST|M\\.2|EMMC") {{ $media = "SSD" }}
            elseif ($dmUpper -match "MQ0|WD\\d{{2,4}}|ST\\d{{3,4}}|BARRACUDA|SPINPOINT|5400|7200") {{ $media = "HDD" }}
            else {{ $media = "SSD" }}
        }}

        # Smart Manufacturer Detection for SSD and HDD
        $dm = "$rawMfg $rawModel".ToUpper()
        $v = ""
        if ($dm -match "TOSHIBA|KIOXIA|KBG|THNS|MQ0") {{ $v = "Toshiba" }}
        elseif ($dm -match "SAMSUNG|MZVL|MZNT|MZ7|MZ8|980 PRO|970 EVO|990 PRO") {{ $v = "Samsung" }}
        elseif ($dm -match "WDC|WD |WESTERN DIGITAL|SN520|SN530|SN550|SN570|SN740|SN750|SN770|SN850|WD10|WD50") {{ $v = "Western Digital" }}
        elseif ($dm -match "SEAGATE|ST\\d{{3,4}}|BARRACUDA|FIRECUDA") {{ $v = "Seagate" }}
        elseif ($dm -match "CRUCIAL|MICRON|MTFD|CT\\d{{3,4}}") {{ $v = "Crucial / Micron" }}
        elseif ($dm -match "KINGSTON|SA400|SKC|OM8P|SNV2|SNV3") {{ $v = "Kingston" }}
        elseif ($dm -match "SKHYNIX|SK HYNIX|HYNIX|HFM|HFS|PC711|BC711|BC511") {{ $v = "SK Hynix" }}
        elseif ($dm -match "SANDISK|SDSS") {{ $v = "SanDisk" }}
        elseif ($dm -match "INTEL|MEMPEK|SSDPE") {{ $v = "Intel" }}
        elseif ($dm -match "ADATA|SX8200|SU650|SU800") {{ $v = "ADATA" }}
        elseif ($dm -match "CORSAIR|FORCE MP") {{ $v = "Corsair" }}
        elseif ($dm -match "SOLIDIGM") {{ $v = "Solidigm" }}
        elseif ($dm -match "LEXAR") {{ $v = "Lexar" }}
        elseif ($dm -match "TRANSCEND") {{ $v = "Transcend" }}
        elseif ($dm -match "PNY") {{ $v = "PNY" }}
        elseif ($dm -match "TEAMGROUP|TEAM ") {{ $v = "TeamGroup" }}
        elseif ($rawMfg -and $rawMfg -notmatch "\\(Standard|Generic|Unknown|None|To be filled") {{ $v = $rawMfg }}
        else {{
            $fw = ($rawModel -split '\\s+')[0]
            if ($fw -and $fw.Length -gt 2 -and $fw -notmatch "^\\d|\\d+(GB|TB)|NVME|SSD|SCSI|DISK|GENERIC") {{
                $v = $fw
            }} else {{
                $v = "OEM $media"
            }}
        }}

        $vendorList += $v
        $modelList += $rawModel
        if ($rawSn -and $rawSn -notmatch "00000000|None|Default") {{ $serialList += $rawSn }}
        $sizeList += "$sizeStr $media"
        $diskList += "$sizeStr $media ($v - $rawModel)"
    }}

    $storage = if ($diskList.Count -gt 0) {{ $diskList -join " + " }} else {{ "512 GB SSD" }}
    $storageVendor = if ($vendorList.Count -gt 0) {{ ($vendorList | Select-Object -Unique) -join " / " }} else {{ "OEM SSD" }}
    $storageModel = if ($modelList.Count -gt 0) {{ $modelList -join " + " }} else {{ "NVMe / SSD" }}
    $storageSerial = if ($serialList.Count -gt 0) {{ $serialList -join " / " }} else {{ "N/A" }}
    $storageSize = if ($sizeList.Count -gt 0) {{ $sizeList -join " + " }} else {{ "512 GB" }}

    # Operating System
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
    $osName = if ($os.Caption) {{
        $name = $os.Caption.Trim()
        $arch = if ($os.OSArchitecture) {{ $os.OSArchitecture.Trim() }} else {{ "" }}
        $build = if ($os.BuildNumber) {{ "Build $($os.BuildNumber.Trim())" }} else {{ "" }}
        $extraParts = @($arch, $build) | Where-Object {{ $_ -and $_.Length -gt 0 }}
        $extra = $extraParts -join ", "
        if ($extra) {{ "$name ($extra)" }} else {{ "$name" }}
    }} else {{ "Microsoft Windows" }}

    # Network IP & MAC
    $ip = "127.0.0.1"
    $mac = ""
    $net = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = True" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($net) {{
        if ($net.IPAddress -and $net.IPAddress[0]) {{ $ip = $net.IPAddress[0] }}
        if ($net.MACAddress) {{ $mac = $net.MACAddress }}
    }}

    $notes = "Auto-enrolled on $hostname | Motherboard: $mb | Storage: $storage | User: $Assigned"

    Write-Host "`n================ DETECTED DEVICE SPECS ================" -ForegroundColor Yellow
    Write-Host "  Device Name    : $hostname"
    Write-Host "  User Name      : $Assigned"
    Write-Host "  Serial Number  : $serial"
    Write-Host "  Manufacturer   : $mfg"
    Write-Host "  Model          : $model"
    Write-Host "  Category       : $assetType"
    Write-Host "  Motherboard    : $mb"
    Write-Host "  Processor      : $cpu"
    Write-Host "  Memory (RAM)   : $ram (Vendor: $ramVendor, Serial: $ramSerial)"
    Write-Host "  Storage        : $storage (Vendor: $storageVendor, Serial: $storageSerial)"
    Write-Host "  OS             : $osName"
    Write-Host "  IP Address     : $ip"
    Write-Host "=======================================================`n" -ForegroundColor Yellow

    $bodyObj = @{{
        barcode = $serial
        serial_number = $serial
        barcode_format = "CODE128"
        asset_type = $assetType
        manufacturer = $mfg
        model = $model
        product_code = ""
        cpu = $cpu
        cpu_model = $cpu
        ram = $ram
        ram_vendor = $ramVendor
        ram_size = "$normGb GB"
        ram_serial = $ramSerial
        storage = $storage
        storage_vendor = $storageVendor
        storage_model = $storageModel
        storage_serial = $storageSerial
        storage_size = $storageSize
        motherboard = $mb
        motherboard_mfg = $boardMfg
        motherboard_product = $boardProd
        motherboard_serial = $boardSerial
        device_name = $hostname
        hostname = $hostname
        assigned_to = $Assigned
        os_name = $osName
        ip_address = $ip
        mac_address = $mac
        status = if ($Assigned) {{ "Assigned" }} else {{ "Available" }}
        department = $Department
        location = $Location
        notes = $notes
    }}

    $jsonBody = $bodyObj | ConvertTo-Json
    $headers = @{{
        "Content-Type" = "application/json"
        "User-Agent" = "ITAssetManagerPowerShellAgent/2.2"
    }}
    if ($Key) {{
        $headers["X-Asset-Key"] = $Key
    }}

    $targetUrl = "$Server/api/autodiscover"
    Write-Host "🚀 Uploading specifications to $targetUrl..." -ForegroundColor Cyan

    $resp = Invoke-RestMethod -Uri $targetUrl -Method Post -Body $jsonBody -Headers $headers -TimeoutSec 15
    $action = if ($resp.action) {{ $resp.action }} else {{ "enrolled" }}
    $assetId = if ($resp.id) {{ $resp.id }} else {{ "" }}
    Write-Host "✅ Success! Asset #$assetId ($mfg $model) has been $action in the database." -ForegroundColor Green
}} catch {{
    Write-Host "❌ Failed to discover or register asset: $_" -ForegroundColor Red
    exit 1
}}
"""
    return script, 200, {'Content-Type': 'text/plain'}

@app.get('/api/verify-key')
@protected
def verify_key():
    return jsonify(ok=True, message='API key is valid')

@app.get('/api/detect/local')
@protected
def detect_local():
    """
    Auto-detects the hardware specs of the local Ubuntu machine.
    """
    specs = hd.get_host_specs()
    return jsonify(ok=True, specs=specs)

@app.get('/api/lookup')
@protected
def lookup():
    barcode = clean(request.args.get('barcode'))
    fmt = clean(request.args.get('format', ''))
    model_hint = clean(request.args.get('model', ''))
    if not barcode:
        return jsonify(error='barcode required'), 400

    with connect() as db:
        # Check if asset exists by barcode or serial number
        row = db.execute('SELECT * FROM assets WHERE barcode=? OR (serial_number != "" AND serial_number=?)', (barcode, barcode)).fetchone()
        
        # Check if another asset has this model to borrow specs
        learned = None
        if not row and model_hint:
            learned_row = db.execute('SELECT manufacturer, model, cpu, ram, storage, asset_type FROM assets WHERE model LIKE ? AND cpu != "" LIMIT 1', (f"%{model_hint}%",)).fetchone()
            if learned_row:
                learned = dict(learned_row)

    suggested = hd.enrich_barcode_details(barcode, fmt, model_hint)

    # Enhance with Multi-Brand AI Engine (covers Apple, Asus, Acer, Surface, HP, Lenovo, Cisco, etc.)
    ai_info = ai.ai_infer_device(f"{barcode} {model_hint}", barcode)
    if not suggested.get('manufacturer') and ai_info.get('manufacturer'):
        suggested['manufacturer'] = ai_info['manufacturer']
    if not suggested.get('model') and ai_info.get('model'):
        suggested['model'] = ai_info['model']
    if not suggested.get('cpu') and ai_info.get('cpu'):
        suggested['cpu'] = ai_info['cpu']
    if not suggested.get('ram') and ai_info.get('ram'):
        suggested['ram'] = ai_info['ram']
    if not suggested.get('storage') and ai_info.get('storage'):
        suggested['storage'] = ai_info['storage']
    if not suggested.get('product_code') and ai_info.get('product_code'):
        suggested['product_code'] = ai_info['product_code']
    if ai_info.get('asset_type') and ai_info['asset_type'] != 'Laptop':
        suggested['asset_type'] = ai_info['asset_type']

    if learned and not suggested.get('cpu'):
        suggested['cpu'] = learned.get('cpu', '')
        suggested['ram'] = learned.get('ram', '')
        suggested['storage'] = learned.get('storage', '')
        suggested['source'] += " + Learned from past inventory record"

    return jsonify(
        found=bool(row),
        asset=dict(row) if row else None,
        suggested=suggested
    )

def build_assets_query(q='', status_filter='', type_filter='', os_filter=''):
    query = 'SELECT * FROM assets WHERE 1=1'
    params = []

    if q:
        like = '%' + q + '%'
        query += ''' AND (barcode LIKE ? OR serial_number LIKE ? OR manufacturer LIKE ? OR model LIKE ? OR assigned_to LIKE ? OR location LIKE ? OR department LIKE ? OR cpu LIKE ? OR os_name LIKE ? OR hostname LIKE ? OR device_name LIKE ? OR storage_vendor LIKE ? OR storage_model LIKE ?)'''
        params.extend([like] * 13)

    if status_filter and status_filter.lower() != 'all':
        query += ' AND status=?'
        params.append(status_filter)

    if type_filter and type_filter.lower() != 'all':
        query += ' AND asset_type=?'
        params.append(type_filter)

    if os_filter and os_filter.lower() != 'all':
        os_lower = os_filter.strip().lower()
        if os_lower in ('ubuntu', 'linux'):
            query += " AND (LOWER(os_name) LIKE ? OR LOWER(os_name) LIKE ? OR LOWER(os_name) LIKE ?)"
            params.extend(['%ubuntu%', '%linux%', '%debian%'])
        elif os_lower == 'windows':
            query += " AND LOWER(os_name) LIKE ?"
            params.append('%windows%')
        elif os_lower in ('mac', 'macos', 'darwin', 'apple'):
            query += " AND (LOWER(os_name) LIKE ? OR LOWER(os_name) LIKE ? OR LOWER(os_name) LIKE ?)"
            params.extend(['%mac%', '%darwin%', '%apple%'])
        else:
            query += " AND LOWER(os_name) LIKE ?"
            params.append(f"%{os_lower}%")

    return query, params

@app.post('/api/ai/infer')
@protected
def ai_infer():
    """
    AI Multi-Brand Spec Extractor (Zero API Key required).
    Parses any model, serial, sticker OCR text, or specs across all brands.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Invalid JSON payload; object expected'), 400
    text = clean(data.get('text', ''), 2000)
    barcode = clean(data.get('barcode', ''), 255)
    if not text and not barcode:
        return jsonify(error='Text or Barcode required for AI inference'), 400

    inferred = ai.ai_infer_device(text or barcode, barcode)
    return jsonify(ok=True, inferred=inferred)

@app.post('/api/scan/image')
@protected
def scan_image():
    """
    Scans an uploaded image or camera snapshot for barcodes and text/labels.
    Uses zxingcpp for 1D/2D barcodes + RapidOCR for label reading,
    and runs the zero-API AI engine to extract serial number, brand, model,
    product code, and hardware specifications.
    """
    img = None
    if 'file' in request.files:
        f = request.files['file']
        if not f or f.filename == '':
            return jsonify(error='No file selected'), 400
        try:
            raw_bytes = f.read()
            if not raw_bytes:
                return jsonify(error='Empty image file provided'), 400
            img = Image.open(io.BytesIO(raw_bytes))
            # Verify image integrity
            img.verify()
            img = Image.open(io.BytesIO(raw_bytes))
        except Exception as e:
            return jsonify(error=f'Invalid image file: {e!s}'), 400
    elif request.is_json and isinstance(request.json, dict) and 'image_base64' in request.json:
        b64_data = request.json['image_base64']
        if ',' in b64_data:
            b64_data = b64_data.split(',', 1)[1]
        try:
            raw_bytes = base64.b64decode(b64_data)
            if not raw_bytes:
                return jsonify(error='Empty base64 image data'), 400
            img = Image.open(io.BytesIO(raw_bytes))
            img.verify()
            img = Image.open(io.BytesIO(raw_bytes))
        except Exception as e:
            return jsonify(error=f'Invalid base64 image: {e!s}'), 400
    else:
        return jsonify(error='Provide an image file in form-data or image_base64 in JSON'), 400

    # 1. Barcode scanning via zxingcpp
    barcodes = []
    try:
        results = zxingcpp.read_barcodes(img, try_rotate=True, try_downscale=True)
        barcodes = [b.text.strip() for b in results if b.text.strip()]
    except Exception:
        pass

    primary_barcode = barcodes[0] if barcodes else ''

    # 2. RapidOCR text reading
    ocr_lines = []
    try:
        img_np = np.array(img.convert('RGB'))
        ocr = get_ocr_engine()
        ocr_res, _ = ocr(img_np)
        if ocr_res:
            ocr_lines = [item[1].strip() for item in ocr_res if item[1].strip()]
    except Exception as e:
        logger.warning(f"RapidOCR error: {e}")

    combined_text = "\n".join(ocr_lines)
    if primary_barcode and primary_barcode not in combined_text:
        combined_text = f"{primary_barcode}\n{combined_text}"

    # 3. AI Hardware Inference
    inferred = ai.ai_infer_device(combined_text, barcode_hint=primary_barcode)

    # Fallback serial to barcode or vice versa
    if not inferred.get("serial_number") and primary_barcode:
        inferred["serial_number"] = primary_barcode
    if not inferred.get("barcode") and inferred.get("serial_number"):
        inferred["barcode"] = inferred["serial_number"]

    return jsonify(
        ok=True,
        barcodes_found=barcodes,
        ocr_lines_found=ocr_lines,
        device=inferred
    )

@app.get('/api/stats')
@protected
def stats():
    with connect() as db:
        total = db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
        available = db.execute("SELECT COUNT(*) FROM assets WHERE status='Available'").fetchone()[0]
        assigned = db.execute("SELECT COUNT(*) FROM assets WHERE status='Assigned'").fetchone()[0]
        repair = db.execute("SELECT COUNT(*) FROM assets WHERE status='In Repair' OR status='Repair'").fetchone()[0]
        retired = db.execute("SELECT COUNT(*) FROM assets WHERE status='Retired'").fetchone()[0]

        # Top asset types
        type_rows = db.execute('SELECT asset_type, COUNT(*) as c FROM assets GROUP BY asset_type ORDER BY c DESC LIMIT 6').fetchall()
        by_type = {r['asset_type'] or 'Uncategorized': r['c'] for r in type_rows}

        # Top manufacturers
        mfg_rows = db.execute('SELECT manufacturer, COUNT(*) as c FROM assets WHERE manufacturer != "" GROUP BY manufacturer ORDER BY c DESC LIMIT 6').fetchall()
        by_mfg = {r['manufacturer']: r['c'] for r in mfg_rows}

        # OS breakdown
        os_rows = db.execute('SELECT os_name, COUNT(*) as c FROM assets WHERE os_name != "" GROUP BY os_name ORDER BY c DESC LIMIT 6').fetchall()
        by_os = {r['os_name']: r['c'] for r in os_rows}

    return jsonify(
        total=total,
        available=available,
        assigned=assigned,
        repair=repair,
        retired=retired,
        by_type=by_type,
        by_manufacturer=by_mfg,
        by_os=by_os
    )

@app.get('/api/assets')
@protected
def list_assets():
    q = clean(request.args.get('q'), 100)
    status_filter = clean(request.args.get('status'), 50)
    type_filter = clean(request.args.get('type'), 50)
    os_filter = clean(request.args.get('os'), 50)

    query, params = build_assets_query(q, status_filter, type_filter, os_filter)
    query += ' ORDER BY id DESC LIMIT 500'

    with connect() as db:
        rows = db.execute(query, params).fetchall()
        total_count = db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]

    return jsonify(assets=[dict(r) for r in rows], total=total_count, count=len(rows))

@app.get('/api/assets/<int:asset_id>')
@protected
def get_asset(asset_id):
    if asset_id <= 0:
        return jsonify(error='Asset not found'), 404
    with connect() as db:
        row = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
        if not row:
            return jsonify(error='Asset not found'), 404
        return jsonify(asset=dict(row))

@app.post('/api/assets')
@protected
def create_asset():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Invalid JSON payload; object expected'), 400

    raw_status = clean(data.get('status', ''))
    if raw_status and raw_status not in VALID_STATUSES:
        return jsonify(error=f"Invalid status '{raw_status}'. Allowed: {', '.join(VALID_STATUSES)}"), 400

    values = {f: clean(data.get(f), 2000 if f == 'notes' else 255) for f in FIELDS}

    # Seamlessly fallback between barcode and serial_number
    if not values['serial_number'] and values['barcode']:
        values['serial_number'] = values['barcode']
    if not values['barcode'] and values['serial_number']:
        values['barcode'] = values['serial_number']

    if not values.get('hostname') and values.get('device_name'):
        values['hostname'] = values['device_name']
    if not values.get('device_name') and values.get('hostname'):
        values['device_name'] = values['hostname']
    if not values.get('cpu_model') and values.get('cpu'):
        values['cpu_model'] = values['cpu']
    if not values.get('cpu') and values.get('cpu_model'):
        values['cpu'] = values['cpu_model']

    if not values['serial_number']:
        return jsonify(error='Serial Number / Service Tag is required'), 400

    values['status'] = raw_status if raw_status in VALID_STATUSES else 'Available'
    if not values['asset_type']:
        values['asset_type'] = 'Laptop'

    now = datetime.now(UTC).isoformat()
    try:
        with connect() as db:
            cols = ','.join(FIELDS) + ',created_at,updated_at'
            placeholders = ','.join(['?'] * (len(FIELDS) + 2))
            cur = db.execute(
                f'INSERT INTO assets ({cols}) VALUES ({placeholders})',
                [values[f] for f in FIELDS] + [now, now]
            )
        return jsonify(ok=True, id=cur.lastrowid), 201
    except DB_INTEGRITY_ERRORS:
        return jsonify(error=f"Serial/Barcode '{values['serial_number']}' is already registered in the system"), 409

@app.put('/api/assets/<int:asset_id>')
@protected
def update_asset(asset_id):
    if asset_id <= 0:
        return jsonify(error='Asset not found'), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Invalid JSON payload; object expected'), 400

    raw_status = clean(data.get('status', ''))
    if raw_status and raw_status not in VALID_STATUSES:
        return jsonify(error=f"Invalid status '{raw_status}'. Allowed: {', '.join(VALID_STATUSES)}"), 400

    values = {f: clean(data.get(f), 2000 if f == 'notes' else 255) for f in FIELDS}

    # Seamlessly fallback between barcode and serial_number
    if not values['serial_number'] and values['barcode']:
        values['serial_number'] = values['barcode']
    if not values['barcode'] and values['serial_number']:
        values['barcode'] = values['serial_number']

    if not values.get('hostname') and values.get('device_name'):
        values['hostname'] = values['device_name']
    if not values.get('device_name') and values.get('hostname'):
        values['device_name'] = values['hostname']
    if not values.get('cpu_model') and values.get('cpu'):
        values['cpu_model'] = values['cpu']
    if not values.get('cpu') and values.get('cpu_model'):
        values['cpu'] = values['cpu_model']

    if not values['serial_number']:
        return jsonify(error='Serial Number / Service Tag is required'), 400

    values['status'] = raw_status if raw_status in VALID_STATUSES else 'Available'

    now = datetime.now(UTC).isoformat()
    try:
        with connect() as db:
            set_clause = ','.join(f'{f}=?' for f in FIELDS) + ',updated_at=?'
            cur = db.execute(
                f'UPDATE assets SET {set_clause} WHERE id=?',
                [values[f] for f in FIELDS] + [now, asset_id]
            )
            if cur.rowcount == 0:
                return jsonify(error='Asset not found'), 404
        return jsonify(ok=True)
    except DB_INTEGRITY_ERRORS:
        return jsonify(error=f"Barcode '{values['barcode']}' already belongs to another asset"), 409

@app.delete('/api/assets/<int:asset_id>')
@protected
def delete_asset(asset_id):
    if asset_id <= 0:
        return jsonify(error='Asset not found'), 404
    with connect() as db:
        cur = db.execute('DELETE FROM assets WHERE id=?', (asset_id,))
        if cur.rowcount == 0:
            return jsonify(error='Asset not found'), 404
    return jsonify(ok=True, message='Asset deleted successfully')

@app.post('/api/quick-status/<int:asset_id>')
@protected
def quick_status(asset_id):
    if asset_id <= 0:
        return jsonify(error='Asset not found'), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Invalid JSON payload; object expected'), 400

    new_status = data.get('status', '').strip()
    if new_status not in VALID_STATUSES:
        return jsonify(error=f"Invalid status '{new_status}'. Allowed: {', '.join(VALID_STATUSES)}"), 400

    now = datetime.now(UTC).isoformat()
    with connect() as db:
        cur = db.execute('UPDATE assets SET status=?, updated_at=? WHERE id=?', (new_status, now, asset_id))
        if cur.rowcount == 0:
            return jsonify(error='Asset not found'), 404
    return jsonify(ok=True, status=new_status)

@app.post('/api/autodiscover')
@protected
def autodiscover():
    """
    Automated enrollment endpoint called by Ubuntu/Windows Agent.
    Upserts device specs based on barcode / serial number.
    Arranges, normalizes, and enriches telemetry with Gemini AI Engine.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Invalid JSON payload; object expected'), 400

    # Process incoming telemetry with Gemini AI Engine to arrange specs into exact fields
    try:
        arranged = ai.arrange_agent_telemetry(data)
        data.update(arranged)
    except Exception:
        pass

    barcode = clean(data.get('barcode'))
    if not barcode:
        barcode = clean(data.get('serial_number'))
    if not barcode:
        return jsonify(error='Barcode or Serial Number required'), 400

    values = {f: clean(data.get(f), 2000 if f == 'notes' else 255) for f in FIELDS}
    values['barcode'] = barcode
    if not values.get('hostname') and values.get('device_name'):
        values['hostname'] = values['device_name']
    if not values.get('device_name') and values.get('hostname'):
        values['device_name'] = values['hostname']
    if not values.get('cpu_model') and values.get('cpu'):
        values['cpu_model'] = values['cpu']
    if not values.get('cpu') and values.get('cpu_model'):
        values['cpu'] = values['cpu_model']

    raw_status = clean(data.get('status', ''))
    values['status'] = raw_status if raw_status in VALID_STATUSES else 'Available'
    if not values['asset_type']:
        values['asset_type'] = 'Laptop'

    now = datetime.now(UTC).isoformat()
    with connect() as db:
        existing = db.execute('SELECT id FROM assets WHERE barcode=?', (barcode,)).fetchone()
        if existing:
            asset_id = existing['id']
            set_clause = ','.join(f'{f}=?' for f in FIELDS) + ',updated_at=?'
            db.execute(f'UPDATE assets SET {set_clause} WHERE id=?', [values[f] for f in FIELDS] + [now, asset_id])
            action = 'updated'
        else:
            cols = ','.join(FIELDS) + ',created_at,updated_at'
            placeholders = ','.join(['?'] * (len(FIELDS) + 2))
            cur = db.execute(f'INSERT INTO assets ({cols}) VALUES ({placeholders})', [values[f] for f in FIELDS] + [now, now])
            asset_id = cur.lastrowid
            action = 'registered'

    return jsonify(ok=True, id=asset_id, action=action)

@app.get('/api/export.xlsx')
@protected
def export_excel():
    q = clean(request.args.get('q'), 100)
    status_filter = clean(request.args.get('status'), 50)
    type_filter = clean(request.args.get('type'), 50)
    os_filter = clean(request.args.get('os'), 50)

    query, params = build_assets_query(q, status_filter, type_filter, os_filter)
    query += ' ORDER BY id DESC'

    with connect() as db:
        rows = db.execute(query, params).fetchall()

    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {'in_memory': True})
    ws = wb.add_worksheet('IT Inventory')

    # Premium styling
    hdr_fmt = wb.add_format({
        'bold': True,
        'font_name': 'Arial',
        'font_size': 11,
        'font_color': '#FFFFFF',
        'bg_color': '#1E3A8A',
        'border': 1,
        'border_color': '#CBD5E1',
        'align': 'center',
        'valign': 'vcenter'
    })
    
    cell_fmt = wb.add_format({
        'font_name': 'Arial',
        'font_size': 10,
        'border': 1,
        'border_color': '#E2E8F0',
        'valign': 'vcenter'
    })

    id_fmt = wb.add_format({
        'font_name': 'Arial',
        'font_size': 10,
        'bold': True,
        'align': 'center',
        'border': 1,
        'border_color': '#E2E8F0'
    })

    status_available = wb.add_format({'font_name': 'Arial', 'font_size': 10, 'bg_color': '#DCFCE7', 'font_color': '#166534', 'bold': True, 'border': 1, 'border_color': '#E2E8F0', 'align': 'center'})
    status_assigned = wb.add_format({'font_name': 'Arial', 'font_size': 10, 'bg_color': '#DBEAFE', 'font_color': '#1E40AF', 'bold': True, 'border': 1, 'border_color': '#E2E8F0', 'align': 'center'})
    status_repair = wb.add_format({'font_name': 'Arial', 'font_size': 10, 'bg_color': '#FEF3C7', 'font_color': '#92400E', 'bold': True, 'border': 1, 'border_color': '#E2E8F0', 'align': 'center'})
    status_retired = wb.add_format({'font_name': 'Arial', 'font_size': 10, 'bg_color': '#F1F5F9', 'font_color': '#475569', 'bold': True, 'border': 1, 'border_color': '#E2E8F0', 'align': 'center'})

    cols = [
        'id', 'device_name', 'os_name', 'mac_address', 'ip_address', 'cpu', 'ram_vendor', 'ram_size', 'ram_serial',
        'storage_vendor', 'storage_model', 'storage_serial', 'storage_size',
        'motherboard_mfg', 'motherboard_product', 'motherboard_serial',
        'serial_number', 'manufacturer', 'model',
        'assigned_to', 'status', 'notes', 'created_at'
    ]
    col_titles = {
        'id': 'Asset ID',
        'device_name': 'Hostname',
        'os_name': 'Operating System',
        'mac_address': 'MAC Address',
        'ip_address': 'IP Address',
        'cpu': 'CPU Model',
        'ram_vendor': 'RAM Vendor',
        'ram_size': 'RAM Size',
        'ram_serial': 'RAM Serial No.',
        'storage_vendor': 'Storage Vendor',
        'storage_model': 'Storage Model',
        'storage_serial': 'Storage Serial No.',
        'storage_size': 'Storage Size',
        'motherboard_mfg': 'Motherboard Manufacturer',
        'motherboard_product': 'Motherboard Product',
        'motherboard_serial': 'Motherboard Serial No.',
        'serial_number': 'Serial Number',
        'manufacturer': 'Manufacturer',
        'model': 'Model',
        'assigned_to': 'User Name',
        'status': 'Status',
        'notes': 'Remarks & Telemetry',
        'created_at': 'Discovered At'
    }

    ws.set_row(0, 28)
    for col_idx, col in enumerate(cols):
        title = col_titles.get(col, col.replace('_', ' ').title())
        ws.write(0, col_idx, title, hdr_fmt)

    for row_idx, row in enumerate(rows, start=1):
        ws.set_row(row_idx, 20)
        for col_idx, key in enumerate(cols):
            val = row[key] if key in row.keys() else ''
            if key == 'id':
                ws.write_number(row_idx, col_idx, val, id_fmt)
            elif key == 'status':
                st = str(val or '')
                if st and st[0] in ('=', '+', '-', '@', '\t', '\r'):
                    st = "'" + st
                fmt = status_available if st == 'Available' else (
                    status_assigned if st == 'Assigned' else (
                        status_repair if 'Repair' in st else status_retired
                    )
                )
                ws.write_string(row_idx, col_idx, st, fmt)
            else:
                str_val = str(val or '')
                # Prevent CSV/Excel Formula Injection (CWE-1236)
                if str_val and str_val[0] in ('=', '+', '-', '@', '\t', '\r'):
                    str_val = "'" + str_val
                ws.write_string(row_idx, col_idx, str_val, cell_fmt)

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(rows), 1), len(cols) - 1)

    # Column widths
    ws.set_column(0, 0, 8)    # ID
    ws.set_column(1, 1, 16)   # Hostname
    ws.set_column(2, 2, 26)   # Operating System
    ws.set_column(3, 3, 20)   # MAC Address
    ws.set_column(4, 4, 16)   # IP Address
    ws.set_column(5, 5, 28)   # CPU Model
    ws.set_column(6, 8, 18)   # RAM Vendor, Size, Serial
    ws.set_column(9, 12, 22)  # Storage Vendor, Model, Serial, Size
    ws.set_column(13, 15, 22) # Motherboard Mfg, Product, Serial
    ws.set_column(16, 18, 20) # Serial Number, Mfg, Model
    ws.set_column(19, 20, 14) # User, Status
    ws.set_column(21, 21, 35) # Remarks & Telemetry
    ws.set_column(22, 22, 22) # Created At

    wb.close()
    output.seek(0)

    filename = f"IT_Assets_Inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5000'))
    print(f"🚀 IT Asset Manager starting on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
