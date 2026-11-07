"""
vargas.py — divisional charts (Parashara's 16 vargas), how reliable each one is for a
given birth-time uncertainty, and North/South Indian chart diagrams as SVG.

Varga rules follow Brihat Parashara Hora Shastra (the defaults in most Jyotish software):
D2 Hora (Sun/Moon halves), D3 Drekkana (1/5/9), D4 (1/4/7/10), D7 (odd: from the sign,
even: from the 7th), D9 (continuous from Aries), D10 (odd: from the sign, even: from the
9th), D12 (from the sign), D16 (movable/fixed/dual from Aries/Leo/Sagittarius), D20
(Aries/Sagittarius/Leo), D24 (odd from Leo, even from Cancer), D27 (continuous), D30
(unequal Parashari portions), D40 (odd from Aries, even from Libra), D45 (Aries/Leo/
Sagittarius), D60 (from the sign).
"""
from __future__ import annotations

import math

from astro_engine import SIGNS, Chart, _bisect_bool

VARGAS = {
    1: ("Rashi", "the whole chart: body and life in general"),
    2: ("Hora", "wealth"),
    3: ("Drekkana", "siblings, courage"),
    4: ("Chaturthamsha", "property, fixed assets, fortune"),
    7: ("Saptamsha", "children"),
    9: ("Navamsha", "marriage, inner strength of every planet"),
    10: ("Dashamsha", "career and status"),
    12: ("Dwadashamsha", "parents"),
    16: ("Shodashamsha", "vehicles, comforts"),
    20: ("Vimshamsha", "spiritual life"),
    24: ("Chaturvimshamsha", "learning, education"),
    27: ("Saptavimshamsha", "strengths and weaknesses"),
    30: ("Trimshamsha", "misfortunes, health troubles"),
    40: ("Khavedamsha", "maternal legacy"),
    45: ("Akshavedamsha", "paternal legacy, character"),
    60: ("Shashtiamsha", "past karma, fine detail of everything"),
}
ABBR = {"Lagna": "As", "Sun": "Su", "Moon": "Mo", "Mars": "Ma", "Mercury": "Me", "Jupiter": "Ju",
        "Venus": "Ve", "Saturn": "Sa", "Rahu": "Ra", "Ketu": "Ke"}

# D30: (upper degree limit, sign) for odd and even signs
_D30_ODD = [(5, 0), (10, 10), (18, 8), (25, 2), (30, 6)]     # Mars, Saturn, Jupiter, Mercury, Venus
_D30_EVEN = [(5, 1), (12, 5), (20, 11), (25, 9), (30, 7)]    # Venus, Mercury, Jupiter, Saturn, Mars


