// OmniStream Pro v2.6.0 - Content Script

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
    } else if (event.data.action === 'PLAYER_AUDIO_TRACKS_DETECTED') {
      chrome.runtime.sendMessage({
        action: 'PLAYER_AUDIO_TRACKS_DETECTED',
        url: event.data.url,
        tracks: event.data.tracks,
        activeTrack: event.data.activeTrack,
        title: event.data.title || document.title
      }).catch(() => {});
    }
  }
});

function scanDomForAudioLanguages() {
  const KNOWN_LANGUAGES = [
    'Bengali', 'German', 'English', 'Spanish', 'French', 'Hindi',
    'Italian', 'Japanese', 'Kannada', 'Korean', 'Malayalam', 'Polish',
    'Telugu', 'Tamil', 'Marathi', 'Punjabi', 'Urdu', 'Arabic',
    'Chinese', 'Russian', 'Portuguese', 'Turkish', 'Thai', 'Vietnamese', 'Indonesian'
  ];

  const foundLangs = [];
  const textMap = new Set();
  let activeLang = '';

  const candidates = document.querySelectorAll(
    'li, div, span, button, a, [class*="track"], [class*="audio"], [class*="menu"], [class*="item"]'
  );

  candidates.forEach(el => {
    const txt = (el.textContent || '').trim();
    if (!txt || txt.length < 3 || txt.length > 30) return;

    for (const lang of KNOWN_LANGUAGES) {
      const re = new RegExp(`(^|\\b)${lang}(\\b|$)`, 'i');
      if (re.test(txt)) {
        if (!textMap.has(lang)) {
          textMap.add(lang);
          foundLangs.push(lang);
        }
        const isSelected = el.classList.contains('active') ||
                           el.classList.contains('selected') ||
                           el.classList.contains('highlight') ||
                           el.getAttribute('aria-selected') === 'true' ||
                           el.querySelector('svg, .icon, [class*="play"], [class*="check"]') !== null ||
                           /▶|✓|✔|•/.test(txt);
        if (isSelected && !activeLang) {
          activeLang = lang;
        }
        break;
      }
    }
  });

  if (foundLangs.length > 0) {
    chrome.runtime.sendMessage({
      action: 'DOM_AUDIO_LANGUAGES_DETECTED',
      languages: foundLangs,
      activeLanguage: activeLang,
      title: document.title
    }).catch(() => {});
  }
}

