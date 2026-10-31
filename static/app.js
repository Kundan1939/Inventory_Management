/**
 * IT Asset Manager — Enterprise Frontend Application
 * Multi-View Single-Page Architecture: Dashboard, Inventory, Scan, Register, Reports, Settings
 */

const $ = id => document.getElementById(id);

let html5QrCode = null;
let isScanning = false;
let currentFilter = 'All';
let currentType = 'All';
let currentOs = 'All';
let searchDebounce = null;
let availableCameras = [];
let selectedCameraId = null;
let currentActiveView = 'dashboard';

// Human-readable titles for navigation & breadcrumbs
const VIEW_TITLES = {
  dashboard: 'Dashboard',
  inventory: 'Asset Inventory',
  scan: 'Scan Barcode',
  register: 'Register Asset',
  reports: 'Reports',
  settings: 'Settings'
};

function getOsIconSvg(osName) {
  const osLower = (osName || '').toLowerCase();
  if (osLower.includes('win')) {
    return `<svg class="os-svg-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.902-1.799"/></svg>`;
  } else if (osLower.includes('mac') || osLower.includes('apple') || osLower.includes('darwin')) {
    return `<svg class="os-svg-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.37c.61-.75 1.04-1.8 0.92-2.87-.9.04-2 .6-2.64 1.35-.57.65-1.06 1.73-.93 2.76 1.01.08 2.03-.5 2.65-1.24z"/></svg>`;
  } else {
    return `<svg class="os-svg-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`;
  }
}


// Safe format codes for Html5Qrcode
// [0=AZTEC, 1=CODABAR, 2=CODE_39, 3=CODE_93, 4=CODE_128, 5=DATA_MATRIX, 6=EAN_8, 7=EAN_13, 8=ITF, 10=PDF_417, 11=QR_CODE, 12=UPC_A, 13=UPC_E]
const ALL_BARCODE_FORMATS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13];

// Ensure global Html5QrcodeSupportedFormats exists to prevent ReferenceError
if (typeof window !== 'undefined') {
  if (window.__Html5QrcodeLibrary__ && window.__Html5QrcodeLibrary__.Html5QrcodeSupportedFormats) {
    window.Html5QrcodeSupportedFormats = window.__Html5QrcodeLibrary__.Html5QrcodeSupportedFormats;
  }
}

// Crisp Sound Effects via Web Audio API (100% offline)
function playBeep(type = 'success') {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (type === 'success') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(1046.5, ctx.currentTime);
      osc.frequency.setValueAtTime(1318.5, ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.22);
      osc.start();
      osc.stop(ctx.currentTime + 0.24);
    } else {
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(220, ctx.currentTime);
      gain.gain.setValueAtTime(0.18, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
      osc.start();
      osc.stop(ctx.currentTime + 0.3);
    }
  } catch (e) {}
}

// Enterprise Toast Notifications
function toast(message, type = 'info') {
  const el = $('toast');
  if (!el) return;
  el.textContent = message;
  el.className = `show ${type}`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => {
    el.className = '';
  }, 4500);
}

// Direct, seamless API Helper (Zero manual key required)
async function api(path, options = {}) {
  const headers = {
    'X-Web-UI': '1',
    ...(options.body ? { 'Content-Type': 'application/json' } : {})
  };

  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    toast('Session error: unauthorized request', 'error');
    throw new Error('Unauthorized');
  }

  let data = null;
  const contentType = res.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    data = await res.json();
  }

  if (!res.ok) {
    const errorMsg = (data && data.error) ? data.error : `HTTP ${res.status}`;
    toast(errorMsg, 'error');
    throw new Error(errorMsg);
  }

  return data;
}

// =============================================================================
// NAVIGATION & VIEW SWITCHING
// =============================================================================

