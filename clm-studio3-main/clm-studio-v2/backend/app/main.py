from html import escape
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, PlainTextResponse, HTMLResponse
from .config import settings, UPLOADS_DIR
from .routes import router
from .storage import read_data, recover_pending_restore

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / 'frontend'

recover_pending_restore()

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://127.0.0.1:8200', 'http://localhost:8200'],
    allow_credentials=True,
    allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type', 'X-Admin-Token', settings.csrf_header_name],
)


def build_csp():
    frame_src = "https://www.youtube.com https://youtube.com https://player.vimeo.com https://www.google.com/maps https://drive.google.com"
    return (
        "default-src 'self'; "
        "img-src 'self' data: blob: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        f"frame-src {frame_src}; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )


@app.middleware('http')
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = build_csp()
    if settings.is_production:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


app.include_router(router, prefix='/api')
app.mount('/assets', StaticFiles(directory=str(FRONTEND_DIR)), name='assets')
app.mount('/uploads', StaticFiles(directory=str(UPLOADS_DIR)), name='uploads')


def normalize_base_url(site_url: str) -> str:
    site_url = (site_url or '').strip().rstrip('/')
    if not site_url:
        return ''
    if not site_url.startswith(('http://', 'https://')):
        site_url = f'https://{site_url}'
    parsed = urlparse(site_url)
    if not parsed.netloc:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'


def absolute_url(base_url: str, path: str) -> str:
    path = (path or '').strip()
    if not path:
        return ''
    if path.startswith(('http://', 'https://')):
        return path
    if not base_url:
        return path
    return f'{base_url}{path}' if path.startswith('/') else f'{base_url}/{path}'


def get_default_og_image(data: dict, lang: str = 'zh') -> str:
    seo = data.get('seo', {}) or {}
    locale_seo = seo.get(lang, {}) or {}
    fallbacks = data.get('fallbacks', {}) or {}
    return locale_seo.get('default_og_image') or fallbacks.get('og_image_default') or '/assets/og-image.jpg'


def get_portfolio_cover(data: dict, item: dict) -> str:
    media = item.get('media') or []
    first_media = next((m.get('url', '') for m in media if m.get('url')), '')
    fallbacks = data.get('fallbacks', {}) or {}
    if item.get('cover_image'):
        return item['cover_image']
    if fallbacks.get('cover_image_from_first_media', True) and first_media:
        return first_media
    return get_default_og_image(data)


def get_portfolio_summary(data: dict, item: dict, lang: str = 'zh') -> str:
    locale = item.get(lang, {}) or {}
    summary = str(locale.get('summary') or '').strip()
    if summary:
        return summary
    fallbacks = data.get('fallbacks', {}) or {}
    return fallbacks.get('summary_message_zh') if lang == 'zh' else fallbacks.get('summary_message_en', '')


def build_title(data: dict, raw_title: str) -> str:
    seo = data.get('seo', {}) or {}
    template = seo.get('title_template') or '%s | CLM Studio'
    default_title = seo.get('default_title') or 'CLM Studio'
    if not raw_title:
        return default_title
    return template.replace('%s', raw_title) if '%s' in template else raw_title


