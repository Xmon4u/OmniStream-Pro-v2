// OmniStream Pro v2.0.0 - Content Script

function injectGodModeScript() {
  try {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('godmode.js');
    script.onload = function() {
      this.remove();
    };
    (document.head || document.documentElement).appendChild(script);
  } catch (e) {
    console.error('[OmniStream Pro] Failed to inject godmode script:', e);
  }
}

injectGodModeScript();

window.addEventListener('message', (event) => {
  if (event.source !== window) return;

  if (event.data && event.data.source === 'OMNISTREAM_GODMODE') {
    if (event.data.action === 'MEDIA_DETECTED') {
      chrome.runtime.sendMessage({
        action: 'GODMODE_MEDIA_CAPTURED',
        url: event.data.url,
        mediaType: event.data.mediaType,
        title: event.data.title || document.title
      }).catch(() => {});
    }
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'CLEAR_GODMODE_CAPTURED') {
    window.postMessage({
      target: 'OMNISTREAM_GODMODE_INJECT',
      action: 'CLEAR_CAPTURED'
    }, '*');
    sendResponse({ success: true });
    return true;
  }

  if (message.action === 'TRIGGER_GOD_MODE_SCAN') {
    window.postMessage({
      target: 'OMNISTREAM_GODMODE_INJECT',
      action: 'FORCE_SCAN'
    }, '*');
    sendResponse({ success: true, message: 'God Mode deep scan triggered' });
    return true;
  }

  if (message.action === 'GET_PAGE_INFO') {
    sendResponse({
      title: document.title,
      url: window.location.href,
      domain: window.location.hostname
    });
    return true;
  }
});