function switchView(viewName) {
  if (!VIEW_TITLES[viewName]) viewName = 'dashboard';
  currentActiveView = viewName;
  window.location.hash = viewName;

  // Update navigation items in sidebar
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.dataset.view === viewName);
  });

  // Toggle view containers
  document.querySelectorAll('.app-view').forEach(view => {
    view.classList.toggle('active', view.id === `view-${viewName}`);
  });

  // Update topbar breadcrumb text
  const breadcrumb = $('activeBreadcrumb');
  if (breadcrumb) {
    breadcrumb.textContent = VIEW_TITLES[viewName];
  }

  // Close mobile sidebar if open
  const sidebar = $('appSidebar');
  if (sidebar && sidebar.classList.contains('open')) {
    sidebar.classList.remove('open');
  }

  // Unconditionally release camera stream when navigating away from scan view
  if (viewName !== 'scan' && isScanning) {
    stopCamera();
  }

  // View-specific data loading
  if (viewName === 'inventory') {
    loadAssets();
  } else if (viewName === 'dashboard') {
    loadStats();
    loadRecentAssets();
  } else if (viewName === 'reports') {
    renderReportsView();
  } else if (viewName === 'settings') {
    refreshDynamicNetworkIp();
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleMobileSidebar() {
  const sidebar = $('appSidebar');
  if (sidebar) {
    sidebar.classList.toggle('open');
  }
}

// =============================================================================
// CAMERA & SCANNER ENGINE
// =============================================================================

// Populate Camera Selector
async function populateCameras() {
  const select = $('cameraSelect');
  if (!select) return;

  const Html5QrcodeClass = window.Html5Qrcode || (window.__Html5QrcodeLibrary__ && window.__Html5QrcodeLibrary__.Html5Qrcode);
  if (!Html5QrcodeClass || !Html5QrcodeClass.getCameras) {
    select.innerHTML = '<option value="">Default Environment Camera</option>';
    return;
  }

  try {
    const devices = await Html5QrcodeClass.getCameras();
    availableCameras = devices || [];
    select.innerHTML = '';

    if (availableCameras.length === 0) {
      select.innerHTML = '<option value="">No physical cameras found (Upload works)</option>';
      return;
    }

    availableCameras.forEach((cam, i) => {
      const opt = document.createElement('option');
      opt.value = cam.id;
      opt.textContent = cam.label || `Camera ${i + 1}`;
      select.appendChild(opt);
    });

    selectedCameraId = availableCameras[0].id;
  } catch (err) {
    select.innerHTML = '<option value="">Camera access restricted or default</option>';
  }
}

function switchCamera(cameraId) {
  selectedCameraId = cameraId;
  if (isScanning) {
    stopCamera().then(() => startCamera());
  }
}

// Toggle Camera Scanner
async function toggleCamera() {
  if (isScanning) {
    await stopCamera();
  } else {
    await startCamera();
  }
}

async function startCamera() {
  const Html5QrcodeClass = window.Html5Qrcode || (window.__Html5QrcodeLibrary__ && window.__Html5QrcodeLibrary__.Html5Qrcode);
  if (!Html5QrcodeClass) {
    toast('Scanner library initializing, please retry...', 'info');
    return;
  }

  const viewport = $('scanner-viewport');
  if (viewport) viewport.classList.add('active');

  try {
    html5QrCode = new Html5QrcodeClass("reader", {
      formatsToSupport: ALL_BARCODE_FORMATS,
      verbose: false
    });

    const cameraConfig = selectedCameraId ? selectedCameraId : { facingMode: "environment" };

    await html5QrCode.start(
      cameraConfig,
      {
        fps: 25,
        qrbox: (viewWidth, viewHeight) => {
          const w = Math.floor(Math.min(viewWidth * 0.9, 450));
          const h = Math.floor(Math.min(viewHeight * 0.65, 260));
          return { width: Math.max(w, 250), height: Math.max(h, 150) };
        },
        aspectRatio: 1.3333,
        experimentalFeatures: {
          useBarCodeDetectorIfSupported: true
        }
      },
      onBarcodeDetected,
      (err) => {}
    );

    isScanning = true;
    $('btnToggleCamera').textContent = 'Stop Camera';
    $('btnToggleCamera').className = 'btn btn-danger btn-sm';
    if ($('btnCaptureFrame')) $('btnCaptureFrame').style.display = 'block';
    toast('Camera active — Aim at device barcode or serial label', 'info');
  } catch (err) {
    stopCamera();
    toast('Camera error: ' + (err.message || err) + ' (Ensure camera permission is allowed)', 'error');
  }
}

async function stopCamera() {
  if (html5QrCode && isScanning) {
    try {
      await html5QrCode.stop();
      html5QrCode.clear();
    } catch (e) {}
  }
  html5QrCode = null;
  isScanning = false;
  const viewport = $('scanner-viewport');
  if (viewport) viewport.classList.remove('active');
  $('btnToggleCamera').textContent = 'Start Camera Scan';
  $('btnToggleCamera').className = 'btn btn-primary btn-sm';
  if ($('btnCaptureFrame')) $('btnCaptureFrame').style.display = 'none';
}

// Capture current video frame from active camera and run AI OCR
async function captureCameraSnapshot() {
  const video = document.querySelector('#reader video');
  if (!video) {
    toast('Camera is not active. Click "Start Camera Scan" first.', 'warning');
    return;
  }
  toast('Capturing frame & analyzing with AI...', 'info');
  try {
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.92);
    await processImageScan(null, dataUrl);
  } catch (err) {
    console.error('Snapshot error:', err);
    toast('Error capturing camera frame: ' + err.message, 'error');
  }
}

// When Barcode is Detected via Camera
async function onBarcodeDetected(decodedText, decodedResult) {
  if (!decodedText) return;
  playBeep('success');
  await stopCamera();

  const cleanText = decodedText.trim();
  toast(`Scanned: ${cleanText}`, 'success');

  // Set Serial Number & Barcode
  if ($('serial_number')) $('serial_number').value = cleanText;
  if ($('barcode')) $('barcode').value = cleanText;
  if ($('quickBarcodeInput')) $('quickBarcodeInput').value = cleanText;

  // Auto-fetch and fill specs
  const autoFillEnabled = $('autoFillOnScanToggle') ? $('autoFillOnScanToggle').checked : true;
  if (autoFillEnabled) {
    await fetchAndFillDeviceDetails(cleanText);
  }
}

// Scan Barcode & Label from Uploaded Photo/Image
async function scanBarcodeFromFile(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;
  await processImageScan(file, null);
  event.target.value = '';
}

// Universal Image Processor (handles both File upload and Camera Snapshot)
async function processImageScan(file, base64Url) {
  toast('Analyzing image with Server-Side AI & OCR...', 'info');
  try {
    let resp;
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      resp = await fetch('/api/scan/image', {
        method: 'POST',
        headers: { 'X-Web-UI': '1' },
        body: formData
      });
    } else if (base64Url) {
      resp = await fetch('/api/scan/image', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Web-UI': '1'
        },
        body: JSON.stringify({ image_base64: base64Url })
      });
    }

    if (!resp || !resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      throw new Error(errData.error || ('Server error ' + resp.status));
    }

    const res = await resp.json();
    if (!res.ok || !res.device) {
      throw new Error('No barcode or device details detected');
    }

    const dev = res.device;
    const sn = dev.serial_number || dev.barcode;

    if (!sn && !dev.manufacturer && !dev.model) {
      toast('Could not find barcode or serial number on label. Ensure the label is clear.', 'warning');
      return;
    }

    playBeep('success');
    if (isScanning) {
      await stopCamera();
    }

    // Populate Form Fields
    if (sn) {
      if ($('serial_number')) $('serial_number').value = sn;
      if ($('barcode')) $('barcode').value = dev.barcode || sn;
      if ($('quickBarcodeInput')) $('quickBarcodeInput').value = sn;
    }
    if (dev.manufacturer && $('manufacturer')) $('manufacturer').value = dev.manufacturer;
    if (dev.model && $('model')) $('model').value = dev.model;
    if (dev.product_code && $('product_code')) $('product_code').value = dev.product_code;
    if (dev.asset_type && $('asset_type')) $('asset_type').value = dev.asset_type;
    if (dev.cpu && $('cpu')) $('cpu').value = dev.cpu;
    if (dev.ram && $('ram')) $('ram').value = dev.ram;
    if (dev.storage && $('storage')) $('storage').value = dev.storage;
    if (dev.os_name && $('os_name')) $('os_name').value = dev.os_name;
    if (dev.notes && $('notes')) $('notes').value = dev.notes;

    // Update Live Inspector Card on Scan page
    updateInspector(dev);

    const label = `${dev.manufacturer || ''} ${dev.model || 'Device'}`.trim();
    toast(`AI Identified: ${label} (${sn || 'No S/N'})`, 'success');

    // If already in inventory, load existing record
    if (sn) {
      try {
        const existing = await api(`/api/lookup?barcode=${encodeURIComponent(sn)}`);
        if (existing && existing.found && existing.asset) {
          toast(`Found existing asset #${existing.asset.id} in inventory. Loaded current record.`, 'info');
          fillForm(existing.asset);
        }
      } catch (e) {}
    }

  } catch (err) {
    console.error('Scan error:', err);
    toast('Scan failed: ' + (err.message || err), 'error');
  }
}

