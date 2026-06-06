from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from .config import settings, UPLOADS_DIR
from .routes import router

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / 'frontend'

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://127.0.0.1:8200', 'http://localhost:8200'],
    allow_credentials=False,
    allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type', 'X-Admin-Token'],
)

@app.middleware('http')
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response
app.include_router(router, prefix='/api')
app.mount('/assets', StaticFiles(directory=str(FRONTEND_DIR)), name='assets')
app.mount('/uploads', StaticFiles(directory=str(UPLOADS_DIR)), name='uploads')

@app.get('/')
def index():
    return FileResponse(FRONTEND_DIR / 'index.html')

@app.get('/about')
def about():
    return FileResponse(FRONTEND_DIR / 'about.html')

@app.get('/services')
def services():
    return FileResponse(FRONTEND_DIR / 'services.html')

@app.get('/portfolio')
def portfolio():
    return FileResponse(FRONTEND_DIR / 'portfolio.html')

@app.get('/portfolio/{item_id}')
def portfolio_detail(item_id: str):
    return FileResponse(FRONTEND_DIR / 'portfolio-detail.html')

@app.get('/contact')
def contact():
    return FileResponse(FRONTEND_DIR / 'contact.html')

@app.get('/admin')
def admin():
    return FileResponse(FRONTEND_DIR / 'admin.html')
