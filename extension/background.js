// OmniStream Pro v2.6.0 — Background Service Worker
// High performance media sniffer with IDM desktop bridge communication.

const tabMediaMap = new Map(); // tabId -> MediaItem[]
const BRIDGE_URL = 'http://127.0.0.1:28795';

let cachedBridgeToken = '';
async function getBridgeToken() {
  if (cachedBridgeToken) return cachedBridgeToken;
  // 1. Try bridge_token.json (written by desktop app on startup)
  try {
    const res = await fetch(chrome.runtime.getURL('bridge_token.json'));
    if (res.ok) {
      const data = await res.json();
      if (data && data.token && !data.token.startsWith('GENERATED_AT_RUNTIME')) {
        cachedBridgeToken = data.token;
        // Persist to storage so next service worker restart doesn't need to re-read the file
        chrome.storage.local.set({ bridgeToken: cachedBridgeToken }).catch(() => {});
        return cachedBridgeToken;
      }
    }
  } catch (e) {}
  // 2. Fallback: chrome.storage.local (survives service worker restarts)
  try {
    const stored = await chrome.storage.local.get('bridgeToken');
    if (stored && stored.bridgeToken) {
      cachedBridgeToken = stored.bridgeToken;
      return cachedBridgeToken;
    }
  } catch (e) {}
  return '';
}

async function bridgeFetch(path, options = {}) {
  const token = await getBridgeToken();
  const headers = Object.assign({}, options.headers || {});
  if (token) {
    headers['X-OmniStream-Token'] = token;
  }
  return fetch(`${BRIDGE_URL}${path}`, Object.assign({}, options, { headers }));
}


