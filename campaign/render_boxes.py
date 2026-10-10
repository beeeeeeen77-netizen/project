"""[하늘에서 애플 박스가 쏟아진다] 롯데하이마트 덕천점 10월 한정 오픈런 캠페인 (1080x1920, 30fps, 19s).

레퍼런스: 부산 도심 하늘에서 흰색 애플 제품 박스들이 쏟아지고, 아래에 매장이 보이는 구도.
- 박스: 3D 투영으로 회전하며 낙하. 박스 앞면 제품 사진은 매장 촬영 영상에서 잘라낸 실제 이미지(assets/)
- 배경: 하늘(태양 플레어·구름) → 카메라가 아래로 틸트하며 부산 도심과 롯데하이마트 덕천점 매장 공개
- 중간: 실제 매장 영상 몽타주 / 엔딩: 박스가 천천히 떠다니는 히어로 컷 + CTA

사용법: python3 render_boxes.py <클립폴더> <폰트폴더> <출력.mp4>
미리보기: FRAMES="10,200,500" python3 render_boxes.py ...
"""
import glob
import math
import os
import random
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
CLIP_DIR, FONT_DIR, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
BH = os.path.join(FONT_DIR, "BlackHanSans.ttf")
NOTO = os.path.join(FONT_DIR, "NotoSansKR-Black.ttf")
NOTO_M = os.path.join(FONT_DIR, "NotoSansKR-Medium.ttf")
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

YELLOW = (255, 230, 0)
RED = (232, 30, 45)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
NAVY = (14, 30, 80)

random.seed(21)


def clip_path(tag):
    return glob.glob(os.path.join(CLIP_DIR, f"*-{tag}.mp4"))[0]


IPAD, IPHONE, WATCH, MAC_BOOT, MAC_OPEN = (clip_path(t) for t in ("11", "22", "33", "44", "55"))


# ---------------------------------------------------------------- 공통 유틸
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def prog(i, s, e):
    return clamp((i - s) / max(1, e - s))


def lerp(a, b, t):
    return a + (b - a) * t


def out_expo(t):
    return 1 if t >= 1 else 1 - 2 ** (-10 * t)


def in_out(t):
    return t * t * (3 - 2 * t)


def out_back(t, k=2.2):
    t -= 1
    return 1 + (k + 1) * t ** 3 + k * t ** 2


def out_elastic(t):
    if t <= 0 or t >= 1:
        return clamp(t)
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1


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


def put(canvas, spr, cx, cy, scale=1.0, rot=0.0, alpha=1.0):
    if scale <= 0.02 or alpha <= 0.01:
        return
    s = spr
    if abs(scale - 1) > 1e-3:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    if abs(rot) > 0.05:
        s = s.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        s = s.copy()
        s.putalpha(s.getchannel("A").point(lambda v: int(v * alpha)))
    canvas.paste(s, (int(cx - s.width / 2), int(cy - s.height / 2)), s)


def cam(img, zoom=1.0, tx=0.0, ty=0.0):
    cx, cy = W / 2, H / 2
    c = 1 / zoom
    return img.transform((W, H), Image.AFFINE, (c, 0, cx - c * (cx + tx), 0, c, cy - c * (cy + ty)),
                         resample=Image.BILINEAR)


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


def darken_grad(img, top=0.5, bottom=0.55, mid=0.12):
    a = np.asarray(img).astype(np.float32)
    y = np.linspace(0, 1, H)[:, None, None]
    k = np.where(y < 0.5, lerp(top, mid, y / 0.5), lerp(mid, bottom, (y - 0.5) / 0.5))
    return Image.fromarray((a * (1 - k)).astype(np.uint8))


def text_sprite(txt, font, size, fill=WHITE, stroke=0, stroke_fill=NAVY, shadow=True, spacing=8):
    f = ImageFont.truetype(font, size)
    l, t, r, b = ImageDraw.Draw(Image.new("RGBA", (1, 1))).multiline_textbbox(
        (0, 0), txt, font=f, stroke_width=stroke, align="center", spacing=spacing)
    pad = 40
    img = Image.new("RGBA", (int(r - l) + pad * 2, int(b - t) + pad * 2), (0, 0, 0, 0))
    pos = (pad - l, pad - t)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).multiline_text((pos[0] + 8, pos[1] + 12), txt, font=f, fill=(0, 0, 0, 150),
                                          stroke_width=stroke, stroke_fill=(0, 0, 0, 150),
                                          align="center", spacing=spacing)
        img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(img).multiline_text(pos, txt, font=f, fill=fill, stroke_width=stroke,
                                       stroke_fill=stroke_fill, align="center", spacing=spacing)
    return img


