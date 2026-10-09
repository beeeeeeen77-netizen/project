"""[하늘에서 애플이 떨어진다] 덕천 하이마트 Apple 10월 한정 오픈런 캠페인 (1080x1920, 30fps, 19s).

컨셉: 하늘(구름) 속으로 아이폰·아이패드·맥북·애플워치가 혜성처럼 떨어지고,
덕천 하이마트 매장에 '쾅' 착지하면 실제 매장 영상으로 전환된다.

사용법: python3 render_sky.py <클립폴더> <폰트폴더> <출력.mp4>
"""
import glob
import math
import os
import random
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
CLIP_DIR, FONT_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BH = os.path.join(FONT_DIR, "BlackHanSans.ttf")
NOTO = os.path.join(FONT_DIR, "NotoSansKR-Black.ttf")

YELLOW = (255, 230, 0)
RED = (255, 40, 50)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
NAVY = (14, 30, 80)

random.seed(11)


def clip_path(tag):
    return glob.glob(os.path.join(CLIP_DIR, f"*-{tag}.mp4"))[0]


IPAD, IPHONE, WATCH, MAC_BOOT, MAC_OPEN = (clip_path(t) for t in ("11", "22", "33", "44", "55"))


# ---------------------------------------------------------------- 공통 유틸
def load_clip(path, start, nframes, speed=1.0):
    vf = (f"setpts=PTS/{speed},fps={FPS},"
          f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    dur = nframes / FPS * speed + 0.5
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-i", path, "-t", str(dur),
           "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (W * H * 3)
    arr = np.frombuffer(raw[: n * W * H * 3], np.uint8).reshape(n, H, W, 3)
    return [Image.fromarray(a) for a in arr[:nframes]]


def at(frames, i):
    return frames[max(0, min(i, len(frames) - 1))]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(i, s, e):
    return clamp((i - s) / max(1, e - s))


def lerp(a, b, t):
    return a + (b - a) * t


def out_expo(t):
    return 1 if t >= 1 else 1 - 2 ** (-10 * t)


def out_back(t, k=2.2):
    t -= 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


def out_elastic(t):
    if t <= 0 or t >= 1:
        return clamp(t)
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


def put(canvas, spr, cx, cy, scale=1.0, rot=0.0, alpha=1.0, sx=1.0, sy=1.0):
    if scale <= 0.02 or alpha <= 0.01:
        return
    s = spr
    fw, fh = scale * sx, scale * sy
    if abs(fw - 1) > 1e-3 or abs(fh - 1) > 1e-3:
        s = s.resize((max(1, int(s.width * fw)), max(1, int(s.height * fh))), Image.BILINEAR)
    if abs(rot) > 0.05:
        s = s.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        s = s.copy()
        s.putalpha(s.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.paste(s, (int(cx - s.width / 2), int(cy - s.height / 2)), s)


def cam(img, zoom=1.0, rot=0.0, tx=0.0, ty=0.0, fill=BLACK):
    cx, cy = W / 2, H / 2
    a = math.radians(rot)
    c, s = math.cos(a) / zoom, math.sin(a) / zoom
    C = cx - c * (cx + tx) - s * (cy + ty)
    F = cy + s * (cx + tx) - c * (cy + ty)
    return img.transform((W, H), Image.AFFINE, (c, s, C, -s, c, F),
                         resample=Image.BILINEAR, fillcolor=fill)


def shake(i, start, dur=10, amp=26):
    t = (i - start) / dur
    if t < 0 or t > 1:
        return 0.0, 0.0
    d = amp * (1 - t) ** 2
    return d * math.sin(i * 2.7), d * math.cos(i * 3.9)


def flash(img, amt, color=WHITE):
    if amt <= 0.01:
        return img
    return Image.blend(img, Image.new("RGB", img.size, color), clamp(amt))


def darken_grad(img, top=0.55, bottom=0.6, mid=0.15):
    a = np.asarray(img).astype(np.float32)
    y = np.linspace(0, 1, H)[:, None, None]
    k = np.where(y < 0.5, lerp(top, mid, y / 0.5), lerp(mid, bottom, (y - 0.5) / 0.5))
    return Image.fromarray((a * (1 - k)).astype(np.uint8))


def motion_blur_v(img, dy, n=7):
    if abs(dy) < 4:
        return img
    a = np.asarray(img).astype(np.float32)
    acc = np.zeros_like(a)
    for k in range(n):
        acc += np.roll(a, int(dy * (k / (n - 1) - 0.5)), axis=0)
    return Image.fromarray((acc / n).astype(np.uint8))


# ---------------------------------------------------------------- 텍스트
def text_sprite(txt, font, size, fill=WHITE, stroke=0, stroke_fill=NAVY, shadow=True):
    f = ImageFont.truetype(font, size)
    l, t, r, b = ImageDraw.Draw(Image.new("RGBA", (1, 1))).multiline_textbbox(
        (0, 0), txt, font=f, stroke_width=stroke, align="center")
    pad = 40
    img = Image.new("RGBA", (int(r - l) + pad * 2, int(b - t) + pad * 2), (0, 0, 0, 0))
    pos = (pad - l, pad - t)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).multiline_text((pos[0] + 10, pos[1] + 14), txt, font=f,
                                          fill=(0, 0, 0, 160), stroke_width=stroke,
                                          stroke_fill=(0, 0, 0, 160), align="center")
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(img).multiline_text(pos, txt, font=f, fill=fill, stroke_width=stroke,
                                       stroke_fill=stroke_fill, align="center")
    return img


def pill(txt, font, size, bg, fg, padx=46, pady=24, radius=None, border=None):
    f = ImageFont.truetype(font, size)
    l, t, r, b = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), txt, font=f)
    w, h = r - l + padx * 2, b - t + pady * 2
    m = 24
    img = Image.new("RGBA", (w + m * 2, h + m * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rad = radius if radius is not None else h // 2
    ImageDraw.Draw(sh).rounded_rectangle((m + 6, m + 10, m + w + 6, m + h + 10), rad,
                                         fill=(0, 0, 0, 140))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((m, m, m + w, m + h), rad, fill=bg, outline=border,
                        width=8 if border else 0)
    d.text((m + padx - l, m + pady - t), txt, font=f, fill=fg)
    return img


# ---------------------------------------------------------------- 애플 기기 일러스트
def load_device(name):
    """매장 영상에서 원근 보정으로 잘라낸 실제 기기 이미지(assets/, make_device_cutouts.py) + 글로우."""
    img = Image.open(os.path.join(ASSET_DIR, f"{name}.png")).convert("RGBA")
    m = 50
    out = Image.new("RGBA", (img.width + 2 * m, img.height + 2 * m), (0, 0, 0, 0))
    a = Image.new("L", out.size, 0)
    a.paste(img.getchannel("A"), (m, m))
    g = Image.new("RGBA", out.size, (255, 255, 255, 0))
    g.putalpha(a.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.55)))
    out = Image.alpha_composite(out, g)
    out.paste(img, (m, m), img)
    return out


ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
DEV = {n: load_device(n) for n in ("iphone", "ipad", "mac", "watch")}
DEV_SCALE = dict(iphone=0.9, ipad=0.82, mac=0.72, watch=0.88)