// Update Live Scan Inspector Card
function updateInspector(dev) {
  if (!dev) return;
  const emptyState = $('inspectorEmptyState');
  const activeContent = $('inspectorActiveContent');
  if (emptyState) emptyState.style.display = 'none';
  if (activeContent) activeContent.style.display = 'block';

  const sn = dev.serial_number || dev.barcode || '';
  const title = ((dev.manufacturer ? dev.manufacturer + ' ' : '') + (dev.model || 'Hardware Device')).trim();
  if ($('inspDeviceTitle')) $('inspDeviceTitle').textContent = title;
  if ($('inspCategoryTitle')) $('inspCategoryTitle').textContent = dev.asset_type || 'Hardware Asset';
  if ($('inspSerial')) $('inspSerial').textContent = sn || '—';
  if ($('inspMfg')) $('inspMfg').textContent = dev.manufacturer || '—';
  if ($('inspModel')) $('inspModel').textContent = dev.model || '—';
  if ($('inspProductCode')) $('inspProductCode').textContent = dev.product_code || '—';
  if ($('inspCpu')) $('inspCpu').textContent = dev.cpu || '—';
  if ($('inspRam')) $('inspRam').textContent = dev.ram || '—';
  if ($('inspStorage')) $('inspStorage').textContent = dev.storage || '—';
  if ($('inspOs')) $('inspOs').textContent = dev.os_name || '—';
  if ($('inspNotesBox')) $('inspNotesBox').textContent = dev.notes || 'Identified with zero-API multi-brand engine.';

  const badge = $('inspectorConfidenceBadge');
  const badgeText = $('inspectorConfidenceText');
  if (badge && badgeText) {
    badge.style.display = 'inline-flex';
    badgeText.textContent = `${Math.round((dev.ai_confidence || 0.95) * 100)}% Match`;
  }
}

function clearInspector() {
  const emptyState = $('inspectorEmptyState');
  const activeContent = $('inspectorActiveContent');
  const badge = $('inspectorConfidenceBadge');
  if (emptyState) emptyState.style.display = 'block';
  if (activeContent) activeContent.style.display = 'none';
  if (badge) badge.style.display = 'none';
}

// Auto-Fetch & Fill Specifications for Any Serial/Barcode
async function fetchAndFillDeviceDetails(serialOrBarcode) {
  const query = (serialOrBarcode || '').trim();
  if (!query) return;

  try {
    toast(`Looking up specifications for ${query}...`, 'info');
    const modelHint = $('model') ? $('model').value.trim() : '';

    const url = `/api/lookup?barcode=${encodeURIComponent(query)}&model=${encodeURIComponent(modelHint)}`;
    const data = await api(url);

    if (data.found && data.asset) {
      fillForm(data.asset);
      $('assetId').value = data.asset.id;
      if ($('formHeaderTitle')) $('formHeaderTitle').textContent = `Edit Asset #${data.asset.id}`;
      $('autoSource').style.display = 'flex';
      $('autoSourceText').textContent = `Existing asset record loaded (#${data.asset.id}) — Mode: Update`;
      updateInspector(data.asset);
      toast(`Existing asset #${data.asset.id} loaded and auto-filled!`, 'success');
      return;
    }

    let specs = data.suggested || { serial_number: query, barcode: query };

    // AI Multi-Brand Engine auto-enrichment
    if (!specs.cpu || !specs.manufacturer || !specs.model) {
      try {
        const aiRes = await api('/api/ai/infer', {
          method: 'POST',
          body: JSON.stringify({ barcode: query, text: `${query} ${modelHint}` })
        });
        if (aiRes && aiRes.inferred) {
          for (const k of ['manufacturer', 'model', 'cpu', 'ram', 'storage', 'serial_number', 'product_code', 'asset_type', 'os_name']) {
            if (!specs[k] && aiRes.inferred[k]) {
              specs[k] = aiRes.inferred[k];
            }
          }
          specs.source = (specs.source || '') + ' + ' + (aiRes.inferred.source || 'AI Multi-Brand Engine');
        }
      } catch (e) {}
    }

    fillForm(specs);
    $('assetId').value = '';
    $('autoSource').style.display = 'flex';
    $('autoSourceText').textContent = `Auto-Enriched: ${specs.source || 'Serial & AI Engine'}`;
    updateInspector(specs);
    toast(`Details auto-filled for ${specs.manufacturer || 'Device'} (${specs.model || query})!`, 'success');
  } catch (err) {
    toast('Notice: ' + err.message, 'info');
  }
}

// Manual lookup trigger
async function lookupBarcode() {
  const serial = ($('serial_number') ? $('serial_number').value.trim() : '') ||
                 ($('quickBarcodeInput') ? $('quickBarcodeInput').value.trim() : '') ||
                 ($('barcode') ? $('barcode').value.trim() : '');

  if (!serial) {
    toast('Please enter or scan a Serial Number first', 'error');
    if ($('serial_number')) $('serial_number').focus();
    return;
  }

  if ($('serial_number')) $('serial_number').value = serial;
  if ($('barcode')) $('barcode').value = serial;
  await fetchAndFillDeviceDetails(serial);
}