def varga_sign(lon: float, d: int) -> int:
    """Sign index (0 = Aries) of a sidereal longitude in divisional chart D-d."""
    lon %= 360.0
    s, deg = int(lon // 30) % 12, lon % 30
    odd = s % 2 == 0                      # Aries, Gemini, ... are the odd signs
    mode = s % 3                          # 0 movable, 1 fixed, 2 dual

    def part(size):
        # index of the equal part of the sign; multiply rather than divide by a rounded
        # part size, so a planet exactly on a boundary (e.g. 0° Taurus) lands correctly
        n = int(round(30 / size))
        return min(int(deg * n / 30), n - 1)

    if d == 1:
        return s
    if d == 2:
        return (4 if deg < 15 else 3) if odd else (3 if deg < 15 else 4)
    if d == 3:
        return (s + 4 * part(10)) % 12
    if d == 4:
        return (s + 3 * part(7.5)) % 12
    if d == 7:
        return ((s if odd else s + 6) + part(30 / 7)) % 12
    if d == 9:
        return int(lon * 9 / 30) % 12
    if d == 10:
        return ((s if odd else s + 8) + part(3)) % 12
    if d == 12:
        return (s + part(2.5)) % 12
    if d == 16:
        return ((0, 4, 8)[mode] + part(30 / 16)) % 12
    if d == 20:
        return ((0, 8, 4)[mode] + part(1.5)) % 12
    if d == 24:
        return ((4 if odd else 3) + part(1.25)) % 12
    if d == 27:
        return int(lon * 27 / 30) % 12
    if d == 30:
        for limit, sign in (_D30_ODD if odd else _D30_EVEN):
            if deg < limit:
                return sign
        return (_D30_ODD if odd else _D30_EVEN)[-1][1]
    if d == 40:
        return ((0 if odd else 6) + part(0.75)) % 12
    if d == 45:
        return ((0, 4, 8)[mode] + part(30 / 45)) % 12
    if d == 60:
        return (s + part(0.5)) % 12
    raise ValueError(f"unsupported varga D{d}")


def varga_options(start: float, spread: float, direction: int, d: int) -> list[int]:
    """Every D-d sign a point could be in, given it lies on the arc from `start`
    moving `spread` degrees in `direction`."""
    if spread <= 0:
        return [varga_sign(start, d)]
    step = min(0.05, 30 / d / 6)
    n = max(1, math.ceil(spread / step))
    out = []
    for i in range(n + 1):
        v = varga_sign(start + direction * spread * i / n, d)
        if v not in out:
            out.append(v)
    return out


def _arc(natal: dict, name: str):
    lo, _ = natal["range"][name]
    retro = natal["retro"].get(name, False) and name != "Ascendant"
    return lo, natal["spread"][name], -1 if retro else 1


def varga_table(natal: dict) -> dict:
    """{d: {point: [possible signs]}} for Lagna (if computed) and the grahas."""
    names = (["Ascendant"] if "Ascendant" in natal["points"] else []) + \
            [g for g in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu")]
    out = {}
    for d in VARGAS:
        row = {}
        for name in names:
            if natal["window"] == 0:
                row[name] = [varga_sign(natal["points"][name], d)]
            else:
                row[name] = varga_options(*_arc(natal, name), d)
        out[d] = row
    return out


def reliability(table: dict, has_lagna: bool) -> dict:
    """{d: 'reliable' | 'Lagna uncertain' | 'uncertain' | 'no Lagna'}."""
    out = {}
    for d, row in table.items():
        lagna_ok = has_lagna and len(row.get("Ascendant", [0, 0])) == 1
        planets_ok = all(len(v) == 1 for k, v in row.items() if k != "Ascendant")
        if lagna_ok and planets_ok:
            out[d] = "reliable"
        elif planets_ok:
            out[d] = "Lagna uncertain" if has_lagna else "no Lagna (needs birth time)"
        else:
            out[d] = "uncertain"
    return out


def time_tolerance(chart: Chart, jd: float, lat: float, lon: float, moon_body: int,
                   max_minutes: int = 240) -> dict:
    """For an exact birth time: how many minutes earlier / later the time could be before
    any varga's Lagna or Moon sign changes. {d: (minutes_earlier, minutes_later)}."""
    def asc(x):
        return chart.angles(x, lat, lon)[0]

    def moon(x):
        return chart.pos(x, moon_body)[0]

    steps = [jd + m / 1440 for m in range(-max_minutes, max_minutes + 1)]
    a_vals, m_vals = [asc(x) for x in steps], [moon(x) for x in steps]
    mid = max_minutes
    out = {}
    for d in VARGAS:
        res = []
        for direction in (-1, 1):
            best = float(max_minutes)
            for fn, vals in ((asc, a_vals), (moon, m_vals)):
                v0 = varga_sign(vals[mid], d)
                i = mid
                while 0 < i < len(steps) - 1 and varga_sign(vals[i + direction], d) == v0:
                    i += direction
                if 0 < i < len(steps) - 1:
                    t = _bisect_bool(lambda x: varga_sign(fn(x), d) == v0, steps[i], steps[i + direction], 30)
                    best = min(best, abs(t - jd) * 1440)
            res.append(best)
        out[d] = (res[0], res[1])
    return out


# ---------------------------------------------------------------------------
# Chart diagrams (inline SVG; colours follow the page text colour)
# ---------------------------------------------------------------------------
def _labels(row: dict, retro: dict) -> dict:
    """{sign: [labels]} from {point: [possible signs]}; uncertain points get a '?'."""
    by_sign = {}
    for name, opts in row.items():
        if name == "Ascendant":
            continue
        lab = ABBR[name] + ("(R)" if retro.get(name) and name not in ("Rahu", "Ketu") else "") + \
            ("?" if len(opts) > 1 else "")
        by_sign.setdefault(opts[0], []).append(lab)
    return by_sign


def _text_block(cx, cy, lines, size=12):
    lines = lines or []
    h = size + 2
    y0 = cy - (len(lines) - 1) * h / 2
    return "".join(f'<text x="{cx:.0f}" y="{y0 + i * h:.0f}" font-size="{size}" text-anchor="middle" '
                   f'dominant-baseline="middle" fill="currentColor">{t}</text>' for i, t in enumerate(lines))


def north_indian(row: dict, retro: dict, lagna_sign: int, title: str = "", lagna_label: str = "Lagna") -> str:
    """Diamond chart: houses are fixed (1st at the top), sign numbers rotate."""
    S = 360
    centers = {1: (180, 95), 2: (90, 38), 3: (38, 90), 4: (95, 180), 5: (38, 270), 6: (90, 322),
               7: (180, 265), 8: (270, 322), 9: (322, 270), 10: (265, 180), 11: (322, 90), 12: (270, 38)}
    num_pos = {1: (180, 160), 2: (90, 75), 3: (75, 90), 4: (160, 180), 5: (75, 270), 6: (90, 285),
               7: (180, 200), 8: (270, 285), 9: (285, 270), 10: (200, 180), 11: (285, 90), 12: (270, 75)}
    by_sign = _labels(row, retro)
    parts = [f'<svg viewBox="0 0 {S} {S + (24 if title else 0)}" width="100%" style="max-width:380px" '
             f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title or "chart"}">',
             '<g fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.8">',
             f'<rect x="1" y="1" width="{S - 2}" height="{S - 2}"/>',
             f'<line x1="1" y1="1" x2="{S - 1}" y2="{S - 1}"/><line x1="{S - 1}" y1="1" x2="1" y2="{S - 1}"/>',
             f'<polygon points="180,1 {S - 1},180 180,{S - 1} 1,180"/></g>']
    for h in range(1, 13):
        sign = (lagna_sign + h - 1) % 12
        nx, ny = num_pos[h]
        parts.append(f'<text x="{nx}" y="{ny}" font-size="10" text-anchor="middle" dominant-baseline="middle" '
                     f'fill="currentColor" opacity="0.55">{sign + 1}</text>')
        labels = by_sign.get(sign, [])
        if h == 1:
            labels = [lagna_label] + labels
        parts.append(_text_block(*centers[h], labels))
    if title:
        parts.append(f'<text x="180" y="{S + 16}" font-size="13" text-anchor="middle" fill="currentColor">{title}</text>')
    parts.append("</svg>")
    return "".join(parts)


def south_indian(row: dict, retro: dict, lagna_sign: int | None, title: str = "", lagna_label: str = "Lagna") -> str:
    """Fixed-sign grid: Pisces top-left, signs run clockwise; the Lagna sign is marked."""
    cell = 90
    pos = {11: (0, 0), 0: (1, 0), 1: (2, 0), 2: (3, 0), 3: (3, 1), 4: (3, 2), 5: (3, 3),
           6: (2, 3), 7: (1, 3), 8: (0, 3), 9: (0, 2), 10: (0, 1)}
    by_sign = _labels(row, retro)
    S = 4 * cell
    parts = [f'<svg viewBox="0 0 {S} {S + (24 if title else 0)}" width="100%" style="max-width:380px" '
             f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title or "chart"}">',
             '<g fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.8">']
    for s, (c, r) in pos.items():
        parts.append(f'<rect x="{c * cell + 1}" y="{r * cell + 1}" width="{cell - 2}" height="{cell - 2}"/>')
    parts.append("</g>")
    for s, (c, r) in pos.items():
        x0, y0 = c * cell, r * cell
        parts.append(f'<text x="{x0 + 6}" y="{y0 + 13}" font-size="10" fill="currentColor" opacity="0.55">'
                     f'{SIGNS[s][:3]}</text>')
        labels = by_sign.get(s, [])
        if lagna_sign is not None and s == lagna_sign:
            labels = [lagna_label] + labels
            parts.append(f'<line x1="{x0 + 1}" y1="{y0 + 22}" x2="{x0 + 22}" y2="{y0 + 1}" '
                         f'stroke="currentColor" stroke-width="1.5"/>')
        parts.append(_text_block(x0 + cell / 2, y0 + cell / 2 + 6, labels))
    if title:
        parts.append(f'<text x="{S / 2}" y="{S + 16}" font-size="13" text-anchor="middle" fill="currentColor">{title}</text>')
    parts.append("</svg>")
    return "".join(parts)
