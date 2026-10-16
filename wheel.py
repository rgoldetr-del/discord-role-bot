"""
Анимированное колесо фортуны для Discord.

Главная идея:
- Сначала выбирается победитель.
- Затем колесо строится так, чтобы победитель находился ровно под стрелкой.
- Анимация останавливается на полном обороте, поэтому финальный кадр всегда честный.
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

# ---------------- Канвас ----------------
W, H = 720, 780
CX, CY = 360, 384
R = 250                      # радиус сектора
RIM = R + 26                 # радиус внешнего обода
D = 2 * (R + 34)             # размер текстуры диска
DC = D // 2

TINY_ANGLE = 2.2             # меньше этого угла считаем "иголкой"
LABEL_ANGLE = 8.5            # меньше этого угла подпись не рисуем

SPIN_FRAMES = 96
CELEBRATE_FRAMES = 38
FRAME_MS = 60

POINTER_TOP = CY - R - 40

GOLD = (255, 214, 110)

# Совместимость с разными версиями Pillow
try:
    RESAMPLE = Image.Resampling.BICUBIC
except AttributeError:
    RESAMPLE = Image.BICUBIC

try:
    RESAMPLE_NEAREST = Image.Resampling.NEAREST
except AttributeError:
    RESAMPLE_NEAREST = Image.NEAREST

try:
    DITHER = Image.Dither.FLOYDSTEINBERG
except AttributeError:
    DITHER = Image.FLOYDSTEINBERG


@dataclass
class Segment:
    label: str
    color: str
    weight: float
    role_id: int | None = None
    is_empty: bool = False


# ---------------- Шрифты ----------------
_BOLD = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
]

_REG = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]


@lru_cache(maxsize=512)
def _font(size: int, bold: bool = False):
    for path in (_BOLD if bold else _REG):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue

    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _width(text: str, size: int, bold: bool = False) -> float:
    f = _font(size, bold)
    try:
        return f.getlength(text)
    except AttributeError:
        return len(text) * size * 0.55


def _text_width(text: str, font) -> float:
    try:
        return font.getlength(text)
    except AttributeError:
        return len(text) * getattr(font, "size", 12) * 0.55


def _fit(text: str, size: int, max_w: float, bold: bool = True):
    text = (text or "?").strip()

    while size > 12 and _width(text, size, bold) > max_w:
        size -= 1

    if _width(text, size, bold) > max_w:
        while text and _width(text + "…", size, bold) > max_w:
            text = text[:-1]
        text += "…"

    return text, _font(size, bold)


# ---------------- Математика ----------------
def _rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _polar(cx, cy, r, deg):
    """
    0 градусов = верх колеса.
    Дальше по часовой стрелке.
    """
    a = math.radians(deg - 90)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def _layout(weights, center_index: int | None = None):
    """
    Честная разметка: угол сектора строго пропорционален весу.

    Если center_index указан, вся разметка сдвигается так,
    чтобы середина этого сектора стала 0 градусами, то есть верхом колеса.
    """
    weights = [max(0.0, float(w)) for w in weights]
    total = sum(weights) or 1.0

    out = []
    cur = 0.0

    for w in weights:
        size = 360.0 * w / total
        out.append((cur, cur + size, cur + size / 2.0, size))
        cur += size

    # Исправляем возможную погрешность округления на последнем секторе
    if out:
        start, _, _, _ = out[-1]
        out[-1] = (start, 360.0, (start + 360.0) / 2.0, 360.0 - start)

    # Сдвигаем так, чтобы выбранный сектор был ровно сверху
    if center_index is not None and 0 <= center_index < len(out):
        shift = out[center_index][2]
        out = [
            (a0 - shift, a1 - shift, mid - shift, size)
            for a0, a1, mid, size in out
        ]

    return out


def _luminance(rgb):
    r, g, b = [v / 255 for v in rgb[:3]]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _radial(size: int) -> Image.Image:
    """Белый центр -> чёрный край, режим L."""
    img = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(img)
    half = size / 2

    for i in range(int(half), 0, -2):
        v = int(255 * (i / half) ** 0.65)
        d.ellipse([half - i, half - i, half + i, half + i], fill=v)

    return img


def _wedge_points(cx, cy, r_inner, r_outer, a0, a1):
    """
    Точки сектора/кольцевого сектора в нашей системе координат.
    r_inner = 0 -> обычный сектор от центра.
    """
    span = a1 - a0
    if span <= 0:
        span += 360.0

    steps = max(2, int(abs(span) / 2.0) + 2)
    pts = []

    if r_inner > 0:
        # Кольцевой сектор: сначала внутренний радиус по ходу, потом внешний обратно
        for i in range(steps + 1):
            ang = a0 + span * i / steps
            pts.append(_polar(cx, cy, r_inner, ang))

        for i in range(steps, -1, -1):
            ang = a0 + span * i / steps
            pts.append(_polar(cx, cy, r_outer, ang))
    else:
        # Обычный сектор: центр -> дуга -> центр
        pts.append((cx, cy))
        for i in range(steps + 1):
            ang = a0 + span * i / steps
            pts.append(_polar(cx, cy, r_outer, ang))

    return pts


def _sector_mask(size: int, dc: int, r: int, a0: float, a1: float) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.polygon(_wedge_points(dc, dc, 0, r, a0, a1), fill=255)
    return mask


# ---------------- Фоновая сцена ----------------
def _background(title: str, subtitle: str) -> Image.Image:
    top = Image.new("RGB", (W, H), (9, 13, 26))
    bottom = Image.new("RGB", (W, H), (27, 35, 62))
    grad = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(bottom, top, grad).convert("RGBA")

    # Мягкое свечение за колесом
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((CX - 300, CY - 300, CX + 300, CY + 300), fill=(72, 104, 210, 65))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(70)))

    # Тень под диском
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse(
        (CX - RIM, CY - RIM + 14, CX + RIM, CY + RIM + 14),
        fill=(0, 0, 0, 170)
    )
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(22)))

    d = ImageDraw.Draw(img)

    # Звёзды / пылинки
    rng = random.Random(42)
    for _ in range(110):
        x, y = rng.randint(12, W - 12), rng.randint(100, H - 20)

        if abs(x - CX) < RIM + 15 and abs(y - CY) < RIM + 15:
            continue

        a = rng.randint(25, 110)
        s = rng.choice([1, 1, 1, 2])
        d.ellipse((x, y, x + s, y + s), fill=(180, 200, 255, a))

    # Заголовок
    d.text((CX + 2, 44), title, font=_font(34, True),
           fill=(0, 0, 0, 200), anchor="mm")
    d.text((CX, 42), title, font=_font(34, True), fill=GOLD, anchor="mm")
    d.text((CX, 80), subtitle.upper(), font=_font(15, False),
           fill=(145, 160, 195), anchor="mm")

    # Декоративные линии по бокам заголовка
    for sign in (-1, 1):
        x1 = CX + sign * 190
        x2 = CX + sign * 285
        d.line((x1, 42, x2, 42), fill=(120, 100, 55), width=2)
        d.ellipse((x2 - 3, 39, x2 + 3, 45), fill=GOLD)

    return img.convert("RGB")


# ---------------- Диск ----------------
def _disc(segments, spans) -> Image.Image:
    img = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    total = sum(s.weight for s in segments) or 1
    radial = _radial(D)

    # Металлический обод
    for rr in range(RIM, R - 1, -1):
        t = (rr - R) / (RIM - R)
        v = 38 + 78 * abs(math.sin(t * math.pi))
        col = (int(v * .82), int(v * .92), int(v * 1.22))
        d.ellipse([DC - rr, DC - rr, DC + rr, DC + rr], fill=col)

    d.ellipse([DC - RIM, DC - RIM, DC + RIM, DC + RIM],
              outline=(190, 165, 105), width=2)
    d.ellipse([DC - R - 3, DC - R - 3, DC + R + 3, DC + R + 3],
              outline=(255, 214, 110), width=3)
    d.ellipse([DC - R, DC - R, DC + R, DC + R],
              outline=(8, 10, 20), width=5)

    # Засечки на ободе
    for i in range(72):
        ang = i * 5
        long = (i % 6 == 0)
        p1 = _polar(DC, DC, RIM - 4, ang)
        p2 = _polar(DC, DC, RIM - (13 if long else 8), ang)
        d.line([p1, p2], fill=(235, 214, 160) if long else (120, 132, 160),
               width=2 if long else 1)

    # Болты
    for i in range(8):
        x, y = _polar(DC, DC, R + 13, i * 45 + 22.5)
        d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(225, 198, 130))
        d.ellipse((x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=(60, 48, 22))

    # 1) Обычные широкие сектора
    for seg, (a0, a1, mid, size) in zip(segments, spans):
        if size < TINY_ANGLE:
            continue

        mask = _sector_mask(D, DC, R, a0, a1)

        base_col = _rgb(seg.color)
        light = Image.new("RGBA", (D, D), base_col + (255,))
        dark = Image.new("RGBA", (D, D), (10, 14, 28, 255))

        alpha = radial.point(lambda p: min(255, int(80 + p * 0.70)))
        shaded = Image.composite(light, dark, alpha)

        img.paste(shaded, (0, 0), mask)

        # Штриховка у пустого сектора
        if seg.is_empty:
            hatch = Image.new("RGBA", (D, D), (0, 0, 0, 0))
            hd = ImageDraw.Draw(hatch)

            for x in range(-D, D, 20):
                hd.line((x, 0, x + D, D), fill=(160, 175, 210, 16), width=3)

            img.paste(hatch, (0, 0), mask)

    # 2) Редкие сектора рисуем поверх, как светящиеся иглы
    d = ImageDraw.Draw(img)

    for seg, (a0, a1, mid, size) in zip(segments, spans):
        if size >= TINY_ANGLE:
            continue

        col = _rgb(seg.color)

        p1 = _polar(DC, DC, R * 0.20, mid)
        p2 = _polar(DC, DC, R * 0.985, mid)

        # Ширина иглы примерно соответствует углу, но не меньше 2px
        arc_px = 2 * R * math.sin(math.radians(max(size, 0.05)) / 2)
        w = max(2, min(4, int(round(arc_px))))

        dark_col = tuple(max(0, int(c * 0.28)) for c in col) + (255,)

        d.line([p1, p2], fill=dark_col, width=w + 2)
        d.line([p1, p2], fill=col + (255,), width=w)

        x, y = _polar(DC, DC, R * 0.985, mid)
        d.ellipse(
            (x - 2, y - 2, x + 2, y + 2),
            fill=GOLD if not seg.is_empty else (120, 132, 160)
        )

    # Разделители. Не рисуем там, где хотя бы одна сторона — иголка.
    d = ImageDraw.Draw(img)
    n = len(spans)

    for i, (a0, a1, mid, size) in enumerate(spans):
        prev_size = spans[(i - 1) % n][3]

        if size < TINY_ANGLE or prev_size < TINY_ANGLE:
            continue

        p1 = _polar(DC, DC, 46, a0)
        p2 = _polar(DC, DC, R, a0)

        if size > 35 and prev_size > 35:
            sw = 3
        elif size > 12 and prev_size > 12:
            sw = 2
        else:
            sw = 1

        d.line([p1, p2], fill=(9, 12, 22), width=sw)
        d.line([p1, p2], fill=(255, 226, 150, 90), width=1)

    # Подписи
    for seg, (a0, a1, mid, size) in zip(segments, spans):
        pct = seg.weight / total * 100

        if size >= LABEL_ANGLE:
            pct_text = f"{pct:.2f}%" if pct < 10 else f"{pct:.1f}%"

            if size > 180:
                max_w = 150
            else:
                max_w = min(
                    150,
                    2 * (R * 0.72) * math.sin(math.radians(size / 2)) * 0.86
                )

            name, f1 = _fit(seg.label, 20 if size > 30 else 16, max_w)
            f2 = _font(13)

            w1 = _text_width(name, f1)
            w2 = _text_width(pct_text, f2)

            tw, th = int(max(w1, w2) + 12), 48

            tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            td = ImageDraw.Draw(tile)

            if seg.is_empty:
                color = (165, 178, 205)
            elif _luminance(_rgb(seg.color)) > 0.55:
                color = (28, 20, 6)
            else:
                color = (245, 248, 255)

            td.text(
                (tw / 2 + 1, 13 + 1),
                name,
                font=f1,
                fill=(0, 0, 0, 160),
                anchor="mm"
            )
            td.text(
                (tw / 2, 13),
                name,
                font=f1,
                fill=color,
                anchor="mm"
            )
            td.text(
                (tw / 2, 34),
                pct_text,
                font=f2,
                fill=(220, 226, 245) if not seg.is_empty else (125, 138, 168),
                anchor="mm"
            )

            mid_norm = mid % 360.0
            rot = -mid_norm if (mid_norm <= 90 or mid_norm >= 270) else 180 - mid_norm
            tile = tile.rotate(rot, resample=RESAMPLE, expand=True)

            x, y = _polar(DC, DC, R * 0.70, mid)
            img.paste(
                tile,
                (int(x - tile.width / 2), int(y - tile.height / 2)),
                tile
            )

        elif size >= TINY_ANGLE:
            # Для маленьких, но не игольчатых секторов — маленькая точка
            x, y = _polar(DC, DC, R * 0.97, mid)
            d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(255, 255, 255, 180))

    return img


# ---------------- Статические оверлеи ----------------
def _hub() -> Image.Image:
    tile = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    c = 70

    d.ellipse((c - 56, c - 56, c + 56, c + 56), fill=(6, 9, 18))
    d.ellipse((c - 52, c - 52, c + 52, c + 52), fill=(20, 26, 44),
              outline=GOLD, width=3)
    d.ellipse((c - 42, c - 42, c + 42, c + 42), fill=(30, 38, 62),
              outline=(86, 98, 132), width=2)

    crown = [
        (-24, 8), (-28, -14), (-14, -4), (0, -22),
        (14, -4), (28, -14), (24, 8)
    ]

    pts = [(c + x, c + y + 2) for x, y in crown]
    d.polygon(pts, fill=GOLD)
    d.rounded_rectangle((c - 24, c + 9, c + 24, c + 16), radius=3, fill=GOLD)

    for x, y in [(-28, -14), (0, -22), (28, -14)]:
        d.ellipse((c + x - 3, c + y - 1, c + x + 3, c + y + 5), fill=(255, 240, 190))

    return tile


def _gloss() -> Image.Image:
    grad = Image.linear_gradient("L").resize((D, D))
    grad = ImageOps.invert(grad).point(lambda p: int(p * .17))

    mask = Image.new("L", (D, D), 0)
    ImageDraw.Draw(mask).ellipse(
        [DC - R, DC - R, DC + R, DC + R], fill=255
    )

    alpha = Image.composite(grad, Image.new("L", (D, D), 0), mask)

    tile = Image.new("RGBA", (D, D), (255, 255, 255, 0))
    tile.putalpha(alpha)
    return tile


def _pointer() -> Image.Image:
    tile = Image.new("RGBA", (120, 110), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)

    # Тень
    d.polygon([(44, 40), (80, 40), (62, 82)], fill=(0, 0, 0, 150))

    # Само перо
    d.polygon([(42, 34), (78, 34), (60, 76)], fill=GOLD,
              outline=(70, 48, 12), width=3)
    d.line((48, 40, 60, 66), fill=(255, 244, 205), width=2)

    # Осевая шайба
    d.ellipse((48, 12, 72, 36), fill=(240, 205, 125),
              outline=(70, 48, 12), width=3)
    d.ellipse((56, 20, 64, 28), fill=(45, 34, 12))

    return tile


# ---------------- Баннер и конфетти ----------------
def _star(d, x, y, r, color):
    pts = []
    for i in range(8):
        ang = math.radians(i * 45 - 90)
        rr = r if i % 2 == 0 else r * .32
        pts.append((x + rr * math.cos(ang), y + rr * math.sin(ang)))
    d.polygon(pts, fill=color)


def _banner(img, small: str, main: str, color=GOLD):
    d = ImageDraw.Draw(img)

    d.rounded_rectangle(
        (86, 690, 634, 762),
        radius=18,
        fill=(15, 21, 39),
        outline=(96, 79, 40),
        width=2
    )

    d.line((106, 692, 614, 692), fill=(180, 150, 85), width=1)
    d.text((CX, 710), small, font=_font(13), fill=(150, 162, 190), anchor="mm")

    text, f = _fit(main, 27, 440)
    d.text((CX, 739), text, font=f, fill=color, anchor="mm")

    _star(d, 112, 738, 9, GOLD)
    _star(d, 608, 738, 9, GOLD)


def _make_confetti(rng, count=70):
    out = []

    for _ in range(count):
        out.append({
            "x0": CX + rng.uniform(-45, 45),
            "y0": CY - R + 45,
            "vx": rng.uniform(-7.5, 7.5),
            "vy": rng.uniform(-13, -4),
            "size": rng.uniform(3, 7),
            "ang": rng.uniform(0, 360),
            "spin": rng.uniform(-14, 14),
            "col": rng.choice([
                GOLD,
                (255, 255, 255),
                (90, 200, 255),
                (255, 110, 170),
                (120, 240, 170),
            ])
        })

    return out


def _confetti_at(parts, i):
    out = []

    for p in parts:
        x = p["x0"] + p["vx"] * i
        y = p["y0"] + p["vy"] * i + 0.20 * i * i

        if y > H + 20:
            continue

        a = math.radians(p["ang"] + p["spin"] * i)
        dx = math.cos(a) * p["size"]
        dy = math.sin(a) * p["size"]

        out.append((
            [
                (x - dx, y - dy),
                (x + dy, y - dx),
                (x + dx, y + dy),
                (x - dy, y + dx),
            ],
            p["col"]
        ))

    return out


# ---------------- Сцена ----------------
class Scene:
    def __init__(self, segments, title, subtitle, center_index: int | None = None):
        self.segments = segments
        self.spans = _layout([s.weight for s in segments], center_index=center_index)
        self.base = _background(title, subtitle)
        self.disc = _disc(segments, self.spans)
        self.hub = _hub()
        self.gloss = _gloss()
        self.pointer = _pointer()
        self.pos = (CX - DC, CY - DC)

    def compose(
        self,
        angle,
        highlight=None,
        hl_alpha=0,
        tilt=0,
        particles=None,
        ring=None,
        small="ИСПЫТЫВАЕМ УДАЧУ",
        main="Колесо вращается",
        main_color=GOLD,
    ):
        img = self.base.copy()

        # Поворачиваем диск.
        # В финале angle будет кратен 360, поэтому диск вернётся в исходное состояние,
        # где победитель уже заранее стоит сверху.
        rotated = self.disc.rotate(
            -(angle % 360),
            resample=RESAMPLE,
            expand=False
        )
        img.paste(rotated, self.pos, rotated)

        # Подсветка выигрышного сектора.
        # Победитель всегда находится сверху, поэтому подсветка тоже сверху.
        if highlight is not None:
            _, _, _, size = self.spans[highlight]
            half = size / 2

            ov = Image.new("RGBA", (D, D), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)

            if size >= TINY_ANGLE:
                pts = _wedge_points(DC, DC, 0, R, -half, half)
                outline_alpha = min(255, int(hl_alpha) + 70)

                od.polygon(
                    pts,
                    fill=(255, 236, 170, int(hl_alpha)),
                    outline=GOLD + (outline_alpha,),
                    width=3
                )
            else:
                # Для игольчатых секторов делаем заметный луч сверху
                od.polygon(
                    [
                        (DC - 6, DC - R + 4),
                        (DC + 6, DC - R + 4),
                        (DC, DC - R + 72),
                    ],
                    fill=(255, 236, 170, int(hl_alpha))
                )
                od.line(
                    (DC, DC - R + 4, DC, DC - R + 72),
                    fill=GOLD + (int(hl_alpha),),
                    width=2
                )

            blur = ov.filter(ImageFilter.GaussianBlur(10))
            img.paste(blur, self.pos, blur)
            img.paste(ov, self.pos, ov)

        # Стоячее бликовое стекло + статичная ступица
        img.paste(self.gloss, self.pos, self.gloss)
        img.paste(self.hub, (CX - 70, CY - 70), self.hub)

        # Указатель
        ptr = self.pointer.rotate(
            tilt,
            resample=RESAMPLE,
            center=(60, 24),
            expand=False
        )
        img.paste(ptr, (CX - 60, POINTER_TOP - 24), ptr)

        d = ImageDraw.Draw(img)

        # Ударная волна при приземлении
        if ring is not None:
            r_i, alpha = ring
            rr = 40 + r_i * 11

            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(ov).ellipse(
                (CX - rr, CY - rr, CX + rr, CY + rr),
                outline=(255, 220, 130, int(alpha)),
                width=4
            )
            img.paste(ov, (0, 0), ov)

        if particles:
            for pts, col in particles:
                d.polygon(pts, fill=col)

        _banner(img, small, main, main_color)
        return img.convert("RGB")

    def pointer_tilt(self, angle):
        """Щелчок указателя каждый раз, когда перегородка проходит сверху."""
        best = 180.0

        for a0, _, _, _ in self.spans:
            p = (a0 + angle) % 360
            dist = min(p, 360 - p)
            best = min(best, dist)

        return 13 * max(0.0, 1 - best / 9.0)


# ---------------- Публичные функции ----------------
def _quantize_save(frames, durations):
    """Сжимаем GIF и гарантированно укладываемся в лимит Discord."""
    if not frames:
        return b""

    last_buf = None

    for scale, step in ((1.0, 1), (.85, 1), (.70, 2)):
        picked = frames[::step]
        durs = durations[::step]

        if not picked:
            continue

        durs[-1] = 2600

        if scale != 1.0:
            size = (int(W * scale), int(H * scale))
            picked = [f.resize(size, RESAMPLE_NEAREST) for f in picked]

        buf = io.BytesIO()
        picked[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=picked[1:],
            duration=durs,
            loop=1,
            optimize=True,
            disposal=2,
        )

        last_buf = buf

        if buf.tell() <= 8_500_000:
            return buf.getvalue()

    return last_buf.getvalue() if last_buf else b""


def make_wheel_png(
    segments,
    title="КОЛЕСО ФОРТУНЫ",
    subtitle="Визуальное колесо",
    highlight: int | None = None
) -> bytes:
    scene = Scene(
        segments,
        title,
        subtitle,
        center_index=highlight if highlight is not None else None
    )

    img = scene.compose(
        angle=0,
        highlight=highlight,
        hl_alpha=45 if highlight is not None else 0,
        small="КАТАЛОГ ПРИЗОВ" if highlight is not None else "КОЛЕСО",
        main=segments[highlight].label if highlight is not None else subtitle,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def make_wheel_gif(
    segments,
    winner: int,
    title="КОЛЕСО ФОРТУНЫ",
    subtitle="Визуальное колесо",
    seed=None
) -> bytes:
    rng = random.Random(seed)
    scene = Scene(segments, title, subtitle, center_index=winner)

    won = segments[winner]

    # Финальный угол всегда кратен 360.
    # Так диск в конце возвращается в состояние, где winner уже стоит сверху.
    start = rng.uniform(45.0, 315.0)
    full_turns = rng.randint(4, 6)
    target = float(full_turns * 360)

    # Палитра строится по финальному кадру -> нет мерцания цветов
    last = scene.compose(
        target,
        highlight=winner,
        hl_alpha=45,
        small="РЕЗУЛЬТАТ",
        main=won.label,
    )

    palette = last.quantize(colors=255)

    def quant(rgb):
        return rgb.quantize(palette=palette, dither=DITHER)

    frames, durations = [], []

    # --- Вращение ---
    for i in range(SPIN_FRAMES):
        t = i / (SPIN_FRAMES - 1)

        # Короткий разгон, затем длинное инерционное замедление
        if t < .12:
            p = .06 * (t / .12) ** 2
        else:
            u = (t - .12) / .88
            p = .06 + .94 * (1 - (1 - u) ** 4)

        angle = start + (target - start) * p
        dots = "." * (1 + i % 3)

        img = scene.compose(
            angle,
            tilt=scene.pointer_tilt(angle),
            small="ИСПЫТЫВАЕМ УДАЧУ",
            main="Колесо вращается" + dots,
            main_color=(225, 232, 250),
        )

        frames.append(quant(img))
        durations.append(FRAME_MS)

    # --- Приземление и праздник ---
    confetti_parts = _make_confetti(
        random.Random(seed if seed is not None else 1)
    )

    for i in range(CELEBRATE_FRAMES):
        pulse = 32 + 22 * math.sin(i * .45)
        tilt = 17 * math.exp(-i * .38) * math.cos(i * .95)

        if won.is_empty:
            small, main, color = "РЕЗУЛЬТАТ", "ПУСТО · крутка сгорела", (165, 178, 205)
            particles = None
            ring = None
        else:
            small, main, color = "ПОЗДРАВЛЯЕМ!", won.label, GOLD
            particles = _confetti_at(confetti_parts, i)
            ring = (i, max(0, 190 - i * 11)) if i < 20 else None

        img = scene.compose(
            target,
            highlight=winner,
            hl_alpha=pulse,
            tilt=max(-14, min(14, tilt)),
            particles=particles,
            ring=ring,
            small=small,
            main=main,
            main_color=color,
        )

        frames.append(quant(img))
        durations.append(FRAME_MS)

    return _quantize_save(frames, durations)