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
const modeTitleOnlyBtn = $('modeTitleOnlyBtn');
const modeImdbBtn = $('modeImdbBtn');
const modeTmdbBtn = $('modeTmdbBtn');
const modeTitleIdBtn = $('modeTitleIdBtn');
const modeSubMergeBtn = $('modeSubMergeBtn');
const batchDownloadBtn = $('batchDownloadBtn');
const clearRefreshBtn = $('clearRefreshBtn');
const clearRefreshLabel = $('clearRefreshLabel');
const clearOnlyBtn = $('clearOnlyBtn');
const themeSelectorEl = $('themeSelector');
let currentDownloadMode = 'normal';
let currentTheme = 'cyber';

function setTheme(theme, save = true) {
  const safeTheme = (theme === 'black' || String(theme).toLowerCase().includes('black')) ? 'black' : 'cyber';
  currentTheme = safeTheme;
  document.body.classList.remove('theme-cyber', 'theme-black');
  document.body.classList.add(`theme-${safeTheme}`);
  if (themeSelectorEl) {
    themeSelectorEl.value = safeTheme;
  }
  if (save) {
    chrome.storage.local.set({ omni_theme: safeTheme });
    const label = safeTheme === 'black' ? 'Midnight Black Theme' : 'Cyber Slate Theme';
    showToast(label);
    chrome.runtime.sendMessage({
      action: 'SET_DESKTOP_THEME',
      theme: safeTheme === 'black' ? 'Midnight Black' : 'Cyber Slate'
    }, () => { void chrome.runtime.lastError; });
  }
}

const downloadIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="M7 11l5 5 5-5"/><path d="M5 21h14"/></svg>';
const subIcon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M6 10h4"/><path d="M6 14h8"/><path d="M14 10h4"/></svg>';
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
  if (mode === 'title_only') {
    currentDownloadMode = 'title_only';
  } else if (mode === 'imdb_rename' || mode === 'netflix_rename') {
    currentDownloadMode = 'imdb_rename';
  } else if (mode === 'tmdb_rename') {
    currentDownloadMode = 'tmdb_rename';
  } else if (mode === 'title_id') {
    currentDownloadMode = 'title_id';
  } else if (mode === 'sub_merge') {
    currentDownloadMode = 'sub_merge';
  } else {
    currentDownloadMode = 'normal';
  }
  if (modeNormalBtn) modeNormalBtn.classList.toggle('active', currentDownloadMode === 'normal');
  if (modeTitleOnlyBtn) modeTitleOnlyBtn.classList.toggle('active', currentDownloadMode === 'title_only');
  if (modeImdbBtn) modeImdbBtn.classList.toggle('active', currentDownloadMode === 'imdb_rename');
  if (modeTmdbBtn) modeTmdbBtn.classList.toggle('active', currentDownloadMode === 'tmdb_rename');
  if (modeTitleIdBtn) modeTitleIdBtn.classList.toggle('active', currentDownloadMode === 'title_id');
  if (modeSubMergeBtn) modeSubMergeBtn.classList.toggle('active', currentDownloadMode === 'sub_merge');
  if (save) {
    chrome.storage.local.set({ omni_download_mode: currentDownloadMode });
    let label = 'Normal Mode';
    if (currentDownloadMode === 'title_only') label = 'Title Only Mode: Movie (Year).mkv';
    else if (currentDownloadMode === 'imdb_rename') label = 'IMDb ID Mode: tt1234567.mkv';
    else if (currentDownloadMode === 'tmdb_rename') label = 'TMDB ID Mode: 8273726.mkv';
    else if (currentDownloadMode === 'title_id') label = 'Title + ID Mode: Movie (Year) tt... tmdb.mkv';
    else if (currentDownloadMode === 'sub_merge') label = 'Sub Merge Mode (Video + Audio + Subs)';
    showToast(label);
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
  const mNetmirror = url.match(/(?:watch|title|movie|series)\/(\d{6,10})/i);
  if (mNetmirror) return mNetmirror[1];
  const m3 = url.match(/\b(\d{7,9})\b/);
  if (m3) return m3[1];
  return null;
}

