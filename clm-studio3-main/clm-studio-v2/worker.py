import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse, PlainTextResponse
from workers import asgi

app = FastAPI(title="CLM Studio Cloudflare")
Default = asgi.entrypoint(app)


async def _asset_response(request: Request, asset_path: str) -> Response:
    env = request.scope["env"]
    resp = await env.ASSETS.fetch(f"https://assets.local/{asset_path.lstrip('/')}")
    body = await resp.bytes()
    headers = dict(resp.headers)
    return Response(content=body, status_code=resp.status, headers=headers)


async def _default_site_json(request: Request) -> str:
    env = request.scope["env"]
    resp = await env.ASSETS.fetch("https://assets.local/data/site.json")
    if resp.status != 200:
        raise HTTPException(status_code=500, detail="default site data unavailable")
    body = await resp.bytes()
    return bytes(body).decode("utf-8")


async def _site_json_text(request: Request) -> str:
    env = request.scope["env"]
    kv = getattr(env, "SITE_KV", None)
    if kv is not None:
        try:
            value = await kv.get("site_json")
            if value:
                return str(value)
        except Exception:
            pass
    return await _default_site_json(request)


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "CLM Studio Cloudflare"}


@app.get("/api/site")
async def site(request: Request):
    text = await _site_json_text(request)
    try:
        return JSONResponse(json.loads(text))
    except Exception:
        raise HTTPException(status_code=500, detail="invalid site data")


@app.get("/robots.txt")
async def robots(request: Request):
    data = json.loads(await _site_json_text(request))
    base = (data.get("seo", {}).get("site_url") or "").rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /api/admin",
        "Disallow: /seo-check",
    ]
    if base:
        lines.append(f"Sitemap: {base}/sitemap.xml")
    return PlainTextResponse("\n".join(lines))


@app.get("/sitemap.xml")
async def sitemap(request: Request):
    data = json.loads(await _site_json_text(request))
    base = (data.get("seo", {}).get("site_url") or "").rstrip("/")
    pages = ["/", "/about", "/services", "/portfolio", "/contact"]
    pages += [f"/portfolio/{item.get('id')}" for item in data.get("portfolio", []) if item.get("id")]
    urls = "\n".join(f"  <url><loc>{base}{path}</loc></url>" for path in pages)
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>'
    return Response(content=xml, media_type="application/xml")


@app.get("/uploads/{path:path}")
async def uploads(path: str, request: Request):
    env = request.scope["env"]
    bucket = getattr(env, "UPLOADS", None)
    if bucket is not None:
        try:
            obj = await bucket.get(path)
            if obj is not None and hasattr(obj, "body"):
                body = await obj.body.bytes()
                headers = {"etag": str(obj.httpEtag)} if hasattr(obj, "httpEtag") else {}
                return Response(content=body, headers=headers)
        except Exception:
            pass
    # Existing Railway-era uploads remain available from the Git repository.
    return await _asset_response(request, f"data/uploads/{path}")


_ROUTE_FILES = {
    "": "frontend/index.html",
    "about": "frontend/about.html",
    "services": "frontend/services.html",
    "portfolio": "frontend/portfolio.html",
    "contact": "frontend/contact.html",
    "admin": "frontend/admin.html",
    "seo-check": "frontend/seo-check.html",
}


@app.get("/{path:path}")
async def frontend(path: str, request: Request):
    clean = path.strip("/")

    if clean.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")

    if clean.startswith("assets/"):
        relative = clean[len("assets/"):]
        return await _asset_response(request, f"frontend/{relative}")

    if clean.startswith("portfolio/") and clean != "portfolio":
        return await _asset_response(request, "frontend/portfolio-detail.html")

    if clean in _ROUTE_FILES:
        return await _asset_response(request, _ROUTE_FILES[clean])

    # Only expose known frontend files; backend/source files are intentionally not proxied.
    if clean in {"favicon.ico", "og-image.jpg"}:
        return await _asset_response(request, f"frontend/{clean}")

    raise HTTPException(status_code=404, detail="not found")
