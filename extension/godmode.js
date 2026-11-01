/**
 * OmniStream Pro v2.6.0 — God Mode Media Sniffer & DevTools Protector
 * Injected into the page's MAIN execution world at document_start.
 * Sniffs HLS, DASH, and direct media streams while neutralizing anti-debugging blocks.
 */
(function() {
  'use strict';

  if (window.__OMNISTREAM_GODMODE_ACTIVE__) return;
  window.__OMNISTREAM_GODMODE_ACTIVE__ = true;

  const capturedUrls = new Set();
  const STREAM_REGEX = /\.(m3u8|mpd|mp4|webm|mkv|m4s)(\?|$|#)/i;

  function isStreamUrl(url) {
    if (!url || typeof url !== 'string') return false;
    const s = url.trim();
    if (s.startsWith('data:') || s.startsWith('blob:') || s.startsWith('javascript:')) return false;
    const lo = s.toLowerCase();
    if (/\.m3u8(\?|#|$)/i.test(lo)) return true;
    if (/\.mpd(\?|#|$)/i.test(lo)) return true;
    if (/[?&](?:format|type)=hls\b/i.test(lo)) return true;
    try {
      const pathname = new URL(s).pathname;
      return STREAM_REGEX.test(pathname);
    } catch {
      return STREAM_REGEX.test(s.split('?')[0].split('#')[0]);
    }
  }

  function detectType(url) {
    const lo = url.toLowerCase();
    if (lo.includes('.m3u8')) return 'HLS (M3U8)';
    if (lo.includes('.mpd')) return 'DASH (MPD)';
    if (lo.includes('.mp4')) return 'MP4 Video';
    if (lo.includes('.webm')) return 'WebM Video';
    return 'Media Stream';
  }

  function toAbsoluteUrl(rawUrl) {
    if (!rawUrl || typeof rawUrl !== 'string') return '';
    let u = rawUrl.trim();
    if (u.startsWith('//')) {
      return window.location.protocol + u;
    }
    if (u.startsWith('/') && !u.startsWith('//')) {
      return window.location.origin + u;
    }
    try {
      return new URL(u, window.location.href).href;
    } catch (e) {
      return u;
    }
  }

  function notifyDetected(url, type) {
    if (!isStreamUrl(url)) return;
    const cleanUrl = toAbsoluteUrl(url);
    if (!cleanUrl || capturedUrls.has(cleanUrl)) return;
    capturedUrls.add(cleanUrl);

    window.postMessage({
      source: 'OMNISTREAM_GODMODE',
      action: 'MEDIA_DETECTED',
      url: cleanUrl,
      mediaType: type || detectType(cleanUrl),
      title: document.title || ''
    }, '*');
  }

  // 1. Anti-DevTools / Right-Click & F12 Unlocker (Safe capture-phase listeners, zero prototype tampering)
  window.addEventListener('contextmenu', (e) => {
    if (e.stopImmediatePropagation) e.stopImmediatePropagation();
  }, true);

  window.addEventListener('keydown', (e) => {
    const isF12 = e.key === 'F12' || e.keyCode === 123;
    const isDevTools = (e.ctrlKey || e.metaKey) && (
      (e.shiftKey && ['I', 'J', 'C', 'i', 'j', 'c'].includes(e.key)) ||
      ['U', 'u'].includes(e.key)
    );
    if (isF12 || isDevTools) {
      if (e.stopImmediatePropagation) e.stopImmediatePropagation();
    }
  }, true);

  try {
    console.clear = function() {
      console.info('[OmniStream Pro] Preserved DevTools console from webpage clear.');
    };
  } catch (e) {}

  // 2. HTMLMediaElement src hook
  const originalSrcDescriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
  if (originalSrcDescriptor && originalSrcDescriptor.set) {
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
      set: function(val) {
        try { notifyDetected(val); } catch (e) {}
        return originalSrcDescriptor.set.call(this, val);
      },
      get: function() { return originalSrcDescriptor.get.call(this); },
      configurable: true
    });
  }

  const origPlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function() {
    try {
      const src = this.currentSrc || this.src;
      notifyDetected(src);
    } catch (e) {}
    return origPlay.apply(this, arguments);
  };

  // 4. Deep DOM & Script Scanner
  const M3U8_SCAN_REGEX = /https?:\/\/[^\s"'<>\\]+?\.(m3u8|mpd|mp4)[^\s"'<>\\]*/gi;

  function deepDOMScan() {
    document.querySelectorAll('video, audio, video source, audio source').forEach(el => {
      notifyDetected(el.src || el.currentSrc || el.getAttribute('src') || '');
      for (const attr of el.attributes) {
        if (isStreamUrl(attr.value)) notifyDetected(attr.value);
      }
    });

    document.querySelectorAll('iframe').forEach((frame) => {
      try {
        const frameDoc = frame.contentDocument || frame.contentWindow?.document;
        if (frameDoc) {
          frameDoc.querySelectorAll('video, audio, source').forEach((el) => {
            notifyDetected(el.src || el.currentSrc || el.getAttribute('src') || '');
          });
        }
      } catch (e) {
        notifyDetected(frame.src || '');
      }
    });

    document.querySelectorAll('script').forEach((sc) => {
      const txt = (sc.textContent || '').slice(0, 300000);
      if (!/\.m3u8|\.mpd/i.test(txt)) return;
      const matches = txt.match(M3U8_SCAN_REGEX);
      if (matches) matches.forEach((m) => notifyDetected(m));
    });

    try {
      const html = (document.documentElement && document.documentElement.innerHTML) || '';
      if (/\.m3u8|\.mpd/i.test(html)) {
        const matches = html.match(M3U8_SCAN_REGEX);
        if (matches) matches.slice(0, 40).forEach((m) => notifyDetected(m));
      }
    } catch (e) {}

    try {
      const entries = performance.getEntriesByType('resource') || [];
      entries.forEach((entry) => notifyDetected(entry.name || ''));
    } catch (e) {}

    if (window.jwplayer && typeof window.jwplayer === 'function') {
      try {
        const jw = window.jwplayer();
        const playlist = jw && jw.getPlaylist ? jw.getPlaylist() : null;
        if (Array.isArray(playlist)) {
          playlist.forEach((entry) => {
            notifyDetected(entry.file || '');
            if (entry.sources) entry.sources.forEach((s) => notifyDetected(s.file || ''));
          });
        }
      } catch (e) {}
    }
  }

  function nudgePlayers() {
    document.querySelectorAll('video').forEach((video) => {
      try {
        const src = video.currentSrc || video.src;
        notifyDetected(src);
        if (video.paused) {
          const wasMuted = video.muted;
          video.muted = true;
          video.play().then(() => {
            setTimeout(() => {
              video.pause();
              video.muted = wasMuted;
            }, 500);
          }).catch(() => {});
        }
      } catch (e) {}
    });

    document.querySelectorAll('.vjs-big-play-button, .play-button, [class*="play"], [id*="play"]').forEach((btn) => {
      try {
        if (btn.offsetWidth > 0 && btn.offsetHeight > 0) {
          btn.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
        }
      } catch (e) {}
    });
  }

  window.addEventListener('message', (event) => {
    if (event.data && event.data.target === 'OMNISTREAM_GODMODE_INJECT') {
      if (event.data.action === 'CLEAR_CAPTURED') {
        capturedUrls.clear();
      }
      if (event.data.action === 'FORCE_SCAN') {
        nudgePlayers();
        deepDOMScan();
        setTimeout(deepDOMScan, 800);
        setTimeout(deepDOMScan, 2000);
      }
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', deepDOMScan);
  } else {
    deepDOMScan();
  }
  setTimeout(deepDOMScan, 2000);

  const observer = new MutationObserver(() => deepDOMScan());
  if (document.documentElement) {
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  function hookPlayers() {
    if (window.Hls && window.Hls.prototype && !window.Hls.prototype.__omniHooked) {
      const orig = window.Hls.prototype.loadSource;
      window.Hls.prototype.loadSource = function(url) {
        notifyDetected(url);
        return orig.apply(this, arguments);
      };
      window.Hls.prototype.__omniHooked = true;
    }
    if (window.shaka && window.shaka.Player && !window.shaka.Player.__omniHooked) {
      const orig = window.shaka.Player.prototype.load;
      window.shaka.Player.prototype.load = function(url) {
        notifyDetected(url);
        return orig.apply(this, arguments);
      };
      window.shaka.Player.__omniHooked = true;
    }
    if (window.videojs && !window.__omniVideoJsHooked) {
      const orig = window.videojs;
      window.videojs = function() {
        const player = orig.apply(this, arguments);
        try {
          player.on('loadstart', () => notifyDetected(player.currentSrc() || ''));
        } catch (e) {}
        return player;
      };
      window.__omniVideoJsHooked = true;
    }
  }

  hookPlayers();
  setInterval(hookPlayers, 1500);
})();