# 혜성 꼬리
def make_trail(length=900, width=260):
    a = np.zeros((length, width), np.float32)
    y = np.linspace(0, 1, length)[:, None]  # 0=꼬리끝, 1=기기쪽
    x = np.linspace(-1, 1, width)[None, :]
    taper = 0.15 + 0.85 * y
    a = np.clip(1 - (np.abs(x) / taper) ** 2, 0, 1) * y ** 1.6
    rgba = np.zeros((length, width, 4), np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = (235 + 20 * y).clip(0, 255).astype(np.uint8)
    rgba[..., 2] = (170 + 85 * (np.abs(x) < 0.3)).clip(0, 255).astype(np.uint8)
    rgba[..., 3] = (a * 230).astype(np.uint8)
    return Image.fromarray(rgba).filter(ImageFilter.GaussianBlur(6))


TRAIL = make_trail()
_rot_cache = {}


def dev_sprite(name, scale, rot):
    key = (name, round(scale, 2), int(round(rot / 2) * 2))
    s = _rot_cache.get(key)
    if s is None:
        s = DEV[name]
        sc = key[1] * DEV_SCALE[name]
        s = s.resize((int(s.width * sc), int(s.height * sc)), Image.LANCZOS)
        if key[2]:
            s = s.rotate(key[2], resample=Image.BICUBIC, expand=True)
        if len(_rot_cache) > 600:
            _rot_cache.clear()
        _rot_cache[key] = s
    return s


def falling_device(canvas, name, x, y, scale=1.0, rot=0.0, vx=0.0, vy=40.0, trail=1.0,
                   sx=1.0, sy=1.0):
    """기기 + 이동 방향 반대쪽 혜성 꼬리."""
    if trail > 0.02 and vy > 1:
        ang = math.degrees(math.atan2(vx, vy))
        L = int(clamp(vy * 14, 150, 1100) * trail)
        tw = int(TRAIL.width * scale * (1.2 if name in ("mac", "ipad") else 0.9))
        t = TRAIL.resize((max(2, tw), max(2, L)), Image.BILINEAR).rotate(ang, expand=True,
                                                                        resample=Image.BICUBIC)
        dx = -math.sin(math.radians(ang)) * L / 2
        dy = -math.cos(math.radians(ang)) * L / 2
        canvas.paste(t, (int(x + dx - t.width / 2), int(y + dy - t.height / 2)), t)
    s = dev_sprite(name, scale, rot)
    if abs(sx - 1) > 1e-3 or abs(sy - 1) > 1e-3:
        s = s.resize((int(s.width * sx), int(s.height * sy)), Image.BILINEAR)
    canvas.paste(s, (int(x - s.width / 2), int(y - s.height / 2)), s)


# ---------------------------------------------------------------- 하늘 / 구름
def make_sky():
    y = np.linspace(0, 1, H)[:, None, None]
    top, bot = np.array((24, 92, 210), np.float32), np.array((150, 210, 255), np.float32)
    img = np.repeat(top * (1 - y) + bot * y, W, axis=1)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    sun = np.exp(-(((xx - 880) ** 2 + (yy - 220) ** 2) / (260 ** 2)))[..., None]
    img = img * (1 - sun * 0.8) + np.array((255, 250, 225), np.float32) * sun * 0.8
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


SKY = make_sky()


def make_cloud(w, seed):
    rng = random.Random(seed)
    h = int(w * 0.8)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    for _ in range(22):
        r = rng.uniform(0.09, 0.19) * w
        cx = rng.uniform(0.28, 0.72) * w
        hump = 0.12 * h * math.cos((cx / w - 0.5) * math.pi * 1.6)
        cy = rng.uniform(0.5, 0.62) * h - hump
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    d.rounded_rectangle((0.22 * w, 0.52 * h, 0.78 * w, 0.68 * h), int(0.08 * h), fill=(255, 255, 255, 255))
    base = np.asarray(img).astype(np.float32)
    gy = np.linspace(0, 1, h)[:, None]
    base[..., 0] -= 70 * gy ** 1.5
    base[..., 1] -= 45 * gy ** 1.5
    base[..., 2] -= 10 * gy ** 1.5
    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    return out.filter(ImageFilter.GaussianBlur(w // 34))


CLOUDS = [make_cloud(random.randint(420, 900), k) for k in range(7)]
SPAN = 5200
CLOUD_FIELD = []
for layer, n, sc in ((0, 14, 0.7), (1, 10, 1.0), (2, 5, 1.8)):
    for _ in range(n):
        CLOUD_FIELD.append(dict(c=random.randrange(len(CLOUDS)), x=random.uniform(-150, W + 150),
                                y=random.uniform(0, SPAN), layer=layer,
                                s=sc * random.uniform(0.8, 1.2)))
_cloud_cache = {}


def cloud_sprite(idx, s, alpha):
    key = (idx, round(s, 1), round(alpha, 1))
    if key not in _cloud_cache:
        c = CLOUDS[idx]
        c = c.resize((int(c.width * key[1]), int(c.height * key[1])), Image.BILINEAR)
        if key[2] < 1:
            c.putalpha(c.getchannel("A").point(lambda v: int(v * key[2])))
        _cloud_cache[key] = c
    return _cloud_cache[key]


def sky_frame(scroll, layers=(0, 1), alpha=1.0):
    """scroll: 누적 낙하 거리(px). 구름은 위로 흘러간다 = 카메라가 떨어지는 느낌."""
    c = SKY.copy()
    for cl in CLOUD_FIELD:
        if cl["layer"] not in layers:
            continue
        speed = (0.5, 1.0, 2.2)[cl["layer"]]
        y = (cl["y"] - scroll * speed) % SPAN - 600
        if y > H + 400:
            continue
        a = (0.75, 0.95, 0.9)[cl["layer"]] * alpha
        s = cloud_sprite(cl["c"], cl["s"], a)
        c.paste(s, (int(cl["x"] - s.width / 2), int(y - s.height / 2)), s)
    return c


def speed_streaks(canvas, i, n=26, alpha=110):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = random.Random(i)
    for _ in range(n):
        x = rng.uniform(0, W)
        y = rng.uniform(-200, H)
        L = rng.uniform(150, 420)
        d.line((x, y, x, y + L), fill=(255, 255, 255, alpha), width=rng.randint(2, 5))
    canvas.paste(layer, (0, 0), layer)


# ---------------------------------------------------------------- 착지 효과
def impact_fx(canvas, cx, cy, t, seed):
    """t: 착지 후 경과 프레임."""
    if t < 0 or t > 22:
        return
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for k, delay in enumerate((0, 4)):
        tt = (t - delay) / 16
        if 0 <= tt <= 1:
            r = lerp(60, 760, out_expo(tt))
            wdt = int(30 * (1 - tt)) + 2
            d.ellipse((cx - r, cy - r * 0.38, cx + r, cy + r * 0.38),
                      outline=(255, 255, 255, int(230 * (1 - tt))), width=wdt)
    rng = random.Random(seed)
    for _ in range(46):
        ang = rng.uniform(math.pi, 2 * math.pi)
        sp = rng.uniform(14, 46)
        px = cx + math.cos(ang) * sp * t
        py = cy + math.sin(ang) * sp * t * 0.6 + 1.6 * t * t
        r = rng.uniform(6, 16) * (1 - t / 22)
        col = rng.choice([(255, 240, 120), (255, 255, 255), (255, 170, 60)])
        d.ellipse((px - r, py - r, px + r, py + r), fill=col + (int(255 * (1 - t / 22)),))
    canvas.paste(layer, (0, 0), layer)


def burst_stars(canvas, cx, cy, t, seed):
    if t < 0 or t > 16:
        return
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(26):
        ang = rng.uniform(0, 2 * math.pi)
        sp = rng.uniform(25, 60)
        px, py = cx + math.cos(ang) * sp * t, cy + math.sin(ang) * sp * t
        r = rng.uniform(14, 28) * (1 - t / 16)
        pts = []
        for k in range(10):
            rr = r if k % 2 == 0 else r * 0.42
            a = k * math.pi / 5 + t * 0.3
            pts.append((px + rr * math.cos(a), py + rr * math.sin(a)))
        d.polygon(pts, fill=rng.choice([YELLOW, WHITE, (255, 140, 200)]) + (255,))
    canvas.paste(layer, (0, 0), layer)


# 하단 띠지 티커
TICKER_TXT = "  10월 한정  ★  선착순 특별혜택  ★  한정수량  ★  오픈런 GO!  ★"
_tf = ImageFont.truetype(BH, 64)
_tw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(TICKER_TXT, font=_tf))
TICKER = Image.new("RGBA", (_tw * 3, 110), RED + (255,))
for _k in range(3):
    ImageDraw.Draw(TICKER).text((_k * _tw, 14), TICKER_TXT, font=_tf, fill=WHITE)


def ticker(canvas, i, y=1720, rot=-4):
    off = (i * 14) % _tw
    strip = TICKER.crop((off, 0, off + W + 300, 110))
    band = Image.new("RGBA", (strip.width, 130), YELLOW + (255,))
    band.paste(strip, (0, 10), strip)
    put(canvas, band, W / 2, y, rot=rot)


CONFETTI = [dict(x=random.uniform(0, W), y=random.uniform(-900, -40), vy=random.uniform(28, 46),
                 vx=random.uniform(-6, 6), r=random.uniform(0, 360), vr=random.uniform(-25, 25),
                 c=random.choice([YELLOW, RED, WHITE, (60, 200, 255), (120, 255, 140)]),
                 w=random.randint(16, 30), h=random.randint(30, 52)) for _ in range(80)]


def confetti(canvas, t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for p in CONFETTI:
        y = p["y"] + p["vy"] * t
        if y < -60 or y > H + 60:
            continue
        x = p["x"] + p["vx"] * t + 40 * math.sin(t * 0.3 + p["r"])
        a = math.radians(p["r"] + p["vr"] * t)
        hw, hh = p["w"] / 2, p["h"] / 2 * (0.3 + 0.7 * abs(math.cos(t * 0.25 + p["r"])))
        d.polygon([(x + dx * math.cos(a) - dy * math.sin(a), y + dx * math.sin(a) + dy * math.cos(a))
                   for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))], fill=p["c"] + (255,))
    canvas.paste(layer, (0, 0), layer)


# ---------------------------------------------------------------- 스프라이트
SP = dict(
    s1_a=text_sprite("부산 하늘에서", NOTO, 110, WHITE, stroke=8),
    s1_b=text_sprite("애플이\n쏟아진다?!", BH, 220, YELLOW, stroke=14),
    s2_pill=pill("덕천 하이마트 × Apple", NOTO, 62, WHITE, NAVY),
    s2_month=text_sprite("10월", BH, 380, YELLOW, stroke=16),
    s2_sub=text_sprite("한정 행사", BH, 190, WHITE, stroke=12),
    land=pill("덕천 하이마트 착륙!", NOTO, 66, RED, WHITE),
    s3_a=text_sprite("iPhone", BH, 150, WHITE, stroke=10),
    s3_b=text_sprite("10월 한정 특가", BH, 150, YELLOW, stroke=12),
    s4_stamp=pill("한정수량", BH, 200, RED, WHITE, padx=60, pady=30, radius=30, border=WHITE),
    s4_sub=text_sprite("iPad도 떨어졌다!", BH, 120, WHITE, stroke=10),
    gauge=text_sprite("남은 수량", NOTO, 54, WHITE, stroke=4, shadow=False),
    s5_a=text_sprite("선착순", BH, 280, YELLOW, stroke=14),
    s5_b=text_sprite("특별혜택", BH, 220, WHITE, stroke=12),
    s5_gift=pill("GIFT", BH, 90, RED, WHITE, radius=20),
    s6_a=text_sprite("오픈런", BH, 320, YELLOW, stroke=16),
    s6_b=text_sprite("달려와!!!", BH, 200, WHITE, stroke=12),
    s7_top=text_sprite("하늘이 준 기회!", BH, 150, WHITE, stroke=12),
    s7_tag=pill("10월 한정 · 선착순 특별혜택", NOTO, 58, YELLOW, BLACK),
    s7_l1=text_sprite("부산 덕천", BH, 190, WHITE, stroke=12),
    s7_l2=text_sprite("하이마트", BH, 220, WHITE, stroke=12),
    s7_l3=text_sprite("Apple 매장", BH, 170, YELLOW, stroke=12),
    s7_cta=pill("지금 오픈런 GO!", BH, 104, RED, WHITE, padx=70, pady=34, border=WHITE),
    s7_note=text_sprite("※ 한정수량 소진 시 조기 종료될 수 있습니다", NOTO, 38, WHITE,
                        stroke=4, shadow=False),
)

# ---------------------------------------------------------------- 타임라인
SCENES = [  # (시작, 끝)
    (0, 90),     # S1 하늘 – 아이폰과 함께 낙하
    (90, 165),   # S2 애플 기기 비
    (165, 240),  # S3 아이폰 착지 → 실제 매장
    (240, 315),  # S4 아이패드 착지 – 한정수량
    (315, 375),  # S5 애플워치 착지 – 선착순 혜택
    (375, 450),  # S6 맥북 착지 – 초고속 오픈런
    (450, 570),  # S7 엔딩 – 하늘에서 쏟아지는 애플 + CTA
]
TOTAL = SCENES[-1][1]
IMPACT = 10  # 착지 장면에서 기기가 바닥에 닿는 프레임

print("클립 로딩…", flush=True)
C = {
    3: load_clip(IPHONE, 1.6, 75, speed=1.2),
    4: load_clip(IPAD, 0.4, 75, speed=1.1),
    5: load_clip(WATCH, 0.0, 60),
    6: load_clip(MAC_BOOT, 2.0, 75),
}
BLUR = {k: [f.filter(ImageFilter.GaussianBlur(16)) for f in v[:IMPACT + 12]] for k, v in C.items()}


def scene1(i):
    scroll = i * 46 + 20 * i * i / 90
    c = sky_frame(scroll, layers=(0, 1))
    speed_streaks(c, i, 18, 90)
    # 아이폰이 카메라와 같이 떨어지며 빙글빙글
    if i < 70:
        y = lerp(-420, 1180, out_expo(prog(i, 0, 22))) + 18 * math.sin(i * 0.2)
        vy = 70 if i < 22 else 30
    else:
        y = 1180 + 140 * ((i - 70) / 6) ** 2
        vy = 60 + 20 * (i - 70)
    falling_device(c, "iphone", W / 2 + 60 * math.sin(i * 0.07), y, 1.05,
                   rot=25 * math.sin(i * 0.12), vy=vy, trail=1.0)
    # 앞 구름 레이어(카메라 근처) – 휙휙 지나감
    for cl in CLOUD_FIELD:
        if cl["layer"] == 2:
            yy = (cl["y"] - scroll * 2.2) % SPAN - 600
            s = cloud_sprite(cl["c"], cl["s"], 0.9)
            c.paste(s, (int(cl["x"] - s.width / 2), int(yy - s.height / 2)), s)
    at_ = out_expo(prog(i, 4, 14))
    put(c, SP["s1_a"], lerp(-700, W / 2, at_), 340)
    bt = prog(i, 14, 22)
    if i >= 14:
        put(c, SP["s1_b"], W / 2, 640, scale=lerp(2.6, 1, out_expo(bt)) * (1 + 0.03 * math.sin(i * 0.6)),
            rot=-5, alpha=clamp(bt * 3))
    return flash(c, (1 - prog(i, 0, 6)) * 0.9)


RAIN = []
for _k in range(14):
    RAIN.append(dict(name=random.choice(["iphone", "ipad", "mac", "watch", "iphone", "watch"]),
                     x=random.uniform(120, W - 120), start=random.uniform(-6, 60),
                     vy=random.uniform(55, 85), vx=random.uniform(-5, 5),
                     s=random.uniform(0.45, 0.75), r0=random.uniform(-40, 40),
                     vr=random.uniform(-6, 6)))


def rain(canvas, i, items=RAIN, alpha_scale=1.0, period=None):
    for d in items:
        t = i - d["start"]
        if period:
            t = t % period
        if t < 0:
            continue
        y = -400 + d["vy"] * t
        if y > H + 500:
            continue
        falling_device(canvas, d["name"], d["x"] + d["vx"] * t, y, d["s"] * alpha_scale,
                       rot=d["r0"] + d["vr"] * t, vx=d["vx"], vy=d["vy"], trail=0.8)


def scene2(i):
    scroll = (90 * 46 + 20 * 90) + i * 30
    c = sky_frame(scroll)
    rain(c, i)
    pt = out_back(prog(i, 2, 12))
    put(c, SP["s2_pill"], W / 2, lerp(-100, 330, pt))
    mt = prog(i, 6, 18)
    sx, sy = shake(i, 9, 10, 20)
    put(c, SP["s2_month"], W / 2 + sx, 760 + sy, scale=out_elastic(mt) * (1 + 0.03 * math.sin(i * 0.5)),
        rot=lerp(-30, -4, out_expo(mt)))
    st = out_expo(prog(i, 16, 24))
    put(c, SP["s2_sub"], lerp(W + 700, W / 2, st), 1080)
    # 장면 끝: 하얗게 번쩍 → 매장으로 낙하
    return flash(c, prog(i, 66, 75) ** 2)


def landing_bg(k, i):
    sharp = at(C[k], i)
    if i < IMPACT + 12:
        b = BLUR[k][min(i, len(BLUR[k]) - 1)]
        t = prog(i, IMPACT + 2, IMPACT + 11)
        return Image.blend(b, sharp, t) if t > 0 else b
    return sharp


def landing(i, k, name, land_y=1180, scale=1.15, seed=0, from_x=None):
    """기기가 하늘에서 떨어져 '쾅' 착지 → 별 터짐과 함께 실제 매장 영상 공개."""
    sx, sy = shake(i, IMPACT, 12, 40)
    c = cam(landing_bg(k, i), zoom=1.08 + 0.0015 * i, tx=sx, ty=sy)
    c = darken_grad(c, 0.55, 0.5, 0.12)
    fx = from_x if from_x is not None else W / 2
    if i < IMPACT:
        t = i / IMPACT
        y = lerp(-600, land_y, t * t)
        falling_device(c, name, lerp(fx, W / 2, t), y, scale, rot=lerp(35, 0, t),
                       vx=(W / 2 - fx) / IMPACT, vy=2 * (land_y + 600) / IMPACT * t + 20, trail=1.0)
        speed_streaks(c, i, 30, 120)
    elif i < IMPACT + 9:
        t = i - IMPACT
        sq = math.exp(-t * 0.45) * math.cos(t * 1.4)
        falling_device(c, name, W / 2 + sx, land_y + sy + 30 * sq, scale, trail=0,
                       sx=1 + 0.22 * sq, sy=1 - 0.22 * sq)
    else:
        t = prog(i, IMPACT + 9, IMPACT + 15)
        s = dev_sprite(name, scale, 0)
        put(c, s, W / 2, land_y, scale=1 + 0.6 * t, alpha=1 - t)
    impact_fx(c, W / 2, land_y + 180, i - IMPACT, seed)
    burst_stars(c, W / 2, land_y, i - IMPACT - 9, seed + 1)
    c = flash(c, (1 - prog(i, IMPACT, IMPACT + 5)) * 0.85 * (i >= IMPACT))
    c = flash(c, (1 - prog(i, 0, 4)) * 0.9)  # 앞 장면에서 넘어오는 화이트
    return c, sx, sy


def scene3(i):
    c, sx, sy = landing(i, 3, "iphone", seed=3)
    put(c, SP["land"], W / 2, lerp(-100, 300, out_back(prog(i, IMPACT, IMPACT + 8))), rot=-3)
    put(c, SP["s3_a"], lerp(-600, W / 2, out_expo(prog(i, IMPACT + 12, IMPACT + 20))), 560)
    bt = prog(i, IMPACT + 18, IMPACT + 28)
    put(c, SP["s3_b"], W / 2, 760, scale=out_elastic(bt), rot=-3)
    ticker(c, i + 165)
    return c


def scene4(i):
    c, sx, sy = landing(i, 4, "ipad", seed=4, from_x=W * 0.9)
    st = prog(i, IMPACT + 1, IMPACT + 7)
    if i > IMPACT:
        put(c, SP["s4_stamp"], W / 2 + sx, 440 + sy, scale=lerp(2.6, 1, out_expo(st)), rot=-9,
            alpha=clamp(st * 2.5))
    put(c, SP["s4_sub"], W / 2, lerp(H + 200, 700, out_back(prog(i, IMPACT + 12, IMPACT + 22))))
    if i >= IMPACT + 18:
        a = out_expo(prog(i, IMPACT + 18, IMPACT + 24))
        lvl = lerp(1.0, 0.17, out_expo(prog(i, IMPACT + 20, 70)))
        d = ImageDraw.Draw(c)
        x0, x1, y0 = 170, 910, 1500
        put(c, SP["gauge"], 330, y0 - 40, alpha=a)
        d.rounded_rectangle((x0, y0, x1, y0 + 70), 35, fill=(40, 40, 40), outline=WHITE, width=6)
        col = RED if (lvl < 0.4 and (i // 3) % 2) else (YELLOW if lvl >= 0.4 else (255, 120, 120))
        d.rounded_rectangle((x0 + 10, y0 + 10, x0 + 10 + int((x1 - x0 - 20) * lvl), y0 + 60), 25, fill=col)
        d.text((x1 - 10, y0 - 70), f"{int(lvl * 100)}%", font=ImageFont.truetype(BH, 70),
               fill=YELLOW, anchor="ra", stroke_width=5, stroke_fill=BLACK)
    ticker(c, i + 240)
    return c


def scene5(i):
    c, sx, sy = landing(i, 5, "watch", land_y=1150, scale=1.2, seed=5, from_x=W * 0.15)
    if i > IMPACT + 6:
        confetti(c, i - IMPACT - 6)
    at_ = out_back(prog(i, IMPACT + 8, IMPACT + 16), 2.5)
    put(c, SP["s5_a"], lerp(-600, W / 2, at_), 520, rot=lerp(30, -5, at_))
    bt = out_back(prog(i, IMPACT + 12, IMPACT + 20), 2.5)
    put(c, SP["s5_b"], lerp(W + 600, W / 2, bt), 780, rot=lerp(-30, 3, bt))
    put(c, SP["s5_gift"], 860, 330, scale=out_elastic(prog(i, IMPACT + 18, IMPACT + 34)),
        rot=15 + 6 * math.sin(i * 0.4))
    ticker(c, i + 315)
    return c


def scene6(i):
    c, sx, sy = landing(i, 6, "mac", land_y=1250, scale=1.1, seed=6)
    if i > IMPACT + 12:
        speed_streaks(c, i, 22, 90)
        sx2, sy2 = 8 * math.sin(i * 2.1), 8 * math.cos(i * 1.7)
    else:
        sx2 = sy2 = 0
    at_ = out_expo(prog(i, IMPACT + 12, IMPACT + 18))
    if i >= IMPACT + 12:
        s = SP["s6_a"]
        stretch = lerp(2.2, 1, at_)
        s = s.resize((int(s.width * stretch), s.height), Image.BILINEAR)
        put(c, s, lerp(W + 900, W / 2, at_) + sx2, 1180 + sy2, rot=8, scale=1 + 0.05 * math.sin(i * 0.9))
    put(c, SP["s6_b"], W / 2, lerp(H + 200, 1420, out_back(prog(i, IMPACT + 20, IMPACT + 28), 3)), rot=-4)
    ticker(c, i + 375)
    return c


RAIN_END = []
for _k in range(12):
    RAIN_END.append(dict(name=["iphone", "ipad", "mac", "watch"][_k % 4],
                         x=[150, 930, 260, 820, 540, 120, 960, 380, 700, 200, 880, 540][_k],
                         start=_k * 7 - 10, vy=random.uniform(40, 60), vx=random.uniform(-3, 3),
                         s=random.uniform(0.35, 0.55), r0=random.uniform(-30, 30),
                         vr=random.uniform(-4, 4)))


def scene7(i):
    scroll = 8000 + i * 18
    c = sky_frame(scroll)
    rain(c, i, RAIN_END, period=60)
    # 글자 가독성을 위한 은은한 남색 베일
    veil = Image.new("RGBA", (W, H), NAVY + (int(90 * prog(i, 0, 10)),))
    c.paste(veil, (0, 0), veil)
    put(c, SP["s7_top"], W / 2, 300, scale=out_elastic(prog(i, 0, 16)), rot=-4)
    put(c, SP["s7_tag"], W / 2, lerp(-100, 500, out_back(prog(i, 8, 18))))
    put(c, SP["s7_l1"], lerp(-800, W / 2, out_expo(prog(i, 12, 20))), 720)
    put(c, SP["s7_l2"], lerp(W + 800, W / 2, out_expo(prog(i, 16, 24))), 950)
    # 'Apple 매장'은 하늘에서 떨어져 쾅
    lt = prog(i, 22, 30)
    if i >= 22:
        y = lerp(-200, 1170, lt * lt)
        sq = math.exp(-(i - 30) * 0.4) * math.cos((i - 30) * 1.4) if i >= 30 else 0
        put(c, SP["s7_l3"], W / 2, y, sx=1 + 0.2 * sq, sy=1 - 0.2 * sq)
    sx, sy = shake(i, 30, 10, 26)
    ct = out_back(prog(i, 36, 46), 2.5)
    pulse = 1 + 0.06 * max(0, math.sin((i - 46) * 0.42)) * (i > 46)
    put(c, SP["s7_cta"], W / 2, lerp(H + 200, 1430, ct), scale=pulse)
    put(c, SP["s7_note"], W / 2, 1700, alpha=prog(i, 46, 56))
    if sx or sy:
        c = cam(c, tx=sx, ty=sy)
    c = flash(c, (1 - prog(i, 30, 35)) * 0.5 * (i >= 30))
    return flash(c, (1 - prog(i, 0, 6)) * 0.9)


RENDER = [scene1, scene2, scene3, scene4, scene5, scene6, scene7]


def frame(n):
    for k, (s, e) in enumerate(SCENES):
        if s <= n < e:
            break
    img = RENDER[k](n - s).convert("RGB")
    # 착지 장면 사이: 아래로 휙 떨어지는 전환 (끝 4프레임)
    if 2 <= k <= 4 and e - n <= 4:
        t = (5 - (e - n)) / 4
        img = flash(motion_blur_v(cam(img, ty=H * 0.6 * t * t), 260 * t, 9), 0.6 * t)
    if k == 5 and e - n <= 5:
        img = flash(img, (6 - (e - n)) / 5 * 0.9)
    return img


# ---------------------------------------------------------------- 오디오
SR = 44100


def make_audio(path):
    dur = TOTAL / FPS
    N = int(SR * dur)
    mix = np.zeros(N, np.float32)
    rng = np.random.default_rng(3)

    def add(sig, t, g=1.0):
        a = int(t * SR)
        if a < 0:
            sig, a = sig[-a:], 0
        if a >= N:
            return
        b = min(N, a + len(sig))
        mix[a:b] += sig[: b - a] * g

    def band_noise(n, lo, hi):
        X = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / SR)
        X[(f < lo) | (f > hi)] = 0
        y = np.fft.irfft(X, n)
        return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)

    tt = np.arange(int(0.45 * SR)) / SR
    kick = np.sin(2 * np.pi * (45 * tt + (110 / 18) * (1 - np.exp(-18 * tt)))) * np.exp(-7 * tt)
    snare = band_noise(int(0.22 * SR), 900, 9000) * np.exp(-18 * np.arange(int(0.22 * SR)) / SR)
    hat = band_noise(int(0.06 * SR), 7000, 16000) * np.exp(-60 * np.arange(int(0.06 * SR)) / SR)
    bt_ = np.arange(int(1.2 * SR)) / SR
    boom = (np.sin(2 * np.pi * (38 * bt_ + 5 * (1 - np.exp(-6 * bt_)))) * np.exp(-3 * bt_)
            + 0.6 * band_noise(len(bt_), 40, 2500) * np.exp(-8 * bt_))

    def fall_whistle(length=0.4, f0=1900, f1=500):
        n = int(length * SR)
        t = np.arange(n) / SR
        f = f0 * (f1 / f0) ** (t / length)
        ph = 2 * np.pi * np.cumsum(f) / SR
        env = np.minimum(1, t * 30) * (0.6 + 0.4 * t / length)
        return (np.sin(ph) * env * 0.5 + band_noise(n, 400, 6000) * (t / length) ** 2 * 0.5).astype(np.float32)

    def whoosh(length=0.35):
        n = int(length * SR)
        return band_noise(n, 300, 8000) * np.linspace(0, 1, n) ** 2.5

    beat, roots = 0.5, [55.0, 43.65, 65.41, 49.0]
    t, k = 0.0, 0
    while t < dur - 0.05:
        if t >= 0.5 and not (14.8 < t < 15.0):
            add(kick, t, 0.85)
            if k % 4 in (1, 3):
                add(snare, t, 0.4)
            add(hat, t + beat / 2, 0.2)
            f0 = roots[(k // 4) % 4]
            for h in (0, 0.25):
                b = np.arange(int(0.22 * SR)) / SR
                env = np.minimum(1, b * 60) * np.exp(-6 * b)
                bass = (np.sin(2 * np.pi * f0 * b) + 0.35 * np.sin(4 * np.pi * f0 * b)) * env
                add(bass.astype(np.float32), t + h + 0.04, 0.32)
        t += beat
        k += 1

    # 낙하 휘슬 + 착지 쾅
    add(fall_whistle(0.8, 2200, 700), 0.0, 0.5)
    add(fall_whistle(0.25, 1600, 600), 70 / FPS, 0.5)
    for s, _ in SCENES[2:6]:
        add(fall_whistle(IMPACT / FPS, 2000, 450), s / FPS, 0.6)
        add(boom, (s + IMPACT) / FPS, 0.9)
    for d in RAIN[::3]:
        add(whoosh(0.3), (90 + max(0, d["start"])) / FPS, 0.25)
    add(boom, 14 / FPS, 0.6)
    add(boom, (90 + 9) / FPS, 0.6)
    add(fall_whistle(8 / 30, 1800, 500), (450 + 22) / FPS, 0.5)
    add(boom, (450 + 30) / FPS, 0.9)
    rn = int(1.2 * SR)
    add(band_noise(rn, 500, 12000) * np.linspace(0, 1, rn) ** 3, 450 / FPS - 1.2, 0.3)

    fade = int(0.6 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix /= np.abs(mix).max() + 1e-9
    mix *= 10 ** (-3 / 20)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    only = os.environ.get("FRAMES")  # 미리보기: FRAMES="10,100,200"
    if only:
        for n in map(int, only.split(",")):
            frame(n).save(OUT.rsplit(".", 1)[0] + f"_{n:03d}.jpg", quality=85)
        sys.exit()
    wav = OUT.rsplit(".", 1)[0] + "_bgm.wav"
    make_audio(wav)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(TOTAL):
        p.stdin.write(frame(n).tobytes())
        if n % 60 == 0:
            print(f"frame {n}/{TOTAL}", flush=True)
    p.stdin.close()
    p.wait()
    print("done", OUT)
