const API='/api';
let SITE_DATA=null;
let CURRENT_LANG=localStorage.getItem('clm-lang')||'zh';

function setLang(next){ localStorage.setItem('clm-lang', next); location.reload(); }
window.setLang=setLang;

function toggleMobileNav(){
  const menu = document.getElementById('mobileMenu');
  if (menu) menu.classList.toggle('open');
}
window.toggleMobileNav = toggleMobileNav;

function escapeHtml(value=''){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}
window.escapeHtml = escapeHtml;

function nl2br(value=''){
  return escapeHtml(value).replace(/\r?\n/g, '<br>');
}
window.nl2br = nl2br;

function safeText(value=''){
  return escapeHtml(value);
}
window.safeText = safeText;

function safeAttr(value=''){
  return escapeHtml(value);
}
window.safeAttr = safeAttr;

function isSafeContactHref(value=''){
  return /^(https?:\/\/|mailto:|tel:)/i.test(String(value || '').trim());
}
window.isSafeContactHref = isSafeContactHref;

function safeHref(value='', fallback='#'){
  return isSafeContactHref(value) ? String(value).trim() : fallback;
}
window.safeHref = safeHref;

async function fetchSite(){
  const res = await fetch(`${API}/site`);
  SITE_DATA = await res.json();
  return SITE_DATA;
}
window.fetchSite = fetchSite;

function getCurrentSite(){
  return SITE_DATA;
}
window.getCurrentSite = getCurrentSite;

function getSeoConfig(){
  return SITE_DATA?.seo || {};
}
window.getSeoConfig = getSeoConfig;

function getContentConfig(){
  return SITE_DATA?.content || {};
}
window.getContentConfig = getContentConfig;

function getSchemaConfig(){
  return SITE_DATA?.schema || {};
}
window.getSchemaConfig = getSchemaConfig;

function getFallbackConfig(){
  return SITE_DATA?.fallbacks || {};
}
window.getFallbackConfig = getFallbackConfig;

function normalizeBaseUrl(siteUrl){
  if (!siteUrl) return '';
  try {
    const value = String(siteUrl).trim();
    if (!value) return '';
    const url = new URL(value.startsWith('http://') || value.startsWith('https://') ? value : `https://${value}`);
    return `${url.protocol}//${url.host}`;
  } catch {
    return '';
  }
}
window.normalizeBaseUrl = normalizeBaseUrl;

function absoluteUrl(path){
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) return path;
  const base = normalizeBaseUrl(getSeoConfig().site_url) || window.location.origin;
  return path.startsWith('/') ? `${base}${path}` : `${base}/${path}`;
}
window.absoluteUrl = absoluteUrl;

function buildTitle(rawTitle){
  const seo = getSeoConfig();
  const template = seo.title_template || '%s | CLM Studio';
  if (!rawTitle) return seo.default_title || 'CLM Studio';
  return template.includes('%s') ? template.replace('%s', rawTitle) : rawTitle;
}
window.buildTitle = buildTitle;