// Periodically check DOM for audio track menus (e.g. NetMirror menu when opened or rendered)
setTimeout(scanDomForAudioLanguages, 1500);
setTimeout(scanDomForAudioLanguages, 3500);
document.addEventListener('click', () => { setTimeout(scanDomForAudioLanguages, 300); }, true);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'FETCH_PLAYLIST_TEXT') {
    fetch(message.url)
      .then(res => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.text();
      })
      .then(text => sendResponse({ success: true, text }))
      .catch(err => sendResponse({ success: false, error: String(err) }));
    return true;
  }

  if (message.action === 'SCAN_DOM_AUDIO') {
    scanDomForAudioLanguages();
    sendResponse({ success: true });
    return true;
  }

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

  if (message.action === 'SCAN_PAGE_MOVIES') {
    try {
      const movies = extractPageMovies();
      sendResponse({ success: true, movies: movies });
    } catch (err) {
      sendResponse({ success: false, error: String(err), movies: [] });
    }
    return true;
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// Universal Movie & Series DOM Scraper
// ─────────────────────────────────────────────────────────────────────────────
function extractPageMovies() {
  const movies = [];
  const seenUrls = new Set();

  function cleanMovieTitle(str) {
    if (!str) return '';
    return str
      .replace(/[\r\n\t]+/g, ' ')
      .replace(/\s+/g, ' ')
      .replace(/\b(Watch Online|Full Movie|Watch Free|Download|Hindi Dubbed|Dual Audio|All Episodes|Free Download|HD 720p|HD 1080p|1080p|720p|480p|Web-DL|BluRay|HDRip|Pre-DVDRip|DVDRip|HDTC|HDCAM)\b/gi, '')
      .replace(/[\|\-\:\/•]+\s*$/g, '')
      .replace(/^\s*[\|\-\:\/•]+/g, '')
      .trim();
  }

  function extractYear(text) {
    const m = String(text || '').match(/\b(19\d{2}|20\d{2})\b/);
    return m ? m[1] : '';
  }

  function getAbsoluteUrl(href) {
    if (!href) return '';
    try {
      return new URL(href, window.location.href).href;
    } catch (e) {
      return href;
    }
  }

  function isValidMovieUrl(url) {
    if (!url || typeof url !== 'string') return false;
    if (!url.startsWith('http://') && !url.startsWith('https://')) return false;
    const u = url.toLowerCase();
    const excludedPatterns = [
      '/category/', '/genre/', '/genres/', '/tag/', '/tags/', '/author/',
      '/page/', '/search/', '/feed', '/rss', '/contact', '/about', '/dmca',
      '/privacy', '/terms', '/login', '/register', '/wp-admin', '/wp-content',
      '/wp-includes', '/xmlrpc', '#', 'javascript:', 'mailto:'
    ];
    if (excludedPatterns.some(p => u.includes(p))) return false;
    try {
      const parsed = new URL(url);
      if (!parsed.pathname || parsed.pathname === '/' || parsed.pathname === '') return false;
    } catch (e) {
      return false;
    }
    return true;
  }

  function extractImgSrc(container) {
    if (!container) return '';
    const img = container.querySelector('img');
    if (img) {
      const srcset = img.getAttribute('srcset') || img.getAttribute('data-srcset');
      if (srcset) {
        const first = srcset.split(',')[0].trim().split(' ')[0];
        if (first && !first.startsWith('data:image')) return getAbsoluteUrl(first);
      }
      const src = img.getAttribute('data-src') ||
                  img.getAttribute('data-original') ||
                  img.getAttribute('data-lazy-src') ||
                  img.getAttribute('src') ||
                  img.src;
      if (src && !src.startsWith('data:image')) {
        return getAbsoluteUrl(src);
      }
    }
    const bgEl = container.querySelector('[style*="background-image"], .poster, .thumb');
    if (bgEl && bgEl.style && bgEl.style.backgroundImage) {
      const m = bgEl.style.backgroundImage.match(/url\(["']?([^"']+)["']?\)/i);
      if (m && m[1] && !m[1].startsWith('data:image')) {
        return getAbsoluteUrl(m[1]);
      }
    }
    return '';
  }

  // 1. Flexible Card Selectors (DooPlay, WordPress, PsyPlay, prmovies, etc.)
  const cardSelectors = [
    'article',
    '.item',
    '.movies-list .item',
    '.item-movies',
    '.item-tvshows',
    '.ml-item',
    '.flw-item',
    '.film-detail',
    '.movie-item',
    '.item-movie',
    '.browse-movie-wrap',
    '.movie-card',
    '.film_list-wrap .flw-item',
    '.featured-item',
    '.post-item',
    'li.movie-item'
  ];

  const cards = document.querySelectorAll(cardSelectors.join(', '));
  cards.forEach(card => {
    const linkEl = card.querySelector('h3 a, h2 a, h4 a, .data h3 a, .title a, .film-name a, .entry-title a, a[href*="/movie/"], a[href*="/watch/"], a[href*="/film/"], a[href*="/series/"]') ||
                   card.querySelector('a.poster, .poster a, a');
    if (!linkEl) return;

    const rawHref = linkEl.getAttribute('href') || linkEl.href;
    const fullUrl = getAbsoluteUrl(rawHref);
    if (!isValidMovieUrl(fullUrl) || seenUrls.has(fullUrl)) return;

    let rawTitle = linkEl.getAttribute('title') ||
                   card.querySelector('h3, h2, h4, .title, .film-name, .entry-title')?.textContent ||
                   linkEl.textContent ||
                   '';
    if (!rawTitle || rawTitle.trim().length < 2) {
      const img = card.querySelector('img');
      rawTitle = img?.getAttribute('alt') || img?.getAttribute('title') || '';
    }

    const title = cleanMovieTitle(rawTitle);
    if (!title || title.length < 2) return;

    const poster = extractImgSrc(card);
    const yearEl = card.querySelector('.year, .release-year, .metadata span, .data span, .date');
    const yearText = yearEl ? yearEl.textContent.trim() : '';
    const year = extractYear(yearText) || extractYear(rawTitle) || '';

    const qualEl = card.querySelector('.quality, .calidad, .badge, .film-poster-quality, .featu, .hd, .mepo span');
    const quality = qualEl ? qualEl.textContent.trim() : 'HD';

    seenUrls.add(fullUrl);
    movies.push({
      id: `auto_${Date.now()}_${movies.length + 1}`,
      title: title,
      page_url: fullUrl,
      poster_url: poster,
      year: year,
      quality: quality || '1080p',
      status: 'Pending'
    });
  });

  // 2. Generic fallback if specific card selectors found 0 movies
  if (movies.length === 0) {
    document.querySelectorAll('a[href*="/movie/"], a[href*="/watch/"], a[href*="/series/"], a[href*="/film/"]').forEach(a => {
      const href = a.getAttribute('href') || a.href;
      const fullUrl = getAbsoluteUrl(href);
      if (!isValidMovieUrl(fullUrl) || seenUrls.has(fullUrl)) return;
      let title = a.getAttribute('title') || a.textContent || '';
      if (!title || title.length < 2) {
        const img = a.querySelector('img');
        if (img) title = img.getAttribute('alt') || img.getAttribute('title') || '';
      }
      title = cleanMovieTitle(title);
      if (title.length < 2) return;

      const poster = extractImgSrc(a) || extractImgSrc(a.closest('div, li, article'));
      const year = extractYear(title);

      seenUrls.add(fullUrl);
      movies.push({
        id: `auto_${Date.now()}_${movies.length + 1}`,
        title: title,
        page_url: fullUrl,
        poster_url: poster,
        year: year,
        quality: 'HD',
        status: 'Pending'
      });
    });
  }

  return movies;
}
