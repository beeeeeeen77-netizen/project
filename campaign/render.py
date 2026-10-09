"""덕천 하이마트 Apple 10월 한정 오픈런 캠페인 숏폼 렌더러 (1080x1920, 30fps, 18.5s).

사용법: python3 render.py <클립폴더> <폰트폴더> <출력.mp4>
클립폴더에는 업로드된 5개 원본(…-11 ~ …-55.mp4)이 있어야 합니다.
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
NAVY = (12, 16, 40)

random.seed(7)


def clip_path(tag):
    return glob.glob(os.path.join(CLIP_DIR, f"*-{tag}.mp4"))[0]


IPAD, IPHONE, WATCH, MAC_BOOT, MAC_OPEN = (clip_path(t) for t in ("11", "22", "33", "44", "55"))


# ---------------------------------------------------------------- 영상 로딩
def load_clip(path, start, nframes, speed=1.0, w=W, h=H):
    vf = (f"setpts=PTS/{speed},fps={FPS},"
          f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}")
    dur = nframes / FPS * speed + 0.5
    cmd = ["ffmpeg", "-v", "error", "-ss", str(start), "-i", path, "-t", str(dur),
           "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    arr = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)
    return [Image.fromarray(a) for a in arr[:nframes]]


def at(frames, i):
    return frames[max(0, min(i, len(frames) - 1))]


# ---------------------------------------------------------------- 이징
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(i, s, e):
    return clamp((i - s) / max(1, e - s))


def out_expo(t):
    return 1 if t >= 1 else 1 - 2 ** (-10 * t)


def out_back(t, k=2.2):
    t -= 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


def out_elastic(t):
    if t <= 0 or t >= 1:
        return clamp(t)
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------- 그래픽 요소
def text_sprite(txt, font, size, fill=WHITE, stroke=0, stroke_fill=BLACK,
                shadow=True, spacing=0, align="center"):
    f = ImageFont.truetype(font, size)
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = tmp.multiline_textbbox((0, 0), txt, font=f, stroke_width=stroke,
                                        spacing=spacing, align=align)
    pad = 40
    img = Image.new("RGBA", (r - l + pad * 2, b - t + pad * 2), (0, 0, 0, 0))
    pos = (pad - l, pad - t)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).multiline_text((pos[0] + 10, pos[1] + 14), txt, font=f,
                                          fill=(0, 0, 0, 170), stroke_width=stroke,
                                          stroke_fill=(0, 0, 0, 170), spacing=spacing,
                                          align=align)
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(img).multiline_text(pos, txt, font=f, fill=fill, stroke_width=stroke,
                                       stroke_fill=stroke_fill, spacing=spacing, align=align)
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
                                         fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((m, m, m + w, m + h), rad, fill=bg,
                        outline=border, width=8 if border else 0)
    d.text((m + padx - l, m + pady - t), txt, font=f, fill=fg)
    return img


def put(canvas, spr, cx, cy, scale=1.0, rot=0.0, alpha=1.0):
    if scale <= 0.02 or alpha <= 0.01:
        return
    s = spr
    if abs(scale - 1) > 1e-3:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))),
                     Image.BILINEAR)
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
    A, B = c, s
    C = cx - c * (cx + tx) - s * (cy + ty)
    D, E = -s, c
    F = cy + s * (cx + tx) - c * (cy + ty)
    return img.transform((W, H), Image.AFFINE, (A, B, C, D, E, F),
                         resample=Image.BILINEAR, fillcolor=fill)


def darken_grad(img, top=0.55, bottom=0.6, mid=0.15):
    a = np.asarray(img).astype(np.float32)
    y = np.linspace(0, 1, H)[:, None, None]
    k = np.where(y < 0.5, lerp(top, mid, y / 0.5), lerp(mid, bottom, (y - 0.5) / 0.5))
    return Image.fromarray((a * (1 - k)).astype(np.uint8))


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


def rgb_split(img, d):
    if d < 1:
        return img
    a = np.asarray(img).copy()
    d = int(d)
    a[:, :, 0] = np.roll(a[:, :, 0], d, axis=1)
    a[:, :, 2] = np.roll(a[:, :, 2], -d, axis=1)
    return Image.fromarray(a)


def glitch_slices(img, strength, seed):
    rng = random.Random(seed)
    a = np.asarray(img).copy()
    for _ in range(int(6 * strength) + 2):
        y = rng.randrange(0, H - 80)
        hgt = rng.randrange(20, 160)
        a[y:y + hgt] = np.roll(a[y:y + hgt], rng.randint(-90, 90) * int(strength + 1), axis=1)
    return Image.fromarray(a)


def motion_blur(img, dx, dy, n=7):
    if abs(dx) + abs(dy) < 4:
        return img
    a = np.asarray(img).astype(np.float32)
    acc = np.zeros_like(a)
    for k in range(n):
        f = k / (n - 1) - 0.5
        acc += np.roll(np.roll(a, int(dx * f), axis=1), int(dy * f), axis=0)
    return Image.fromarray((acc / n).astype(np.uint8))


# 스피드 라인 (오픈런 장면)
SPEED_LINES = [(random.uniform(0, 2 * math.pi), random.uniform(0.004, 0.012),
                random.uniform(0.35, 0.7)) for _ in range(70)]


def speed_lines(canvas, i, alpha=170):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy, R = W / 2, H * 0.45, 1500
    rng = random.Random(i)
    for ang, wd, r0 in SPEED_LINES:
        if rng.random() < 0.45:
            continue
        r_in = R * (r0 + rng.uniform(-0.08, 0.08))
        p = [(cx + math.cos(ang - wd) * R, cy + math.sin(ang - wd) * R),
             (cx + math.cos(ang + wd) * R, cy + math.sin(ang + wd) * R),
             (cx + math.cos(ang) * r_in, cy + math.sin(ang) * r_in)]
        d.polygon(p, fill=(255, 255, 255, alpha))
    canvas.paste(layer, (0, 0), layer)


# 컨페티 (선착순 혜택 장면)
CONFETTI = [dict(x=random.uniform(0, W), y=random.uniform(-900, -40), vy=random.uniform(28, 46),
                 vx=random.uniform(-6, 6), r=random.uniform(0, 360), vr=random.uniform(-25, 25),
                 c=random.choice([YELLOW, RED, WHITE, (60, 200, 255), (120, 255, 140)]),
                 w=random.randint(16, 30), h=random.randint(30, 52)) for _ in range(90)]


def confetti(canvas, t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for p in CONFETTI:
        y = p["y"] + p["vy"] * t
        if y < -60 or y > H + 60:
            continue
        x = p["x"] + p["vx"] * t + 40 * math.sin(t * 0.3 + p["r"])
        a = math.radians(p["r"] + p["vr"] * t)
        sq = abs(math.cos(t * 0.25 + p["r"]))
        hw, hh = p["w"] / 2, p["h"] / 2 * (0.3 + 0.7 * sq)
        pts = [(x + dx * math.cos(a) - dy * math.sin(a), y + dx * math.sin(a) + dy * math.cos(a))
               for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        ImageDraw.Draw(layer).polygon(pts, fill=p["c"] + (255,))
    canvas.paste(layer, (0, 0), layer)


# 하단 띠지 티커
TICKER_TXT = "  10월 한정  ★  선착순 특별혜택  ★  한정수량  ★  오픈런 GO!  ★"
_tf = ImageFont.truetype(BH, 64)
_tw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(TICKER_TXT, font=_tf))
TICKER = Image.new("RGBA", (_tw * 3, 110), RED + (255,))
for k in range(3):
    ImageDraw.Draw(TICKER).text((k * _tw, 14), TICKER_TXT, font=_tf, fill=WHITE)
TICKER_W = _tw


def ticker(canvas, i, y=1690, rot=-4):
    off = (i * 14) % TICKER_W
    strip = TICKER.crop((off, 0, off + W + 300, 110))
    band = Image.new("RGBA", (strip.width, 130), YELLOW + (255,))
    band.paste(strip, (0, 10), strip)
    put(canvas, band, W / 2, y, rot=rot)


# 해바라기 배경 (S6)
def sunburst(i, c1=(255, 200, 0), c2=(255, 120, 0), n=18):
    img = Image.new("RGB", (W, H), c2)
    d = ImageDraw.Draw(img)
    cx, cy, R = W / 2, H * 0.42, 2400
    base = i * 1.6
    for k in range(n):
        a0 = math.radians(base + k * 360 / n)
        a1 = math.radians(base + k * 360 / n + 180 / n)
        d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)),
                   (cx + R * math.cos(a1), cy + R * math.sin(a1))], fill=c1)
    return img


def card(frame, w=470, h=640, label=None):
    f = frame.resize((w, int(w * H / W)), Image.BILINEAR)
    top = (f.height - h) // 2
    f = f.crop((0, top, w, top + h)).convert("RGBA")
    m = 30
    out = Image.new("RGBA", (w + 2 * m + 20, h + 2 * m + 20), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((m + 6, m + 14, m + w + 26, m + h + 34), 46,
                                         fill=(0, 0, 0, 160))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(10)))
    mask = Image.new("L", (w + 20, h + 20), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w + 19, h + 19), 46, fill=255)
    frame_box = Image.new("RGBA", (w + 20, h + 20), WHITE + (255,))
    inner = Image.new("L", (w, h), 0)
    ImageDraw.Draw(inner).rounded_rectangle((0, 0, w - 1, h - 1), 38, fill=255)
    frame_box.paste(f, (10, 10), inner)
    out.paste(frame_box, (m, m), mask)
    if label:
        put(out, label, out.width / 2, out.height - 90)
    return out


# ---------------------------------------------------------------- 스프라이트
SP = dict(
    s1_top=text_sprite("부산 애플 유저", NOTO, 120, WHITE, stroke=6),
    s1_big=text_sprite("주목!!", BH, 300, YELLOW, stroke=14),
    s1_badge=pill("긴급 속보", NOTO, 64, RED, WHITE, radius=18),
    s2_pill=pill("덕천 하이마트 × Apple", NOTO, 62, WHITE, NAVY),
    s2_month=text_sprite("10월", BH, 400, YELLOW, stroke=16),
    s2_sub=text_sprite("한정 행사", BH, 190, WHITE, stroke=12),
    s3_stamp=pill("한정수량", BH, 210, RED, WHITE, padx=60, pady=30, radius=30, border=WHITE),
    s3_sub=text_sprite("특가 찬스!", BH, 150, WHITE, stroke=10),
    s3_gauge_lbl=text_sprite("남은 수량", NOTO, 54, WHITE, stroke=4, shadow=False),
    s4_a=text_sprite("선착순", BH, 290, YELLOW, stroke=14),
    s4_b=text_sprite("특별혜택", BH, 230, WHITE, stroke=12),
    s4_gift=pill("GIFT", BH, 90, RED, WHITE, radius=20),
    s5_a=text_sprite("오픈런", BH, 330, YELLOW, stroke=16),
    s5_b=text_sprite("달려와!!!", BH, 200, WHITE, stroke=12),
    s6_top=text_sprite("놓치면 끝!", BH, 230, WHITE, stroke=14),
    s6_badge=pill("선착순 마감 임박", NOTO, 70, RED, WHITE),
    s6_labels=[pill(t, NOTO, 44, NAVY, WHITE, padx=30, pady=14)
               for t in ("iPhone", "iPad", "Mac", "Watch")],
    s7_tag=pill("10월 한정 · 선착순", NOTO, 66, YELLOW, BLACK),
    s7_l1=text_sprite("부산 덕천", BH, 200, WHITE, stroke=10),
    s7_l2=text_sprite("하이마트", BH, 230, WHITE, stroke=10),
    s7_l3=text_sprite("Apple 매장", BH, 170, YELLOW, stroke=10),
    s7_cta=pill("지금 오픈런 GO!", BH, 104, RED, WHITE, padx=70, pady=34, border=WHITE),
    s7_note=text_sprite("※ 한정수량 소진 시 조기 종료될 수 있습니다", NOTO, 38, (230, 230, 230),
                        stroke=3, shadow=False),
)

# ---------------------------------------------------------------- 타임라인
#  (시작프레임, 끝프레임, 들어오는 전환)
SCENES = [(0, 60, None), (60, 135, "whip"), (135, 210, "zoom"), (210, 270, "spin"),
          (270, 345, "glitch"), (345, 435, "drop"), (435, 555, "zoom")]
TOTAL = SCENES[-1][1]
TR = 6  # 전환 길이(프레임) – 이전 장면 끝 TR 프레임 + 다음 장면 처음 TR 프레임

print("클립 로딩…", flush=True)
C = {
    1: load_clip(MAC_OPEN, 0.15, 60, speed=1.35),
    2: load_clip(IPHONE, 1.5, 75, speed=1.25),
    3: load_clip(IPAD, 0.4, 75, speed=1.1),
    4: load_clip(WATCH, 0.0, 60, speed=1.0),
    5: load_clip(MAC_BOOT, 2.35, 75, speed=1.0),
    7: load_clip(MAC_OPEN, 4.6, 120, speed=0.9),
}
GRID = [load_clip(p, s, 90, speed=1.0, w=540, h=960)
        for p, s in ((IPHONE, 2.6), (IPAD, 1.0), (MAC_BOOT, 2.6), (WATCH, 0.3))]


def scene1(i):
    bg = at(C[1], i)
    t = out_expo(prog(i, 0, 14))
    sx, sy = shake(i, 12, 12, 30)
    img = darken_grad(cam(bg, zoom=lerp(1.5, 1.06, t) + 0.0015 * i, tx=sx, ty=sy))
    c = img.convert("RGB")
    # 긴급 속보 배지: 위에서 떨어지며 바운스
    bt = out_back(prog(i, 16, 26), 1.7)
    put(c, SP["s1_badge"], W / 2, lerp(-120, 450, bt), rot=lerp(25, 4, bt))
    # 부산 애플 유저: 왼쪽에서 슬라이드
    tt = out_expo(prog(i, 2, 12))
    put(c, SP["s1_top"], lerp(-700, W / 2, tt) + sx, 700 + sy)
    # 주목!!: 크게 쾅
    st = prog(i, 8, 14)
    if i >= 8:
        put(c, SP["s1_big"], W / 2 + sx, 960 + sy, scale=lerp(3.2, 1, out_expo(st))
            * (1 + 0.04 * math.sin(i * 0.8)), rot=-6, alpha=clamp(st * 3))
    c = flash(c, (1 - prog(i, 0, 5)) * 0.9 + (1 - prog(i, 13, 18)) * 0.5 * (i >= 13))
    return c


def scene2(i):
    bg = at(C[2], i)
    sx, sy = shake(i, 10, 10, 24)
    c = darken_grad(cam(bg, zoom=1.12 - 0.0015 * i, tx=sx, ty=sy), 0.6, 0.55)
    pt = out_back(prog(i, 2, 12))
    put(c, SP["s2_pill"], W / 2, lerp(-100, 330, pt))
    mt = prog(i, 6, 16)
    put(c, SP["s2_month"], W / 2 + sx, 740 + sy, scale=out_elastic(mt) * (1 + 0.03 * math.sin(i * 0.5)),
        rot=lerp(-30, -4, out_expo(mt)))
    st = out_expo(prog(i, 14, 22))
    put(c, SP["s2_sub"], lerp(W + 700, W / 2, st), 1080)
    ticker(c, i + 60)
    return c


def scene3(i):
    bg = at(C[3], i)
    sx, sy = shake(i, 14, 12, 34)
    c = darken_grad(cam(bg, zoom=1.08 + 0.002 * i, tx=sx, ty=sy), 0.6, 0.6)
    st = prog(i, 8, 14)
    if i >= 8:
        put(c, SP["s3_stamp"], W / 2 + sx, 640 + sy, scale=lerp(2.8, 1, out_expo(st)),
            rot=-10, alpha=clamp(st * 2.5))
    put(c, SP["s3_sub"], W / 2, lerp(H + 200, 950, out_back(prog(i, 18, 28))))
    # 재고 게이지: 줄어드는 바
    gt = prog(i, 24, 70)
    if i >= 22:
        a = out_expo(prog(i, 22, 28))
        d = ImageDraw.Draw(c)
        x0, x1, y0 = 170, 910, 1180
        lvl = lerp(1.0, 0.17, out_expo(gt))
        put(c, SP["s3_gauge_lbl"], 330, y0 - 40, alpha=a)
        d.rounded_rectangle((x0, y0, x1, y0 + 70), 35, fill=(40, 40, 40), outline=WHITE, width=6)
        col = RED if (lvl < 0.4 and (i // 3) % 2) else (YELLOW if lvl >= 0.4 else (255, 120, 120))
        d.rounded_rectangle((x0 + 10, y0 + 10, x0 + 10 + int((x1 - x0 - 20) * lvl), y0 + 60), 25, fill=col)
        d.text((x1 - 10, y0 - 70), f"{int(lvl * 100)}%", font=ImageFont.truetype(BH, 70),
               fill=YELLOW, anchor="ra", stroke_width=5, stroke_fill=BLACK)
    ticker(c, i + 135)
    return flash(c, (1 - prog(i, 13, 17)) * 0.6 * (i >= 13))


def scene4(i):
    bg = at(C[4], i)
    c = darken_grad(cam(bg, zoom=1.1 + 0.002 * i, rot=math.sin(i * 0.1) * 1.5), 0.55, 0.6)
    confetti(c, i)
    at_ = out_back(prog(i, 4, 13), 2.5)
    put(c, SP["s4_a"], lerp(-600, W / 2, at_), 620, rot=lerp(30, -5, at_))
    bt = out_back(prog(i, 9, 18), 2.5)
    put(c, SP["s4_b"], lerp(W + 600, W / 2, bt), 900, rot=lerp(-30, 3, bt))
    gt = out_elastic(prog(i, 16, 34))
    put(c, SP["s4_gift"], 850, 430, scale=gt, rot=15 + 6 * math.sin(i * 0.4))
    ticker(c, i + 210)
    return c


def scene5(i):
    bg = at(C[5], i)
    sx, sy = shake(i, 0, 75, 14)
    c = cam(bg, zoom=1.05 + 0.004 * i, tx=sx, ty=sy)
    c = darken_grad(c, 0.35, 0.55, 0.1)
    speed_lines(c, i, 120)
    at_ = out_expo(prog(i, 8, 14))
    if i >= 8:
        s = SP["s5_a"]
        stretch = lerp(2.2, 1, at_)
        sp = s.resize((int(s.width * stretch), s.height), Image.BILINEAR)
        put(c, sp, lerp(W + 900, W / 2, at_) + sx, 1180 + sy, rot=8,
            scale=1 + 0.05 * math.sin(i * 0.9))
    bt = out_back(prog(i, 16, 24), 3)
    put(c, SP["s5_b"], W / 2, lerp(H + 200, 1420, bt), rot=-4)
    ticker(c, i + 270)
    c = flash(c, (1 - prog(i, 13, 17)) * 0.5 * (i >= 13))
    return rgb_split(c, 10 * (1 - prog(i, 13, 20)) * (i >= 13))


def scene6(i):
    c = sunburst(i)
    dirs = [(-900, -500, -40), (W + 900, -500, 40), (-900, H + 500, 30), (W + 900, H + 500, -30)]
    pos = [(285, 820, -6), (795, 820, 5), (285, 1350, 4), (795, 1350, -5)]
    for k in range(4):
        t = out_back(prog(i, 4 + k * 4, 16 + k * 4), 1.8)
        if t <= 0:
            continue
        sx0, sy0, r0 = dirs[k]
        x, y, r = pos[k]
        cd = card(at(GRID[k], i), 430, 560, SP["s6_labels"][k])
        bob = 8 * math.sin(i * 0.25 + k)
        put(c, cd, lerp(sx0, x, t), lerp(sy0, y, t) + bob, scale=0.98, rot=lerp(r0, r, t))
    tt = prog(i, 0, 8)
    put(c, SP["s6_top"], W / 2, 330, scale=lerp(2.5, 1, out_expo(tt)) * (1 + 0.05 * math.sin(i * 0.7)),
        rot=-3, alpha=clamp(tt * 3))
    if i >= 10 and (i // 5) % 2 == 0 or i >= 60:
        put(c, SP["s6_badge"], W / 2, 520, scale=out_back(prog(i, 10, 18)), rot=2)
    ticker(c, i + 345, y=1720)
    return c


def scene7(i):
    bg = at(C[7], i).filter(ImageFilter.GaussianBlur(14))
    c = cam(bg, zoom=1.15 + 0.0012 * i)
    a = np.asarray(c).astype(np.float32) * 0.35 + np.array(NAVY, np.float32) * 0.4
    c = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    put(c, SP["s7_tag"], W / 2, lerp(-100, 420, out_back(prog(i, 2, 12))))
    put(c, SP["s7_l1"], lerp(-800, W / 2, out_expo(prog(i, 6, 14))), 650)
    put(c, SP["s7_l2"], lerp(W + 800, W / 2, out_expo(prog(i, 10, 18))), 870)
    lt = prog(i, 15, 24)
    put(c, SP["s7_l3"], W / 2, 1080, scale=out_elastic(lt))
    ct = out_back(prog(i, 24, 34), 2.5)
    pulse = 1 + 0.06 * max(0, math.sin((i - 34) * 0.42)) * (i > 34)
    put(c, SP["s7_cta"], W / 2, lerp(H + 200, 1390, ct), scale=pulse)
    put(c, SP["s7_note"], W / 2, 1640, alpha=prog(i, 34, 44))
    sx, sy = shake(i, 17, 10, 18)
    if sx or sy:
        c = cam(c, tx=sx, ty=sy)
    return flash(c, (1 - prog(i, 15, 19)) * 0.45 * (i >= 15))


RENDER = [scene1, scene2, scene3, scene4, scene5, scene6, scene7]


def transition(img, kind, t, direction):
    """t: 0→1 (전환 강도), direction: 'out' 또는 'in'."""
    e = t * t
    if kind == "whip":
        dx = (-1 if direction == "out" else 1) * W * 0.9 * e
        return motion_blur(cam(img, tx=dx), 220 * t, 0, 9)
    if kind == "drop":
        dy = (1 if direction == "out" else -1) * H * 0.8 * e
        return motion_blur(cam(img, ty=dy), 0, 260 * t, 9)
    if kind == "zoom":
        z = 1 + 1.6 * e if direction == "out" else 1 + 0.9 * e
        return flash(cam(img, zoom=z), 0.85 * t)
    if kind == "spin":
        rot = (35 if direction == "out" else -35) * e
        im = cam(img, zoom=1 + 0.8 * e, rot=rot)
        return flash(im.filter(ImageFilter.GaussianBlur(10 * t)), 0.3 * t)
    if kind == "glitch":
        return rgb_split(glitch_slices(img, 3 * t, int(t * 100)), 40 * t)
    return img


def frame(n):
    for k, (s, e, _) in enumerate(SCENES):
        if s <= n < e:
            break
    img = RENDER[k](n - s).convert("RGB")
    li = n - s
    kind_in = SCENES[k][2]
    if kind_in and li < TR:
        img = transition(img, kind_in, 1 - li / TR, "in")
    if k + 1 < len(SCENES) and e - n <= TR:
        img = transition(img, SCENES[k + 1][2], (TR - (e - n) + 1) / TR, "out")
    return img


# ---------------------------------------------------------------- 오디오 (BGM + 효과음)
SR = 44100


def make_audio(path):
    dur = TOTAL / FPS
    N = int(SR * dur)
    mix = np.zeros(N, np.float32)
    rng = np.random.default_rng(3)

    def add(sig, t, g=1.0):
        a = int(t * SR)
        if a >= N:
            return
        b = min(N, a + len(sig))
        mix[a:b] += sig[: b - a] * g

    def band_noise(n, lo, hi):
        x = rng.standard_normal(n)
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(n, 1 / SR)
        X[(f < lo) | (f > hi)] = 0
        y = np.fft.irfft(X, n)
        return (y / (np.abs(y).max() + 1e-9)).astype(np.float32)

    tt = np.arange(int(0.45 * SR)) / SR
    kick = np.sin(2 * np.pi * (45 * tt + (110 / 18) * (1 - np.exp(-18 * tt)))) * np.exp(-7 * tt)
    snare = band_noise(int(0.22 * SR), 900, 9000) * np.exp(-18 * np.arange(int(0.22 * SR)) / SR)
    hat = band_noise(int(0.06 * SR), 7000, 16000) * np.exp(-60 * np.arange(int(0.06 * SR)) / SR)
    boom_t = np.arange(int(1.2 * SR)) / SR
    boom = (np.sin(2 * np.pi * (38 * boom_t + 30 * (1 - np.exp(-6 * boom_t)) / 6)) * np.exp(-3 * boom_t)
            + 0.5 * band_noise(len(boom_t), 40, 1500) * np.exp(-9 * boom_t))

    def whoosh(length=0.35):
        n = int(length * SR)
        env = np.linspace(0, 1, n) ** 2.5
        return band_noise(n, 300, 8000) * env

    beat = 0.5  # 120 BPM
    roots = [55.0, 43.65, 65.41, 49.0]  # A1 F1 C2 G1
    t = 0.0
    k = 0
    while t < dur - 0.05:
        bar_beat = k % 4
        in_break = 16.9 < t < 17.4
        if not in_break:
            add(kick, t, 0.9)
            if bar_beat in (1, 3):
                add(snare, t, 0.45)
            add(hat, t + beat / 2, 0.22)
            if 11.5 <= t < 14.5:  # 드롭 구간 16비트 하이햇
                add(hat, t + beat / 4, 0.15)
                add(hat, t + 3 * beat / 4, 0.15)
            # 베이스 (사이드체인 느낌의 8분음)
            f0 = roots[(k // 4) % 4]
            for h in (0, 0.25):
                bt = np.arange(int(0.22 * SR)) / SR
                env = np.minimum(1, bt * 60) * np.exp(-6 * bt)
                bass = (np.sin(2 * np.pi * f0 * bt) + 0.35 * np.sin(4 * np.pi * f0 * bt)
                        + 0.15 * np.sin(6 * np.pi * f0 * bt)) * env
                add(bass.astype(np.float32), t + h + 0.04, 0.35)
        t += beat
        k += 1

    # 전환 우쉬 + 임팩트
    for s, _, kind in SCENES[1:]:
        ts = s / FPS
        add(whoosh(), ts - 0.33, 0.55)
    for f in (8, 135 + 8, 270 + 8, 345, 435 + 15):
        add(boom, f / FPS, 0.8)
    # 엔딩 직전 라이저
    rn = int(1.4 * SR)
    add(band_noise(rn, 500, 12000) * np.linspace(0, 1, rn) ** 3, 435 / FPS - 1.4, 0.35)

    fade = int(0.6 * SR)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix /= np.abs(mix).max() + 1e-9
    mix *= 10 ** (-3 / 20)
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    wav = OUT.rsplit(".", 1)[0] + "_bgm.wav"
    make_audio(wav)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
           "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(TOTAL):
        p.stdin.write(frame(n).tobytes())
        if n % 30 == 0:
            print(f"frame {n}/{TOTAL}", flush=True)
    p.stdin.close()
    p.wait()
    print("done", OUT)
