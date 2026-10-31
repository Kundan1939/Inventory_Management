# 🚀 IT Asset Manager v2 — Automated Hardware & Barcode Tracking

Complete IT Asset Management system built for Ubuntu / Linux with **Flask**, **live camera scanning (1D/2D)**, **hardware auto-discovery**, **SQLite database**, and **custom-styled Excel (.xlsx) export**.

---

## ✨ Features

1. **📷 Barcode & QR Camera Scanning**:
   - Supports existing device barcodes (Code 128, Code 39, EAN-13, UPC, Codabar) and 2D QR codes / DataMatrix.
   - Built-in audio feedback (Web Audio API synth beep on successful scan).
   - Camera switcher (environment/rear vs. front webcam).
   - **File / Image Scanner**: Upload/drop a photo of a barcode or serial label if camera is unavailable.

2. **🤖 Zero-API AI Hardware Intelligence Engine (All Brands)**:
   - **No Paid or Vendor API Keys Required**: You don't need Dell, HP, Lenovo, or OpenAI API keys.
   - **Multi-Brand Pattern & NLP Extractor**: Automatically parses text, model names, and stickers across **Apple, Dell, HP, Lenovo, ASUS, Acer, Microsoft Surface, Samsung, Dynabook/Toshiba, MSI, LG, Cisco, Ubiquiti, Brother, Canon, Epson**.
   - **Automated Spec Extraction**: Extracts CPU (Intel, AMD Ryzen, Apple M-series), RAM, Storage, OS, Serial number, and Asset Type.
   - **Free Open Web Intelligence**: Queries free, non-authenticated open knowledge bases (Wikipedia/Wikidata/GTIN) when specs need deeper technical details.
   - **One-Click Local Ubuntu Auto-Detect**: Instantly inspects the current Ubuntu machine (`/sys/class/dmi`, `/proc/cpuinfo`, `/proc/meminfo`, disk sizes, network interfaces) and auto-populates all specs.
   - **Dell Service Tag Decoder**: Automatically recognizes 7-character Dell tags and computes the Dell Express Service Code.
   - **Lenovo & HP Serial Recognizers**: Auto-detects ThinkPad MTM / serial formats and HP serials.
   - **MAC Address OUI Resolver**: Converts scanned MAC address barcodes into hardware manufacturer names.

3. **💻 Remote Workstation Auto-Enrollment (`agent.py` & `agent.sh`)**:
   - One-line command to auto-register any Ubuntu machine across your network:
     ```bash
     curl -sSL http://<SERVER_IP>:5000/agent.sh | sudo bash -s -- --key <YOUR_API_KEY>
     ```

4. **📋 Modern Inventory Dashboard**:
   - Live KPI cards: Total, Available, Assigned, In Repair, Retired.
   - Real-time instant search and filtering by category or status.
   - Quick one-click status transitions on table rows.
   - Delete confirmation.

5. **📊 Formatted Excel Export**:
   - Generates `.xlsx` spreadsheets with colored headers, proper column auto-widths, freeze panes, and status color highlights.

---

## 🚀 Quick Start on Ubuntu

### 1. Run the Server

#### Option A: With Docker & Docker Compose (Recommended)
```bash
# Start in the background with persistent SQLite storage
docker compose up -d --build

# View real-time container logs
docker compose logs -f

# Stop the container
docker compose down
```

#### Option B: Standalone Docker Run
```bash
# Build the image
docker build -t it-asset-manager:latest .

# Run with local data directory mounted for persistence
docker run -d \
  --name it-asset-manager \
  --restart unless-stopped \
  -p 5000:5000 \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  it-asset-manager:latest
```

#### Option C: Native Python Environment
```bash
cd "it-asset-manager-v2"
source .venv/bin/activate
python app.py
```

The application runs on `http://127.0.0.1:5000` (and on your local network IP `http://192.168.0.x:5000`).

### 2. Connect to the Dashboard
1. Open `http://127.0.0.1:5000` in Google Chrome or Firefox.
2. Enter your `ASSET_API_KEY` (saved in `.env`) and click **Connect**.
3. The dashboard connects and automatically remembers your session.

### 3. Run Automated Tests
```bash
# Inside Docker:
docker run --rm it-asset-manager:latest pytest -v tests/test_asset_manager.py

# Or in native virtualenv:
.venv/bin/pytest -v tests/test_asset_manager.py
```
*(All 15 unit & integration test scenarios pass with 100% success rate)*.

---

## 🔒 Configuration

Settings are saved in `.env`:
```ini
ASSET_API_KEY=fnbmzfeaC_EIfPhFi8Eamy4bfdORcsdD7bWPJCKyTWY
ASSET_DB=data/assets.db
PORT=5000
```
