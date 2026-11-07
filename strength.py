"""
strength.py — planetary strength: the parts of Shadbala that have single, well-agreed
formulas. Values are in virupas (60 virupas = 1 rupa).

Included (10 sub-components):
  Sthana:  Uchcha (exaltation), Ojayugma (odd/even sign in D1 and D9), Kendradi
           (kendra / panaphara / apoklima), Drekkana (male / neuter / female decanate)
  Dig:     directional strength from the Ascendant / MC axes
  Kala:    Natonnata (day / night), Paksha (lunar phase), Vara and Hora lords
  Naisargika: fixed natural strength

Left out, because texts and software disagree or they need extra conventions:
Saptavargaja bala, Abda/Masa bala, Tribhaga, Ayana, Yuddha, Cheshta and Drik bala.
So the totals are NOT comparable with full Shadbala from other software, and the
classical "required rupas" thresholds are not applied. Use the table to compare the
planets with each other.
"""
from __future__ import annotations

import swisseph as swe

from astro_engine import Chart, _SWE, _wrap
from panchanga import VARAS, sun_event
from vargas import varga_sign

SEVEN = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
DEEP_EXALT = {"Sun": 10, "Moon": 33, "Mars": 298, "Mercury": 165, "Jupiter": 95, "Venus": 357, "Saturn": 200}
NAISARGIKA = {"Sun": 60.0, "Moon": 51.43, "Venus": 42.86, "Jupiter": 34.29, "Mercury": 25.71,
              "Mars": 17.14, "Saturn": 8.57}
# Dig bala: the point where each planet is strongest
DIG_STRONG = {"Sun": "MC", "Mars": "MC", "Jupiter": "Asc", "Mercury": "Asc",
              "Moon": "IC", "Venus": "IC", "Saturn": "Desc"}
DAY_STRONG = {"Sun", "Jupiter", "Venus"}
NIGHT_STRONG = {"Moon", "Mars", "Saturn"}
BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
GENDER_DREKKANA = {"Sun": 0, "Mars": 0, "Jupiter": 0, "Mercury": 1, "Saturn": 1, "Moon": 2, "Venus": 2}
CHALDEAN = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]


def _dist(a: float, b: float) -> float:
    return abs(_wrap(a - b))


def strengths(chart: Chart, natal: dict, lat: float, lon: float) -> list[dict]:
    jd = natal["jd"]
    pts = natal["points"]
    asc, mc = pts["Ascendant"], pts["Midheaven"]
    axis = {"Asc": asc, "Desc": (asc + 180) % 360, "MC": mc, "IC": (mc + 180) % 360}
    lagna = int(asc // 30)

    # Sun's hour angle for day/night strength
    with _SWE:
        ra = swe.calc_ut(jd, swe.SUN, swe.FLG_MOSEPH | swe.FLG_EQUATORIAL)[0][0]
        lst = (swe.sidtime(jd) * 15 + lon) % 360
    hour_angle = abs(_wrap(lst - ra))                       # 0 at local noon, 180 at midnight
    day_part = 60 * (180 - hour_angle) / 180

    # Paksha: Moon–Sun elongation, folded to 0–180
    e = (pts["Moon"] - pts["Sun"]) % 360
    e = 360 - e if e > 180 else e

    # Vara and hora lords (the Vedic day starts at sunrise; horas are equal hours)
    rise = sun_event(jd - 1.2, lat, lon, True)               # last sunrise before birth
    while rise is not None:
        nxt = sun_event(rise + 0.01, lat, lon, True)
        if nxt is None or nxt > jd:
            break
        rise = nxt
    vara_lord = hora_lord = None
    if rise is not None and rise <= jd:
        from astro_engine import from_jd
        # weekday of that sunrise at the birthplace (local mean time, so no time zone needed)
        local_rise_day = from_jd(rise + lon / 360, "UTC").date()
        vara_lord = VARAS[(local_rise_day.weekday() + 1) % 7][2]
        hora_lord = _hora_lord(vara_lord, int((jd - rise) * 24))

    rows = []
    for p in SEVEN:
        l = pts[p]
        s = int(l // 30)
        uchcha = 60 * _dist(l, (DEEP_EXALT[p] + 180) % 360) / 180
        odd_d1, odd_d9 = s % 2 == 0, varga_sign(l, 9) % 2 == 0
        wants_even = p in ("Moon", "Venus")
        oja = 15 * ((odd_d1 != wants_even) + (odd_d9 != wants_even))
        h = (s - lagna) % 12 + 1
        kendradi = 60 if h in (1, 4, 7, 10) else 30 if h in (2, 5, 8, 11) else 15
        drek = 15 if int((l % 30) // 10) == GENDER_DREKKANA[p] else 0
        dig = 60 * _dist(l, (axis[DIG_STRONG[p]] + 180) % 360) / 180
        if p == "Mercury":
            nato = 60.0
        elif p in DAY_STRONG:
            nato = day_part
        else:
            nato = 60 - day_part
        paksha = e / 3 if p in BENEFICS else 60 - e / 3
        if p == "Moon":
            paksha *= 2
        vara = 45.0 if p == vara_lord else 0.0
        hora = 60.0 if p == hora_lord else 0.0
        sthana = uchcha + oja + kendradi + drek
        kala = nato + paksha + vara + hora
        total = sthana + dig + kala + NAISARGIKA[p]
        rows.append({"Planet": p, "Uchcha": uchcha, "Ojayugma": oja, "Kendradi": kendradi,
                     "Drekkana": drek, "Dig": dig, "Natonnata": nato, "Paksha": paksha,
                     "Vara+Hora": vara + hora, "Naisargika": NAISARGIKA[p],
                     "Partial total": total, "Rupas": total / 60})
    order = sorted(rows, key=lambda r: -r["Partial total"])
    for i, r in enumerate(order):
        r["Rank"] = i + 1
    return rows


def _hora_lord(day_lord: str, hours_since_sunrise: int) -> str:
    """Horas follow the descending Chaldean order Saturn, Jupiter, Mars, Sun, Venus,
    Mercury, Moon, starting with the lord of the day."""
    return CHALDEAN[(CHALDEAN.index(day_lord) + hours_since_sunrise) % 7]
