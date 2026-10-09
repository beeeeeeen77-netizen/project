"""매장 촬영 영상 프레임에서 기기 정면을 원근 보정으로 잘라내 투명 PNG로 만든다.

사용법: python3 make_device_cutouts.py <프레임폴더> <출력폴더>
프레임폴더: iphone.png(22번 0.8s), ipad.png(11번 0.0s), mac.png(55번 5.0s), watch.png(33번 1.0s)
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SRC, OUT = sys.argv[1], sys.argv[2]
SS = 2


def warp(img, quad, size):
    """quad(TL,TR,BR,BL) → size 직사각형으로 원근 보정."""
    w, h = size
    dst = [(0, 0), (w, 0), (w, h), (0, h)]
    A, B = [], []
    for (x, y), (u, v) in zip(quad, dst):
        A.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); B.append(x)
        A.append([0, 0, 0, u, v, 1, -u * y, -v * y]); B.append(y)
    coef = np.linalg.solve(np.array(A, float), np.array(B, float))
    return img.transform(size, Image.PERSPECTIVE, tuple(coef), Image.BICUBIC)


def rounded(img, r):
    m = Image.new("L", (img.width * SS, img.height * SS), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, m.width - 1, m.height - 1), r * SS, fill=255)
    out = img.convert("RGBA")
    out.putalpha(m.resize(img.size, Image.LANCZOS))
    return out


def enhance(img, sat=1.12, con=1.06):
    from PIL import ImageEnhance
    img = ImageEnhance.Color(img).enhance(sat)
    return ImageEnhance.Contrast(img).enhance(con)


def frame_border(img, r, color, width):
    """기기 테두리(메탈 프레임)를 덧그려 가장자리를 깔끔하게."""
    lay = Image.new("RGBA", (img.width * SS, img.height * SS), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle((0, 0, lay.width - 1, lay.height - 1), r * SS,
                                          outline=color, width=width * SS)
    return Image.alpha_composite(img, lay.resize(img.size, Image.LANCZOS))


def load(n):
    return Image.open(os.path.join(SRC, n)).convert("RGB")


# iPhone (정면, 실제 화면)
ip = warp(load("iphone.png"), [(503, 612), (842, 663), (547, 1298), (193, 1203)], (340, 700))
ip = frame_border(rounded(enhance(ip), 56), 56, (12, 12, 16, 255), 14)
ip = frame_border(ip, 56, (150, 175, 215, 255), 6)
ip.save(os.path.join(OUT, "iphone.png"))

# iPad Pro (가로, 실제 화면)
pad = warp(load("ipad.png"), [(226, 380), (780, 338), (864, 700), (316, 800)], (720, 500))
pad = frame_border(rounded(enhance(pad), 34), 34, (60, 60, 66, 255), 7)
pad.save(os.path.join(OUT, "ipad.png"))

# MacBook Air: 실제 화면(뚜껑) + 하판
lid = warp(load("mac.png"), [(183, 464), (933, 509), (880, 1040), (165, 968)], (760, 490))
lid = enhance(lid)
mw, mh = 860, 545
mac = Image.new("RGBA", (mw * SS, mh * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(mac)
lx = (mw - 760) // 2
d.rounded_rectangle((lx * SS, 0, (lx + 760) * SS, 492 * SS), 26 * SS, fill=(150, 160, 178, 255))
mac = mac.resize((mw, mh), Image.LANCZOS)
lm = Image.new("L", (760 * SS, 490 * SS), 0)
ImageDraw.Draw(lm).rounded_rectangle((3 * SS, 3 * SS, 757 * SS, 520 * SS), 24 * SS, fill=255)
mac.paste(lid, (lx, 0), lm.resize((760, 490), Image.LANCZOS))
base = Image.new("RGBA", (mw * SS, 60 * SS), (0, 0, 0, 0))
bd = ImageDraw.Draw(base)
bd.polygon([(30 * SS, 0), ((mw - 30) * SS, 0), (mw * SS, 30 * SS), (0, 30 * SS)], fill=(196, 204, 218, 255))
bd.rounded_rectangle((0, 26 * SS, mw * SS - 1, 52 * SS), 12 * SS, fill=(150, 160, 178, 255))
bd.rounded_rectangle(((mw // 2 - 80) * SS, 26 * SS, (mw // 2 + 80) * SS, 36 * SS), 5 * SS,
                     fill=(120, 130, 148, 255))
base = base.resize((mw, 60), Image.LANCZOS)
full = Image.new("RGBA", (mw, mh), (0, 0, 0, 0))
full.paste(mac, (0, 0), mac)
full.paste(base, (0, 490), base)
full.save(os.path.join(OUT, "mac.png"))

# Apple Watch: 실제 화면 + 케이스/밴드
scr = enhance(warp(load("watch.png"), [(330, 582), (594, 545), (664, 808), (364, 840)], (250, 300)), 1.0, 1.15)
ww, wh = 300, 620
wt = Image.new("RGBA", (ww * SS, wh * SS), (0, 0, 0, 0))
d = ImageDraw.Draw(wt)
band = (24, 24, 28, 255)
d.rounded_rectangle((70 * SS, 0, 230 * SS, 200 * SS), 34 * SS, fill=band)
d.rounded_rectangle((70 * SS, 420 * SS, 230 * SS, 620 * SS), 34 * SS, fill=band)
for k in range(5):
    y = (470 + k * 26) * SS
    d.ellipse((143 * SS, y, 157 * SS, y + 14 * SS), fill=(70, 70, 80, 255))
d.rounded_rectangle((276 * SS, 230 * SS, 296 * SS, 300 * SS), 8 * SS, fill=(60, 60, 68, 255))
d.rounded_rectangle((276 * SS, 330 * SS, 290 * SS, 380 * SS), 6 * SS, fill=(60, 60, 68, 255))
d.rounded_rectangle((10 * SS, 140 * SS, 282 * SS, 480 * SS), 72 * SS, fill=(44, 44, 50, 255),
                    outline=(110, 110, 122, 255), width=5 * SS)
d.rounded_rectangle((22 * SS, 152 * SS, 270 * SS, 468 * SS), 62 * SS, fill=(0, 0, 0, 255))
wt = wt.resize((ww, wh), Image.LANCZOS)
sm = Image.new("L", (250 * SS, 300 * SS), 0)
ImageDraw.Draw(sm).rounded_rectangle((0, 0, 250 * SS - 1, 300 * SS - 1), 52 * SS, fill=255)
wt.paste(scr, (21, 160), sm.resize((250, 300), Image.LANCZOS))
wt.save(os.path.join(OUT, "watch.png"))
print("ok")
