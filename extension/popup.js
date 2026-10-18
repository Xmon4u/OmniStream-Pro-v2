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
const modeNormalBtn = $('modeNormalBtn');
const modeNetflixBtn = $('modeNetflixBtn');
let currentDownloadMode = 'normal';

const downloadIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="M7 11l5 5 5-5"/><path d="M5 21h14"/></svg>';
const copyIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
const checkIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';
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
    let label = decodeURIComponent(parts[parts.length - 1] || 'player');
    label = label.replace(/\.(m3u8|mpd|mp4|webm|mkv|m4s)(\?.*)?$/i, '');
    return label || 'player';
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

function setMode(mode, save = true) {
  currentDownloadMode = (mode === 'netflix_rename') ? 'netflix_rename' : 'normal';
  if (modeNormalBtn) modeNormalBtn.classList.toggle('active', currentDownloadMode === 'normal');
  if (modeNetflixBtn) modeNetflixBtn.classList.toggle('active', currentDownloadMode === 'netflix_rename');
  if (save) {
    chrome.storage.local.set({ omni_download_mode: currentDownloadMode });
    showToast(currentDownloadMode === 'netflix_rename' ? 'Netflix Rename Mode' : 'Normal Mode');
    chrome.runtime.sendMessage({
      action: 'SET_DESKTOP_MODE',
      mode: currentDownloadMode
    }, () => { void chrome.runtime.lastError; });
    renderDetected();
  }
}

function extractNetflixId(url) {
  if (!url || typeof url !== 'string') return null;
  const m = url.match(/netflix\.com\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?(?:watch|title)\/(\d{6,10})/i);
  if (m) return m[1];
  const m2 = url.match(/(?:movieid|titleid|netflix_id)[=:_\-](\d{6,10})/i);
  if (m2) return m2[1];
  const m3 = url.match(/\b(\d{7,9})\b/);
  if (m3) return m3[1];
  return null;
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

  chrome.storage.local.get(['omni_download_mode'], (res) => {
    if (res && res.omni_download_mode) {
      setMode(res.omni_download_mode, false);
    }
  });

  if (modeNormalBtn) modeNormalBtn.onclick = () => setMode('normal', true);
  if (modeNetflixBtn) modeNetflixBtn.onclick = () => setMode('netflix_rename', true);

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
    const connected = !!(res && res.connected);
    bridgeStatusEl.classList.toggle('connected', connected);
    if (connected && res.data && res.data.mode && res.data.mode !== currentDownloadMode) {
      setMode(res.data.mode, false);
    }
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
    const nid = item.netflixId || extractNetflixId(item.url) || extractNetflixId(currentTabUrl);
    const netflixPill = (currentDownloadMode === 'netflix_rename' && nid)
      ? `<span class="kind" style="background:#e50914;color:#fff;border-color:#b91c1c;font-weight:700;">Netflix ID: ${escapeHtml(nid)}</span>`
      : '';
    card.innerHTML = `
      <div class="card-top">
        ${playIcon}
        <div class="title" title="${url}">${label}</div>
        ${netflixPill}
        <span class="kind">${kindLabel(item)} · ${audioLabel(item)}</span>
      </div>
      ${langLine}
      <div class="url" title="${url}">${url}</div>
      <div class="btn-row">
        <button class="download" type="button">${downloadIcon}<span>Download</span></button>
        <button class="copy-btn" type="button" title="Copy link">${copyIcon}<span>Copy</span></button>
      </div>
    `;
    card.querySelector('.download').onclick = (e) => sendToDesktop(item, e.currentTarget);
    card.querySelector('.copy-btn').onclick = () => copyLink(item.url);
    detectedListEl.appendChild(card);
  });
}

function copyLink(url) {
  navigator.clipboard.writeText(url).then(() => {
    showToast('Link copied!');
  }).catch(() => {
    // Fallback for older Chrome
    const ta = document.createElement('textarea');
    ta.value = url;
    ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); showToast('Link copied!'); }
    catch (e) { showToast('Copy failed'); }
    document.body.removeChild(ta);
  });
}

function sendToDesktop(item, btn) {
  const nid = item.netflixId || extractNetflixId(item.url) || extractNetflixId(currentTabUrl);
  const payload = {
    url: item.url,
    title: fileLabel(item.url),
    curl: item.curl || `curl "${item.url}"`,
    referer: item.referer || currentTabUrl,
    origin: item.origin || '',
    userAgent: item.userAgent || navigator.userAgent,
    headers: item.headers || {},
    size: item.size || 0,
    type: item.type || 'Stream',
    mode: currentDownloadMode,
    netflixId: nid || undefined
  };
  chrome.runtime.sendMessage({ action: 'SEND_TO_OMNISTREAM', data: payload }, (res) => {
    if (res && res.success) {
      showToast('Sent to OmniStream');
      if (btn) {
        btn.classList.add('sent');
        btn.innerHTML = `${checkIcon}<span>Queued</span>`;
        setTimeout(() => {
          btn.classList.remove('sent');
          btn.innerHTML = `${downloadIcon}<span>Download</span>`;
        }, 2500);
      }
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