function updateSeo({ title, description, path='/', image='', type='website', keywords=[], noindex=false, structuredData=null }={}){
  const seo = getSeoConfig();
  const finalTitle = title || seo.default_title || 'CLM Studio';
  const finalDescription = description || seo.default_description || '';
  const finalImage = absoluteUrl(image || getDefaultOgImage());
  const finalUrl = absoluteUrl(path || '/');
  const finalKeywords = [...new Set([...(seo.default_keywords || []), ...(keywords || [])].filter(Boolean))].join(', ');
  document.title = finalTitle;

  const html = document.documentElement;
  html.lang = CURRENT_LANG === 'zh' ? 'zh-Hant' : 'en';

  const setMeta = (selector, attr, value) => {
    let el = document.head.querySelector(selector);
    if (!el) {
      el = document.createElement('meta');
      if (attr === 'name') el.setAttribute('name', selector.match(/name="([^"]+)"/)?.[1] || '');
      if (attr === 'property') el.setAttribute('property', selector.match(/property="([^"]+)"/)?.[1] || '');
      document.head.appendChild(el);
    }
    el.setAttribute('content', value || '');
  };

  const ensureMetaByName = (name, value) => setMeta(`meta[name="${name}"]`, 'name', value);
  const ensureMetaByProperty = (property, value) => setMeta(`meta[property="${property}"]`, 'property', value);

  ensureMetaByName('description', finalDescription);
  ensureMetaByName('keywords', finalKeywords);
  ensureMetaByName('robots', noindex ? 'noindex, nofollow' : (seo.robots || 'index, follow, max-image-preview:large'));
  ensureMetaByName('twitter:card', seo.twitter_card || 'summary_large_image');
  ensureMetaByName('twitter:title', finalTitle);
  ensureMetaByName('twitter:description', finalDescription);
  ensureMetaByName('twitter:image', finalImage);
  ensureMetaByProperty('og:title', finalTitle);
  ensureMetaByProperty('og:description', finalDescription);
  ensureMetaByProperty('og:type', type);
  ensureMetaByProperty('og:url', finalUrl);
  ensureMetaByProperty('og:image', finalImage);
  ensureMetaByProperty('og:site_name', seo.site_name || 'CLM Studio');
  ensureMetaByProperty('og:locale', CURRENT_LANG === 'zh' ? 'zh_TW' : 'en_US');

  let canonical = document.head.querySelector('link[rel="canonical"]');
  if (!canonical) {
    canonical = document.createElement('link');
    canonical.setAttribute('rel', 'canonical');
    document.head.appendChild(canonical);
  }
  canonical.setAttribute('href', finalUrl);

  document.head.querySelectorAll('script[data-seo-jsonld="true"]').forEach(el => el.remove());
  const jsonBlocks = Array.isArray(structuredData) ? structuredData : (structuredData ? [structuredData] : []);
  jsonBlocks.filter(Boolean).forEach(block => {
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.dataset.seoJsonld = 'true';
    script.textContent = JSON.stringify(block);
    document.head.appendChild(script);
  });
}
window.updateSeo = updateSeo;

function getOrganizationJsonLd(){
  const seo = getSeoConfig();
  const schema = getSchemaConfig();
  const s = SITE_DATA.site[CURRENT_LANG];
  return {
    '@context': 'https://schema.org',
    '@type': schema.organization_type || 'Organization',
    name: seo.site_name || s.studio_name || 'CLM Studio',
    alternateName: s.english_name || 'CLM Studio',
    url: absoluteUrl('/'),
    logo: absoluteUrl(SITE_DATA.site.branding.logo_path || getDefaultOgImage()),
    image: absoluteUrl(getDefaultOgImage()),
    sameAs: (SITE_DATA.contacts || []).map(item => item.url).filter(url => /^https?:\/\//i.test(url)),
    description: seo.default_description || s.hero_subtitle || ''
  };
}
window.getOrganizationJsonLd = getOrganizationJsonLd;

function getDefaultOgImage(){
  const seo = getSeoConfig();
  const localeSeo = seo[CURRENT_LANG] || {};
  const fallbacks = getFallbackConfig();
  return localeSeo.default_og_image || fallbacks.og_image_default || '/assets/og-image.jpg';
}
window.getDefaultOgImage = getDefaultOgImage;

function getPortfolioCover(item){
  const media = Array.isArray(item?.media) ? item.media : [];
  const firstMedia = media.find(m => m?.url)?.url || '';
  const fallbacks = getFallbackConfig();
  if (item?.cover_image) return item.cover_image;
  if (fallbacks.cover_image_from_first_media && firstMedia) return firstMedia;
  return getDefaultOgImage();
}
window.getPortfolioCover = getPortfolioCover;

function getPortfolioSummary(item, lang = CURRENT_LANG){
  const locale = item?.[lang] || {};
  const summary = String(locale.summary || '').trim();
  if (summary) return summary;
  const fallbacks = getFallbackConfig();
  return lang === 'zh' ? (fallbacks.summary_message_zh || '這個作品目前還沒填摘要。') : (fallbacks.summary_message_en || 'This project does not have a summary yet.');
}
window.getPortfolioSummary = getPortfolioSummary;

function getPortfolioDetail(item, lang = CURRENT_LANG){
  const locale = item?.[lang] || {};
  const detail = String(locale.detail || '').trim();
  if (detail) return detail;
  const fallbacks = getFallbackConfig();
  return lang === 'zh' ? (fallbacks.detail_message_zh || '這個作品目前還沒填詳細介紹。') : (fallbacks.detail_message_en || 'This project does not have a detailed description yet.');
}
window.getPortfolioDetail = getPortfolioDetail;

function buildPortfolioSeoTitle(item, lang = CURRENT_LANG){
  const locale = item?.[lang] || {};
  if (locale.seo_title) return locale.seo_title;
  const fallbacks = getFallbackConfig();
  if (fallbacks.seo_title_from_project_title && locale.title) return buildTitle(locale.title);
  return buildTitle(locale.title || 'Portfolio');
}
window.buildPortfolioSeoTitle = buildPortfolioSeoTitle;

function buildPortfolioSeoDescription(item, lang = CURRENT_LANG){
  const locale = item?.[lang] || {};
  if (locale.seo_description) return locale.seo_description;
  const fallbacks = getFallbackConfig();
  if (fallbacks.seo_description_from_summary) return getPortfolioSummary(item, lang);
  return getPortfolioSummary(item, lang);
}
window.buildPortfolioSeoDescription = buildPortfolioSeoDescription;

function buildBreadcrumbJsonLd(items = []){
  const schema = getSchemaConfig();
  if (!schema.enable_breadcrumb || !items.length) return null;
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path)
    }))
  };
}
window.buildBreadcrumbJsonLd = buildBreadcrumbJsonLd;

