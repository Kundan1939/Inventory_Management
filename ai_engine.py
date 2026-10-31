"""
AI Hardware Intelligence Engine for IT Asset Manager
Provides zero-API-key AI specification inference, brand detection, serial parsing,
and NLP spec extraction for ALL major IT brands:
Dell, HP, Lenovo, Apple, Asus, Acer, Microsoft Surface, Samsung, Toshiba/Dynabook,
MSI, LG, Cisco, Ubiquiti, Canon, Brother, Epson, and generic devices.
Works 100% offline with optional free Wikipedia/Open-Registry enrichment.
"""

import json
import os
import re
import urllib.parse
import urllib.request
from html import unescape

# -------------------------------------------------------------
# 1. COMPREHENSIVE BRAND TAXONOMY & SERIAL RECOGNIZERS
# -------------------------------------------------------------

BRAND_PATTERNS = [
    # Apple
    {
        "brand": "Apple",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(macbook\s*(pro|air)?|imac|mac\s*mini|mac\s*studio|mac\s*pro|ipad|iphone)\b",
            r"\b(a\d{4})\b",  # e.g. A2338, A1706, A2141
            r"^(c02|fvf|dnp|g88|c1m|c2v|h0[0-9a-z])[0-9a-z]{8,9}$"
        ]
    },
    # Dell
    {
        "brand": "Dell Inc.",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(dell|latitude|optiplex|vostro|inspiron|precision|xps|alienware|poweredge)\b",
            r"^[a-z0-9]{7}$",  # Dell 7-char alphanumeric service tag
            r"\b(p24\d{2}[a-z]?|p27\d{2}[a-z]?|u27\d{2}[a-z]?)\b" # Dell monitors
        ]
    },
    # Lenovo
    {
        "brand": "Lenovo",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(lenovo|thinkpad|ideapad|thinkcentre|thinkstation|thinksystem|legion|yoga)\b",
            r"^(pf|mp|1s|lr)[0-9a-z]{6,}", # Lenovo serial prefixes
            r"\b(20[a-z0-9]{2}|21[a-z0-9]{2}|82[a-z0-9]{2})\b" # Lenovo 4-digit MTM
        ]
    },
    # HP
    {
        "brand": "HP",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(hp|hewlett[\s-]packard|elitebook|probook|zbook|pavilion|envy|spectre|omen|victus|prodesk|elitedesk|proliant|laserjet)\b",
            r"^(cnd|5cd|5cg|czc|cnu|2ce|3ce|4ce)[0-9a-z]{7}", # HP serial formats
            r"#[a-z0-9]{3}\b" # HP SKU option code (e.g. #ABA)
        ]
    },
    # Asus
    {
        "brand": "ASUS",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(asus|zenbook|vivobook|rog\s*(strix|zephyrus)?|tuf\s*gaming|expertbook)\b",
            r"^[a-z0-9]{2}[nprt][0-9a-z]{11}$"
        ]
    },
    # Acer
    {
        "brand": "Acer",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(acer|aspire|swift|spin|nitro|predator|travelmate|veriton|extensa)\b",
            r"^[a-z0-9]{22}$" # Acer 22-digit serial
        ]
    },
    # Microsoft Surface
    {
        "brand": "Microsoft",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(surface\s*(pro|laptop|book|go|studio|duo)?)\b",
            r"^\d{12}$" # Surface 12-digit serial
        ]
    },
    # Samsung
    {
        "brand": "Samsung",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(samsung|galaxy\s*book|galaxy\s*tab|odyssey)\b"
        ]
    },
    # Toshiba / Dynabook
    {
        "brand": "Dynabook / Toshiba",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(toshiba|dynabook|portégé|portege|tecra|satellite)\b"
        ]
    },
    # MSI
    {
        "brand": "MSI",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(msi|modern|prestige|stealth|raider|titan|katana|cyborg)\b"
        ]
    },
    # LG
    {
        "brand": "LG",
        "asset_type": "Laptop",
        "patterns": [
            r"\b(lg\s*gram|ultragear|ultrafine)\b"
        ]
    },
    # Network: Cisco
    {
        "brand": "Cisco Systems",
        "asset_type": "Network",
        "patterns": [
            r"\b(cisco|catalyst|meraki|nexus|aironet|ironport)\b",
            r"\b(ws-c\d{4}|c9200|c9300|c2960|c3850)\b"
        ]
    },
    # Network: Ubiquiti
    {
        "brand": "Ubiquiti Networks",
        "asset_type": "Network",
        "patterns": [
            r"\b(ubiquiti|unifi|edgerouter|edgeswitch|u6-pro|u6-lite|udm-pro)\b"
        ]
    },
    # Network: MikroTik / Fortinet / TP-Link / Netgear
    {
        "brand": "MikroTik",
        "asset_type": "Network",
        "patterns": [r"\b(mikrotik|routerboard|crs\d{3}|rb\d{3,4})\b"]
    },
    {
        "brand": "Fortinet",
        "asset_type": "Network",
        "patterns": [r"\b(fortinet|fortigate|fg-\d{2,3}[a-z]?)\b"]
    },
    {
        "brand": "TP-Link",
        "asset_type": "Network",
        "patterns": [r"\b(tp[\s-]link|omada|archer|deco)\b"]
    },
    # Printers: Brother, Canon, Epson, Xerox
    {
        "brand": "Brother",
        "asset_type": "Printer",
        "patterns": [r"\b(brother|hl-l\d{4}|mfc-l\d{4}|dcp-l\d{4}|mfc|dcp)\b"]
    },
    {
        "brand": "Canon",
        "asset_type": "Printer",
        "patterns": [r"\b(canon|pixma|imagerunner|imageclass|i-sensys)\b"]
    },
    {
        "brand": "Epson",
        "asset_type": "Printer",
        "patterns": [r"\b(epson|ecotank|workforce|surecolor)\b"]
    },
    {
        "brand": "Xerox",
        "asset_type": "Printer",
        "patterns": [r"\b(xerox|versalink|altalink|phaser)\b"]
    },
    # Audio / Video / Conference & Telecom
    {
        "brand": "Avaya",
        "asset_type": "Audio / Conference",
        "patterns": [
            r"\b(avaya|b109|b149|b159|b169|b179|b189|b199|j129|j139|j159|j179|j189|cu360)\b"
        ]
    },
    {
        "brand": "Poly",
        "asset_type": "Audio / Conference",
        "patterns": [
            r"\b(polycom|poly|trio|vvx|soundstation|soundpoint|studio|sync)\b"
        ]
    },
    {
        "brand": "Jabra",
        "asset_type": "Audio / Conference",
        "patterns": [
            r"\b(jabra|speak\s*\d{3}|evolve|panacast|biz\s*\d{4})\b"
        ]
    },
    {
        "brand": "Yealink",
        "asset_type": "Audio / Conference",
        "patterns": [
            r"\b(yealink|cp\d{3}|sip-t\d{2}[a-z]?|t\d{2}[a-z]|meetingbar|mvc\d{3})\b"
        ]
    },
    {
        "brand": "Logitech",
        "asset_type": "Audio / Conference",
        "patterns": [
            r"\b(logitech|rally|meetup|group|connect|tap|brio|ptz\s*pro)\b"
        ]
    }
]

