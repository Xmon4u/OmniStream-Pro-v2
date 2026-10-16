/**
 * OmniStream Pro v2.0.0 — God Mode Media Sniffer & DevTools Protector
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

  function notifyDetected(url, type) {
    if (!isStreamUrl(url)) return;
    const cleanUrl = url.trim();
    if (capturedUrls.has(cleanUrl)) return;
    capturedUrls.add(cleanUrl);

    window.postMessage({
      source: 'OMNISTREAM_GODMODE',
      action: 'MEDIA_DETECTED',
      url: cleanUrl,
      mediaType: type || detectType(cleanUrl),
      title: document.title || ''
    }, '*');
  }

  // 1. Anti-DevTools & Anti-F12 Blocker Neutralizer
  const origFunction = window.Function;
  const FunctionHandler = function(...args) {
    if (args.length > 0) {
      const code = args[args.length - 1];
      if (typeof code === 'string' && /debugger\s*;?/i.test(code)) {
        args[args.length - 1] = code.replace(/debugger\s*;?/gi, '/* [OmniStream neutralized debugger] */');
      }
    }
    return origFunction.apply(this, args);
  };
  FunctionHandler.prototype = origFunction.prototype;
  window.Function = FunctionHandler;

  console.clear = function() {
    console.info('[OmniStream Pro] Preserved DevTools console from webpage clear.');
  };

  const origAddEventListener = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, listener, options) {
    if (['contextmenu', 'keydown', 'keyup'].includes(type) && typeof listener === 'function') {
      const wrappedListener = function(event) {
        const isF12 = event.key === 'F12' || event.keyCode === 123;
        const isDevToolsShortcut = (event.ctrlKey || event.metaKey) && (
          event.shiftKey && ['I', 'J', 'C', 'i', 'j', 'c'].includes(event.key) ||
          ['U', 'u'].includes(event.key)
        );
        const isContextMenu = event.type === 'contextmenu';

        if (isF12 || isDevToolsShortcut || isContextMenu) {
          const origPreventDefault = event.preventDefault;
          const origStopPropagation = event.stopPropagation;
          const origStopImmediatePropagation = event.stopImmediatePropagation;
          event.preventDefault = () => {};
          event.stopPropagation = () => {};
          event.stopImmediatePropagation = () => {};

          try {
            return listener.apply(this, arguments);
          } finally {
            event.preventDefault = origPreventDefault;
            event.stopPropagation = origStopPropagation;
            event.stopImmediatePropagation = origStopImmediatePropagation;
          }
        }
        return listener.apply(this, arguments);
      };
      return origAddEventListener.call(this, type, wrappedListener, options);
    }
    return origAddEventListener.call(this, type, listener, options);
  };

  window.addEventListener('contextmenu', (e) => {
    e.stopImmediatePropagation ? e.stopImmediatePropagation() : null;
  }, true);

  // 2. Network Hooks (XHR & Fetch)
  const origXHROpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url) {
    try { notifyDetected(url); } catch (e) {}
    return origXHROpen.apply(this, arguments);
  };

  const origFetch = window.fetch;
  window.fetch = function(input, init) {
    try {
      const url = typeof input === 'string' ? input : (input && input.url ? input.url : '');
      notifyDetected(url);
    } catch (e) {}
    return origFetch.apply(this, arguments);
  };

  // 3. HTMLMediaElement src hook
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
  const M3U8_SCAN_REGEX = /https?:\/\/[^\s"'<>\\]+\.(m3u8|mpd|mp4)[^\s"'<>\\]*/gi;

  function deepDOMScan() {
    document.querySelectorAll('video, audio, video source, audio source').forEach(el => {
      notifyDetected(el.src || el.getAttribute('src') || '');
      for (const attr of el.attributes) {
        if (attr.name.startsWith('data-') && isStreamUrl(attr.value)) {
          notifyDetected(attr.value);
        }
      }
    });

    document.querySelectorAll('script:not([src])').forEach(sc => {
      const txt = sc.textContent || '';
      const matches = txt.match(M3U8_SCAN_REGEX);
      if (matches) {
        matches.forEach(m => notifyDetected(m));
      }
    });
  }

  window.addEventListener('message', (event) => {
    if (event.source !== window) return;
    if (event.data && event.data.target === 'OMNISTREAM_GODMODE_INJECT' && event.data.action === 'FORCE_SCAN') {
      deepDOMScan();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', deepDOMScan);
  } else {
    deepDOMScan();
  }
  setTimeout(deepDOMScan, 2000);
})();