function buildWebSiteJsonLd(){
  const seo = getSeoConfig();
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: seo.site_name || 'CLM Studio',
    url: absoluteUrl('/'),
    description: seo.default_description || '',
    inLanguage: CURRENT_LANG === 'zh' ? 'zh-Hant' : 'en'
  };
}
window.buildWebSiteJsonLd = buildWebSiteJsonLd;

function nav(){
  const site = SITE_DATA.site[CURRENT_LANG];
  const logo = SITE_DATA.site.branding.logo_path;
  return `<nav class="nav nav-contrast"><div class="container nav-inner"><a class="brand" href="/"><img src="${safeAttr(logo)}" alt="logo"><div><small>${safeText(site.english_name)}</small><strong>${safeText(site.studio_name)}</strong></div></a><div class="nav-links"><a href="/about">${CURRENT_LANG==='zh'?'關於我們':'About'}</a><a href="/services">${CURRENT_LANG==='zh'?'服務內容':'Services'}</a><a href="/portfolio">${CURRENT_LANG==='zh'?'作品集':'Portfolio'}</a><a href="/contact">${CURRENT_LANG==='zh'?'聯絡我們':'Contact'}</a><div class="lang-switch"><button class="lang-btn ${CURRENT_LANG==='zh'?'active':''}" onclick="setLang('zh')">中</button><button class="lang-btn ${CURRENT_LANG==='en'?'active':''}" onclick="setLang('en')">EN</button></div></div><button class='mobile-toggle' onclick='toggleMobileNav()'>☰</button></div><div class='container mobile-menu' id='mobileMenu'><a href='/about'>${CURRENT_LANG==='zh'?'關於我們':'About'}</a><a href='/services'>${CURRENT_LANG==='zh'?'服務內容':'Services'}</a><a href='/portfolio'>${CURRENT_LANG==='zh'?'作品集':'Portfolio'}</a><a href='/contact'>${CURRENT_LANG==='zh'?'聯絡我們':'Contact'}</a><div class='lang-switch'><button class='lang-btn ${CURRENT_LANG==='zh'?'active':''}' onclick="setLang('zh')">中</button><button class='lang-btn ${CURRENT_LANG==='en'?'active':''}' onclick="setLang('en')">EN</button></div></div></nav>`;
}
window.nav = nav;

function footer(){
  const site = SITE_DATA.site[CURRENT_LANG];
  return `<footer class="footer"><div class="container footer-row"><span>${safeText(site.english_name)} · ${safeText(site.tagline)}</span><span>${safeText(site.studio_name)}</span></div></footer>`;
}
window.footer = footer;

function mountReveal(){
  const items = document.querySelectorAll('.reveal');
  if (!items.length) return;
  const isMobileOrTablet = window.matchMedia('(max-width: 1024px)').matches;
  document.body.classList.add('js-reveal');
  if (isMobileOrTablet) {
    const mobileObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('show');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });
    items.forEach((el) => mobileObserver.observe(el));
    return;
  }
  const desktopObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('show');
      } else {
        entry.target.classList.remove('show');
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
  items.forEach((el) => desktopObserver.observe(el));
}
window.mountReveal = mountReveal;
