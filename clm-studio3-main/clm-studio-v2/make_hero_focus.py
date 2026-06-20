from PIL import Image, ImageFilter

src = r'C:\Users\cl201\.openclaw\workspace\clm-studio-v2\data\uploads\clm-hero-source.png'
out = r'C:\Users\cl201\.openclaw\workspace\clm-studio-v2\data\uploads\clm-hero-focused.png'

img = Image.open(src).convert('RGBA')
w, h = img.size
# trim most of the top/bottom empty beige space while keeping full composition
crop = img.crop((80, 230, w - 80, h - 320))
cw, ch = crop.size
canvas = Image.new('RGBA', (cw, ch), (248, 244, 238, 255))
bg = crop.resize((cw, ch)).filter(ImageFilter.GaussianBlur(18))
canvas.alpha_composite(bg)
overlay = Image.new('RGBA', (cw, ch), (255, 248, 240, 38))
canvas.alpha_composite(overlay)
canvas.alpha_composite(crop, (0, 0))
canvas.convert('RGB').save(out, quality=95)
print(out)
