// OmniStream Pro v2.0.0 — Popup Script

let currentTabId    = null;
let currentTabUrl   = '';
let currentTabHost  = '';
let detectedStreams = [];
let downloadQueue    = [];
let isBridgeOnline  = false;

/* ── DOM refs ─────────────────────────────────────────── */
const $dom = id => document.getElementById(id);
const currentDomainEl    = $dom('currentDomain');
const bridgeStatusEl     = $dom('bridgeStatus');
const bridgeStatusLabel  = $dom('bridgeStatusLabel');
const bridgeTextStatusEl = $dom('bridgeTextStatus');
const appQueueInfoRow    = $dom('appQueueInfoRow');
const appQueueCountEl    = $dom('appQueueCount');
const godModeBtn         = $dom('godModeBtn');
const godBtnText         = $dom('godBtnText');
const detectedCountEl    = $dom('detectedCount');
const queueCountEl       = $dom('queueCount');
const detectedListEl     = $dom('detectedList');
const queueListEl        = $dom('queueList');
const clearDetectedBtn   = $dom('clearDetectedBtn');
const clearQueueBtn      = $dom('clearQueueBtn');
const sendAllDetectedBtn = $dom('sendAllDetectedBtn');
const sendAllToDesktopBtn= $dom('sendAllToDesktopBtn');
const recheckBridgeBtn   = $dom('recheckBridgeBtn');
const remoteDownloadAllBtn = $dom('remoteDownloadAllBtn');
const toastEl            = $dom('toast');

