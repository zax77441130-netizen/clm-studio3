from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"

if PUBLIC.exists():
    shutil.rmtree(PUBLIC)

(PUBLIC / "data").mkdir(parents=True, exist_ok=True)

shutil.copytree(ROOT / "frontend", PUBLIC / "frontend")
shutil.copy2(ROOT / "data" / "site.json", PUBLIC / "data" / "site.json")
shutil.copytree(ROOT / "data" / "uploads", PUBLIC / "data" / "uploads")

print("Cloudflare static assets prepared in ./public")
