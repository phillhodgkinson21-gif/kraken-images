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


def _logo_white(path, height):
    """Sponsor logo as a clean white mark on transparency (handles light or dark logo backgrounds)."""
    im = Image.open(path).convert('RGB')
    a = np.asarray(im, dtype=np.float32) / 255.0
    nonwhite = (a.min(axis=2) < 0.92)
    ys, xs = np.where(nonwhite)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    corner = a[:4, :4].mean()
    if corner < 0.35:                                   # logo printed on a dark box: keep the light ink
        alpha = np.clip((a.max(axis=2) - 0.25) / 0.6, 0, 1)
    else:                                               # logo on white: anything away from white is ink
        alpha = np.clip((1 - a.min(axis=2) - 0.08) / 0.6, 0, 1)
    rows = np.where(alpha.max(axis=1) > 0.2)[0]; cols = np.where(alpha.max(axis=0) > 0.2)[0]
    alpha = alpha[rows.min():rows.max() + 1, cols.min():cols.max() + 1]
    mark = Image.new('RGBA', (alpha.shape[1], alpha.shape[0]), (255, 255, 255, 0))
    mark.putalpha(Image.fromarray((alpha * 235).astype(np.uint8)))
    return mark.resize((max(1, int(mark.width * height / mark.height)), height), Image.LANCZOS)


def _logo_chip(path, height, pad=0.16, radius=6):
    """Sponsor logo in its ORIGINAL colours on its own background chip (trimmed, padded, rounded)."""
    crop = Image.open(path).convert('RGB')
    for _ in range(2):                     # trim outer margin; if the logo sits in its own box, trim to inside it
        a = np.asarray(crop, dtype=np.float32) / 255.0
        bg = a[:3, :3].reshape(-1, 3).mean(axis=0)
        ys, xs = np.where(np.abs(a - bg).max(axis=2) > 0.12)
        if len(xs) == 0:
            break
        crop = crop.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
        a2_ = np.asarray(crop, dtype=np.float32) / 255.0
        if np.abs(a2_[:3, :3].reshape(-1, 3).mean(axis=0) - bg).max() < 0.2:
            break                          # no inner box: done
    a = np.asarray(crop, dtype=np.float32) / 255.0
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(edge, axis=0)
    inner_h = int(height * (1 - 2 * pad))
    crop = crop.resize((max(1, int(crop.width * inner_h / crop.height)), inner_h), Image.LANCZOS)
    p = int(height * pad)
    chip = Image.new('RGBA', (crop.width + 2 * p + 4, height), tuple(int(c * 255) for c in bg) + (255,))
    chip.paste(crop, (p + 2, p))
    mask = Image.new('L', chip.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, chip.width - 1, chip.height - 1], radius=radius, fill=255)
    chip.putalpha(mask)
    return chip