function extractImdbId(url) {
  if (!url || typeof url !== 'string') return null;
  const m = url.match(/\b(tt\d{7,10})\b/i);
  if (m) return m[1].toLowerCase();
  return null;
}

function extractTmdbId(url) {
  if (!url || typeof url !== 'string') return null;
  const m = url.match(/themoviedb\.org\/(?:movie|tv)\/(\d+)/i);
  if (m) return m[1];
  const m2 = url.match(/(?:tmdb|tmdb_id|tmdbid)[=:_\-](\d+)/i);
  if (m2) return m2[1];
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

  chrome.storage.local.get(['omni_download_mode', 'omni_theme'], (res) => {
    if (res && res.omni_download_mode) {
      setMode(res.omni_download_mode, false);
    }
    if (res && res.omni_theme) {
      setTheme(res.omni_theme, false);
    } else {
      setTheme('cyber', false);
    }
  });

  if (themeSelectorEl) {
    themeSelectorEl.onchange = (e) => setTheme(e.target.value, true);
  }

  if (modeNormalBtn) modeNormalBtn.onclick = () => setMode('normal', true);
  if (modeTitleOnlyBtn) modeTitleOnlyBtn.onclick = () => setMode('title_only', true);
  if (modeImdbBtn) modeImdbBtn.onclick = () => setMode('imdb_rename', true);
  if (modeTmdbBtn) modeTmdbBtn.onclick = () => setMode('tmdb_rename', true);
  if (modeTitleIdBtn) modeTitleIdBtn.onclick = () => setMode('title_id', true);
  if (modeSubMergeBtn) modeSubMergeBtn.onclick = () => setMode('sub_merge', true);
  if (batchDownloadBtn) batchDownloadBtn.onclick = sendAllToDesktop;

  if (clearRefreshBtn) clearRefreshBtn.onclick = clearAndRefreshTab;
  if (clearOnlyBtn) clearOnlyBtn.onclick = clearOnlyStreams;

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
    if (chrome.runtime.lastError) return; // Service worker asleep or extension reloaded
    if (res && res.success) {
      detectedStreams = res.list || [];
      renderDetected();
    }
  });
}

function checkBridge() {
  chrome.runtime.sendMessage({ action: 'CHECK_OMNISTREAM_BRIDGE' }, (res) => {
    if (chrome.runtime.lastError) return; // Service worker not ready
    const connected = !!(res && res.connected);
    const authed = !!(connected && res.data && res.data.authenticated !== false);
    bridgeStatusEl.classList.toggle('connected', connected && authed);
    if (connected && !authed) {
      bridgeStatusEl.title = 'Authentication failed. Please restart OmniStream Pro app.';
    } else if (connected) {
      bridgeStatusEl.title = 'Connected to OmniStream Pro';
    } else {
      bridgeStatusEl.title = 'Desktop app offline (127.0.0.1:28795)';
    }
    if (connected && res.data && res.data.mode && res.data.mode !== currentDownloadMode) {
      setMode(res.data.mode, false);
    }
    if (connected && res.data && res.data.theme) {
      const desktopTheme = res.data.theme.toLowerCase().includes('black') ? 'black' : 'cyber';
      chrome.storage.local.get(['omni_theme'], (storageRes) => {
        if (!storageRes || !storageRes.omni_theme) {
          setTheme(desktopTheme, false);
        }
      });
    }
  });
}