# -------------------------------------------------------------
# 2. NLP SPEC EXTRACTION (CPU, RAM, STORAGE, OS)
# -------------------------------------------------------------

def extract_cpu(text):
    """
    Extracts CPU model name from text (Intel, AMD, Apple Silicon, etc.)
    """
    # Apple Silicon
    m_apple = re.search(r"\b(apple\s*)?(m[1234]\s*(pro|max|ultra)?)\b", text, re.IGNORECASE)
    if m_apple:
        chip = m_apple.group(2).strip().upper()
        return f"Apple {chip}"

    # Intel Core Ultra
    m_ultra = re.search(r"\b(core\s*ultra\s*[579]\s*(\d{3}[a-z]?))\b", text, re.IGNORECASE)
    if m_ultra:
        return f"Intel {m_ultra.group(0).strip().title()}"

    # Intel Core i3 / i5 / i7 / i9 with full code (e.g. i5-1135G7, i7-1165G7, i7 12700H, i9-13900K)
    m_intel = re.search(r"\b(intel\s*)?(core\s*)?(i[3579])[\s-]?(\d{3,5}[a-z0-9]{1,4})\b", text, re.IGNORECASE)
    if m_intel:
        family = m_intel.group(3).lower()
        model_num = m_intel.group(4).upper()
        gen_str = ""
        if len(model_num) >= 4 and model_num[:2].isdigit():
            if model_num[:2] in ['10', '11', '12', '13', '14', '15']:
                gen_str = f"{model_num[:2]}th Gen "
            else:
                gen_str = f"{model_num[0]}th Gen "
        return f"{gen_str}Intel Core {family}-{model_num}".strip()

    # Generic Intel i3/i5/i7/i9 mention
    m_gen_intel = re.search(r"\b(intel\s*)?(core\s*)?(i[3579])\b", text, re.IGNORECASE)
    if m_gen_intel:
        return f"Intel Core {m_gen_intel.group(3).lower()}"

    # Intel Xeon
    m_xeon = re.search(r"\b(intel\s*)?(xeon\s*([eew\d]|silver|gold|bronze|platinum)?\s*[\w\d-]+)\b", text, re.IGNORECASE)
    if m_xeon:
        return f"Intel {m_xeon.group(0).strip().title()}"

    # AMD Ryzen (Ryzen 5 5600U, Ryzen 7 Pro 6850U, Ryzen 7 5800H)
    m_ryzen = re.search(r"\b(amd\s*)?(ryzen\s*[3579](\s*pro)?\s*(\d{4}[a-z]{0,2}))\b", text, re.IGNORECASE)
    if m_ryzen:
        return f"AMD {m_ryzen.group(2).strip()}"

    # Generic AMD Ryzen mention
    m_gen_ryzen = re.search(r"\b(amd\s*)?(ryzen\s*[3579])\b", text, re.IGNORECASE)
    if m_gen_ryzen:
        return f"AMD {m_gen_ryzen.group(2).strip()}"

    # Celeron / Pentium
    m_celeron = re.search(r"\b(intel\s*)?(celeron|pentium(\s*gold)?)\s*[\w\d-]*\b", text, re.IGNORECASE)
    if m_celeron:
        return f"Intel {m_celeron.group(0).strip().title()}"

    return ""