const STREAM_URL_REGEX = /\.(m3u8|mpd|mp4|webm|mkv|m4s)(\?|$|#)/i;
const MEDIA_MIME_TYPES = [
  'application/vnd.apple.mpegurl',
  'application/x-mpegurl',
  'application/dash+xml',
  'video/mp4',
  'video/webm',
  'video/x-matroska'
];

const BLOCK_PATTERNS = [
  'google-analytics', '/analytics', 'doubleclick', 'googlesyndication',
  'facebook.com', '/beacon', 'segment.io', 'hotjar', 'newrelic',
  '/ads/', 'prebid', 'moatads', 'scorecardresearch'
];

function isDuplicate(list, url) {
  const norm = url.split('?')[0].toLowerCase();
  return list.some(item => item.url === url || item.url.split('?')[0].toLowerCase() === norm);
}

function generateCurl(details) {
  let curl = `curl "${details.url}"`;
  if (details.requestHeaders) {
    for (const h of details.requestHeaders) {
      const name = h.name.toLowerCase();
      if (['host', 'content-length', 'connection', 'accept-encoding'].includes(name)) continue;
      const val = (h.value || '').replace(/"/g, '\\"');
      curl += ` \\\n  -H "${h.name}: ${val}"`;
    }
  }
  return curl;
}

function isBlocklisted(url) {
  const lo = url.toLowerCase();
  return BLOCK_PATTERNS.some(p => lo.includes(p));
}

function isMediaStreamUrl(url) {
  if (!url || typeof url !== 'string') return false;
  const lo = url.toLowerCase();
  if (/\.m3u8(\?|#|$)/i.test(lo)) return true;
  if (/\.mpd(\?|#|$)/i.test(lo)) return true;
  if (/[?&](?:format|type)=hls\b/i.test(lo)) return true;
  try {
    const pathname = new URL(url).pathname;
    return STREAM_URL_REGEX.test(pathname);
  } catch {
    const pathPart = url.split('?')[0].split('#')[0];
    return STREAM_URL_REGEX.test(pathPart);
  }
}

function detectType(url, mime = '') {
  const lo = url.toLowerCase();
  if (lo.includes('.m3u8') || mime.includes('mpegurl')) return 'HLS (M3U8)';
  if (lo.includes('.mpd') || mime.includes('dash+xml')) return 'DASH (MPD)';
  if (lo.includes('.mp4') || mime.includes('video/mp4')) return 'MP4 Video';
  if (lo.includes('.webm') || mime.includes('video/webm')) return 'WebM Video';
  if (lo.includes('.mkv')) return 'MKV Video';
  return 'Media Stream';
}

function isPlaylistItem(item) {
  const url = String((item && item.url) || '');
  if (!url) return false;
  const lo = url.toLowerCase();
  let path = lo;
  try { path = new URL(url).pathname.toLowerCase(); } catch (e) {}

  // Drop segments and non-playable media pieces
  if (/\.(m4s|ts|aac|m4a|vtt|srt|jpg|png|webp|gif)(\?|#|$)/.test(path)) return false;
  if (/(preview|trailer|thumb|sprite|poster|preroll|advert|\/ads\/)/.test(lo)) return false;
  if (/(^|\/)(audio|audios|subtitle|subtitles|caption)\//.test(path)) return false;

  const mime = String(item.mime || '').toLowerCase();
  const typeLo = String(item.type || '').toLowerCase();
  if (/\.m3u8(\?|#|$)/i.test(lo) || mime.includes('mpegurl') || typeLo.includes('hls')) return true;
  if (/\.mpd(\?|#|$)/i.test(lo) || mime.includes('dash+xml') || typeLo.includes('dash')) return true;
  if (/\.(mp4|webm|mkv)(\?|#|$)/i.test(path) || mime.includes('video/mp4') || mime.includes('video/webm')) return true;
  return false;
}

function streamScore(item) {
  if (!isPlaylistItem(item)) return -1;
  const url = String(item.url || '');
  const lo = url.toLowerCase();
  let path = lo;
  try { path = new URL(url).pathname.toLowerCase(); } catch (e) {}

  let score = 20;
  if (/master/.test(path)) score += 40;
  if (/player/.test(lo)) score += 30;
  if (/\.mpd(\?|#|$)/.test(lo)) score += 25;
  if (/playlist\.m3u8/.test(path)) score += 20;
  if (/\.m3u8(\?|#|$)/.test(lo)) score += 15;
  if (/\.(mp4|webm|mkv)(\?|#|$)/.test(path)) score += 10;
  if (/(chunklist|media_\d|seg-\d)/.test(path)) score -= 8;
  if (item && item.isGodMode) score += 10;
  const langs = item.audioLanguages || [];
  if (langs.length >= 2) score += 50;
  else if (langs.length === 1) score += 10;
  return score;
}

function selectPlayerStreams(list) {
  const ranked = [];
  const seen = new Set();
  (list || []).forEach((item) => {
    if (!isPlaylistItem(item)) return;
    const key = String(item.url || '').split('?')[0].toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    ranked.push({ item, score: streamScore(item), ts: item.timestamp || 0 });
  });
  ranked.sort((a, b) => {
    const al = (a.item.audioLanguages || []).length;
    const bl = (b.item.audioLanguages || []).length;
    if (al >= 2 && bl < 2) return -1;
    if (bl >= 2 && al < 2) return 1;
    return b.score - a.score || b.ts - a.ts;
  });
  if (ranked.length) {
    return ranked.slice(0, 8).map((row) => row.item);
  }

  // Fallback like the old extension: if scoring found nothing, still show
  // any captured m3u8/mpd/hls URL so Download buttons appear.
  const fallback = [];
  const seen2 = new Set();
  (list || []).forEach((item) => {
    const url = String(item.url || '');
    const lo = url.toLowerCase();
    const mime = String(item.mime || '').toLowerCase();
    const typeLo = String(item.type || '').toLowerCase();
    const ok = /\.m3u8|\.mpd/i.test(lo)
      || mime.includes('mpegurl')
      || mime.includes('dash+xml')
      || typeLo.includes('hls')
      || typeLo.includes('dash')
      || typeLo.includes('m3u8');
    if (!ok) return;
    const key = url.split('?')[0].toLowerCase();
    if (seen2.has(key)) return;
    seen2.add(key);
    fallback.push(item);
  });
  fallback.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
  return fallback.slice(0, 8);
}

function playlistKind(url) {
  const lo = String(url || '').toLowerCase();
  if (lo.includes('.m3u8')) return 'hls';
  if (lo.includes('.mpd')) return 'dash';
  return '';
}

function hlsLanguages(text) {
  const langs = [];
  const re = /#EXT-X-MEDIA:([^\r\n]*)/gi;
  let match;
  while ((match = re.exec(text))) {
    if (!/TYPE=AUDIO/i.test(match[1])) continue;
    const lang = /LANGUAGE="([^"]*)"/i.exec(match[1]);
    const name = /NAME="([^"]*)"/i.exec(match[1]);
    langs.push((lang && lang[1]) || (name && name[1]) || ('audio-' + (langs.length + 1)));
  }
  return [...new Set(langs.map((item) => item.trim()).filter(Boolean))];
}

function dashLanguages(text) {
  const langs = [];
  text.split(/<AdaptationSet\b/i).slice(1).forEach((chunk) => {
    const end = chunk.search(/<\/AdaptationSet>/i);
    const body = end >= 0 ? chunk.slice(0, end) : chunk.slice(0, 4000);
    if (!/(?:mimeType|contentType)="audio\//i.test(body) && !/contentType="audio"/i.test(body)) return;
    const lang = /lang="([^"]+)"/i.exec(body);
    langs.push(lang ? lang[1] : ('audio-' + (langs.length + 1)));
  });
  return [...new Set(langs)];
}

function persistTab(tabId, mediaList) {
  updateBadge(tabId);
  chrome.storage.local.set({ [`omni_tab_${tabId}`]: mediaList });
}

function rememberStream(tabId, mediaList, item) {
  mediaList.push(item);
  persistTab(tabId, mediaList);
  inspectAudio(item, tabId, mediaList);
}

async function inspectAudio(item, tabId, mediaList) {
  const kind = playlistKind(item.url);
  if (!kind || !isPlaylistItem(item)) {
    item.audioLanguages = [];
    persistTab(tabId, mediaList);
    return;
  }
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 6000);
    const headers = {};
    if (item.referer) headers.Referer = item.referer;
    if (item.origin) headers.Origin = item.origin;
    const response = await fetch(item.url, { credentials: 'include', headers, signal: controller.signal });
    clearTimeout(timer);
    const text = await response.text();
    item.audioLanguages = kind === 'hls' ? hlsLanguages(text) : dashLanguages(text);
  } catch (e) {
    item.audioLanguages = [];
  }
  persistTab(tabId, mediaList);
}

function updateBadge(tabId) {
  if (tabId < 0) return;
  const list = selectPlayerStreams(tabMediaMap.get(tabId) || []);
  const count = list.length;
  try {
    if (count > 0) {
      chrome.action.setBadgeText({ tabId, text: count > 99 ? '99+' : String(count) });
      chrome.action.setBadgeBackgroundColor({ tabId, color: '#6366f1' });
      if (chrome.action.setBadgeTextColor) {
        chrome.action.setBadgeTextColor({ tabId, color: '#f8fafc' });
      }
    } else {
      chrome.action.setBadgeText({ tabId, text: '' });
    }
  } catch (e) {}
}

function captureFromRequest(details, extra) {
  if (details.tabId < 0) return;
  const url = details.url;
  if (!url || isBlocklisted(url)) return;

  const mime = (extra && extra.mime) || '';
  if (!isMediaStreamUrl(url) && !MEDIA_MIME_TYPES.some((m) => mime.toLowerCase().includes(m))) return;

  if (!tabMediaMap.has(details.tabId)) tabMediaMap.set(details.tabId, []);
  const mediaList = tabMediaMap.get(details.tabId);
  if (isDuplicate(mediaList, url)) return;

  const headersObj = (extra && extra.headers) || {};
  const mediaItem = {
    id: 'stream_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7),
    url,
    type: detectType(url, mime),
    mime: mime || undefined,
    size: (extra && extra.size) || 0,
    headers: headersObj,
    referer: headersObj['referer'] || details.initiator || '',
    origin: headersObj['origin'] || '',
    userAgent: headersObj['user-agent'] || '',
    curl: (extra && extra.curl) || `curl "${url}"`,
    title: '',
    timestamp: Date.now(),
    tabId: details.tabId
  };

  // Persist immediately so popup can see the link even before tabs.get returns
  rememberStream(details.tabId, mediaList, mediaItem);
  chrome.tabs.get(details.tabId, (tab) => {
    if (chrome.runtime.lastError || !tab) return;
    mediaItem.title = tab.title || mediaItem.title;
    try { mediaItem.domain = new URL(tab.url || url).hostname; } catch (e) {}
    if (tab.url) {
      const nMatch = tab.url.match(/netflix\.com\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?(?:watch|title)\/(\d{6,10})/i)
        || tab.url.match(/(?:watch|title|movie|series)\/(\d{6,10})/i)
        || tab.url.match(/(?:movieid|titleid|netflix_id)[=:_\-](\d{6,10})/i);
      if (nMatch) mediaItem.netflixId = nMatch[1];

      const imdbMatch = tab.url.match(/\b(tt\d{7,10})\b/i);
      if (imdbMatch) mediaItem.imdbId = imdbMatch[1].toLowerCase();

      const tmdbMatch = tab.url.match(/themoviedb\.org\/(?:movie|tv)\/(\d+)/i)
        || tab.url.match(/(?:tmdb|tmdb_id|tmdbid)[=:_\-](\d+)/i);
      if (tmdbMatch) mediaItem.tmdbId = tmdbMatch[1];
    }
    persistTab(details.tabId, mediaList);
  });
}

// Primary capture — URL only, most reliable on modern Chrome
chrome.webRequest.onBeforeRequest.addListener(
  (details) => { captureFromRequest(details); },
  { urls: ['<all_urls>'] }
);

// Header capture for MIME + curl (optional; must not break primary capture)
try {
  chrome.webRequest.onBeforeSendHeaders.addListener(
    (details) => {
      const headersObj = {};
      if (details.requestHeaders) {
        for (const h of details.requestHeaders) {
          headersObj[h.name.toLowerCase()] = h.value;
        }
      }
      captureFromRequest(details, {
        headers: headersObj,
        curl: generateCurl(details)
      });
    },
    { urls: ['<all_urls>'] },
    ['requestHeaders', 'extraHeaders']
  );
} catch (e) {
  chrome.webRequest.onBeforeSendHeaders.addListener(
    (details) => {
      const headersObj = {};
      if (details.requestHeaders) {
        for (const h of details.requestHeaders) {
          headersObj[h.name.toLowerCase()] = h.value;
        }
      }
      captureFromRequest(details, { headers: headersObj, curl: generateCurl(details) });
    },
    { urls: ['<all_urls>'] },
    ['requestHeaders']
  );
}

try {
  chrome.webRequest.onHeadersReceived.addListener(
    (details) => {
      const respHeaders = details.responseHeaders || [];
      let contentType = '';
      let contentLength = 0;
      for (const h of respHeaders) {
        const name = h.name.toLowerCase();
        if (name === 'content-type') contentType = h.value || '';
        if (name === 'content-length') contentLength = parseInt(h.value || '0', 10);
      }
      captureFromRequest(details, { mime: contentType, size: contentLength });
    },
    { urls: ['<all_urls>'] },
    ['responseHeaders', 'extraHeaders']
  );
} catch (e) {
  chrome.webRequest.onHeadersReceived.addListener(
    (details) => {
      const respHeaders = details.responseHeaders || [];
      let contentType = '';
      for (const h of respHeaders) {
        if (h.name.toLowerCase() === 'content-type') contentType = h.value || '';
      }
      captureFromRequest(details, { mime: contentType });
    },
    { urls: ['<all_urls>'] },
    ['responseHeaders']
  );
}

chrome.tabs.onRemoved.addListener((tabId) => {
  tabMediaMap.delete(tabId);
  chrome.storage.local.remove([`omni_tab_${tabId}`]);
});

chrome.tabs.onActivated.addListener((activeInfo) => {
  updateBadge(activeInfo.tabId);
});

// ── Messages & Desktop Bridge Communication ──────────────────────────────────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'GET_TAB_MEDIA') {
    const tabId = message.tabId;
    const memory = tabMediaMap.get(tabId) || [];
    chrome.storage.local.get([`omni_tab_${tabId}`], (res) => {
      const stored = res[`omni_tab_${tabId}`] || [];
      const merged = [...memory];
      stored.forEach((item) => {
        if (!isDuplicate(merged, item.url)) merged.push(item);
      });
      sendResponse({ success: true, list: selectPlayerStreams(merged) });
    });
    return true;
  }

  if (message.action === 'CLEAR_TAB_MEDIA') {
    const tabId = message.tabId;
    tabMediaMap.set(tabId, []);
    chrome.storage.local.remove([`omni_tab_${tabId}`], () => {
      updateBadge(tabId);
      if (tabId) {
        chrome.tabs.sendMessage(tabId, { action: 'CLEAR_GODMODE_CAPTURED' }, () => {
          void chrome.runtime.lastError;
        });
      }
      sendResponse({ success: true });
    });
    return true;
  }

  if (message.action === 'CLEAR_AND_REFRESH_TAB') {
    const tabId = message.tabId;
    tabMediaMap.set(tabId, []);
    chrome.storage.local.remove([`omni_tab_${tabId}`], () => {
      updateBadge(tabId);
      if (tabId) {
        chrome.tabs.sendMessage(tabId, { action: 'CLEAR_GODMODE_CAPTURED' }, () => {
          void chrome.runtime.lastError;
        });
        chrome.tabs.reload(tabId, { bypassCache: false }, () => {
          void chrome.runtime.lastError;
        });
      }
      sendResponse({ success: true });
    });
    return true;
  }

  if (message.action === 'GODMODE_MEDIA_CAPTURED') {
    const tabId = sender.tab ? sender.tab.id : message.tabId;
    const url = message.url || '';

    if (tabId && url && !isBlocklisted(url) && isMediaStreamUrl(url)) {
      if (!tabMediaMap.has(tabId)) tabMediaMap.set(tabId, []);
      const mediaList = tabMediaMap.get(tabId);

      if (!isDuplicate(mediaList, url)) {
        const tabUrl = sender.tab ? sender.tab.url : '';
        const mediaItem = {
          id: 'stream_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7),
          url,
          type: detectType(url),
          curl: `curl "${url}" \\\n  -H "Referer: ${tabUrl}"`,
          title: message.title || (sender.tab ? sender.tab.title : ''),
          domain: tabUrl ? new URL(tabUrl).hostname : '',
          isGodMode: true,
          timestamp: Date.now(),
          tabId
        };
        if (!mediaItem.referer && tabUrl) mediaItem.referer = tabUrl;
        rememberStream(tabId, mediaList, mediaItem);
      }
    }
    sendResponse({ success: true });
    return true;
  }

  // Check OmniStream Pro Desktop Bridge Status
  if (message.action === 'CHECK_OMNISTREAM_BRIDGE') {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1800);

    bridgeFetch('/health', { method: 'GET', signal: controller.signal })
      .then(res => res.json())
      .then(data => {
        clearTimeout(timeoutId);
        sendResponse({ connected: true, data });
      })
      .catch(() => {
        clearTimeout(timeoutId);
        sendResponse({ connected: false });
      });
    return true;
  }

  // Send single stream to OmniStream Pro Desktop
  if (message.action === 'SEND_TO_OMNISTREAM') {
    bridgeFetch('/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.data)
    })
      .then(res => res.json())
      .then(data => {
        if (data && data.success) {
          sendResponse({ success: true, data });
        } else {
          sendResponse({ success: false, error: (data && data.error) || 'Failed to add stream to desktop queue.' });
        }
      })
      .catch(err => {
        sendResponse({
          success: false,
          error: 'OmniStream Pro desktop application is offline or unreachable on 127.0.0.1:28795.'
        });
      });
    return true;
  }

  // Send batch of streams to OmniStream Pro Desktop (IDM batch mode)
  if (message.action === 'SEND_BATCH_TO_OMNISTREAM') {
    bridgeFetch('/batch_add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.data)
    })
      .then(res => res.json())
      .then(data => {
        if (data && data.success) {
          sendResponse({ success: true, data });
        } else {
          sendResponse({ success: false, error: (data && data.error) || 'Failed to add batch to desktop queue.' });
        }
      })
      .catch(err => {
        sendResponse({
          success: false,
          error: 'OmniStream Pro desktop application is offline or unreachable on 127.0.0.1:28795.'
        });
      });
    return true;
  }

  // Trigger Download All remotely
  if (message.action === 'START_DESKTOP_QUEUE') {
    bridgeFetch('/start_queue', { method: 'POST' })
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: String(err) }));
    return true;
  }

  // Set Desktop Mode remotely
  if (message.action === 'SET_DESKTOP_MODE') {
    bridgeFetch('/set_mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: message.mode })
    })
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: String(err) }));
    return true;
  }

  // Set Desktop Theme remotely
  if (message.action === 'SET_DESKTOP_THEME') {
    bridgeFetch('/set_theme', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: message.theme })
    })
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: String(err) }));
    return true;
  }

  // Browser download fallback
  if (message.action === 'DOWNLOAD_FILE') {
    try {
      chrome.downloads.download({
        url: message.url,
        filename: message.filename || 'stream.m3u8',
        saveAs: false
      }, (downloadId) => {
        if (chrome.runtime.lastError) {
          sendResponse({ success: false, error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ success: true, downloadId });
        }
      });
    } catch (e) {
      sendResponse({ success: false, error: e.message });
    }
    return true;
  }
});

function pingDesktopBridge() {
  bridgeFetch('/health', { method: 'GET', cache: 'no-store' }).catch(() => {});
}

pingDesktopBridge();
chrome.runtime.onStartup.addListener(pingDesktopBridge);
chrome.runtime.onInstalled.addListener(pingDesktopBridge);
try {
  chrome.alarms.create('omniBridgePing', { periodInMinutes: 1 });
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === 'omniBridgePing') pingDesktopBridge();
  });
} catch (e) {}