function renderDetected(isRefreshing = false) {
  if (isRefreshing) {
    detectedListEl.innerHTML = '<div class="empty"><svg class="play-icon" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation:omni-spin 0.85s linear infinite;margin:0 auto 8px;display:block;"><path d="M21 2v6h-6"/><path d="M21 13a9 9 0 1 1-3-7.7L21 8"/></svg><strong>Refreshing page...</strong><span>Old files cleared. Reloading page to sniff new streams...</span></div>';
    return;
  }

  if (!detectedStreams.length) {
    detectedListEl.innerHTML = '<div class="empty"><svg class="play-icon" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="1.7"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5-4.5-2.5z" fill="#64748b" stroke="none"/></svg><strong>No stream yet</strong><span>Play the video, then tap <strong>God Mode scan</strong> or <strong>Clear & Refresh</strong>. Download appears when a playlist is found.</span></div>';
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
    const imdbId = item.imdbId || extractImdbId(item.url) || extractImdbId(currentTabUrl);
    const tmdbId = item.tmdbId || extractTmdbId(item.url) || extractTmdbId(currentTabUrl);

    let modePill = '';
    if (currentDownloadMode === 'title_only') {
      modePill = `<span class="kind" style="background:#0284c7;color:#fff;font-weight:600;">Title Only</span>`;
    } else if (currentDownloadMode === 'tmdb_rename') {
      modePill = tmdbId
        ? `<span class="kind" style="background:#01b4e4;color:#032541;border-color:#0284c7;font-weight:700;">TMDB: ${escapeHtml(tmdbId)}</span>`
        : `<span class="kind" style="background:#0e7490;color:#cffafe;font-weight:600;">TMDB Mode</span>`;
    } else if (currentDownloadMode === 'imdb_rename' || currentDownloadMode === 'netflix_rename') {
      modePill = imdbId
        ? `<span class="kind" style="background:#f5c518;color:#000;border-color:#d97706;font-weight:700;">IMDb: ${escapeHtml(imdbId)}</span>`
        : (nid ? `<span class="kind" style="background:#e50914;color:#fff;font-weight:700;">NF: ${escapeHtml(nid)}</span>` : `<span class="kind" style="background:#78350f;color:#fef3c7;font-weight:600;">IMDb Mode</span>`);
    } else if (currentDownloadMode === 'title_id') {
      modePill = `<span class="kind" style="background:#8b5cf6;color:#fff;border-color:#7c3aed;font-weight:700;">Title + ID</span>`;
    } else if (currentDownloadMode === 'sub_merge') {
      modePill = `<span class="kind" style="background:#059669;color:#fff;font-weight:600;">Sub Merge</span>`;
    }

    card.innerHTML = `
      <div class="card-top">
        ${playIcon}
        <div class="title" title="${url}">${label}</div>
        ${modePill}
        <span class="kind">${kindLabel(item)} · ${audioLabel(item)}</span>
      </div>
      ${langLine}
      <div class="url" title="${url}">${url}</div>
      <div class="btn-row">
        <button class="download" type="button">${downloadIcon}<span>Download</span></button>
        <button class="sub-btn" type="button" title="Download Subtitles 1-Click">${subIcon}<span>Subs</span></button>
        <button class="copy-btn" type="button" title="Copy link">${copyIcon}<span>Copy</span></button>
      </div>
    `;
    card.querySelector('.download').onclick = (e) => sendToDesktop(item, e.currentTarget);
    card.querySelector('.sub-btn').onclick = (e) => sendSubtitlesToDesktop(item, e.currentTarget);
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
  const imdbId = item.imdbId || extractImdbId(item.url) || extractImdbId(currentTabUrl);
  const tmdbId = item.tmdbId || extractTmdbId(item.url) || extractTmdbId(currentTabUrl);
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
    netflixId: nid || undefined,
    imdbId: imdbId || undefined,
    tmdbId: tmdbId || undefined
  };
  chrome.runtime.sendMessage({ action: 'SEND_TO_OMNISTREAM', data: payload }, (res) => {
    if (chrome.runtime.lastError) {
      showToast('Extension error — try again');
      return;
    }
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
      showToast((res && res.error) ? res.error : 'Open the OmniStream app first');
    }
  });
}

