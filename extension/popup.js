let currentTabId = null;
let currentTabUrl = '';
let detectedStreams = [];
let scanPollTimer = null;

const $ = (id) => document.getElementById(id);
const currentDomainEl = $('currentDomain');
const bridgeStatusEl = $('bridgeStatus');
const detectedListEl = $('detectedList');
const godScanBtn = $('godScanBtn');
const godScanLabel = $('godScanLabel');
const toastEl = $('toast');

const downloadIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="M7 11l5 5 5-5"/><path d="M5 21h14"/></svg>';
const playIcon = '<svg class="play-icon" viewBox="0 0 24 24" fill="currentColor"><path d="M9 7.5v9l8-4.5-8-4.5z"/></svg>';

let toastTimer = null;
function showToast(text) {
  toastEl.textContent = text;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2200);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function fileLabel(url) {
  try {
    const parts = new URL(url).pathname.split('/').filter(Boolean);
    return decodeURIComponent(parts[parts.length - 1] || 'player');
  } catch (e) {
    return 'player';
  }
}

function kindLabel(item) {
  const lo = String(item.type || item.url || '').toLowerCase();
  if (lo.includes('mpd') || lo.includes('dash')) return 'DASH';
  if (lo.includes('mp4')) return 'MP4';
  if (lo.includes('webm')) return 'WEBM';
  return 'HLS';
}

function audioLabel(item) {
  const langs = item.audioLanguages || [];
  if (langs.length >= 2) return `${langs.length} audio`;
  if (langs.length === 1) return '1 audio';
  return item.isGodMode ? 'god scan' : 'player';
}

async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  currentTabId = tab.id;
  currentTabUrl = tab.url || '';
  try {
    currentDomainEl.textContent = new URL(currentTabUrl).hostname;
  } catch (e) {
    currentDomainEl.textContent = 'This tab';
  }
  runGodScan(false);
  checkBridge();
}

function runGodScan(showFeedback) {
  if (!currentTabId || godScanBtn.classList.contains('scanning')) return;
  godScanBtn.classList.add('scanning');
  godScanLabel.textContent = 'Scanning...';
  chrome.scripting.executeScript({
    target: { tabId: currentTabId, allFrames: true },
    func: () => {
      window.postMessage({ target: 'OMNISTREAM_GODMODE_INJECT', action: 'FORCE_SCAN' }, '*');
    }
  }).catch(() => {
    chrome.tabs.sendMessage(currentTabId, { action: 'TRIGGER_GOD_MODE_SCAN' }, () => {
      void chrome.runtime.lastError;
    });
  });
  let tries = 0;
  clearInterval(scanPollTimer);
  scanPollTimer = setInterval(() => {
    loadDetectedStreams();
    tries += 1;
    if (tries >= 8) {
      clearInterval(scanPollTimer);
      godScanBtn.classList.remove('scanning');
      godScanLabel.textContent = 'God Mode scan';
      if (showFeedback) showToast('God Mode scan finished');
    }
  }, 500);
  setTimeout(loadDetectedStreams, 250);
}

function loadDetectedStreams() {
  if (!currentTabId) return;
  chrome.runtime.sendMessage({ action: 'GET_TAB_MEDIA', tabId: currentTabId }, (res) => {
    if (res && res.success) {
      detectedStreams = res.list || [];
      renderDetected();
    }
  });
}

function checkBridge() {
  chrome.runtime.sendMessage({ action: 'CHECK_OMNISTREAM_BRIDGE' }, (res) => {
    bridgeStatusEl.classList.toggle('connected', !!(res && res.connected));
  });
}

function renderDetected() {
  if (!detectedStreams.length) {
    detectedListEl.innerHTML = '<div class="empty"><svg class="play-icon" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.7"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5-4.5-2.5z" fill="#64748b" stroke="none"/></svg><strong>No stream yet</strong><span>Play the video, then tap <strong>God Mode scan</strong>. Download appears when a playlist is found.</span></div>';
    return;
  }

  detectedListEl.innerHTML = '';
  detectedStreams.forEach((item) => {
    const card = document.createElement('article');
    card.className = 'card';
    const label = escapeHtml(fileLabel(item.url));
    const url = escapeHtml(item.url);
    const langs = (item.audioLanguages || []).join(' · ');
    const langLine = langs
      ? `<div class="url" title="${escapeHtml(langs)}">${escapeHtml(langs)}</div>`
      : '';
    card.innerHTML = `
      <div class="card-top">
        ${playIcon}
        <div class="title" title="${url}">${label}</div>
        <span class="kind">${kindLabel(item)} · ${audioLabel(item)}</span>
      </div>
      ${langLine}
      <div class="url" title="${url}">${url}</div>
      <button class="download" type="button">${downloadIcon}<span>Download</span></button>
    `;
    card.querySelector('.download').onclick = () => sendToDesktop(item);
    detectedListEl.appendChild(card);
  });
}

function sendToDesktop(item) {
  const payload = {
    url: item.url,
    title: fileLabel(item.url),
    curl: item.curl || `curl "${item.url}"`,
    referer: item.referer || currentTabUrl,
    origin: item.origin || '',
    userAgent: item.userAgent || navigator.userAgent,
    headers: item.headers || {},
    size: item.size || 0,
    type: item.type || 'Stream'
  };
  chrome.runtime.sendMessage({ action: 'SEND_TO_OMNISTREAM', data: payload }, (res) => {
    if (res && res.success) {
      showToast('Sent to OmniStream');
      checkBridge();
    } else {
      showToast('Open the OmniStream app first');
    }
  });
}

godScanBtn.addEventListener('click', () => runGodScan(true));

chrome.storage.onChanged.addListener((changes) => {
  if (currentTabId && changes['omni_tab_' + currentTabId]) loadDetectedStreams();
});

document.addEventListener('DOMContentLoaded', init);