def pill(txt, font, size, bg, fg, padx=46, pady=24, radius=None, border=None):
    f = ImageFont.truetype(font, size)
    l, t, r, b = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), txt, font=f)
    w, h = int(r - l) + padx * 2, int(b - t) + pady * 2
    m = 24
    img = Image.new("RGBA", (w + m * 2, h + m * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rad = radius if radius is not None else h // 2
    ImageDraw.Draw(sh).rounded_rectangle((m + 6, m + 10, m + w + 6, m + h + 10), rad, fill=(0, 0, 0, 130))
    img = Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((m, m, m + w, m + h), rad, fill=bg, outline=border, width=8 if border else 0)
    d.text((m + padx - l, m + pady - t), txt, font=f, fill=fg)
    return img


# ---------------------------------------------------------------- 제품 박스 텍스처
PX = 700  # 박스 1단위 = 700px 텍스처
BOX_WHITE = (247, 247, 249)


def face_bg(w, h, top=(252, 252, 253), bot=(238, 239, 242)):
    y = np.linspace(0, 1, h)[:, None, None]
    a = np.array(top, np.float32) * (1 - y) + np.array(bot, np.float32) * y
    return Image.fromarray(np.repeat(a, w, axis=1).astype(np.uint8)).convert("RGBA")


def front_tex(dev, w, h, fill=0.78):
    img = face_bg(w, h)
    d = Image.open(os.path.join(ASSET_DIR, f"{dev}.png")).convert("RGBA")
    d = ImageEnhance.Brightness(d).enhance(1.05)
    s = min(w * fill / d.width, h * fill / d.height)
    d = d.resize((int(d.width * s), int(d.height * s)), Image.LANCZOS)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    a = Image.new("L", img.size, 0)
    a.paste(d.getchannel("A"), ((w - d.width) // 2 + 8, (h - d.height) // 2 + 14))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.35)))
    img = Image.alpha_composite(img, sh)
    img.paste(d, ((w - d.width) // 2, (h - d.height) // 2), d)
    return img


def side_tex(name, w, h, vertical=True):
    img = face_bg(w, h, (244, 244, 246), (232, 233, 236))
    if not name:
        return img
    size = int(min(w, h) * 0.42) if vertical else int(min(w, h) * 0.3)
    f = ImageFont.truetype(NOTO_M, max(12, size))
    l, t, r, b = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), name, font=f)
    txt = Image.new("RGBA", (int(r - l) + 10, int(b - t) + 10), (0, 0, 0, 0))
    ImageDraw.Draw(txt).text((5 - l, 5 - t), name, font=f, fill=(70, 70, 76, 255))
    if vertical:
        txt = txt.rotate(-90, expand=True)
        maxh = h * 0.8
        if txt.height > maxh:
            txt = txt.resize((int(txt.width * maxh / txt.height), int(maxh)), Image.LANCZOS)
        img.paste(txt, ((w - txt.width) // 2, int(h * 0.1)), txt)
    else:
        maxw = w * 0.8
        if txt.width > maxw:
            txt = txt.resize((int(maxw), int(txt.height * maxw / txt.width)), Image.LANCZOS)
        img.paste(txt, ((w - txt.width) // 2, (h - txt.height) // 2), txt)
    return img


def mips(img):
    out = [img]
    while min(out[-1].size) > 24:
        p = out[-1]
        out.append(p.resize((max(1, p.width // 2), max(1, p.height // 2)), Image.LANCZOS))
    return out


PRODUCTS = {  # (w, h, d) 단위, 앞면 기기, 측면 이름
    "iphone": dict(dims=(0.56, 1.0, 0.16), dev="iphone", name="iPhone 18 Pro", fill=0.8),
    "ipad": dict(dims=(1.0, 0.78, 0.1), dev="ipad", name="iPad Pro", fill=0.86),
    "mac": dict(dims=(1.3, 0.86, 0.11), dev="mac", name="MacBook Air", fill=0.86),
    "watch": dict(dims=(0.62, 0.72, 0.42), dev="watch", name="Apple Watch", fill=0.78),
}


def build_box(kind):
    p = PRODUCTS[kind]
    w, h, d = p["dims"]
    tw, th, td = int(w * PX), int(h * PX), max(24, int(d * PX))
    tex = {
        "front": front_tex(p["dev"], tw, th, p["fill"]),
        "back": side_tex("", tw, th),
        "right": side_tex(p["name"], td, th),
        "left": side_tex(p["name"], td, th),
        "top": side_tex(p["name"], tw, td, vertical=False),
        "bottom": side_tex("", tw, td, vertical=False),
    }
    return dict(dims=(w, h, d), mips={k: mips(v) for k, v in tex.items()})


print("박스 텍스처 생성…", flush=True)
BOXES = {k: build_box(k) for k in PRODUCTS}


# ---------------------------------------------------------------- 3D 박스 렌더
F = 1150.0  # 초점거리(px)
LIGHT = np.array([-0.45, -0.75, -0.5])
LIGHT /= np.linalg.norm(LIGHT)


def rot_matrix(yaw, pitch, roll):
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    Rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    return Rz @ Rx @ Ry


def faces(w, h, d):
    x, y, z = w / 2, h / 2, d / 2
    return {
        "front": ([(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z)], (0, 0, -1)),
        "back": ([(x, -y, z), (-x, -y, z), (-x, y, z), (x, y, z)], (0, 0, 1)),
        "right": ([(x, -y, -z), (x, -y, z), (x, y, z), (x, y, -z)], (1, 0, 0)),
        "left": ([(-x, -y, z), (-x, -y, -z), (-x, y, -z), (-x, y, z)], (-1, 0, 0)),
        "top": ([(-x, -y, z), (x, -y, z), (x, -y, -z), (-x, -y, -z)], (0, -1, 0)),
        "bottom": ([(-x, y, -z), (x, y, -z), (x, y, z), (-x, y, z)], (0, 1, 0)),
    }


def persp_coeffs(out_pts, in_pts):
    A, B = [], []
    for (x, y), (u, v) in zip(out_pts, in_pts):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.solve(np.array(A, float), np.array(B, float))


def draw_box(canvas, kind, pos, angles, scale=1.0, fade=1.0):
    """pos=(X,Y,Z) 카메라 좌표(Y 아래 +, Z 앞 +). 화면 밖이면 건너뜀."""
    X, Y, Z = pos
    if Z < 0.35:
        return
    box = BOXES[kind]
    w, h, d = (v * scale for v in box["dims"])
    R = rot_matrix(*angles)
    sx0, sy0 = W / 2 + F * X / Z, H / 2 + F * Y / Z
    rad = F * max(w, h) / Z
    if sx0 < -rad or sx0 > W + rad or sy0 < -rad or sy0 > H + rad:
        return
    haze = clamp((Z - 6) / 22) * 0.55  # 원거리 박스는 하늘색으로 살짝 흐리게
    for name, (corners, normal) in faces(w, h, d).items():
        n = R @ np.array(normal, float)
        P = [R @ np.array(c, float) + np.array(pos, float) for c in corners]
        center = sum(P) / 4
        if n @ center >= 0 or min(p[2] for p in P) < 0.2:
            continue
        pts = [(W / 2 + F * p[0] / p[2], H / 2 + F * p[1] / p[2]) for p in P]
        x0 = int(math.floor(min(p[0] for p in pts))) - 1
        y0 = int(math.floor(min(p[1] for p in pts))) - 1
        x1 = int(math.ceil(max(p[0] for p in pts))) + 1
        y1 = int(math.ceil(max(p[1] for p in pts))) + 1
        bw, bh = x1 - x0, y1 - y0
        if bw < 2 or bh < 2 or x1 < 0 or y1 < 0 or x0 > W or y0 > H:
            continue
        # 투영 크기에 맞는 밉맵 선택(모아레/깨짐 방지)
        edge = max(math.dist(pts[0], pts[1]), math.dist(pts[1], pts[2]))
        lv = box["mips"][name]
        k = 0
        while k + 1 < len(lv) and max(lv[k + 1].size) >= edge * 1.1:
            k += 1
        tex = lv[k]
        tw, th = tex.size
        local = [(p[0] - x0, p[1] - y0) for p in pts]
        try:
            cf = persp_coeffs(local, [(0, 0), (tw, 0), (tw, th), (0, th)])
        except np.linalg.LinAlgError:
            continue
        img = tex.transform((bw, bh), Image.PERSPECTIVE, tuple(cf), Image.BILINEAR)
        shade = 0.74 + 0.3 * max(0.0, float(n @ LIGHT))
        arr = np.asarray(img).astype(np.float32)
        rgb = arr[..., :3] * shade
        if haze > 0:
            rgb = rgb * (1 - haze) + np.array((185, 215, 245), np.float32) * haze
        # 안티앨리어싱 마스크 (2배 슈퍼샘플)
        m = Image.new("L", (bw * 2, bh * 2), 0)
        ImageDraw.Draw(m).polygon([(x * 2, y * 2) for x, y in local], fill=255, outline=255)
        m = m.resize((bw, bh), Image.BOX)
        if fade < 1:
            m = m.point(lambda v: int(v * fade))
        face = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
        canvas.paste(face, (x0, y0), m)


# ---------------------------------------------------------------- 배경 (하늘 → 부산 도심 → 매장)
BGH = 3100
HORIZON = 2240


def make_cloud(w, seed):
    rng = random.Random(seed)
    h = int(w * 0.7)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    for _ in range(26):
        r = rng.uniform(0.07, 0.16) * w
        cx = rng.uniform(0.2, 0.8) * w
        hump = 0.14 * h * math.cos((cx / w - 0.5) * math.pi * 1.6)
        cy = rng.uniform(0.55, 0.66) * h - hump
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255))
    base = np.asarray(img).astype(np.float32)
    gy = np.linspace(0, 1, h)[:, None]
    base[..., 0] -= 60 * gy ** 1.5
    base[..., 1] -= 38 * gy ** 1.5
    base[..., 2] -= 8 * gy ** 1.5
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(w // 40))


def ridge(n, seed, octaves=5):
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    for o in range(octaves):
        k = 2 ** o * 3
        pts = rng.uniform(-1, 1, k + 2)
        y += np.interp(np.linspace(0, k, n), np.arange(k + 2), pts) / (2 ** o)
    return y


def make_background():
    rng = random.Random(5)
    yy = np.linspace(0, 1, BGH)[:, None, None]
    top, mid, low = (np.array(c, np.float32) for c in ((22, 86, 205), (90, 165, 240), (200, 228, 250)))
    t = np.clip(yy / (HORIZON / BGH), 0, 1)
    sky = np.where(t < 0.6, top * (1 - t / 0.6) + mid * (t / 0.6), mid * (1 - (t - 0.6) / 0.4) + low * ((t - 0.6) / 0.4))
    img = np.repeat(sky, W, axis=1)
    # 태양 + 플레어 (좌상단)
    Y, X = np.mgrid[0:BGH, 0:W].astype(np.float32)
    sx, sy = 170, 300
    r2 = (X - sx) ** 2 + (Y - sy) ** 2
    glow = np.exp(-r2 / 330 ** 2)[..., None] * 0.9 + np.exp(-r2 / 70 ** 2)[..., None]
    img = img * (1 - np.clip(glow, 0, 1)) + 255 * np.clip(glow, 0, 1)
    ang = np.arctan2(Y - sy, X - sx)
    rays = (np.cos(ang * 14) * 0.5 + 0.5) ** 6 * np.exp(-np.sqrt(r2) / 600)
    img = img + rays[..., None] * 60
    bg = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(bg, "RGBA")
    # 렌즈 플레어 링
    for k, (fx, fr, a) in enumerate(((0.35, 40, 40), (0.55, 70, 28), (0.8, 26, 50))):
        cx, cy = sx + (W / 2 - sx) * fx * 2, sy + (900 - sy) * fx * 2
        d.ellipse((cx - fr, cy - fr, cx + fr, cy + fr), fill=(255, 255, 230, a))
    # 구름 (지평선 근처 띠 + 상공에 몇 개)
    clouds = [make_cloud(rng.randint(500, 1000), k) for k in range(8)]
    for k in range(16):
        c = clouds[k % 8]
        s = rng.uniform(0.7, 1.3)
        c2 = c.resize((int(c.width * s), int(c.height * s)), Image.BILINEAR)
        cy = rng.uniform(HORIZON - 520, HORIZON - 80) if k < 11 else rng.uniform(500, 1500)
        bg.paste(c2, (int(rng.uniform(-300, W - 200)), int(cy - c2.height / 2)), c2)
    # 산 (안개 낀 3겹 능선)
    for k, (col, base, amp) in enumerate((((150, 180, 210), HORIZON - 40, 160),
                                          ((120, 150, 185), HORIZON - 5, 120),
                                          ((95, 125, 160), HORIZON + 25, 80))):
        r = ridge(W, 10 + k)
        pts = [(x, base - amp * (0.6 + 0.4 * r[x])) for x in range(0, W, 4)] + [(W, BGH), (0, BGH)]
        d.polygon(pts, fill=col + (255,))
    # 바다/강
    d.rectangle((0, HORIZON + 60, W, HORIZON + 170), fill=(150, 195, 230, 255))
    for k in range(60):
        x = rng.uniform(0, W)
        y = rng.uniform(HORIZON + 70, HORIZON + 165)
        d.line((x, y, x + rng.uniform(20, 90), y), fill=(235, 248, 255, 160), width=2)
    # 광안대교 느낌의 다리
    d.line((0, HORIZON + 110, W, HORIZON + 95), fill=(225, 230, 240, 255), width=6)
    for x in (300, 760):
        d.line((x, HORIZON + 103, x, HORIZON + 10), fill=(230, 235, 245, 255), width=8)
        for k in range(-6, 7):
            d.line((x, HORIZON + 14, x + k * 38, HORIZON + 100), fill=(230, 235, 245, 200), width=2)
    # 도시 빌딩 (먼 줄 → 가까운 줄)
    rows = [(HORIZON + 200, 0.65, (40, 120), (190, 205, 222)),
            (HORIZON + 330, 0.35, (60, 200), (170, 186, 206)),
            (HORIZON + 520, 0.15, (90, 320), (150, 166, 188)),
            (HORIZON + 760, 0.0, (140, 460), (128, 144, 168))]
    for base_y, haze, (hmin, hmax), col in rows:
        x = -20
        while x < W:
            bw = rng.randint(50, 130) if haze > 0.3 else rng.randint(80, 180)
            bh = rng.randint(hmin, hmax)
            c = tuple(int(v + rng.randint(-12, 12)) for v in col)
            d.rectangle((x, base_y - bh, x + bw, base_y + 400), fill=c + (255,))
            lit = tuple(min(255, v + 40) for v in c)
            d.rectangle((x, base_y - bh, x + 6, base_y + 400), fill=lit + (255,))
            wc = tuple(max(0, v - 30) for v in c)
            gx, gy = (14, 18) if haze > 0.3 else (20, 26)
            for wy in range(int(base_y - bh + 10), int(base_y + 380), gy):
                for wx in range(x + 10, x + bw - 8, gx):
                    if rng.random() < 0.85:
                        d.rectangle((wx, wy, wx + gx - 7, wy + gy - 9), fill=wc + (255,))
            x += bw + rng.randint(2, 14)
    return bg


def make_store(bg):
    """롯데하이마트 덕천점 매장(유리 파사드)을 배경 하단 중앙에 합성."""
    d = ImageDraw.Draw(bg, "RGBA")
    x0, x1, top, bot = 90, 990, BGH - 520, BGH
    # 바닥 광장
    d.rectangle((0, bot - 70, W, bot), fill=(205, 205, 210, 255))
    # 건물 몸체 + 유리
    gl = np.zeros((bot - top, x1 - x0, 3), np.float32)
    gy = np.linspace(0, 1, bot - top)[:, None]
    gx = np.linspace(0, 1, x1 - x0)[None, :]
    for c, v in enumerate((150, 200, 240)):
        gl[..., c] = v + 70 * (1 - gy) - 40 * gy + 30 * np.sin(gx * 9 + gy * 3)
    glass = Image.fromarray(np.clip(gl, 0, 255).astype(np.uint8))
    bg.paste(glass, (x0, top))
    # 반사 하이라이트
    for k in range(5):
        xx = x0 + 80 + k * 190
        d.polygon([(xx, top + 90), (xx + 60, top + 90), (xx - 40, bot - 70), (xx - 100, bot - 70)],
                  fill=(255, 255, 255, 40))
    # 멀리언(프레임)
    for xx in range(x0, x1 + 1, 112):
        d.rectangle((xx - 3, top + 90, xx + 3, bot - 70), fill=(225, 228, 235, 255))
    d.rectangle((x0, top + 300, x1, top + 306), fill=(225, 228, 235, 255))
    # 지붕 + 빨간 간판 밴드
    d.rectangle((x0 - 30, top - 10, x1 + 30, top + 90), fill=RED + (255,))
    d.rectangle((x0 - 30, top + 84, x1 + 30, top + 96), fill=(250, 250, 250, 255))
    f = ImageFont.truetype(NOTO, 64)
    d.text((W / 2, top + 40), "롯데하이마트  덕천점", font=f, fill=WHITE, anchor="mm")
    # 유리 안쪽 'Apple' 사인
    f2 = ImageFont.truetype(NOTO_M, 70)
    d.rounded_rectangle((W / 2 - 170, top + 150, W / 2 + 170, top + 260), 20, fill=(255, 255, 255, 215))
    d.text((W / 2, top + 205), "Apple", font=f2, fill=(30, 30, 34), anchor="mm")
    # 입구
    d.rectangle((W / 2 - 120, bot - 230, W / 2 + 120, bot - 70), fill=(60, 80, 110, 200))
    d.line((W / 2, bot - 230, W / 2, bot - 70), fill=(225, 228, 235, 255), width=5)
    # 가로수
    for xx in (40, 1040):
        d.rectangle((xx - 6, bot - 220, xx + 6, bot - 70), fill=(90, 70, 50, 255))
        d.ellipse((xx - 70, bot - 360, xx + 70, bot - 190), fill=(70, 140, 80, 255))
    return bg


print("배경 생성…", flush=True)
BG = make_store(make_background())


def bg_view(off):
    off = int(clamp(off, 0, BGH - H))
    return BG.crop((0, off, W, off + H))


# ---------------------------------------------------------------- 낙하 박스 배치
KINDS = ["iphone", "ipad", "mac", "watch"]


def make_rain(n, seed, zmin, zmax, speed=(0.9, 1.6)):
    rng = random.Random(seed)
    out = []
    for k in range(n):
        Z = rng.uniform(zmin, zmax)
        out.append(dict(kind=KINDS[k % 4] if k < 8 else rng.choice(KINDS), Z=Z,
                        X=rng.uniform(-0.5, 0.5) * W / F * Z * 1.1,
                        y0=rng.uniform(-1.2, 1.0), v=rng.uniform(*speed),
                        a0=[rng.uniform(-3, 3) for _ in range(3)],
                        w=[rng.uniform(-1.6, 1.6) for _ in range(3)]))
    out.sort(key=lambda b: -b["Z"])
    return out


RAIN = make_rain(30, 1, 4.5, 26)


def draw_rain(c, t, rain=RAIN, tscale=1.0, spin=1.0):
    """t: 초. 화면 높이 기준으로 위→아래 순환."""
    for b in rain:
        yh = ((b["y0"] + b["v"] * t * tscale / (b["Z"] ** 0.35)) % 2.6) - 1.3  # 화면 높이 비율
        Y = yh * H / F * b["Z"]
        ang = [a + w * t * spin for a, w in zip(b["a0"], b["w"])]
        draw_box(c, b["kind"], (b["X"], Y, b["Z"]), ang)


# ---------------------------------------------------------------- 텍스트 스프라이트
SP = dict(
    a1=text_sprite("부산 하늘에서", NOTO, 104, WHITE, stroke=8),
    a2=text_sprite("애플이\n쏟아진다?!", BH, 210, YELLOW, stroke=14),
    b_top=pill("10월 한정 특가", BH, 84, RED, WHITE, padx=50, pady=20, border=WHITE),
    names={k: text_sprite(n, BH, 120, WHITE, stroke=10) for k, n in
           (("iphone", "iPhone 18 Pro"), ("ipad", "iPad Pro"), ("mac", "MacBook Air"))},
    c1=text_sprite("롯데하이마트 덕천점에", NOTO, 84, WHITE, stroke=8),
    c2=text_sprite("착륙 예정!", BH, 200, YELLOW, stroke=14),
    m=[(pill("한정수량", BH, 180, RED, WHITE, padx=56, pady=26, radius=30, border=WHITE), "iPhone"),
       (text_sprite("10월 특가", BH, 200, YELLOW, stroke=14), "iPad"),
       (text_sprite("선착순\n특별혜택", BH, 190, YELLOW, stroke=14), "Watch"),
       (text_sprite("오픈런\nGO!!", BH, 230, YELLOW, stroke=16), "Mac")],
    m_small={n: pill(n, NOTO, 56, WHITE, NAVY) for n in ("iPhone", "iPad", "Watch", "Mac")},
    e_tag=pill("10월 한정 · 선착순 특별혜택", NOTO, 56, YELLOW, BLACK),
    e1=text_sprite("롯데하이마트", BH, 190, WHITE, stroke=12),
    e2=text_sprite("덕천점", BH, 230, YELLOW, stroke=14),
    e_tel=pill("T. 051-335-6100", NOTO, 64, WHITE, NAVY, padx=40, pady=18),
    e_cta=pill("지금 오픈런 GO!", BH, 100, RED, WHITE, padx=70, pady=32, border=WHITE),
    e_note=text_sprite("※ 한정수량 소진 시 조기 종료될 수 있습니다", NOTO, 36, WHITE, stroke=4, shadow=False),
)

# ---------------------------------------------------------------- 타임라인
A_END, B_END, C_END, D_END, TOTAL = 90, 180, 270, 390, 570
TILT_END = BGH - H

print("클립 로딩…", flush=True)
MONTAGE = [load_clip(IPHONE, 2.4, 30, 1.0), load_clip(IPAD, 0.4, 30, 1.1),
           load_clip(WATCH, 0.3, 30, 1.0), load_clip(MAC_BOOT, 2.6, 30, 1.0)]

HERO = {  # 장면 B: 카메라 바로 앞을 스쳐 지나가는 큰 박스
    "iphone": (90, -0.25),
    "ipad": (120, 0.2),
    "mac": (150, -0.1),
}


def scene_a(i):
    t = i / FPS
    c = bg_view(0)
    draw_rain(c, t + 0.0)
    at_ = out_expo(prog(i, 6, 16))
    put(c, SP["a1"], lerp(-700, W / 2, at_), 600)
    bt = prog(i, 16, 24)
    if i >= 16:
        put(c, SP["a2"], W / 2, 880, scale=lerp(2.5, 1, out_expo(bt)) * (1 + 0.025 * math.sin(i * 0.5)),
            rot=-4, alpha=clamp(bt * 3))
    return flash(c, (1 - prog(i, 0, 8)) * 0.8)


def scene_b(i):
    n = A_END + i
    t = n / FPS
    c = bg_view(lerp(0, 180, i / 90))
    draw_rain(c, t)
    for kind, (start, xoff) in HERO.items():
        k = n - start
        if -2 <= k < 34:
            p = k / 32
            Z = lerp(1.9, 1.45, p)
            Y = lerp(-1.0, 1.3, p - 0.13 * math.sin(2 * math.pi * p)) * H / F * Z
            draw_box(c, kind, (xoff * Z, Y, Z), (0.35 * math.sin(p * 3) - 0.2, 0.25 - 0.3 * p, 0.15 - 0.25 * p))
            if 6 <= k < 30:
                a = min(1, (k - 6) / 4, (30 - k) / 4)
                put(c, SP["names"][kind], W / 2, 1560, scale=0.9 + 0.1 * out_back(prog(k, 6, 12)), alpha=a)
    put(c, SP["b_top"], W / 2, lerp(-120, 300, out_back(prog(i, 0, 10))), rot=-3)
    return c


def scene_c(i):
    n = B_END + i
    t = n / FPS
    tilt = lerp(180, TILT_END, in_out(prog(i, 0, 55)))
    c = bg_view(tilt)
    # 매장 쪽으로 쏟아지는 박스: 틸트 진행만큼 화면상 위로 밀린다(카메라가 내려가는 느낌)
    draw_rain(c, t + (tilt - 180) / H * 1.2)
    put(c, SP["c1"], lerp(-800, W / 2, out_expo(prog(i, 40, 50))), 520)
    put(c, SP["c2"], W / 2, 730, scale=out_elastic(prog(i, 48, 64)), rot=-4)
    return flash(c, prog(i, 82, 90) ** 2 * 0.95)


def scene_d(i):
    k, j = divmod(i, 30)
    sx, sy = shake(j, 0, 10, 34)
    c = darken_grad(cam(at(MONTAGE[k], j), zoom=1.1 + 0.004 * j, tx=sx, ty=sy))
    big, small = SP["m"][k]
    st = prog(j, 1, 7)
    put(c, big, W / 2 + sx, 760 + sy, scale=lerp(2.4, 1, out_expo(st)), rot=-6 if k % 2 else 5,
        alpha=clamp(st * 3))
    put(c, SP["m_small"][small], W / 2, lerp(-100, 330, out_back(prog(j, 3, 11))))
    # 박스가 위에서 떨어져 화면을 가르는 컷 전환
    if j >= 22:
        p = (j - 22) / 8
        draw_box(c, KINDS[(k + 1) % 4], (0, lerp(-1.4, 0.2, p * p) * H / F * 1.6, 1.6), (0.3, 0.4, 0.2))
    return flash(c, (1 - prog(j, 0, 5)) * 0.85)


END_FLOAT = [  # 엔딩: 레퍼런스처럼 큰 박스들이 천천히 떠 있음 (종류, 화면x, 화면y, Z, 각도)
    ("ipad", 170, 220, 3.4, (0.5, 0.35, -0.25)),
    ("iphone", 920, 200, 3.0, (-0.45, 0.3, 0.2)),
    ("watch", 110, 1130, 4.2, (0.6, 0.4, 0.15)),
    ("mac", 950, 1150, 4.6, (-0.55, 0.45, -0.2)),
]
RAIN_SLOW = make_rain(22, 7, 8, 30)


def scene_e(i):
    n = D_END + i
    t = n / FPS
    c = bg_view(TILT_END)
    draw_rain(c, t, RAIN_SLOW, tscale=0.35, spin=0.35)
    for k, (kind, sx_, sy_, Z, ang) in enumerate(END_FLOAT):
        p = out_expo(prog(i, k * 4, k * 4 + 22))
        y = lerp(-500, sy_, p) + 18 * math.sin(i * 0.05 + k)
        X, Y = (sx_ - W / 2) * Z / F, (y - H / 2) * Z / F
        draw_box(c, kind, (X, Y, Z), (ang[0] + 0.15 * math.sin(i * 0.03 + k), ang[1] + 0.003 * i, ang[2]))
    veil = Image.new("RGBA", (W, H), (10, 25, 70, int(70 * prog(i, 0, 15))))
    c.paste(veil, (0, 0), veil)
    put(c, SP["e_tag"], W / 2, lerp(-100, 430, out_back(prog(i, 10, 20))))
    put(c, SP["e1"], lerp(-900, W / 2, out_expo(prog(i, 16, 24))), 620)
    lt = prog(i, 22, 30)
    sxk, syk = shake(i, 30, 10, 20)
    if i >= 22:
        put(c, SP["e2"], W / 2 + sxk, lerp(-200, 840, lt * lt) + syk)
    put(c, SP["e_tel"], W / 2, 1030, scale=out_back(prog(i, 34, 42)))
    pulse = 1 + 0.06 * max(0, math.sin((i - 52) * 0.42)) * (i > 52)
    put(c, SP["e_cta"], W / 2, lerp(H + 200, 1185, out_back(prog(i, 42, 52), 2.5)), scale=pulse)
    put(c, SP["e_note"], W / 2, 1320, alpha=prog(i, 52, 62))
    c = flash(c, (1 - prog(i, 30, 35)) * 0.4 * (i >= 30))
    return flash(c, (1 - prog(i, 0, 6)) * 0.9)


def frame(n):
    if n < A_END:
        return scene_a(n)
    if n < B_END:
        return scene_b(n - A_END)
    if n < C_END:
        return scene_c(n - B_END)
    if n < D_END:
        return scene_d(n - C_END)
    return scene_e(n - D_END)


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

    def whoosh(length=0.5):
        n = int(length * SR)
        env = np.sin(np.linspace(0, np.pi, n)) ** 2
        return band_noise(n, 250, 7000) * env

    beat, roots = 0.5, [55.0, 43.65, 65.41, 49.0]
    t, k = 0.0, 0
    while t < dur - 0.05:
        if t >= 0.5:
            add(kick, t, 0.85)
            if k % 4 in (1, 3):
                add(snare, t, 0.4)
            add(hat, t + beat / 2, 0.2)
            if D_END / FPS - 4 <= t < D_END / FPS:
                add(hat, t + beat / 4, 0.14)
                add(hat, t + 3 * beat / 4, 0.14)
            f0 = roots[(k // 4) % 4]
            for h in (0, 0.25):
                b = np.arange(int(0.22 * SR)) / SR
                env = np.minimum(1, b * 60) * np.exp(-6 * b)
                bass = (np.sin(2 * np.pi * f0 * b) + 0.35 * np.sin(4 * np.pi * f0 * b)) * env
                add(bass.astype(np.float32), t + h + 0.04, 0.32)
        t += beat
        k += 1

    add(boom, 16 / FPS, 0.6)
    for start, _ in HERO.values():
        add(whoosh(0.9), (start + 2) / FPS, 0.6)
    add(whoosh(1.6), (B_END + 5) / FPS, 0.45)
    add(boom, (B_END + 48) / FPS, 0.6)
    for k in range(4):
        add(boom, (C_END + k * 30) / FPS, 0.85)
        add(whoosh(0.3), (C_END + k * 30 + 22) / FPS, 0.4)
    add(boom, (D_END + 30) / FPS, 0.85)
    rn = int(1.2 * SR)
    add(band_noise(rn, 500, 12000) * np.linspace(0, 1, rn) ** 3, C_END / FPS - 1.2, 0.3)

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
    only = os.environ.get("FRAMES")
    if only:
        for n in map(int, only.split(",")):
            frame(n).save(OUT.rsplit(".", 1)[0] + f"_{n:03d}.jpg", quality=88)
        sys.exit()
    wav = OUT.rsplit(".", 1)[0] + "_bgm.wav"
    make_audio(wav)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", OUT]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(TOTAL):
        p.stdin.write(frame(n).convert("RGB").tobytes())
        if n % 60 == 0:
            print(f"frame {n}/{TOTAL}", flush=True)
    p.stdin.close()
    p.wait()
    print("done", OUT)