// AI Spec Extractor for ALL brands
async function runAiInference() {
  const text = ($('aiTextInput') ? $('aiTextInput').value.trim() : '');
  const serial = ($('serial_number') ? $('serial_number').value.trim() : '') ||
                 ($('quickBarcodeInput') ? $('quickBarcodeInput').value.trim() : '');

  if (!text && !serial) {
    toast('Please enter model, sticker text, or serial number for AI extraction', 'error');
    if ($('aiTextInput')) $('aiTextInput').focus();
    return;
  }

  try {
    toast('AI analyzing device specs across multi-brand database...', 'info');
    const res = await api('/api/ai/infer', {
      method: 'POST',
      body: JSON.stringify({ text, barcode: serial })
    });

    if (res && res.inferred) {
      fillForm(res.inferred);
      $('autoSource').style.display = 'flex';
      $('autoSourceText').textContent = `AI Multi-Brand Engine (${res.inferred.source || 'Zero-API'})`;
      updateInspector(res.inferred);
      playBeep('success');
      toast(`AI auto-filled specs for ${res.inferred.manufacturer || 'Device'} (${res.inferred.model || 'Detected'})!`, 'success');
    }
  } catch (err) {
    toast('AI Extraction failed: ' + err.message, 'error');
  }
}

// Auto-Detect Local Ubuntu PC
async function autoDetectLocalHost() {
  try {
    toast('Scanning local Ubuntu hardware specs...', 'info');
    const res = await api('/api/detect/local');
    if (res && res.specs) {
      fillForm(res.specs);
      $('autoSource').style.display = 'flex';
      $('autoSourceText').textContent = res.specs.source || 'Detected from Ubuntu Host DMI & /proc';
      updateInspector(res.specs);
      playBeep('success');
      toast('Local Ubuntu PC specifications detected and filled!', 'success');
      switchView('register');
    }
  } catch (err) {
    toast('Failed to detect local specs: ' + err.message, 'error');
  }
}

// =============================================================================
// FORM HELPERS & CRUD OPERATIONS
// =============================================================================

const FORM_FIELDS = [
  'serial_number', 'device_name', 'product_code', 'asset_type', 'manufacturer', 'model',
  'motherboard', 'motherboard_mfg', 'motherboard_product', 'motherboard_serial',
  'cpu', 'ram', 'ram_vendor', 'ram_size', 'ram_serial',
  'storage', 'storage_vendor', 'storage_model', 'storage_serial', 'storage_size',
  'os_name', 'ip_address', 'mac_address',
  'assigned_to', 'department', 'location', 'status', 'notes'
];

function fillForm(data) {
  for (const f of FORM_FIELDS) {
    if ($(f)) {
      $(f).value = data[f] ?? '';
    }
  }

  // Sync barcode with serial_number
  const sn = data.serial_number || data.barcode || '';
  if ($('serial_number')) $('serial_number').value = sn;
  if ($('barcode')) $('barcode').value = sn;

  if (!data.status && $('status')) {
    $('status').value = 'Available';
  }
  if (!data.asset_type && $('asset_type')) {
    $('asset_type').value = 'Laptop';
  }
}

function clearForm() {
  $('assetForm').reset();
  $('assetId').value = '';
  $('barcode').value = '';
  if ($('formHeaderTitle')) $('formHeaderTitle').textContent = 'Register Asset';
  $('autoSource').style.display = 'none';
  if ($('status')) $('status').value = 'Available';
  if ($('asset_type')) $('asset_type').value = 'Laptop';
}

