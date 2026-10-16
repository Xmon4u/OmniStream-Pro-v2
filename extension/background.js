// OmniStream Pro v2.0.0 — Background Service Worker
// High performance media sniffer with IDM desktop bridge communication.

const tabMediaMap = new Map(); // tabId -> MediaItem[]
const BRIDGE_URL = 'http://127.0.0.1:28795';

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
  '/ads/', 'prebid', 'moatads', 'scorecardresearch', 'favicon', '.jpg', '.png', '.gif', '.css'
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

function updateBadge(tabId) {
  if (tabId < 0) return;
  const list = tabMediaMap.get(tabId) || [];
  const count = list.length;
  if (count > 0) {
    chrome.action.setBadgeText({ tabId, text: count > 99 ? '99+' : String(count) });
    chrome.action.setBadgeBackgroundColor({ tabId, color: '#6366f1' }); // OmniStream Indigo
    chrome.action.setBadgeTextColor({ tabId, color: '#f8fafc' });
  } else {
    chrome.action.setBadgeText({ tabId, text: '' });
  }
}

// ── Request interceptor ──────────────────────────────────────────────────────
chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (details.tabId < 0) return;
    const url = details.url;

    if (!isMediaStreamUrl(url) || isBlocklisted(url)) return;

    if (!tabMediaMap.has(details.tabId)) tabMediaMap.set(details.tabId, []);
    const mediaList = tabMediaMap.get(details.tabId);
    if (isDuplicate(mediaList, url)) return;

    const headersObj = {};
    if (details.requestHeaders) {
      for (const h of details.requestHeaders) {
        headersObj[h.name.toLowerCase()] = h.value;
      }
    }

    const type = detectType(url);
    const mediaItem = {
      id: 'stream_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7),
      url,
      type,
      headers: headersObj,
      referer: headersObj['referer'] || details.initiator || '',
      origin: headersObj['origin'] || '',
      userAgent: headersObj['user-agent'] || '',
      curl: generateCurl(details),
      title: '',
      timestamp: Date.now(),
      tabId: details.tabId
    };

    chrome.tabs.get(details.tabId, (tab) => {
      if (!chrome.runtime.lastError && tab) {
        mediaItem.title = tab.title || '';
        try { mediaItem.domain = new URL(tab.url || url).hostname; } catch {}
      }
      mediaList.push(mediaItem);
      updateBadge(details.tabId);
      chrome.storage.local.set({ [`omni_tab_${details.tabId}`]: mediaList });
    });
  },
  { urls: ['<all_urls>'] },
  ['requestHeaders', 'extraHeaders']
);

// ── Response interceptor ─────────────────────────────────────────────────────
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.tabId < 0) return;
    const url = details.url;
    if (isBlocklisted(url)) return;

    const respHeaders = details.responseHeaders || [];
    let contentType = '';
    let contentLength = 0;

    for (const h of respHeaders) {
      const name = h.name.toLowerCase();
      if (name === 'content-type')  contentType   = h.value || '';
      if (name === 'content-length') contentLength = parseInt(h.value || '0', 10);
    }

    const isMediaMime = MEDIA_MIME_TYPES.some(m => contentType.toLowerCase().includes(m));
    if (!isMediaMime && !isMediaStreamUrl(url)) return;

    if (!tabMediaMap.has(details.tabId)) tabMediaMap.set(details.tabId, []);
    const mediaList = tabMediaMap.get(details.tabId);
    if (isDuplicate(mediaList, url)) return;

    const type = detectType(url, contentType);
    const mediaItem = {
      id: 'stream_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7),
      url,
      type,
      mime: contentType,
      size: contentLength,
      curl: `curl "${url}"`,
      timestamp: Date.now(),
      tabId: details.tabId
    };

    chrome.tabs.get(details.tabId, (tab) => {
      if (!chrome.runtime.lastError && tab) {
        mediaItem.title = tab.title || '';
        try { mediaItem.domain = new URL(tab.url || url).hostname; } catch {}
      }
      mediaList.push(mediaItem);
      updateBadge(details.tabId);
      chrome.storage.local.set({ [`omni_tab_${details.tabId}`]: mediaList });
    });
  },
  { urls: ['<all_urls>'] },
  ['responseHeaders', 'extraHeaders']
);

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
    chrome.storage.local.get([`omni_tab_${tabId}`], (res) => {
      const list = res[`omni_tab_${tabId}`] || tabMediaMap.get(tabId) || [];
      sendResponse({ success: true, list });
    });
    return true;
  }

  if (message.action === 'CLEAR_TAB_MEDIA') {
    const tabId = message.tabId;
    tabMediaMap.set(tabId, []);
    chrome.storage.local.remove([`omni_tab_${tabId}`], () => {
      updateBadge(tabId);
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
        mediaList.push(mediaItem);
        updateBadge(tabId);
        chrome.storage.local.set({ [`omni_tab_${tabId}`]: mediaList });
      }
    }
    sendResponse({ success: true });
    return true;
  }

  // Check OmniStream Pro Desktop Bridge Status
  if (message.action === 'CHECK_OMNISTREAM_BRIDGE') {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1800);

    fetch(`${BRIDGE_URL}/health`, { method: 'GET', signal: controller.signal })
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
    fetch(`${BRIDGE_URL}/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.data)
    })
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data }))
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
    fetch(`${BRIDGE_URL}/batch_add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(message.data)
    })
      .then(res => res.json())
      .then(data => sendResponse({ success: true, data }))
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
    fetch(`${BRIDGE_URL}/start_queue`, { method: 'POST' })
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