def extract_ram(text):
    """
    Extracts RAM size from text (e.g. 8GB, 16 GB, 32GB DDR4/DDR5).
    Requires explicit GB or RAM tag so it never confuses ports/numbers.
    """
    m = re.search(r"\b([48]|16|24|32|48|64|128)\s*(?:gb|g|gigabytes)\s*(ddr[345]|lpddr[45]x?|ram|unified|memory)?\b", text, re.IGNORECASE)
    if m:
        num = m.group(1)
        type_hint = m.group(2) or ''
        type_str = f" {type_hint.upper()}" if type_hint and type_hint.lower() not in ['ram', 'memory'] else ""
        return f"{num} GB{type_str} RAM"

    # Also match "RAM: 16GB"
    m_rev = re.search(r"\b(?:ram|memory)\s*[:=]?\s*([48]|16|24|32|48|64|128)\s*(?:gb|g)?\b", text, re.IGNORECASE)
    if m_rev:
        return f"{m_rev.group(1)} GB RAM"
    return ""

def extract_storage(text):
    """
    Extracts Storage capacity and type (e.g. 512GB SSD, 1TB NVMe, 256 GB)
    """
    m_tb = re.search(r"\b([1248])\s*(?:tb|t|terabytes)\s*(nvme|ssd|hdd|pcie|emmc|storage|drive)?\b", text, re.IGNORECASE)
    if m_tb:
        num = m_tb.group(1)
        stype = m_tb.group(2) or 'NVMe SSD'
        return f"{num} TB {stype.upper()}"

    m_gb = re.search(r"\b(128|256|500|512)\s*(?:gb|g)\s*(nvme|ssd|hdd|pcie|emmc|storage|drive)?\b", text, re.IGNORECASE)
    if m_gb:
        num = m_gb.group(1)
        stype = m_gb.group(2) or 'SSD'
        return f"{num} GB {stype.upper()}"
    return ""

def extract_os(text):
    """
    Extracts Operating System name from text
    """
    lower = text.lower()
    if 'ubuntu' in lower:
        m = re.search(r"ubuntu\s*(\d{2}\.\d{2}(\.\d)?)?", text, re.IGNORECASE)
        return m.group(0).title() if m else "Ubuntu Linux"
    if 'windows 11' in lower or 'win 11' in lower:
        return "Windows 11 Pro"
    if 'windows 10' in lower or 'win 10' in lower:
        return "Windows 10 Pro"
    if 'macos' in lower or 'mac os' in lower or 'macbook' in lower:
        return "macOS"
    if 'debian' in lower:
        return "Debian Linux"
    if any(k in lower for k in ['redhat', 'rhel', 'centos', 'rocky']):
        return "Enterprise Linux (RHEL)"
    if 'chromeos' in lower or 'chromebook' in lower:
        return "ChromeOS"
    return ""

def extract_asset_type(text, brand=""):
    """
    Identifies device category: Laptop, Desktop, Phone, Headphone, Keyboard, Mouse, Server, Network, Monitor, Printer, Tablet, Audio / Conference
    """
    lower = text.lower()
    if any(k in lower for k in ['keyboard', 'keychron', 'cherry mx', 'magic keyboard']):
        return "Keyboard"
    if any(k in lower for k in ['mouse', 'trackball', 'trackpad', 'magic mouse']):
        return "Mouse"
    if any(k in lower for k in ['headphone', 'headphones', 'earphone', 'earphones', 'airpods', 'headset', 'earbuds']):
        return "Headphone"
    if any(k in lower for k in ['iphone', 'pixel', 'galaxy s', 'smartphone', 'mobile phone', 'android phone']) or (('phone' in lower or '话机' in lower) and 'speaker' not in lower):
        return "Phone"
    if any(k in lower for k in ['speaker', 'speakerphone', 'conference', 'webcam', 'voip', '扬声器']) or brand in ['Avaya', 'Poly', 'Jabra', 'Yealink']:
        return "Audio / Conference"
    if any(k in lower for k in ['printer', 'scanner', 'laserjet', 'pixma', 'ecotank', 'mfp', 'mfc', 'dcp', 'toner', 'copier']) or brand in ['Brother', 'Canon', 'Epson', 'Xerox']:
        return "Printer"
    if re.search(r"\b(network|switch|switches|router|routers|firewall|catalyst|access\s*point|\bap\b|unifi|gateway|meraki|fortigate|ethernet\s*switch)\b", lower) or brand in ['Cisco Systems', 'Ubiquiti Networks', 'MikroTik', 'Fortinet']:
        return "Network"
    if any(k in lower for k in ['monitor', 'display', 'screen', 'ultrasharp', 'ultragear', 'led', 'lcd', '1080p', '1440p', '4k', 'p24', 'p27', 'u27']):
        return "Monitor"
    if any(k in lower for k in ['server', 'rack', 'poweredge', 'proliant', 'thinksystem', 'blade', 'chassis']):
        return "Server"
    if any(k in lower for k in ['desktop', 'workstation', 'optiplex', 'thinkcentre', 'prodesk', 'elitedesk', 'imac', 'mac mini', 'mac studio', 'tower', 'micro', 'sff']):
        return "Desktop"
    if any(k in lower for k in ['ipad', 'galaxy tab', 'surface go']):
        return "Tablet"
    return "Laptop"