def _ease(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


KE_BOX = []


def build_layers(headline_lines, kicker, index, tagline, fonts_dir, bb_logo, reveal_label='', sponsors=None, ke_logo=None, static_logo=False,
                 feature_logo=None, feature_label='', feature_size=190, pop=False):
    KE_BOX[:] = []
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
    FEAT_H = feature_size            # prominent partner logo block (label + logo) under the tagline
    has_feat = bool(feature_logo and os.path.exists(feature_logo))
    top_zone, bot_zone = 300, H - 410 - (FEAT_H + 40 if has_feat else 0)
    TAG_LINES = tagline.split('|') if (pop and tagline) else [tagline]
    TAG_H = (92 + 62 * (len(TAG_LINES) - 1)) if pop else 70        # pop: bigger, bolder tagline on a dark strip
    avail = bot_zone - top_zone - (TAG_H if tagline else 0)
    while True:                      # fit width AND height of the zone
        hf = _f(fonts_dir, cut, size)
        probe = ImageDraw.Draw(Image.new('L', (8, 8))).textbbox((0, 0), 'H', font=hf)
        cap_top, cap = probe[1], probe[3] - probe[1]
        gap = int(cap * 0.09)
        lead = cap + gap
        block_h = lead * (len(lines) - 1) + cap
        if block_h <= avail or size <= 100:
            break
        size -= 4
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
    if pop:
        _spaced(d, (W - M, 150), kicker.upper(), _f(fonts_dir, big, 40), CYAN + (255,), track=0.06, anchor_right=True)
    else:
        _spaced(d, (W - M, 160), kicker.upper(), m22, CYAN + (255,), track=0.28, anchor_right=True)
    tag = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if tagline:
        ty = min(y0 + block_h + 56, H - 360)
        if pop:
            dt0 = ImageDraw.Draw(tag)
            meas = ImageDraw.Draw(Image.new('RGBA', (8, 8)))
            for tsz in range(52, 30, -2):           # shrink to fit the measure
                tf = _f(fonts_dir, big, tsz)
                tws = [_spaced(meas, (0, 0), ln.strip().upper(), tf, (0, 0, 0, 0), track=0.04) for ln in TAG_LINES]
                if max(tws) <= W - 2 * M:
                    break
            tb = dt0.textbbox((0, 0), 'H', font=tf)
            for i_, (ln, tw) in enumerate(zip(TAG_LINES, tws)):
                yy = ty + i_ * 62
                dt0.rounded_rectangle([M - 16, yy - 10, M + tw + 16, yy + tb[3] + 12], radius=8, fill=(0, 0, 0, 175))
                _spaced(dt0, (M, yy), ln.strip().upper(), tf, GOLD + (255,), track=0.04)
        else:
            _spaced(ImageDraw.Draw(tag), (M, ty), tagline.upper(), m20, (255, 255, 255, 190), track=0.24)
    if has_feat:
        fy = (min(y0 + block_h + 56, H - 360) + ((84 + 62 * (len(TAG_LINES) - 1)) if pop else 52)) if tagline else (y0 + block_h + 56)
        fy = min(fy, H - 330 - FEAT_H)
        dt = ImageDraw.Draw(tag)
        if feature_label:
            if pop:
                lf = _f(fonts_dir, big, 38)
                lw = _spaced(ImageDraw.Draw(Image.new('RGBA', (8, 8))), (0, 0), feature_label.upper(), lf, (0, 0, 0, 0), track=0.05)
                lb = dt.textbbox((0, 0), 'H', font=lf)
                dt.rounded_rectangle([M - 14, fy - 4 + lb[1] - 8, M + lw + 14, fy - 4 + lb[3] + 8], radius=8, fill=(0, 0, 0, 175))
                _spaced(dt, (M, fy - 4), feature_label.upper(), lf, CYAN + (255,), track=0.05)
            else:
                _spaced(dt, (M, fy), feature_label.upper(), m22, CYAN + (255,), track=0.28)
        fl = Image.open(feature_logo).convert('RGBA')
        lh_ = FEAT_H - (40 if feature_label else 0)
        fw_ = int(lh_ * fl.width / fl.height)
        if fw_ > W - 2 * M:
            fw_ = W - 2 * M
            lh_ = int(fw_ * fl.height / fl.width)
        fl = fl.resize((fw_, lh_), Image.LANCZOS)
        tag.alpha_composite(fl, (M, fy + (40 if feature_label else 0)))
    rev = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if reveal_label:
        _spaced(ImageDraw.Draw(rev), (M, H - 352), reveal_label.upper(), m22, CYAN + (255,), track=0.3)

    bot = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(bot)
    d.line([(M, H - 300), (W - M, H - 300)], fill=(255, 255, 255, 60), width=1)
    _spaced(d, (M, H - 276), VENUE, m22, (255, 255, 255, 230), track=0.22)
    _spaced(d, (M, H - 238), DATE, _f(fonts_dir, big, 84), GOLD + (255,), track=0.02)
    # Beyond Blue badge, always paired with the Kraken Expeditions badge (Kraken holds the Beyond Blue agreement)
    bh, bx = 72, W - M
    if bb_logo and os.path.exists(bb_logo):
        bb = Image.open(bb_logo).convert('RGBA')
        bb = bb.resize((int(bh * bb.width / bb.height), bh), Image.LANCZOS)
        bx -= bb.width
        bot.alpha_composite(bb, (bx, H - 232))
        pool = os.path.dirname(bb_logo)
        kh = 100                                            # Kraken Expeditions logo, a touch taller than the BB badge
        anim = os.path.join(pool, 'kraken-logo-pulse.mp4')
        still_png = ke_logo or os.path.join(pool, 'kraken-logo.png')
        if os.path.exists(anim) and not static_logo:       # animated pulse, composited per frame
            kw_ = int(round(kh * 436 / 300 / 2) * 2)
            bx -= kw_ + 14
            KE_BOX[:] = [anim, bx, H - 196 - kh // 2, kw_, kh]
        elif os.path.exists(still_png):
            ke = Image.open(still_png).convert('RGBA')
            ke = ke.resize((int(kh * ke.width / ke.height), kh), Image.LANCZOS)
            bx -= ke.width + 14
            bot.alpha_composite(ke, (bx, H - 196 - kh // 2))
    if sponsors:
        sy, lh = H - 136, 46
        lab_w = _spaced(d, (M, sy + 14), 'PRESENTED WITH', _f(fonts_dir, mono, 17), (255, 255, 255, 170), track=0.3)
        x = M + lab_w + 30
        for sp in sponsors:
            lg = _logo_chip(sp, lh)
            if x + lg.width > W - M:
                break
            bot.alpha_composite(lg, (int(x), sy))
            x += lg.width + 16
    _spaced(d, (M, H - 76), SITE, _f(fonts_dir, mono, 18), (255, 255, 255, 140), track=0.3)
    _cross(d, M, H - 26)
    _cross(d, W - M, H - 26)

    def prem(img):
        a = np.asarray(img, dtype=np.float32) / 255.0
        return a[..., :3] * a[..., 3:4], a[..., 3:4]
    return line_masks, bounds, edge, prem(top), prem(bot), prem(tag), prem(rev)


def render_reel(clip, out, headline_lines, kicker, index=1, tagline='', ffmpeg='ffmpeg',
                fonts_dir='.', bb_logo=None, start=0.0, duration=10.0, scale=1.0, t0=0.0,
                reveal=None, reveal_at=6.4, reveal_label='', sponsors=None, static_logo=False,
                feature_logo=None, feature_label='', feature_size=190, pop=False):
    """scale<1 renders smaller (e.g. 2/3 -> 720x1280). t0 lets you render a later segment."""
    global W, H
    line_masks, bounds, edge, (top_rgb, top_a), (bot_rgb, bot_a), (tag_rgb, tag_a), (rev_rgb, rev_a) = build_layers(
        headline_lines, kicker, index, tagline, fonts_dir, bb_logo, reveal_label, sponsors, None, static_logo,
        feature_logo, feature_label, feature_size, pop)
    W0, H0 = W, H
    ke = list(KE_BOX)
    if ke and scale != 1.0:
        ke = [ke[0]] + [int(round(v * scale / 2) * 2) for v in ke[1:]]
    if scale != 1.0:
        W, H = int(round(W0 * scale / 2) * 2), int(round(H0 * scale / 2) * 2)
        rs = lambda a: np.asarray(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS), dtype=np.float32) / 255.0
        line_masks = [rs(m) for m in line_masks]
        bounds = [(int(r0 * scale), int(r1 * scale)) for r0, r1 in bounds]
        edge = rs(edge)
        top_rgb = np.dstack([rs(top_rgb[..., c]) for c in range(3)]); top_a = rs(top_a[..., 0])[..., None]
        bot_rgb = np.dstack([rs(bot_rgb[..., c]) for c in range(3)]); bot_a = rs(bot_a[..., 0])[..., None]
        tag_rgb = np.dstack([rs(tag_rgb[..., c]) for c in range(3)]); tag_a = rs(tag_a[..., 0])[..., None]
        rev_rgb = np.dstack([rs(rev_rgb[..., c]) for c in range(3)]); rev_a = rs(rev_a[..., 0])[..., None]
    try:
        return _render(clip, out, line_masks, bounds, edge, top_rgb, top_a, bot_rgb, bot_a,
                       ffmpeg, start, duration, t0, tag_rgb, tag_a, rev_rgb, rev_a, reveal, reveal_at, ke)
    finally:
        W, H = W0, H0


def _decoder(ffmpeg, src, ss, dur):
    return subprocess.Popen(
        [ffmpeg, '-loglevel', 'error', '-stream_loop', '-1', '-ss', str(ss), '-i', src, '-t', str(dur), '-vf',
         'scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d,fps=%d' % (W, H, W, H, FPS),
         '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)


def _render(clip, out, line_masks, bounds, edge, top_rgb, top_a, bot_rgb, bot_a, ffmpeg, start, duration, t0,
            tag_rgb, tag_a, rev_rgb, rev_a, reveal=None, reveal_at=6.4, ke=None):
    n = int(duration * FPS)
    BLACK_IN, BLACK_OUT = 0.28, 0.55          # shutter: stencil -> ink -> clean plate
    rdec = _decoder(ffmpeg, reveal, 0, max(0.5, t0 + duration - reveal_at + 0.5)) if reveal else None
    shade = np.ones((H, 1, 1), np.float32)     # top/bottom ink falloff so labels sit on the clean plate
    for y in range(H):
        a = 0.0
        if y < 0.20 * H:
            a = 0.80 * (1 - y / (0.20 * H)) ** 0.9
        if y > 0.70 * H:
            a = max(a, 0.86 * ((y - 0.70 * H) / (0.30 * H)) ** 1.15)
        shade[y, 0, 0] = 1 - a
    rlast = None
    kdec = None
    if ke:
        k_src, kx, ky, kw_, kh_ = ke
        kdec = subprocess.Popen([ffmpeg, '-loglevel', 'error', '-stream_loop', '-1', '-i', k_src, '-t', str(t0 + duration + 1),
                                 '-vf', 'scale=%d:%d:flags=lanczos,fps=%d' % (kw_, kh_, FPS),
                                 '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
        klast = [None]

    def put_logo(img, amt):
        if kdec is None or amt <= 0:
            return img
        rr = kdec.stdout.read(kw_ * kh_ * 3)
        if len(rr) == kw_ * kh_ * 3:
            klast[0] = np.frombuffer(rr, np.uint8).reshape(kh_, kw_, 3).astype(np.float32) / 255.0
        if klast[0] is None:
            return img
        lg = klast[0]
        a = np.clip((lg.max(axis=2, keepdims=True) - 0.06) / 0.14, 0, 1) * amt
        reg = img[ky:ky + kh_, kx:kx + kw_]
        img[ky:ky + kh_, kx:kx + kw_] = reg * (1 - a) + lg * a
        return img

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
        if rdec is not None and t >= reveal_at - BLACK_IN:
            if t < reveal_at:                       # close the shutter on the stencil
                k_ = (t - (reveal_at - BLACK_IN)) / BLACK_IN
                img = img * (1 - _ease(k_)) + ink * _ease(k_)
            else:                                   # open on the clean, full-colour plate
                rr = rdec.stdout.read(W * H * 3)
                if len(rr) == W * H * 3:
                    plate_c = np.frombuffer(rr, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
                    plate_c = np.clip((plate_c - 0.5) * 1.06 + 0.5, 0, 1)
                    rlast = plate_c * shade + ink * (1 - shade)
                img = rlast
                k_ = _ease((t - reveal_at) / BLACK_OUT)
                img = ink * (1 - k_) + img * k_
                img = img * (1 - top_a) + top_rgb
                img = img * (1 - bot_a) + bot_rgb
                img = put_logo(np.ascontiguousarray(img), 1.0)
                ka = _ease((t - reveal_at - 0.35) / 0.6)
                if ka > 0:
                    img = img * (1 - rev_a * ka) + rev_rgb * ka
                enc.stdin.write((np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
                continue
        if a1 > 0:
            img = img * (1 - top_a * a1) + top_rgb * a1
            img = img * (1 - tag_a * a1) + tag_rgb * a1
        a2 = _ease((t - 1.5) / 0.7)
        if a2 > 0:
            img = img * (1 - bot_a * a2) + bot_rgb * a2
        if a2 > 0:
            img = put_logo(np.ascontiguousarray(img), a2)
        elif kdec is not None:
            kdec.stdout.read(kw_ * kh_ * 3)          # keep the pulse in sync
        enc.stdin.write((np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()
    dec.kill()
    if rdec:
        rdec.kill()
    if kdec:
        kdec.kill()
    return out


def still(clip, out_png, at=6.0, size=None, **kw):
    """Render one frame. size=(1080,1350) gives an Instagram 4:5 feed post."""
    global W, H
    tmp = out_png + '.mp4'
    W0, H0 = W, H
    if size:
        W, H = size
    try:
        render_reel(clip, tmp, duration=at + 0.1, **kw)
    finally:
        W, H = W0, H0
    subprocess.run([kw.get('ffmpeg', 'ffmpeg'), '-loglevel', 'error', '-y', '-sseof', '-0.05', '-i', tmp,
                    '-frames:v', '1', out_png])
    os.remove(tmp)
    return out_png