function sendSubtitlesToDesktop(item, btn) {
  const nid = item.netflixId || extractNetflixId(item.url) || extractNetflixId(currentTabUrl);
  const imdbId = item.imdbId || extractImdbId(item.url) || extractImdbId(currentTabUrl);
  const tmdbId = item.tmdbId || extractTmdbId(item.url) || extractTmdbId(currentTabUrl);
  const payload = {
    url: item.url,
    title: fileLabel(item.url),
    curl: item.curl || `curl "${item.url}"`,
    referer: item.referer || currentTabUrl,
    origin: item.origin || '',
    userAgent: item.userAgent || navigator.userAgent,
    headers: item.headers || {},
    isSubtitleJob: true,
    type: 'subtitles',
    autoStart: true,
    mode: currentDownloadMode,
    netflixId: nid || undefined,
    imdbId: imdbId || undefined,
    tmdbId: tmdbId || undefined
  };
  chrome.runtime.sendMessage({ action: 'SEND_TO_OMNISTREAM', data: payload }, (res) => {
    if (chrome.runtime.lastError) {
      showToast('Extension error — try again');
      return;
    }
    if (res && res.success) {
      showToast('Subtitles sent to OmniStream');
      if (btn) {
        btn.classList.add('sent');
        btn.innerHTML = `${checkIcon}<span>Started</span>`;
        setTimeout(() => {
          btn.classList.remove('sent');
          btn.innerHTML = `${subIcon}<span>Subs</span>`;
        }, 2500);
      }
      checkBridge();
    } else {
      showToast((res && res.error) ? res.error : 'Open the OmniStream app first');
    }
  });
}

function sendAllToDesktop() {
  if (!detectedStreams || !detectedStreams.length) {
    showToast('No streams detected yet');
    return;
  }
  let count = 0;
  const cards = detectedListEl.querySelectorAll('.card');
  detectedStreams.forEach((item, idx) => {
    const btn = cards[idx] ? cards[idx].querySelector('.download') : null;
    sendToDesktop(item, btn);
    count++;
  });
  showToast(`Queued ${count} stream(s) to OmniStream`);
}

godScanBtn.addEventListener('click', () => runGodScan(true));

function clearAndRefreshTab() {
  if (!currentTabId || (clearRefreshBtn && clearRefreshBtn.classList.contains('refreshing'))) return;

  if (clearRefreshBtn) clearRefreshBtn.classList.add('refreshing');
  if (clearRefreshLabel) clearRefreshLabel.textContent = 'Refreshing...';

  // Immediately wipe detected list in UI & show refreshing animation
  detectedStreams = [];
  renderDetected(true);

  chrome.runtime.sendMessage({ action: 'CLEAR_TAB_MEDIA', tabId: currentTabId }, () => {
    const isWebUrl = currentTabUrl && /^https?:\/\//i.test(currentTabUrl);
    if (!isWebUrl) {
      if (clearRefreshBtn) clearRefreshBtn.classList.remove('refreshing');
      if (clearRefreshLabel) clearRefreshLabel.textContent = 'Clear & Refresh';
      showToast('Stream list cleared');
      renderDetected(false);
      return;
    }

    let finished = false;
    const cleanup = () => {
      if (finished) return;
      finished = true;
      try { chrome.tabs.onUpdated.removeListener(onUpdatedListener); } catch (e) {}
      clearTimeout(safetyTimer);
      if (clearRefreshBtn) clearRefreshBtn.classList.remove('refreshing');
      if (clearRefreshLabel) clearRefreshLabel.textContent = 'Clear & Refresh';
      showToast('Cleared & refreshed tab');
      // Automatically trigger God Mode scan to find new streams from reloaded player
      setTimeout(() => {
        runGodScan(false);
      }, 500);
    };

    const onUpdatedListener = (tabId, changeInfo) => {
      if (tabId === currentTabId && changeInfo.status === 'complete') {
        cleanup();
      }
    };

    try { chrome.tabs.onUpdated.addListener(onUpdatedListener); } catch (e) {}

    // Safety fallback in case status complete takes longer or page streams continuously
    const safetyTimer = setTimeout(() => {
      cleanup();
    }, 4500);

    chrome.tabs.reload(currentTabId, { bypassCache: false }, () => {
      if (chrome.runtime.lastError) {
        cleanup();
      }
    });
  });
}

function clearOnlyStreams() {
  if (!currentTabId) return;
  detectedStreams = [];
  renderDetected(false);
  chrome.runtime.sendMessage({ action: 'CLEAR_TAB_MEDIA', tabId: currentTabId }, () => {
    showToast('Stream list cleared');
  });
}

chrome.storage.onChanged.addListener((changes) => {
  if (currentTabId && changes['omni_tab_' + currentTabId]) loadDetectedStreams();
});

document.addEventListener('DOMContentLoaded', init);
