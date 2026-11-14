"""Kinetic Stencil reel renderer — Release the Kraken 4x4 Music Festival.

Headline letters are cut through a darkened, desaturated plate of the same
footage, revealing it at full colour inside the type.

render_reel(clip, out, headline_lines, kicker, index, tagline, ffmpeg='ffmpeg',
            fonts_dir='.', bb_logo=None, start=0.0, duration=10.0)
"""
import os
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
M = 72                                     # outer margin
CYAN = (11, 247, 254)
GOLD = (240, 162, 30)
INK = (8, 13, 16)
VENUE = 'LARDNER PARK  —  GIPPSLAND VIC'
DATE = '3—4 APRIL 2027'
SITE = 'KRAKENEXPEDITIONS.COM.AU'


def _f(fonts_dir, name, size):
    return ImageFont.truetype(os.path.join(fonts_dir, name), size)


def _spaced(d, xy, text, font, fill, track=0.0, anchor_right=False):
    """Draw letter-spaced text; returns width."""
    widths = [d.textlength(c, font=font) for c in text]
    total = sum(widths) + track * font.size * (len(text) - 1)
    x, y = xy
    if anchor_right:
        x -= total
    for c, w in zip(text, widths):
        d.text((x, y), c, font=font, fill=fill)
        x += w + track * font.size
    return total


def _cross(d, cx, cy, r=10, fill=(255, 255, 255, 150)):
    d.line([(cx - r, cy), (cx + r, cy)], fill=fill, width=2)
    d.line([(cx, cy - r), (cx, cy + r)], fill=fill, width=2)


def _ease(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def build_layers(headline_lines, kicker, index, tagline, fonts_dir, bb_logo):
    big = 'BigShoulders-Bold.ttf'
    cut = 'Anton-Regular.ttf'
    mono = 'DMMono-Regular.ttf'
    lines = [l.upper() for l in headline_lines]

    # ---- headline sizing: widest line fills the measure exactly
    measure = W - 2 * M
    size = 460
    while size > 120:
        f = _f(fonts_dir, cut, size)
        tmp = ImageDraw.Draw(Image.new('L', (8, 8)))
        if max(tmp.textlength(l, font=f) for l in lines) <= measure:
            break
        size -= 4
    hf = _f(fonts_dir, cut, size)
    probe = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), 'H', font=hf)
    cap_top, cap = probe[1], probe[3] - probe[1]
    gap = int(cap * 0.09)
    lead = cap + gap
    block_h = lead * (len(lines) - 1) + cap
    top_zone, bot_zone = 300, 1530
    y0 = top_zone + (bot_zone - top_zone - block_h) // 2

    line_masks = []
    for i, l in enumerate(lines):
        m = Image.new('L', (W, H), 0)
        dm = ImageDraw.Draw(m)
        bbox = dm.textbbox((0, 0), l, font=hf)
        x = M - bbox[0]
        y = y0 + i * lead - cap_top
        dm.text((x, y), l, font=hf, fill=255)
        line_masks.append(np.asarray(m, dtype=np.float32) / 255.0)
    bounds = []
    for lm in line_masks:
        rows = np.where(lm.max(axis=1) > 0)[0]
        bounds.append((rows.min(), rows.max()))

    # hairline contour of the cut
    full = Image.fromarray((np.clip(sum(line_masks), 0, 1) * 255).astype(np.uint8))
    edge = np.asarray(full.filter(ImageFilter.MaxFilter(5)), dtype=np.float32) / 255.0 - \
        np.asarray(full, dtype=np.float32) / 255.0
    edge = np.clip(edge, 0, 1)

    # ---- instrumentation layers (RGBA)
    top = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(top)
    m26, m22, m20 = _f(fonts_dir, mono, 26), _f(fonts_dir, mono, 22), _f(fonts_dir, mono, 20)
    _cross(d, M, 96)
    _cross(d, W - M, 96)
    _spaced(d, (M + 28, 82), 'RELEASE THE KRAKEN', m26, CYAN + (255,), track=0.22)
    _spaced(d, (W - M - 28, 82), 'N°%02d' % index, m26, (255, 255, 255, 170), track=0.22, anchor_right=True)
    d.line([(M, 140), (W - M, 140)], fill=(255, 255, 255, 60), width=1)
    _spaced(d, (M, 160), '4X4 MUSIC FESTIVAL', m22, (255, 255, 255, 200), track=0.28)
    _spaced(d, (W - M, 160), kicker.upper(), m22, CYAN + (255,), track=0.28, anchor_right=True)
    if tagline:
        ty = min(y0 + block_h + 56, 1580)
        _spaced(d, (M, ty), tagline.upper(), m20, (255, 255, 255, 190), track=0.24)

    bot = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(bot)
    d.line([(M, 1640), (W - M, 1640)], fill=(255, 255, 255, 60), width=1)
    _spaced(d, (M, 1664), VENUE, m22, (255, 255, 255, 230), track=0.22)
    _spaced(d, (M, 1702), DATE, _f(fonts_dir, big, 92), GOLD + (255,), track=0.02)
    if bb_logo and os.path.exists(bb_logo):
        bb = Image.open(bb_logo).convert('RGBA')
        bw = 210
        bb = bb.resize((bw, int(bw * bb.height / bb.width)), Image.LANCZOS)
        bot.alpha_composite(bb, (W - M - bw, 1700))
    _spaced(d, (M, 1830), SITE, m20, (255, 255, 255, 150), track=0.3)
    _cross(d, M, 1880 - 14)
    _cross(d, W - M, 1880 - 14)

    def prem(img):
        a = np.asarray(img, dtype=np.float32) / 255.0
        return a[..., :3] * a[..., 3:4], a[..., 3:4]
    return line_masks, bounds, edge, prem(top), prem(bot)


