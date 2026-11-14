"""Kraken festival promo renderer.
render(photo_path, out_path, kicker, headline, sub, layout='portrait'|'square', concept=False)
Brand: near-black #080D10, cyan #0BF7FE, gold #F0A21E.
"""
from PIL import Image, ImageDraw, ImageFont, ImageOps
import glob

CYAN = (11, 247, 254); GOLD = (240, 162, 30); DARK = (8, 13, 16)


def _font(size):
    for p in glob.glob('/usr/share/fonts/**/DejaVuSans-Bold.ttf', recursive=True):
        return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ''
    for w in words:
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    return lines


def _grad(W, H, start, top=260):
    g = Image.new('L', (W, H), 0)
    px = g.load()
    for y in range(H):
        v = 0
        if y > H * start:
            v = int(235 * min(1, (y / H - start) / (1 - start) * 1.15))
        if y < top:
            v = max(v, int(170 * (1 - y / top)))
        for x in range(W):
            px[x, y] = v
    return g


def render(photo_path, out_path, kicker, headline, sub, layout='portrait', concept=False,
           bb_logo=None, focus=(0.5, 0.45)):
    W, H = (1080, 1350) if layout == 'portrait' else (1080, 1080)
    im = ImageOps.fit(Image.open(photo_path).convert('RGB'), (W, H), Image.LANCZOS, centering=focus)
    im = Image.composite(Image.new('RGB', (W, H), DARK), im, _grad(W, H, 0.38 if layout == 'portrait' else 0.30))
    d = ImageDraw.Draw(im)
    d.text((70, 60), 'RELEASE THE KRAKEN', font=_font(44), fill=CYAN)
    d.text((70, 115), 'MOTORSPORT FESTIVAL', font=_font(28), fill=(230, 230, 230))
    if bb_logo:
        bb = Image.open(bb_logo).convert('RGBA')
        bb = bb.resize((250, int(250 * bb.height / bb.width)))
        im.paste(bb, (W - 320, 55), bb)
    hf = _font(88 if len(headline) < 26 else 74)
    sf = _font(34)
    hl = _wrap(d, headline.upper(), hf, W - 140)
    sl = _wrap(d, sub, sf, W - 140)
    block = 60 + len(hl) * (hf.size + 12) + 50 + len(sl) * 46
    y = H - 110 - block
    d.text((70, y), kicker.upper(), font=_font(34), fill=CYAN); y += 60
    for ln in hl:
        d.text((70, y), ln, font=hf, fill=(255, 255, 255)); y += hf.size + 12
    d.rectangle([70, y + 14, 250, y + 22], fill=GOLD); y += 50
    for ln in sl:
        d.text((70, y), ln, font=sf, fill=(225, 225, 225)); y += 46
    d.text((70, H - 80), '3–4 APRIL 2027  •  krakenexpeditions.com.au', font=_font(30), fill=GOLD)
    if concept:
        d.text((W - 300, H - 140), 'CONCEPT RENDER', font=_font(22), fill=(200, 200, 200))
    im.save(out_path, 'JPEG', quality=90)
    return out_path