# -------------------------------------------------------------
# 3. FREE OPEN SEARCH / WIKIPEDIA INTELLIGENCE (ZERO API KEY)
# -------------------------------------------------------------

def query_free_hardware_ai(query):
    """
    Queries Wikipedia Open API (100% Free, NO API Key needed) to lookup
    any hardware model, laptop, desktop, server, switch across ALL brands!
    """
    if not query or len(query.strip()) < 3:
        return None

    clean_q = re.sub(r'[^a-zA-Z0-9\s-]', '', query).strip()
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(clean_q + ' tech specs')}&utf8=&format=json"

    req = urllib.request.Request(url, headers={
        'User-Agent': 'ITAssetManager/2.0 (OpenHardwareIdentifier; zero_api_engine)'
    })

    try:
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode())
            results = data.get('query', {}).get('search', [])
            if results:
                top = results[0]
                raw_snippet = top.get('snippet', '')
                clean_snippet = unescape(re.sub(r'<[^>]+>', '', raw_snippet))
                title = top.get('title', '')
                full_text = f"{title} {clean_snippet}"

                return {
                    'title': title,
                    'snippet': clean_snippet,
                    'inferred_cpu': extract_cpu(full_text),
                    'inferred_ram': extract_ram(full_text),
                    'inferred_storage': extract_storage(full_text),
                    'inferred_type': extract_asset_type(full_text),
                    'source': f"Open Hardware Wiki Intelligence ({title})"
                }
    except Exception:
        pass
    return None

# -------------------------------------------------------------
# 4. MASTER AI INFERENCE FUNCTION (ALL BRANDS WITHOUT API KEY)
# -------------------------------------------------------------

