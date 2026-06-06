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

async function fetchSite(){
  const res = await fetch(`${API}/site`);
  SITE_DATA = await res.json();
  return SITE_DATA;
}

function nav(){
  const site = SITE_DATA.site[CURRENT_LANG];
  const logo = SITE_DATA.site.branding.logo_path;
  return `<nav class="nav nav-contrast"><div class="container nav-inner"><a class="brand" href="/"><img src="${logo}" alt="logo"><div><small>${site.english_name}</small><strong>${site.studio_name}</strong></div></a><div class="nav-links"><a href="/about">${CURRENT_LANG==='zh'?'關於我們':'About'}</a><a href="/services">${CURRENT_LANG==='zh'?'服務內容':'Services'}</a><a href="/portfolio">${CURRENT_LANG==='zh'?'作品集':'Portfolio'}</a><a href="/contact">${CURRENT_LANG==='zh'?'聯絡我們':'Contact'}</a><div class="lang-switch"><button class="lang-btn ${CURRENT_LANG==='zh'?'active':''}" onclick="setLang('zh')">中</button><button class="lang-btn ${CURRENT_LANG==='en'?'active':''}" onclick="setLang('en')">EN</button></div></div><button class='mobile-toggle' onclick='toggleMobileNav()'>☰</button></div><div class='container mobile-menu' id='mobileMenu'><a href='/about'>${CURRENT_LANG==='zh'?'關於我們':'About'}</a><a href='/services'>${CURRENT_LANG==='zh'?'服務內容':'Services'}</a><a href='/portfolio'>${CURRENT_LANG==='zh'?'作品集':'Portfolio'}</a><a href='/contact'>${CURRENT_LANG==='zh'?'聯絡我們':'Contact'}</a><div class='lang-switch'><button class='lang-btn ${CURRENT_LANG==='zh'?'active':''}' onclick="setLang('zh')">中</button><button class='lang-btn ${CURRENT_LANG==='en'?'active':''}' onclick="setLang('en')">EN</button></div></div></nav>`;
}

function footer(){
  const site = SITE_DATA.site[CURRENT_LANG];
  return `<footer class="footer"><div class="container footer-row"><span>${site.english_name} · ${site.tagline}</span><span>${site.studio_name}</span></div></footer>`;
}

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