/* ── SVG icons ────────────────────────────────────────── */
const ICONS = {
  download: `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
  queue:    `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  desktop:  `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  curl:     `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
  send:     `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
  remove:   `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`
};

/* ── Toast Helper ─────────────────────────────────────── */
let _toastTimer = null;
function showToast(text, ms = 2400) {
  toastEl.textContent = text;
  toastEl.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => toastEl.classList.remove('show'), ms);
}

function extractFilename(url) {
  try {
    const pathname = new URL(url).pathname;
    const seg = pathname.split('/').filter(Boolean);
    const last = seg[seg.length - 1] || '';
    return last || 'stream';
  } catch {
    const idx = url.lastIndexOf('/');
    const raw = url.substring(idx + 1).split('?')[0];
    return raw || 'stream';
  }
}

function copyText(text, msg = 'Copied to clipboard') {
  navigator.clipboard.writeText(text).then(() => showToast(msg)).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    showToast(msg);
  });
}

function typeTagClass(typeStr = '') {
  const lo = String(typeStr).toLowerCase();
  if (lo.includes('hls') || lo.includes('m3u8')) return 'tag-hls';
  if (lo.includes('dash') || lo.includes('mpd')) return 'tag-dash';
  if (lo.includes('mp4')) return 'tag-mp4';
  if (lo.includes('webm')) return 'tag-webm';
  return 'tag-dash';
}

/* ── Init ─────────────────────────────────────────────── */
async function init() {
  setupTabs();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    currentTabId  = tab.id;
    currentTabUrl = tab.url || '';
    try {
      const u = new URL(currentTabUrl);
      currentTabHost = u.hostname;
      currentDomainEl.textContent = u.hostname;
    } catch {
      currentDomainEl.textContent = 'Active Tab';
    }
    loadDetectedStreams();
  }

  loadDownloadQueue();
  checkBridge();
}

function setupTabs() {
  const btns  = document.querySelectorAll('.tab-btn');
  const panes = document.querySelectorAll('.tab-pane');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      btns.forEach(b  => b.classList.remove('active'));
      panes.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const pane = document.getElementById(btn.dataset.tab);
      if (pane) pane.classList.add('active');
    });
  });
}

/* ── Data loading ─────────────────────────────────────── */
function loadDetectedStreams() {
  if (!currentTabId) return;
  chrome.runtime.sendMessage({ action: 'GET_TAB_MEDIA', tabId: currentTabId }, res => {
    if (res && res.success) {
      detectedStreams = res.list || [];
      renderDetected();
    }
  });
}

function loadDownloadQueue() {
  chrome.storage.local.get(['omnistream_download_queue'], res => {
    downloadQueue = res.omnistream_download_queue || [];
    renderQueue();
  });
}

function saveQueue() {
  chrome.storage.local.set({ omnistream_download_queue: downloadQueue }, renderQueue);
}

function checkBridge() {
  chrome.runtime.sendMessage({ action: 'CHECK_OMNISTREAM_BRIDGE' }, res => {
    if (res && res.connected) {
      isBridgeOnline = true;
      bridgeStatusEl.classList.add('connected');
      bridgeStatusLabel.textContent = 'Desktop: Online';
      bridgeTextStatusEl.textContent = 'Connected (v' + (res.data?.version || '2.0') + ')';
      bridgeTextStatusEl.className = 'status-online';

      if (res.data?.queue_count !== undefined) {
        appQueueInfoRow.style.display = 'flex';
        appQueueCountEl.textContent = `${res.data.queue_count} item(s)`;
      }
    } else {
      isBridgeOnline = false;
      bridgeStatusEl.classList.remove('connected');
      bridgeStatusLabel.textContent = 'Desktop: Offline';
      bridgeTextStatusEl.textContent = 'Disconnected — Launch OmniStream Pro';
      bridgeTextStatusEl.className = 'status-offline';
      appQueueInfoRow.style.display = 'none';
    }
  });
}

/* ── Empty State ──────────────────────────────────────── */
function emptyHTML(title, hint) {
  return `<div class="empty-state">
    <div class="empty-graphic">
      <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="#2a3a55" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="2" width="20" height="20" rx="3"/>
        <line x1="7"  y1="2"  x2="7"  y2="22"/>
        <line x1="17" y1="2"  x2="17" y2="22"/>
        <line x1="2"  y1="12" x2="22" y2="12"/>
        <line x1="2"  y1="7"  x2="7"  y2="7"/>
        <line x1="2"  y1="17" x2="7"  y2="17"/>
        <line x1="17" y1="17" x2="22" y2="17"/>
        <line x1="17" y1="7"  x2="22" y2="7"/>
      </svg>
    </div>
    <div class="empty-title">${title}</div>
    <div class="empty-hint">${hint}</div>
  </div>`;
}

/* ── Render: Detected Streams ─────────────────────────── */
function renderDetected() {
  detectedCountEl.textContent = detectedStreams.length;

  if (detectedStreams.length === 0) {
    detectedListEl.innerHTML = emptyHTML(
      'No media streams detected yet',
      'Play a video on the page, or click <strong>ACTIVATE GOD MODE SCAN</strong> above.'
    );
    return;
  }

  detectedListEl.innerHTML = '';
  detectedStreams.forEach(item => {
    const card = buildStreamCard(item, false);
    detectedListEl.appendChild(card);
  });
}

/* ── Render: Download Queue ───────────────────────────── */
function renderQueue() {
  queueCountEl.textContent = downloadQueue.length;

  if (downloadQueue.length === 0) {
    queueListEl.innerHTML = emptyHTML(
      'Batch queue is empty',
      'Click <strong>+ Queue</strong> on any detected stream to batch them for desktop download.'
    );
    return;
  }

  queueListEl.innerHTML = '';
  downloadQueue.forEach((item, idx) => {
    const card = buildStreamCard(item, true, idx);
    queueListEl.appendChild(card);
  });
}

/* ── Build stream card ────────────────────────────────── */
function buildStreamCard(item, isQueue, queueIndex) {
  const card = document.createElement('div');
  card.className = 'video-card';

  const filename = extractFilename(item.url);
  const tagCls   = typeTagClass(item.type);
  const tagLabel = item.type || 'Stream';

  const safeUrl  = String(item.url).replace(/"/g, '&quot;');
  const safeFile = escapeHtml(item.title || filename);

  let metaChips = '';
  if (item.isGodMode) metaChips += `<span class="meta-chip godmode">GOD MODE</span>`;
  if (item.size > 0)  metaChips += `<span class="meta-chip">${fmtSize(item.size)}</span>`;

  if (!isQueue) {
    card.innerHTML = `
      <div class="card-filename">
        <span class="filename-text" title="${safeUrl}">${safeFile}</span>
        <span class="tag-badge ${tagCls}">${tagLabel}</span>
      </div>
      <div class="card-url-row" title="${safeUrl}">${safeUrl}</div>
      ${metaChips ? `<div class="card-meta">${metaChips}</div>` : ''}
      <div class="card-actions">
        <button class="card-btn btn-desktop" data-action="desktop">
          ${ICONS.send}<span>⚡ Send to OmniStream Pro App</span>
        </button>
        <button class="card-btn btn-queue" data-action="queue">
          ${ICONS.queue}<span>+ Queue</span>
        </button>
        <button class="card-btn btn-download" data-action="download">
          ${ICONS.download}<span>Download</span>
        </button>
        <button class="card-btn btn-curl" data-action="curl">
          ${ICONS.curl}<span>Copy cURL</span>
        </button>
      </div>
    `;
    card.querySelector('[data-action="desktop"]').onclick  = () => actionSendSingleToDesktop(item);
    card.querySelector('[data-action="queue"]').onclick    = () => actionQueue(item);
    card.querySelector('[data-action="download"]').onclick = () => actionDownload(item);
    card.querySelector('[data-action="curl"]').onclick     = () => actionCurl(item);
  } else {
    card.innerHTML = `
      <div class="card-filename">
        <span class="filename-text" title="${safeUrl}">${safeFile}</span>
        <span class="tag-badge ${tagCls}">${tagLabel}</span>
      </div>
      <div class="card-url-row" title="${safeUrl}">${safeUrl}</div>
      <div class="card-actions">
        <button class="card-btn btn-desktop" data-action="desktop">
          ${ICONS.send}<span>⚡ Send to App</span>
        </button>
        <button class="card-btn btn-download" data-action="download">
          ${ICONS.download}<span>Download</span>
        </button>
        <button class="card-btn btn-curl" data-action="curl">
          ${ICONS.curl}<span>Copy cURL</span>
        </button>
        <button class="card-btn btn-remove" data-action="remove">
          ${ICONS.remove}<span>Remove</span>
        </button>
      </div>
    `;
    card.querySelector('[data-action="desktop"]').onclick  = () => actionSendSingleToDesktop(item);
    card.querySelector('[data-action="download"]').onclick = () => actionDownload(item);
    card.querySelector('[data-action="curl"]').onclick     = () => actionCurl(item);
    card.querySelector('[data-action="remove"]').onclick   = () => {
      downloadQueue.splice(queueIndex, 1);
      saveQueue();
      showToast('Removed from queue');
    };
  }

  return card;
}

/* ── Actions ──────────────────────────────────────────── */
function buildPayload(item) {
  return {
    url: item.url,
    title: item.title || extractFilename(item.url),
    curl: item.curl || `curl "${item.url}"`,
    referer: item.referer || currentTabUrl,
    origin: item.origin || '',
    userAgent: item.userAgent || navigator.userAgent,
    headers: item.headers || {},
    size: item.size || 0,
    type: item.type || 'Stream'
  };
}

function actionSendSingleToDesktop(item) {
  const payload = buildPayload(item);
  chrome.runtime.sendMessage({ action: 'SEND_TO_OMNISTREAM', data: payload }, res => {
    if (res && res.success) {
      showToast('✅ Sent to OmniStream Pro App Queue!');
      checkBridge();
    } else {
      showToast('⚠️ Desktop App Offline — Launch OmniStream Pro', 3200);
      copyText(payload.curl, 'cURL command copied to clipboard');
    }
  });
}

function actionQueue(item) {
  if (downloadQueue.some(q => q.url === item.url)) {
    showToast('Already in batch queue');
    return;
  }
  downloadQueue.push({ ...item, addedAt: Date.now() });
  saveQueue();
  showToast('Added to batch queue');
}

function actionDownload(item) {
  const filename = extractFilename(item.url).replace(/[\\/:*?"<>|]/g, '_');
  chrome.runtime.sendMessage({ action: 'DOWNLOAD_FILE', url: item.url, filename }, res => {
    if (res && res.success) showToast('Download started in browser');
    else showToast('Browser download failed — use Send to App or cURL');
  });
}

function actionCurl(item) {
  const cmd = item.curl || `curl "${item.url}"`;
  copyText(cmd, 'cURL command copied to clipboard');
}

/* ── Batch Send Actions (IDM Style) ───────────────────── */
sendAllDetectedBtn.addEventListener('click', () => {
  if (detectedStreams.length === 0) {
    showToast('No detected streams to send');
    return;
  }

  const items = detectedStreams.map(it => buildPayload(it));
  chrome.runtime.sendMessage({ action: 'SEND_BATCH_TO_OMNISTREAM', data: { items } }, res => {
    if (res && res.success) {
      showToast(`🚀 Transferred all ${items.length} streams to Desktop App!`);
      checkBridge();
    } else {
      showToast('⚠️ Desktop App Offline — Launch OmniStream Pro', 3200);
    }
  });
});

sendAllToDesktopBtn.addEventListener('click', () => {
  if (downloadQueue.length === 0) {
    showToast('Queue is empty');
    return;
  }

  const items = downloadQueue.map(it => buildPayload(it));
  chrome.runtime.sendMessage({ action: 'SEND_BATCH_TO_OMNISTREAM', data: { items } }, res => {
    if (res && res.success) {
      showToast(`🚀 Transferred ${items.length} queued streams to Desktop App!`);
      checkBridge();
    } else {
      showToast('⚠️ Desktop App Offline — Launch OmniStream Pro', 3200);
    }
  });
});

remoteDownloadAllBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'START_DESKTOP_QUEUE' }, res => {
    if (res && res.success) {
      showToast('▶ Initiated "Download All" on OmniStream Pro Desktop!');
    } else {
      showToast('Could not trigger queue: Desktop App Offline');
    }
  });
});

/* ── Clear / Recheck ──────────────────────────────────── */
clearDetectedBtn.addEventListener('click', () => {
  if (!currentTabId) return;
  chrome.runtime.sendMessage({ action: 'CLEAR_TAB_MEDIA', tabId: currentTabId }, () => {
    detectedStreams = [];
    renderDetected();
    showToast('Cleared detected streams');
  });
});

clearQueueBtn.addEventListener('click', () => {
  downloadQueue = [];
  saveQueue();
  showToast('Queue cleared');
});

bridgeStatusEl.addEventListener('click', () => {
  showToast('Pinging Desktop Bridge (127.0.0.1:28795)...');
  checkBridge();
});

recheckBridgeBtn.addEventListener('click', () => {
  showToast('Pinging Desktop Bridge...');
  checkBridge();
});

/* ── God Mode ─────────────────────────────────────────── */
godModeBtn.addEventListener('click', () => {
  if (godModeBtn.classList.contains('scanning')) return;
  godModeBtn.classList.add('scanning');
  godBtnText.textContent = 'SCANNING — DEEP DOM PROBE...';

  if (currentTabId) {
    chrome.tabs.sendMessage(currentTabId, { action: 'TRIGGER_GOD_MODE_SCAN' }, () => {});
  }

  setTimeout(() => {
    loadDetectedStreams();
    godModeBtn.classList.remove('scanning');
    godBtnText.textContent = 'ACTIVATE GOD MODE SCAN';
    showToast('God Mode scan complete');
  }, 1400);
});

/* ── Utilities ────────────────────────────────────────── */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

/* ── Boot ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', init);