// Save Asset (Create or Update)
async function saveAsset(e) {
  e.preventDefault();
  const id = $('assetId').value.trim();
  const payload = {};

  for (const f of FORM_FIELDS) {
    if ($(f)) {
      payload[f] = $(f).value.trim();
    }
  }

  // Ensure barcode & serial_number are synced
  const sn = payload.serial_number || $('barcode').value.trim();
  if (!sn) {
    toast('Serial Number / Service Tag is required', 'error');
    if ($('serial_number')) $('serial_number').focus();
    return;
  }
  payload.serial_number = sn;
  payload.barcode = sn;
  payload.barcode_format = 'CODE128';

  const submitBtn = (e && e.target && e.target.querySelector('button[type="submit"]')) || $('saveAssetBtn');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.dataset.origText = submitBtn.innerHTML;
    submitBtn.innerHTML = `<span>Saving...</span>`;
  }

  try {
    if (id) {
      await api(`/api/assets/${id}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      toast(`Asset #${id} updated successfully!`, 'success');
    } else {
      const res = await api('/api/assets', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      toast(`Asset #${res.id} registered successfully!`, 'success');
      clearForm();
    }
    loadStats();
    loadAssets();
    loadRecentAssets();
    switchView('inventory');
  } catch (err) {
    toast(err.message || 'Failed to save asset', 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      if (submitBtn.dataset.origText) {
        submitBtn.innerHTML = submitBtn.dataset.origText;
      }
    }
  }
}

// Delete Asset
async function deleteAsset(id, identifier) {
  if (!confirm(`Are you sure you want to permanently delete asset #${id} (${identifier})?`)) {
    return;
  }
  try {
    await api(`/api/assets/${id}`, { method: 'DELETE' });
    toast(`Asset #${id} deleted`, 'info');
    if ($('assetId').value === String(id)) {
      clearForm();
    }
    loadStats();
    loadAssets();
    loadRecentAssets();
  } catch (err) {
    toast('Delete failed: ' + err.message, 'error');
  }
}

// Quick Status Update
async function updateStatus(id, newStatus) {
  try {
    await api(`/api/quick-status/${id}`, {
      method: 'POST',
      body: JSON.stringify({ status: newStatus })
    });
    toast(`Asset #${id} status changed to ${newStatus}`, 'success');
    loadStats();
    loadAssets();
    loadRecentAssets();
  } catch (err) {
    toast('Failed to change status', 'error');
  }
}

// Edit Asset
async function editAsset(id) {
  try {
    const data = await api(`/api/assets/${id}`);
    if (data && data.asset) {
      fillForm(data.asset);
      $('assetId').value = data.asset.id;
      if ($('formHeaderTitle')) $('formHeaderTitle').textContent = `Edit Asset #${data.asset.id}`;
      $('autoSource').style.display = 'flex';
      $('autoSourceText').textContent = `Editing Record #${data.asset.id} (${data.asset.manufacturer || ''} ${data.asset.model || ''})`;
      switchView('register');
      toast(`Loaded asset #${id} for editing`, 'info');
    }
  } catch (err) {
    toast('Could not load asset: ' + err.message, 'error');
  }
}

// =============================================================================
// KPI STATS & DASHBOARD RECENT ASSETS
// =============================================================================

// Load KPI Stats
async function loadStats() {
  try {
    const data = await api('/api/stats');
    const total = data.total ?? 0;
    const avail = data.available ?? 0;
    const assigned = data.assigned ?? 0;
    const repair = data.repair ?? 0;
    const retired = data.retired ?? 0;

    if ($('statTotal')) $('statTotal').textContent = total;
    if ($('sidebarAssetBadge')) $('sidebarAssetBadge').textContent = total;
    if ($('statAvailable')) $('statAvailable').textContent = avail;
    if ($('statAssigned')) $('statAssigned').textContent = assigned;
    if ($('statRepair')) $('statRepair').textContent = repair;
    if ($('statRetired')) $('statRetired').textContent = retired;

    // Update Overview Card
    if ($('legendAvailable')) $('legendAvailable').textContent = avail;
    if ($('legendAssigned')) $('legendAssigned').textContent = assigned;
    if ($('legendRepair')) $('legendRepair').textContent = repair;
    if ($('legendRetired')) $('legendRetired').textContent = retired;

    if (total > 0) {
      if ($('segAvailable')) $('segAvailable').style.width = `${((avail / total) * 100).toFixed(1)}%`;
      if ($('segAssigned')) $('segAssigned').style.width = `${((assigned / total) * 100).toFixed(1)}%`;
      if ($('segRepair')) $('segRepair').style.width = `${((repair / total) * 100).toFixed(1)}%`;
      if ($('segRetired')) $('segRetired').style.width = `${((retired / total) * 100).toFixed(1)}%`;
    }
  } catch (e) {}
}

// Load Recent Assets for Dashboard View
async function loadRecentAssets() {
  const tbody = $('dashboardRecentTableBody');
  if (!tbody) return;

  try {
    const data = await api('/api/assets?q=&status=All&type=All');
    const assets = (data && data.assets) ? data.assets.slice(0, 6) : [];

    if (assets.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; padding: 24px; color: var(--text-secondary);">
            No assets registered yet. <a href="#register" onclick="switchView('register')" style="color: var(--primary); font-weight: 500; text-decoration: none;">Register first asset &rarr;</a>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = '';
    for (const a of assets) {
      const tr = document.createElement('tr');
      let badgeClass = 'available';
      const st = (a.status || 'Available').toLowerCase();
      if (st.includes('assigned')) badgeClass = 'assigned';
      else if (st.includes('repair')) badgeClass = 'repair';
      else if (st.includes('retired')) badgeClass = 'retired';

      const serialDisplay = a.serial_number || a.barcode || '—';
      const osIcon = getOsIconSvg(a.os_name);

      tr.innerHTML = `
        <td><span class="code-badge">${escapeHtml(serialDisplay)}</span></td>
        <td>
          <div style="font-weight: 600; color: var(--text-main); font-size: 13px;">${escapeHtml(a.manufacturer || '')} ${escapeHtml(a.model || '')}</div>
          ${a.os_name ? `<div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px; display: flex; align-items: center;">${osIcon}<span>${escapeHtml(a.os_name)}</span></div>` : ''}
        </td>
        <td><span style="font-size: 12px; color: var(--text-secondary);">${escapeHtml(a.asset_type || 'Device')}</span></td>
        <td>
          <span class="badge-status ${badgeClass}">
            <span class="dot"></span> ${escapeHtml(a.status || 'Available')}
          </span>
        </td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="editAsset(${a.id})">
            <span>Edit</span>
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color: var(--danger-text);">Failed to load recent assets</td></tr>`;
  }
}

// =============================================================================
// INVENTORY TABLE VIEW
// =============================================================================

async function loadAssets() {
  const q = $('searchInput') ? $('searchInput').value.trim() : '';
  const status = currentFilter;
  const type = currentType;
  const os = currentOs;

  const url = `/api/assets?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}&type=${encodeURIComponent(type)}&os=${encodeURIComponent(os)}`;

  try {
    const data = await api(url);
    const tbody = $('inventoryTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const assets = data.assets || [];
    if ($('inventoryCount')) {
      $('inventoryCount').textContent = `Showing ${assets.length} of ${data.total || 0} assets`;
    }

    if (assets.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align:center; padding: 40px; color: var(--text-secondary);">
            No matching IT assets found. Scan a serial label or auto-detect this Ubuntu machine to get started!
          </td>
        </tr>
      `;
      return;
    }

    for (const a of assets) {
      const tr = document.createElement('tr');

      let badgeClass = 'available';
      const st = (a.status || 'Available').toLowerCase();
      if (st.includes('assigned')) badgeClass = 'assigned';
      else if (st.includes('repair')) badgeClass = 'repair';
      else if (st.includes('retired')) badgeClass = 'retired';

      const serialDisplay = a.serial_number || a.barcode || '—';
      const osIcon = getOsIconSvg(a.os_name);

      // Build Hardware Specs cleanly
      const hasSpecs = Boolean(
        (a.cpu && a.cpu.trim() && a.cpu !== '—') ||
        (a.ram && a.ram.trim() && a.ram !== '—') ||
        (a.ram_size && a.ram_size.trim()) ||
        (a.storage && a.storage.trim() && a.storage !== '—') ||
        (a.storage_size && a.storage_size.trim()) ||
        (a.motherboard && a.motherboard.trim() && a.motherboard !== '—') ||
        (a.motherboard_product && a.motherboard_product.trim())
      );

      let specsHtml = '';
      if (!hasSpecs) {
        specsHtml = `<div class="hw-spec-none">No internal hardware specs (${escapeHtml(a.asset_type || 'Peripheral')})</div>`;
      } else {
        specsHtml = `<div class="hw-specs-container">`;
        if (a.cpu && a.cpu.trim() && a.cpu !== '—') {
          specsHtml += `<div class="hw-spec-cpu" title="${escapeHtml(a.cpu)}"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>${escapeHtml(a.cpu)}</div>`;
        }
        const ramVal = (a.ram_size || a.ram || '').trim();
        if (ramVal && ramVal !== '—') {
          specsHtml += `
            <div class="hw-spec-line" title="RAM: ${escapeHtml(ramVal)}">
              <strong>RAM:</strong> <span>${escapeHtml(ramVal)}</span>${a.ram_vendor ? ` <span class="hw-vendor">[${escapeHtml(a.ram_vendor)}]</span>` : ''}${a.ram_serial && a.ram_serial !== 'N/A' ? ` <span class="hw-serial" title="S/N: ${escapeHtml(a.ram_serial)}">S/N: ${escapeHtml(a.ram_serial)}</span>` : ''}
            </div>
          `;
        }
        const diskVal = (a.storage || a.storage_size || '').trim();
        if (diskVal && diskVal !== '—') {
          specsHtml += `
            <div class="hw-spec-line" title="Disk: ${escapeHtml(diskVal)}">
              <strong>Disk:</strong> <span>${escapeHtml(diskVal)}</span>${a.storage_vendor ? ` <span class="hw-vendor">[${escapeHtml(a.storage_vendor)}]</span>` : ''}${a.storage_serial && a.storage_serial !== 'N/A' ? ` <span class="hw-serial" title="S/N: ${escapeHtml(a.storage_serial)}">S/N: ${escapeHtml(a.storage_serial)}</span>` : ''}
            </div>
          `;
        }
        const boardVal = ([a.motherboard_mfg, a.motherboard_product].filter(Boolean).join(' ') || a.motherboard || '').trim();
        if (boardVal && boardVal !== '—') {
          specsHtml += `
            <div class="hw-spec-line" title="Board: ${escapeHtml(boardVal)}">
              <strong>Board:</strong> <span>${escapeHtml(boardVal)}</span>${a.motherboard_serial && a.motherboard_serial !== 'N/A' ? ` <span class="hw-serial" title="S/N: ${escapeHtml(a.motherboard_serial)}">S/N: ${escapeHtml(a.motherboard_serial)}</span>` : ''}
            </div>
          `;
        }
        specsHtml += `</div>`;
      }

      tr.innerHTML = `
        <td class="inv-col-id" style="font-weight: 600; color: var(--text-secondary); font-size: 12px; text-align: center;">#${a.id}</td>
        <td class="inv-col-serial">
          <span class="serial-badge">${escapeHtml(serialDisplay)}</span>
          ${a.device_name ? `<div class="device-hostname"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>${escapeHtml(a.device_name)}</div>` : ''}
          ${a.product_code ? `<div class="device-subinfo">${escapeHtml(a.product_code)}</div>` : ''}
        </td>
        <td class="inv-col-device">
          <div class="device-model-name">${escapeHtml(a.manufacturer || '')} ${escapeHtml(a.model || '')}</div>
          <div class="device-category">${escapeHtml(a.asset_type || 'Device')}</div>
        </td>
        <td class="inv-col-os">
          ${a.os_name ? `
            <div class="badge-os" title="${escapeHtml(a.os_name)}">
              <span class="os-icon">${osIcon}</span>
              <span class="os-text">${escapeHtml(a.os_name)}</span>
            </div>
          ` : `
            <span style="color: var(--text-muted); font-size: 12px;">—</span>
          `}
        </td>
        <td class="inv-col-mac">
          ${a.mac_address ? `<div class="mac-badge">${escapeHtml(a.mac_address)}</div>` : `<span style="color: var(--text-muted); font-size: 12px;">—</span>`}
          ${a.ip_address ? `<div class="ip-label"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" style="display:inline-block; vertical-align:-1px; margin-right:3px;"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>${escapeHtml(a.ip_address)}</div>` : ''}
        </td>
        <td class="inv-col-specs">
          ${specsHtml}
        </td>
        <td class="inv-col-assign">
          <div class="assign-name">${escapeHtml(a.assigned_to || 'Unassigned')}</div>
          <div class="assign-dept">${escapeHtml(a.department || '')}${a.location ? ' • ' + escapeHtml(a.location) : ''}</div>
        </td>
        <td class="inv-col-status" style="text-align: center;">
          <span class="badge-status ${badgeClass}">
            <span class="dot"></span> ${escapeHtml(a.status || 'Available')}
          </span>
        </td>
        <td class="inv-col-actions" style="text-align: right; white-space: nowrap;">
          <div class="table-action-group">
            <button class="btn btn-secondary btn-sm" onclick="editAsset(${a.id})" title="Edit details">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 12px; height: 12px;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
              <span>Edit</span>
            </button>
            <select class="form-control action-status-select" onchange="updateStatus(${a.id}, this.value)">
              <option value="" disabled selected>Status…</option>
              <option value="Available">Available</option>
              <option value="Assigned">Assigned</option>
              <option value="In Repair">In Repair</option>
              <option value="Retired">Retired</option>
            </select>
            <button class="btn btn-danger btn-sm action-delete-btn" data-id="${a.id}" data-serial="${escapeHtml(serialDisplay)}" onclick="deleteAsset(this.dataset.id, this.dataset.serial)" title="Delete">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 12px; height: 12px;"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {}
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Search debounce
function handleSearchInput() {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(loadAssets, 250);
}

// Filter pills
function setFilter(status) {
  currentFilter = status;
  document.querySelectorAll('.filter-pills .pill-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.status === status);
  });
  loadAssets();
}

function setTypeFilter(type) {
  currentType = type;
  loadAssets();
}

function setOsFilter(os) {
  currentOs = os;
  loadAssets();
}

// =============================================================================
// REPORTS VIEW
// =============================================================================

async function renderReportsView() {
  try {
    const statsData = await api('/api/stats');
    const total = statsData.total || 0;

    // 1. Status table
    const statusTbody = $('reportStatusTableBody');
    if (statusTbody) {
      const statuses = [
        { label: 'Available (In Stock)', count: statsData.available || 0, badge: 'available' },
        { label: 'Assigned (In Use)', count: statsData.assigned || 0, badge: 'assigned' },
        { label: 'In Repair', count: statsData.repair || 0, badge: 'repair' },
        { label: 'Retired', count: statsData.retired || 0, badge: 'retired' }
      ];

      statusTbody.innerHTML = '';
      for (const s of statuses) {
        const pct = total > 0 ? Math.round((s.count / total) * 100) : 0;
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>
            <span class="badge-status ${s.badge}">
              <span class="dot"></span> ${s.label}
            </span>
          </td>
          <td style="font-weight: 600; font-variant-numeric: tabular-nums;">${s.count}</td>
          <td>
            <div style="display: flex; align-items: center; gap: 8px;">
              <div style="flex: 1; height: 6px; background: var(--border-color); border-radius: 3px; overflow: hidden;">
                <div style="width: ${pct}%; height: 100%; background: var(--primary);"></div>
              </div>
              <span style="font-size: 11.5px; color: var(--text-secondary); width: 34px;">${pct}%</span>
            </div>
          </td>
        `;
        statusTbody.appendChild(tr);
      }
    }

    // 2. Categories breakdown
    const catList = $('reportCategoryList');
    if (catList) {
      const byType = statsData.by_type || {};
      const entries = Object.entries(byType);
      if (entries.length === 0) {
        catList.innerHTML = `<div style="color: var(--text-secondary); font-size: 13px;">No category records yet.</div>`;
      } else {
        catList.innerHTML = entries.map(([type, count]) => {
          const pct = total > 0 ? Math.round((count / total) * 100) : 0;
          return `
            <div style="display: flex; flex-direction: column; gap: 3px;">
              <div style="display: flex; justify-content: space-between; font-size: 12.5px;">
                <span style="font-weight: 500; color: var(--text-main);">${escapeHtml(type)}</span>
                <span style="color: var(--text-secondary); font-variant-numeric: tabular-nums;">${count} units (${pct}%)</span>
              </div>
              <div style="height: 6px; background: var(--border-color); border-radius: 3px; overflow: hidden;">
                <div style="width: ${pct}%; height: 100%; background: var(--primary);"></div>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    // 3. Manufacturers breakdown
    const mfgList = $('reportManufacturerList');
    if (mfgList) {
      const byMfg = statsData.by_manufacturer || {};
      const entries = Object.entries(byMfg);
      if (entries.length === 0) {
        mfgList.innerHTML = `<div style="color: var(--text-secondary); font-size: 13px;">No manufacturer records yet.</div>`;
      } else {
        mfgList.innerHTML = entries.map(([mfg, count]) => {
          const pct = total > 0 ? Math.round((count / total) * 100) : 0;
          return `
            <div style="display: flex; flex-direction: column; gap: 3px;">
              <div style="display: flex; justify-content: space-between; font-size: 12.5px;">
                <span style="font-weight: 500; color: var(--text-main);">${escapeHtml(mfg)}</span>
                <span style="color: var(--text-secondary); font-variant-numeric: tabular-nums;">${count} units (${pct}%)</span>
              </div>
              <div style="height: 6px; background: var(--border-color); border-radius: 3px; overflow: hidden;">
                <div style="width: ${pct}%; height: 100%; background: #059669;"></div>
              </div>
            </div>
          `;
        }).join('');
      }
    }
  } catch (e) {}
}

// Excel Export (.xlsx)
function downloadExcel() {
  toast('Preparing Excel (.xlsx) export...', 'info');
  const q = $('searchInput') ? $('searchInput').value.trim() : '';
  const status = currentFilter;
  const type = currentType;
  const os = currentOs;
  window.location.href = `/api/export.xlsx?q=${encodeURIComponent(q)}&status=${encodeURIComponent(status)}&type=${encodeURIComponent(type)}&os=${encodeURIComponent(os)}`;
}

// Remote Agent Modal
let currentTargetMode = 'lan';
let customServerBase = '';

function setCustomServerIp(val) {
  const clean = (val || '').trim();
  if (clean) {
    if (clean.startsWith('http://') || clean.startsWith('https://')) {
      customServerBase = clean.replace(/\/+$/, '');
    } else {
      const port = window.location.port || '5000';
      customServerBase = clean.includes(':') ? `http://${clean}` : `http://${clean}:${port}`;
    }
  } else {
    customServerBase = '';
  }
  if ($('currentServerLabel')) $('currentServerLabel').textContent = getServerBaseUrl();
  updateAgentCommandBoxes();
}

function setServerTarget(mode) {
  currentTargetMode = mode;
  customServerBase = '';
  if ($('customServerIpInput')) $('customServerIpInput').value = '';
  if ($('btnModalLan') && $('btnModalLocal')) {
    if (mode === 'lan') {
      $('btnModalLan').className = 'btn btn-sm btn-primary';
      $('btnModalLocal').className = 'btn btn-sm btn-secondary';
    } else {
      $('btnModalLan').className = 'btn btn-sm btn-secondary';
      $('btnModalLocal').className = 'btn btn-sm btn-primary';
    }
  }
  const base = getServerBaseUrl();
  if ($('currentServerLabel')) $('currentServerLabel').textContent = base;
  updateAgentCommandBoxes();
}

function getServerBaseUrl() {
  if (customServerBase) {
    return customServerBase;
  }
  if (currentTargetMode === 'localhost') {
    const port = window.location.port || '5000';
    return `http://127.0.0.1:${port}`;
  }
  // Check if browser was opened via an explicit LAN IP or host (not 127.0.0.1 and not docker internal 172.x)
  if (window.location.hostname &&
      window.location.hostname !== '127.0.0.1' &&
      window.location.hostname !== 'localhost' &&
      !window.location.hostname.startsWith('172.')) {
    return `${window.location.protocol}//${window.location.host}`;
  }
  if (window.SERVER_LAN_URL && !window.SERVER_LAN_URL.includes('172.') && !window.SERVER_LAN_URL.includes('127.0.0.1')) {
    return window.SERVER_LAN_URL;
  }
  if (window.SERVER_LAN_IP && !window.SERVER_LAN_IP.startsWith('172.') && !window.SERVER_LAN_IP.startsWith('127.')) {
    const port = window.location.port || '5000';
    return `http://${window.SERVER_LAN_IP}:${port}`;
  }
  return `${window.location.protocol}//${window.location.host}`;
}

function getLinuxCommand() {
  const origin = getServerBaseUrl();
  return `curl -sSL ${origin}/agent.sh | sudo bash`;
}

function getWindowsCommand() {
  const origin = getServerBaseUrl();
  return `irm ${origin}/agent.ps1 | iex`;
}

function getMacCommand() {
  const origin = getServerBaseUrl();
  return `curl -sSL ${origin}/agent.sh | bash`;
}

function updateAgentCommandBoxes() {
  const lCmd = getLinuxCommand();
  const wCmd = getWindowsCommand();
  const mCmd = getMacCommand();
  if ($('agentCommandLinux')) $('agentCommandLinux').textContent = lCmd;
  if ($('agentCommandWindows')) $('agentCommandWindows').textContent = wCmd;
  if ($('agentCommandMac')) $('agentCommandMac').textContent = mCmd;
  if ($('settingsAgentCommandLinux')) $('settingsAgentCommandLinux').textContent = lCmd;
  if ($('settingsAgentCommandWindows')) $('settingsAgentCommandWindows').textContent = wCmd;
  if ($('settingsAgentCommandMac')) $('settingsAgentCommandMac').textContent = mCmd;
}

async function refreshDynamicNetworkIp() {
  try {
    const data = await api('/api/network-ip');
    if (data && data.ip && !data.ip.startsWith('172.') && !data.ip.startsWith('127.')) {
      window.SERVER_LAN_IP = data.ip;
      window.SERVER_LAN_URL = data.url;
      if ($('modalLanIpLabel')) $('modalLanIpLabel').textContent = data.ip;
      if ($('btnModalLan')) $('btnModalLan').textContent = `LAN IP (${data.ip})`;
      if ($('currentServerLabel')) $('currentServerLabel').textContent = getServerBaseUrl();
      updateAgentCommandBoxes();
    }
  } catch (e) {}
}

function openAgentModal() {
  if ($('currentServerLabel')) $('currentServerLabel').textContent = getServerBaseUrl();
  updateAgentCommandBoxes();
  $('agentModal').classList.add('active');
  refreshDynamicNetworkIp();
}

function closeAgentModal() {
  $('agentModal').classList.remove('active');
}

function copyMacCommand() {
  navigator.clipboard.writeText(getMacCommand()).then(() => {
    toast('macOS agent command copied! Run in Terminal on your Mac.', 'success');
  }).catch(() => {
    toast('Select text and copy with Cmd+C', 'info');
  });
}

function copyLinuxCommand() {
  navigator.clipboard.writeText(getLinuxCommand()).then(() => {
    toast('Linux agent command copied! Run with sudo on Ubuntu/Linux.', 'success');
  }).catch(() => {
    toast('Select text and copy with Ctrl+C', 'info');
  });
}

function copyWindowsCommand() {
  navigator.clipboard.writeText(getWindowsCommand()).then(() => {
    toast('Windows agent command copied! Run in PowerShell on Windows.', 'success');
  }).catch(() => {
    toast('Select text and copy with Ctrl+C', 'info');
  });
}

function copyAgentCommand() {
  copyLinuxCommand();
}

// =============================================================================
// APPLICATION INITIALIZATION
// =============================================================================

window.addEventListener('DOMContentLoaded', () => {
  // Update Remote Command URLs with dynamic origin
  updateAgentCommandBoxes();

  loadStats();
  loadAssets();
  loadRecentAssets();
  populateCameras();
  refreshDynamicNetworkIp();

  // Route according to initial hash or default to dashboard
  const initialHash = (window.location.hash || '').replace('#', '').trim();
  if (initialHash && VIEW_TITLES[initialHash]) {
    switchView(initialHash);
  } else {
    switchView('dashboard');
  }

  // Hash navigation listener
  window.addEventListener('hashchange', () => {
    const hash = (window.location.hash || '').replace('#', '').trim();
    if (hash && VIEW_TITLES[hash] && hash !== currentActiveView) {
      switchView(hash);
    }
  });

  if ($('serial_number')) {
    $('serial_number').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        lookupBarcode();
      }
    });
  }

  if ($('quickBarcodeInput')) {
    $('quickBarcodeInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if ($('serial_number')) $('serial_number').value = e.target.value;
        lookupBarcode();
      }
    });
  }

  if ($('assetForm')) {
    $('assetForm').addEventListener('submit', saveAsset);
  }

  // Drag and drop for image upload
  const dropzone = $('fileDropzone');
  if (dropzone) {
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = 'var(--primary)';
      dropzone.style.background = 'var(--primary-subtle)';
    });
    dropzone.addEventListener('dragleave', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = '';
      dropzone.style.background = '';
    });
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = '';
      dropzone.style.background = '';
      const files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length > 0) {
        processImageScan(files[0], null);
      }
    });
  }
});