def render_reel(clip, out, headline_lines, kicker, index=1, tagline='', ffmpeg='ffmpeg',
                fonts_dir='.', bb_logo=None, start=0.0, duration=10.0, scale=1.0, t0=0.0):
    """scale<1 renders smaller (e.g. 2/3 -> 720x1280). t0 lets you render a later segment."""
    global W, H
    line_masks, bounds, edge, (top_rgb, top_a), (bot_rgb, bot_a) = build_layers(
        headline_lines, kicker, index, tagline, fonts_dir, bb_logo)
    W0, H0 = W, H
    if scale != 1.0:
        W, H = int(round(W0 * scale / 2) * 2), int(round(H0 * scale / 2) * 2)
        rs = lambda a: np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS), dtype=np.float32) / 255.0
        line_masks = [rs(m) for m in line_masks]
        bounds = [(int(r0 * scale), int(r1 * scale)) for r0, r1 in bounds]
        edge = rs(edge)
        top_rgb = np.dstack([rs(top_rgb[..., c]) for c in range(3)]); top_a = rs(top_a[..., 0])[..., None]
        bot_rgb = np.dstack([rs(bot_rgb[..., c]) for c in range(3)]); bot_a = rs(bot_a[..., 0])[..., None]
    try:
        return _render(clip, out, line_masks, bounds, edge, top_rgb, top_a, bot_rgb, bot_a,
                       ffmpeg, start, duration, t0)
    finally:
        W, H = W0, H0


def _render(clip, out, line_masks, bounds, edge, top_rgb, top_a, bot_rgb, bot_a, ffmpeg, start, duration, t0):
    n = int(duration * FPS)

    dec = subprocess.Popen(
        [ffmpeg, '-loglevel', 'error', '-stream_loop', '-1', '-ss', str(start + t0), '-i', clip,
         '-t', str(duration), '-vf',
         'scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d,fps=%d' % (W, H, W, H, FPS),
         '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
    enc = subprocess.Popen(
        [ffmpeg, '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H),
         '-r', str(FPS), '-i', '-', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=stereo',
         '-shortest', '-c:v', 'libx264', '-preset', 'medium', '-crf', '25', '-maxrate', '7M', '-bufsize', '14M', '-pix_fmt', 'yuv420p',
         '-c:a', 'aac', '-b:a', '64k', '-movflags', '+faststart', out], stdin=subprocess.PIPE)

    rng = np.random.default_rng(7)
    grain = [rng.normal(0, 3.2, (H, W, 1)).astype(np.float32) / 255.0 for _ in range(4)]
    tint = np.array([0.80, 0.93, 1.0], dtype=np.float32)
    ink = np.array(INK, dtype=np.float32) / 255.0
    cyan = np.array(CYAN, dtype=np.float32) / 255.0
    full_mask = np.clip(sum(line_masks), 0, 1)[..., None]
    edge3 = edge[..., None]
    last = None
    for k in range(n):
        raw = dec.stdout.read(W * H * 3)
        if len(raw) < W * H * 3:
            if last is None:
                break
            frame = last
        else:
            frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
            last = frame
        t = t0 + k / FPS
        lum = (frame @ np.array([0.299, 0.587, 0.114], dtype=np.float32))[..., None]
        plate = ink + (lum * tint) * 0.15 + grain[k % 4]
        vivid = np.clip((frame - 0.5) * 1.12 + 0.52, 0, 1)
        vivid = np.clip(lum + (vivid - lum) * 1.25, 0, 1) ** 0.72

        # roller-door reveal, line by line
        if t < 0.25 + 0.2 * len(line_masks) + 0.6:
            mask = np.zeros((H, W), np.float32)
            for i, (lm, (r0, r1)) in enumerate(zip(line_masks, bounds)):
                p = _ease((t - 0.25 - 0.2 * i) / 0.55)
                if p <= 0:
                    continue
                cut = int(r1 - (r1 - r0 + 1) * p)
                part = lm.copy()
                part[:max(cut, 0), :] = 0
                mask += part
            mask = np.clip(mask, 0, 1)[..., None]
            e = edge3 * min(1.0, max(0.0, (t - 0.9) / 0.5))
        else:
            mask = full_mask
            e = edge3
        img = plate * (1 - mask) + vivid * mask
        img = img * (1 - e * 0.45) + cyan * e * 0.45

        a1 = _ease((t - 1.0) / 0.7)
        if a1 > 0:
            img = img * (1 - top_a * a1) + top_rgb * a1
        a2 = _ease((t - 1.5) / 0.7)
        if a2 > 0:
            img = img * (1 - bot_a * a2) + bot_rgb * a2
        enc.stdin.write((np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    dec.kill()
    return out


def still(clip, out_png, at=6.0, **kw):
    """Render one frame (for previews)."""
    tmp = out_png + '.mp4'
    render_reel(clip, tmp, duration=at + 0.1, **kw)
    subprocess.run([kw.get('ffmpeg', 'ffmpeg'), '-loglevel', 'error', '-y', '-sseof', '-0.05', '-i', tmp,
                    '-frames:v', '1', out_png])
    os.remove(tmp)
    return out_png