def render_html(template_name: str, meta: dict, noindex: bool = False) -> HTMLResponse:
    html = (FRONTEND_DIR / template_name).read_text(encoding='utf-8')
    head_injection = f"""
<meta name=\"description\" content=\"{escape(meta.get('description', ''))}\">
<meta name=\"keywords\" content=\"{escape(meta.get('keywords', ''))}\">
<meta name=\"robots\" content=\"{'noindex, nofollow' if noindex else escape(meta.get('robots', 'index, follow, max-image-preview:large'))}\">
<meta property=\"og:title\" content=\"{escape(meta.get('title', ''))}\">
<meta property=\"og:description\" content=\"{escape(meta.get('description', ''))}\">
<meta property=\"og:type\" content=\"{escape(meta.get('type', 'website'))}\">
<meta property=\"og:url\" content=\"{escape(meta.get('url', ''))}\">
<meta property=\"og:image\" content=\"{escape(meta.get('image', ''))}\">
<meta property=\"og:site_name\" content=\"{escape(meta.get('site_name', 'CLM Studio'))}\">
<meta property=\"og:locale\" content=\"zh_TW\">
<meta name=\"twitter:card\" content=\"{escape(meta.get('twitter_card', 'summary_large_image'))}\">
<meta name=\"twitter:title\" content=\"{escape(meta.get('title', ''))}\">
<meta name=\"twitter:description\" content=\"{escape(meta.get('description', ''))}\">
<meta name=\"twitter:image\" content=\"{escape(meta.get('image', ''))}\">
<link rel=\"canonical\" href=\"{escape(meta.get('url', ''))}\">
""".strip()
    if '<title>' in html:
        start = html.find('<title>')
        end = html.find('</title>', start)
        if start != -1 and end != -1:
            html = html[:start] + f"<title>{escape(meta.get('title', 'CLM Studio'))}</title>\n" + head_injection + html[end + len('</title>'):]
    else:
        html = html.replace('</head>', f'<title>{escape(meta.get("title", "CLM Studio"))}</title>\n{head_injection}\n</head>')
    return HTMLResponse(content=html)


def page_meta(path: str, page_key: str, default_label_zh: str, default_desc: str):
    data = read_data()
    seo = data.get('seo', {}) or {}
    zh = seo.get('zh', {}) or {}
    base_url = normalize_base_url(seo.get('site_url', ''))
    title = zh.get(f'{page_key}_title') or build_title(data, default_label_zh)
    description = zh.get(f'{page_key}_description') or default_desc or seo.get('default_description') or ''
    image = absolute_url(base_url, get_default_og_image(data, 'zh'))
    return data, {
        'title': title,
        'description': description,
        'type': 'website',
        'url': absolute_url(base_url, path),
        'image': image,
        'site_name': seo.get('site_name') or 'CLM Studio',
        'twitter_card': seo.get('twitter_card') or 'summary_large_image',
        'keywords': ', '.join(seo.get('default_keywords') or []),
        'robots': seo.get('robots') or 'index, follow, max-image-preview:large',
    }


@app.get('/robots.txt')
def robots_txt():
    data = read_data()
    seo = data.get('seo', {})
    base_url = normalize_base_url(seo.get('site_url', ''))
    robots_value = seo.get('robots', 'index, follow, max-image-preview:large')
    rules = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /admin',
        'Disallow: /api/admin',
        'Disallow: /seo-check',
        f'# robots: {robots_value}',
    ]
    if base_url:
        rules.append(f'Sitemap: {base_url}/sitemap.xml')
    return PlainTextResponse('\n'.join(rules), media_type='text/plain; charset=utf-8')


@app.get('/sitemap.xml')
def sitemap_xml():
    data = read_data()
    seo = data.get('seo', {})
    base_url = normalize_base_url(seo.get('site_url', ''))
    if not base_url:
        base_url = ''
    pages = ['/', '/about', '/services', '/portfolio', '/contact']
    urls = [f'  <url><loc>{base_url}{path}</loc></url>' for path in pages]
    for item in data.get('portfolio', []):
        item_id = item.get('id', '').strip()
        if item_id:
            urls.append(f'  <url><loc>{base_url}/portfolio/{item_id}</loc></url>')
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += '\n'.join(urls)
    xml += '\n</urlset>'
    return Response(content=xml, media_type='application/xml')


@app.get('/')
def index():
    data, meta = page_meta('/', 'home', '首頁', (data := read_data()).get('site', {}).get('zh', {}).get('hero_subtitle', ''))
    return render_html('index.html', meta)