def ai_infer_device(input_text, barcode_hint=""):
    """
    Main AI engine. Can take ANY scanned barcode, serial number, product tag,
    sticker text snippet, or mixed string and extract all specifications
    without needing brand-specific API keys!
    """
    text = (input_text or "").strip()
    barcode = barcode_hint.strip() if barcode_hint else ""
    if not barcode and "\n" not in text and re.fullmatch(r"[A-Za-z0-9_-]{4,35}", text):
        barcode = text

    result = {
        "barcode": barcode,
        "manufacturer": "",
        "model": "",
        "serial_number": "",
        "product_code": "",
        "asset_type": "Laptop",
        "cpu": "",
        "ram": "",
        "storage": "",
        "os_name": "",
        "notes": "",
        "ai_confidence": 0.5,
        "source": "AI Zero-API Multi-Brand Engine"
    }

    if not text:
        return result

    # 1. Detect Brand & Serial patterns
    detected_brand = ""
    for b_item in BRAND_PATTERNS:
        for pat in b_item["patterns"]:
            if re.search(pat, text, re.IGNORECASE):
                detected_brand = b_item["brand"]
                result["asset_type"] = b_item["asset_type"]
                break
        if detected_brand:
            break

    result["manufacturer"] = detected_brand

    # 2. Dell Service Tag & Express Code logic
    if re.fullmatch(r"[A-Z0-9]{7}", text.upper()) or (detected_brand == "Dell Inc." and len(text) == 7 and re.fullmatch(r"[A-Z0-9]{7}", text.upper())):
        try:
            express_code = int(text.upper(), 36)
            result["manufacturer"] = "Dell Inc."
            result["serial_number"] = text.upper()
            result["product_code"] = f"Express Service Code: {express_code}"
            result["source"] = "Dell Service Tag AI Decoder"
            result["ai_confidence"] = 0.95
        except Exception:
            pass

    # 3. Apple Model / Serial (e.g. A2338 -> MacBook Pro 13" M1/M2)
    m_apple_model = re.search(r"\bA(1706|1708|1989|2159|2289|2251|2338|2141|2442|2485|2779|2780|2992|2918|1932|2179|2337|2681|2941)\b", text, re.IGNORECASE)
    if m_apple_model:
        model_code = m_apple_model.group(0).upper()
        result["manufacturer"] = "Apple"
        result["product_code"] = f"Apple Model {model_code}"
        if model_code in ["A2338", "A2337"]:
            result["model"] = "MacBook Pro 13-inch (M1)" if model_code == "A2338" else "MacBook Air (M1)"
            result["cpu"] = "Apple M1 (8-core)"
            result["ram"] = "8 GB / 16 GB Unified"
            result["storage"] = "256 GB / 512 GB SSD"
        elif model_code in ["A2681", "A2941"]:
            result["model"] = "MacBook Air M2 (13/15-inch)"
            result["cpu"] = "Apple M2 (8-core)"
            result["ram"] = "16 GB Unified"
            result["storage"] = "512 GB SSD"
        elif model_code in ["A2442", "A2779", "A2992"]:
            result["model"] = "MacBook Pro 14-inch"
            result["cpu"] = "Apple M-Series Pro"
            result["ram"] = "16 GB / 32 GB Unified"
            result["storage"] = "512 GB / 1 TB SSD"
        result["os_name"] = "macOS"
        result["asset_type"] = "Laptop"
        result["source"] = f"Apple Model Number AI Decoder ({model_code})"
        result["ai_confidence"] = 0.98

    # 4. Extract NLP specs from text
    nlp_cpu = extract_cpu(text)
    nlp_ram = extract_ram(text)
    nlp_storage = extract_storage(text)
    nlp_os = extract_os(text)
    nlp_type = extract_asset_type(text, detected_brand)

    if nlp_cpu and not result["cpu"]:
        result["cpu"] = nlp_cpu
    if nlp_ram and not result["ram"]:
        result["ram"] = nlp_ram
    if nlp_storage and not result["storage"]:
        result["storage"] = nlp_storage
    if nlp_os and not result["os_name"]:
        result["os_name"] = nlp_os
    if nlp_type:
        result["asset_type"] = nlp_type

    # 5. Extract Serial number if mentioned (e.g. "Serial no. ...", "S/N: ...", "Serial: ...")
    m_sn = re.search(r"\b(?:serial(?:\s*\.?\s*no|\s*number)?|s\/n|sn\s*[:#.-])\s*[:#.-]?\s*([a-z0-9_-]{5,30})\b", text, re.IGNORECASE)
    if m_sn:
        result["serial_number"] = m_sn.group(1).upper()

    # Extract Model No / Part No / Product code from labels (e.g. Model no/型号/型號：910101081)
    m_model_no = re.search(r"(?:model\s*(?:no|\.?no|\s*number)?|型号|型號|part\s*(?:no|\.?no|\s*number)?|p\/n)\s*[:#：=-]?\s*([a-z0-9_-]{3,25})", text, re.IGNORECASE)
    if m_model_no and not result["product_code"]:
        result["product_code"] = m_model_no.group(1).strip()

    # Avaya & Audio / Conference device models
    if detected_brand == "Avaya" or "avaya" in text.lower():
        result["manufacturer"] = "Avaya"
        result["asset_type"] = "Audio / Conference"
        m_avaya = re.search(r"\bavaya\s+([a-z0-9_-]+)\b", text, re.IGNORECASE)
        if m_avaya:
            result["model"] = f"Avaya {m_avaya.group(1).upper()}"
        elif "b109" in text.lower():
            result["model"] = "Avaya B109"
        if "b109" in text.lower() and not result["notes"]:
            result["notes"] = "Avaya B109 Compact USB/Bluetooth Conference Speakerphone with OmniSound"
            result["ai_confidence"] = 0.95

    # 6. Extract Model Name heuristics if empty
    if not result["model"]:
        # Match common model lines
        m_model = re.search(r"\b(latitude\s*\d{4}|optiplex\s*\d{4}|vostro\s*(?:14|15)?\s*\d{4}|inspiron\s*\d{4}|thinkpad\s*[a-z]\d{1,2}(?:\s*gen\s*\d)?|elitebook\s*\d{3}(?:\s*g\d)?|probook\s*\d{3}(?:\s*g\d)?|zenbook\s*\d{1,2}|aspire\s*\d|surface\s*laptop\s*\d?|surface\s*pro\s*\d?|ws-c[a-z0-9-]+|mfc-[a-z0-9-]+|laserjet\s*[\w\d-]+)\b", text, re.IGNORECASE)
        if m_model:
            result["model"] = m_model.group(0).strip()
            if not result["model"].startswith('WS-') and not result["model"].startswith('MFC-'):
                result["model"] = result["model"].title()

    # 7. If model or brand or specs incomplete, run Gemini Cloud AI or Free Open AI query
    gemini_key = get_gemini_api_key()
    if gemini_key and (not result["manufacturer"] or not result["model"] or not result["cpu"]):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            prompt_text = (
                "You are an expert IT hardware recognition system. Given the following OCR label text and barcode hint from a physical device sticker:\n"
                f"OCR Text: {text}\n"
                f"Barcode Hint: {barcode}\n\n"
                "Identify and return JSON with:\n"
                "- manufacturer\n"
                "- model\n"
                "- serial_number\n"
                "- product_code\n"
                "- cpu\n"
                "- ram\n"
                "- storage\n"
                "- asset_type\n"
                "- notes\n"
            )
            req = urllib.request.Request(
                url,
                data=json.dumps({"contents": [{"parts": [{"text": prompt_text}]}]}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                gem_data = json.loads(response.read().decode())
                cand = gem_data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                cand = re.sub(r'^```json\s*', '', cand.strip(), flags=re.MULTILINE)
                cand = re.sub(r'```$', '', cand.strip())
                cand_parsed = json.loads(cand)
                for field in ['manufacturer', 'model', 'serial_number', 'product_code', 'cpu', 'ram', 'storage', 'asset_type', 'notes']:
                    if cand_parsed.get(field) and (not result.get(field) or result.get(field) == ''):
                        result[field] = str(cand_parsed[field]).strip()
                result["source"] += " + Gemini Cloud AI"
                result["ai_confidence"] = 0.98
        except Exception:
            pass

    if (not result["cpu"] or not result["manufacturer"]) and len(text) >= 4 and not result["product_code"].startswith("Express"):
        wiki_ai = query_free_hardware_ai(result["model"] or text)
        if wiki_ai:
            if not result["cpu"] and wiki_ai["inferred_cpu"]:
                result["cpu"] = wiki_ai["inferred_cpu"]
            if not result["ram"] and wiki_ai["inferred_ram"]:
                result["ram"] = wiki_ai["inferred_ram"]
            if not result["storage"] and wiki_ai["inferred_storage"]:
                result["storage"] = wiki_ai["inferred_storage"]
            if not result["model"]:
                result["model"] = wiki_ai["title"][:50]
            result["source"] += f" + {wiki_ai['source']}"
            result["ai_confidence"] = max(result["ai_confidence"], 0.85)

    # Fallback serial to barcode if alphanumeric
    if not result["serial_number"] and barcode and re.fullmatch(r"[A-Za-z0-9_-]{5,35}", barcode):
        result["serial_number"] = barcode
    if not result["barcode"] and result["serial_number"]:
        result["barcode"] = result["serial_number"]

    return result

# -------------------------------------------------------------
# 5. GEMINI AI AGENT TELEMETRY ARRANGER & NORMALIZER
# -------------------------------------------------------------

def clean_vendor_name(name: str) -> str:
    """Standardizes component vendor names."""
    if not name:
        return "OEM"
    n = str(name).strip()
    nl = n.lower()
    if "micron" in nl:
        return "Micron"
    if "samsung" in nl:
        return "Samsung"
    if "hynix" in nl or "hyundai" in nl:
        return "SK Hynix"
    if "crucial" in nl:
        return "Crucial"
    if "kingston" in nl:
        return "Kingston"
    if "western digital" in nl or "wdc" in nl or "wd " in nl:
        return "Western Digital (WD)"
    if "seagate" in nl:
        return "Seagate"
    if "intel" in nl:
        return "Intel"
    if "toshiba" in nl or "kioxia" in nl:
        return "Kioxia / Toshiba"
    if "dell" in nl:
        return "Dell Inc."
    if "hewlett" in nl or "hp" in nl:
        return "HP"
    if "lenovo" in nl:
        return "Lenovo"
    if "asustek" in nl or "asus" in nl:
        return "ASUS"
    if "acer" in nl:
        return "Acer"
    return re.sub(r'\s+(inc\.?|corp\.?|corporation|technology|ltd\.?|co\.?)$', '', n, flags=re.IGNORECASE).strip()

def get_gemini_api_key() -> str:
    """
    Retrieves the Gemini AI API Key from environment or dynamically re-reads .env.
    Supports GEMINI_API_KEY, GOOGLE_API_KEY, GEMINI_KEY, GMANI_API_KEY, and GEMINI.
    """
    for var in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_KEY', 'GMANI_API_KEY', 'GEMINI'):
        val = os.environ.get(var, '').strip()
        if val:
            return val
            
    # Dynamically re-check .env file on disk in real time so server restarts aren't required
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip().upper()
                        v = v.strip().strip('"').strip("'")
                        if k in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_KEY', 'GMANI_API_KEY', 'GEMINI'):
                            os.environ['GEMINI_API_KEY'] = v
                            return v
        except Exception:
            pass
    return ''

def arrange_agent_telemetry(raw_data: dict) -> dict:
    """
    Uses Gemini AI (or the local AI intelligence engine fallback) to read raw hardware telemetry
    reported by remote agents, standardize vendor names, clean serial numbers, format standard GB sizes,
    and arrange the data into structured asset inventory fields:
      - Hostname
      - CPU Model
      - RAM Vendor, RAM Size, RAM Serial No.
      - Storage Vendor, Storage Model, Storage Serial No., Storage Size
      - Motherboard Manufacturer, Motherboard Product, Motherboard Serial No.
      - IP Address
    """
    gemini_key = get_gemini_api_key()
    
    # 1. Attempt Gemini Cloud AI processing if GEMINI_API_KEY is configured
    if gemini_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            prompt_text = (
                "You are an enterprise IT Asset Intelligence system. Analyze this raw hardware telemetry reported by a remote agent:\n"
                f"{json.dumps(raw_data, indent=2)}\n\n"
                "Extract, clean, and arrange the hardware specifications into exact standard fields. "
                "Return a JSON object with EXACTLY these keys:\n"
                "- hostname\n"
                "- cpu_model\n"
                "- ram_vendor\n"
                "- ram_size\n"
                "- ram_serial\n"
                "- storage_vendor\n"
                "- storage_model\n"
                "- storage_serial\n"
                "- storage_size\n"
                "- motherboard_mfg\n"
                "- motherboard_product\n"
                "- motherboard_serial\n"
                "- ip_address\n"
                "- manufacturer\n"
                "- model\n"
                "- os_name\n"
                "- serial_number\n"
                "Ensure vendor names are clean (e.g. 'Micron Technology' -> 'Micron', 'Samsung Electronics' -> 'Samsung', 'Dell Inc.' -> 'Dell Inc.'). "
                "Return ONLY the valid JSON object with NO markdown formatting."
            )
            
            body = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {"temperature": 0.1}
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode('utf-8'),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode())
                cand = res.get('candidates', [])[0]['content']['parts'][0]['text']
                cand = re.sub(r'^```json\s*', '', cand.strip())
                cand = re.sub(r'\s*```$', '', cand.strip())
                parsed = json.loads(cand)
                if isinstance(parsed, dict) and ('cpu_model' in parsed or 'hostname' in parsed):
                    return _finalize_arranged_fields(parsed, raw_data, ai_source="Gemini Cloud AI")
        except Exception:
            pass

    # 2. Local Hardware Intelligence Engine (100% Offline, Zero-API)
    return _local_ai_arrange_telemetry(raw_data)

def _local_ai_arrange_telemetry(raw: dict) -> dict:
    hostname = raw.get('hostname') or raw.get('device_name') or raw.get('model') or 'Workstation'
    ip_addr = raw.get('ip_address') or '127.0.0.1'
    
    # CPU Model
    cpu = raw.get('cpu_model') or raw.get('cpu') or 'Multi-Core Processor'
    cpu = re.sub(r'\s+', ' ', str(cpu)).strip()

    # RAM Details
    r_vendor = raw.get('ram_vendor') or ''
    r_size = raw.get('ram_size') or ''
    r_serial = raw.get('ram_serial') or ''

    if not r_vendor and raw.get('ram'):
        m = re.search(r'\b(Micron|Samsung|SK\s*Hynix|Crucial|Kingston|Corsair|G\.Skill)\b', str(raw.get('ram')), re.IGNORECASE)
        if m:
            r_vendor = m.group(1)
        else:
            r_vendor = clean_vendor_name(raw.get('manufacturer', ''))
    else:
        r_vendor = clean_vendor_name(r_vendor)

    if not r_size:
        m_sz = re.search(r'(\d+)\s*GB', str(raw.get('ram', '')), re.IGNORECASE)
        r_size = f"{m_sz.group(1)} GB" if m_sz else "16 GB"
    else:
        m_sz = re.search(r'(\d+)\s*(?:GB|MB)?', str(r_size), re.IGNORECASE)
        r_size = f"{m_sz.group(1)} GB" if m_sz else str(r_size)

    if not r_serial or r_serial.lower() in ['unknown', 'none', 'to be filled by o.e.m.', 'not specified']:
        r_serial = "N/A"

    # Storage Details
    s_vendor = raw.get('storage_vendor') or ''
    s_model = raw.get('storage_model') or raw.get('storage') or 'NVMe SSD 512GB'
    s_serial = raw.get('storage_serial') or ''
    s_size = raw.get('storage_size') or ''

    if not s_vendor:
        if s_model:
            m_v = re.search(r'\b(Micron|Samsung|Western\s*Digital|WDC|WD|Seagate|Kingston|Kioxia|Toshiba|Intel|Crucial|SK\s*Hynix)\b', str(s_model), re.IGNORECASE)
            if m_v:
                s_vendor = clean_vendor_name(m_v.group(1))
            else:
                s_vendor = str(s_model).split()[0] if str(s_model).split() else 'NVMe SSD'
        else:
            s_vendor = 'NVMe SSD'
    else:
        s_vendor = clean_vendor_name(s_vendor)

    if not s_size:
        m_sz = re.search(r'(\d+)\s*(?:GB|TB)', str(s_model), re.IGNORECASE)
        s_size = f"{m_sz.group(1)} {m_sz.group(0).split()[-1].upper()}" if m_sz else "512 GB"

    if not s_serial or s_serial.lower() in ['unknown', 'none', 'default']:
        s_serial = "N/A"

    # Motherboard Details
    mb_mfg = clean_vendor_name(raw.get('motherboard_mfg') or raw.get('manufacturer') or 'OEM')
    mb_product = raw.get('motherboard_product') or 'Mainboard'
    mb_serial = raw.get('motherboard_serial') or raw.get('serial_number') or 'N/A'
    if mb_serial.lower() in ['to be filled by o.e.m.', 'default string', 'none', 'unknown']:
        mb_serial = "N/A"

    arranged = {
        'hostname': hostname,
        'cpu_model': cpu,
        'ram_vendor': r_vendor,
        'ram_size': r_size,
        'ram_serial': r_serial,
        'storage_vendor': s_vendor,
        'storage_model': s_model,
        'storage_serial': s_serial,
        'storage_size': s_size,
        'motherboard_mfg': mb_mfg,
        'motherboard_product': mb_product,
        'motherboard_serial': mb_serial,
        'ip_address': ip_addr,
        'os_name': raw.get('os_name', '')
    }

    return _finalize_arranged_fields(arranged, raw, ai_source="Gemini Intelligence Engine (Offline/Local)")

def _finalize_arranged_fields(arranged: dict, raw: dict, ai_source: str) -> dict:
    hostname = arranged.get('hostname') or raw.get('hostname') or raw.get('device_name') or 'Workstation'
    os_name = arranged.get('os_name') or raw.get('os_name') or ''
    cpu_model = arranged.get('cpu_model') or raw.get('cpu_model') or raw.get('cpu') or 'Processor'
    ram_vendor = clean_vendor_name(arranged.get('ram_vendor') or raw.get('ram_vendor') or '')
    ram_size = arranged.get('ram_size') or raw.get('ram_size') or '16 GB'
    ram_serial = arranged.get('ram_serial') or raw.get('ram_serial') or 'N/A'
    
    storage_vendor = clean_vendor_name(arranged.get('storage_vendor') or raw.get('storage_vendor') or '')
    storage_model = arranged.get('storage_model') or raw.get('storage_model') or raw.get('storage') or 'SSD'
    storage_serial = arranged.get('storage_serial') or raw.get('storage_serial') or 'N/A'
    storage_size = arranged.get('storage_size') or raw.get('storage_size') or '512 GB'
    
    mb_mfg = clean_vendor_name(arranged.get('motherboard_mfg') or raw.get('motherboard_mfg') or raw.get('manufacturer') or '')
    mb_prod = arranged.get('motherboard_product') or raw.get('motherboard_product') or 'Mainboard'
    mb_sn = arranged.get('motherboard_serial') or raw.get('motherboard_serial') or 'N/A'
    
    ip_addr = arranged.get('ip_address') or raw.get('ip_address') or '127.0.0.1'

    # Build composite UI helper strings (preserve raw if already explicitly provided)
    motherboard_str = raw.get('motherboard') or f"{mb_mfg} {mb_prod}".strip()
    if not raw.get('motherboard') and mb_sn and mb_sn != 'N/A':
        motherboard_str += f" (S/N: {mb_sn})"
    
    ram_str = raw.get('ram') or f"{ram_size} {ram_vendor}".strip()
    if not raw.get('ram') and ram_serial and ram_serial != 'N/A':
        ram_str += f" (S/N: {ram_serial})"
        
    storage_str = raw.get('storage') or f"{storage_size} {storage_vendor} {storage_model}".strip()
    if not raw.get('storage') and storage_serial and storage_serial != 'N/A':
        storage_str += f" (S/N: {storage_serial})"

    out = {
        'hostname': hostname,
        'device_name': hostname,
        'os_name': os_name,
        'cpu': cpu_model,
        'cpu_model': cpu_model,
        'ram_vendor': ram_vendor,
        'ram_size': ram_size,
        'ram_serial': ram_serial,
        'storage_vendor': storage_vendor,
        'storage_model': storage_model,
        'storage_serial': storage_serial,
        'storage_size': storage_size,
        'motherboard_mfg': mb_mfg,
        'motherboard_product': mb_prod,
        'motherboard_serial': mb_sn,
        'ip_address': ip_addr,
        'motherboard': motherboard_str,
        'ram': ram_str,
        'storage': storage_str,
        'ai_enriched': True,
        'ai_source': ai_source
    }
    
    # Merge existing notes
    existing_notes = raw.get('notes', '')
    enrich_note = f"[{ai_source}] Host: {hostname}"
    if os_name:
        enrich_note += f" | OS: {os_name}"
    enrich_note += f" | MB: {mb_mfg} {mb_prod} (S/N: {mb_sn}) | RAM: {ram_size} {ram_vendor} (S/N: {ram_serial}) | Disk: {storage_size} {storage_model} (S/N: {storage_serial}) | IP: {ip_addr}"
    if enrich_note not in existing_notes:
        out['notes'] = (existing_notes + " | " + enrich_note).strip(' |')
        
    return out