@app.get('/about')
def about():
    data = read_data()
    default_desc = data.get('site', {}).get('zh', {}).get('about_content', '')[:160]
    _, meta = page_meta('/about', 'about', '關於我們', default_desc)
    return render_html('about.html', meta)


@app.get('/services')
def services():
    data = read_data()
    default_desc = data.get('content', {}).get('zh', {}).get('services', {}).get('intro', '') or data.get('site', {}).get('zh', {}).get('hero_subtitle', '')
    _, meta = page_meta('/services', 'services', '服務內容', default_desc)
    return render_html('services.html', meta)


@app.get('/portfolio')
def portfolio():
    data = read_data()
    default_desc = data.get('content', {}).get('zh', {}).get('portfolio', {}).get('intro', '') or data.get('seo', {}).get('default_description', '')
    _, meta = page_meta('/portfolio', 'portfolio', '作品集', default_desc)
    return render_html('portfolio.html', meta)


@app.get('/portfolio/{item_id}')
def portfolio_detail(item_id: str):
    data = read_data()
    seo = data.get('seo', {}) or {}
    base_url = normalize_base_url(seo.get('site_url', ''))
    item = next((x for x in data.get('portfolio', []) if x.get('id') == item_id), None)
    if not item:
        meta = {
            'title': 'Portfolio Not Found | CLM Studio',
            'description': 'The requested portfolio item does not exist.',
            'type': 'website',
            'url': absolute_url(base_url, f'/portfolio/{item_id}'),
            'image': absolute_url(base_url, get_default_og_image(data, 'zh')),
            'site_name': seo.get('site_name') or 'CLM Studio',
            'twitter_card': seo.get('twitter_card') or 'summary_large_image',
            'keywords': ', '.join(seo.get('default_keywords') or []),
            'robots': 'noindex, nofollow',
        }
        return render_html('portfolio-detail.html', meta, noindex=True)
    zh = item.get('zh', {}) or {}
    summary = get_portfolio_summary(data, item, 'zh')
    cover = get_portfolio_cover(data, item)
    meta = {
        'title': zh.get('seo_title') or build_title(data, zh.get('title') or '作品集'),
        'description': zh.get('seo_description') or summary,
        'type': 'article',
        'url': absolute_url(base_url, f'/portfolio/{item_id}'),
        'image': absolute_url(base_url, cover),
        'site_name': seo.get('site_name') or 'CLM Studio',
        'twitter_card': seo.get('twitter_card') or 'summary_large_image',
        'keywords': ', '.join((seo.get('default_keywords') or []) + (zh.get('tech_stack') or [])),
        'robots': seo.get('robots') or 'index, follow, max-image-preview:large',
    }
    return render_html('portfolio-detail.html', meta)


@app.get('/contact')
def contact():
    data = read_data()
    default_desc = data.get('site', {}).get('zh', {}).get('contact_note', '')
    _, meta = page_meta('/contact', 'contact', '聯絡我們', default_desc)
    return render_html('contact.html', meta)


@app.get('/admin')
def admin():
    return FileResponse(FRONTEND_DIR / 'admin.html')


@app.get('/seo-check')
def seo_check():
    data = read_data()
    seo = data.get('seo', {}) or {}
    base_url = normalize_base_url(seo.get('site_url', ''))
    meta = {
        'title': build_title(data, 'SEO 檢查'),
        'description': '用來檢查 canonical、sitemap、robots、OG 與站點設定是否正確。',
        'type': 'website',
        'url': absolute_url(base_url, '/seo-check'),
        'image': absolute_url(base_url, get_default_og_image(data, 'zh')),
        'site_name': seo.get('site_name') or 'CLM Studio',
        'twitter_card': seo.get('twitter_card') or 'summary_large_image',
        'keywords': ', '.join(seo.get('default_keywords') or []),
        'robots': 'noindex, nofollow',
    }
    return render_html('seo-check.html', meta, noindex=True)
