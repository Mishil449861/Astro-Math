"""
ashtakavarga.py — Bhinnashtakavarga (BAV) and Sarvashtakavarga (SAV), Parashara's tables.

For each of the seven planets, eight contributors (the seven planets and the Lagna) give
one bindu to the signs listed below, counted from the contributor's own sign. The
totals are fixed whatever the chart (Sun 48, Moon 49, Mars 39, Mercury 54, Jupiter 56,
Venus 52, Saturn 39; SAV 337), which the tests use as a check on these tables.

In transit, a planet passing through a sign where its own BAV has 4+ bindus is
traditionally supported; 0–3 bindus weakens it. A sign with 28+ SAV bindus is strong.
"""
from __future__ import annotations

from itertools import product

PLANETS7 = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
CONTRIBUTORS = PLANETS7 + ["Lagna"]

BAV_RULES = {
    "Sun": {"Sun": [1, 2, 4, 7, 8, 9, 10, 11], "Moon": [3, 6, 10, 11], "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
            "Mercury": [3, 5, 6, 9, 10, 11, 12], "Jupiter": [5, 6, 9, 11], "Venus": [6, 7, 12],
            "Saturn": [1, 2, 4, 7, 8, 9, 10, 11], "Lagna": [3, 4, 6, 10, 11, 12]},
    "Moon": {"Sun": [3, 6, 7, 8, 10, 11], "Moon": [1, 3, 6, 7, 10, 11], "Mars": [2, 3, 5, 6, 9, 10, 11],
             "Mercury": [1, 3, 4, 5, 7, 8, 10, 11], "Jupiter": [1, 4, 7, 8, 10, 11, 12],
             "Venus": [3, 4, 5, 7, 9, 10, 11], "Saturn": [3, 5, 6, 11], "Lagna": [3, 6, 10, 11]},
    "Mars": {"Sun": [3, 5, 6, 10, 11], "Moon": [3, 6, 11], "Mars": [1, 2, 4, 7, 8, 10, 11],
             "Mercury": [3, 5, 6, 11], "Jupiter": [6, 10, 11, 12], "Venus": [6, 8, 11, 12],
             "Saturn": [1, 4, 7, 8, 9, 10, 11], "Lagna": [1, 3, 6, 10, 11]},
    "Mercury": {"Sun": [5, 6, 9, 11, 12], "Moon": [2, 4, 6, 8, 10, 11], "Mars": [1, 2, 4, 7, 8, 9, 10, 11],
                "Mercury": [1, 3, 5, 6, 9, 10, 11, 12], "Jupiter": [6, 8, 11, 12],
                "Venus": [1, 2, 3, 4, 5, 8, 9, 11], "Saturn": [1, 2, 4, 7, 8, 9, 10, 11],
                "Lagna": [1, 2, 4, 6, 8, 10, 11]},
    "Jupiter": {"Sun": [1, 2, 3, 4, 7, 8, 9, 10, 11], "Moon": [2, 5, 7, 9, 11], "Mars": [1, 2, 4, 7, 8, 10, 11],
                "Mercury": [1, 2, 4, 5, 6, 9, 10, 11], "Jupiter": [1, 2, 3, 4, 7, 8, 10, 11],
                "Venus": [2, 5, 6, 9, 10, 11], "Saturn": [3, 5, 6, 12], "Lagna": [1, 2, 4, 5, 6, 7, 9, 10, 11]},
    "Venus": {"Sun": [8, 11, 12], "Moon": [1, 2, 3, 4, 5, 8, 9, 11, 12], "Mars": [3, 4, 6, 9, 11, 12],
              "Mercury": [3, 5, 6, 9, 11], "Jupiter": [5, 8, 9, 10, 11], "Venus": [1, 2, 3, 4, 5, 8, 9, 10, 11],
              "Saturn": [3, 4, 5, 8, 9, 10, 11], "Lagna": [1, 2, 3, 4, 5, 8, 9, 11]},
    "Saturn": {"Sun": [1, 2, 4, 7, 8, 10, 11], "Moon": [3, 6, 11], "Mars": [3, 5, 6, 10, 11, 12],
               "Mercury": [6, 8, 9, 10, 11, 12], "Jupiter": [5, 6, 11, 12], "Venus": [6, 11, 12],
               "Saturn": [3, 5, 6, 11], "Lagna": [1, 3, 4, 6, 10, 11]},
}
BAV_TOTALS = {"Sun": 48, "Moon": 49, "Mars": 39, "Mercury": 54, "Jupiter": 56, "Venus": 52, "Saturn": 39}


def bav(signs: dict) -> dict:
    """signs: contributor -> sign index (0 = Aries). Returns planet -> [12 bindus], or for
    a chart without a Lagna, only the seven planetary contributors are counted."""
    out = {}
    for planet, rules in BAV_RULES.items():
        row = [0] * 12
        for contrib, houses in rules.items():
            if contrib not in signs:
                continue
            for h in houses:
                row[(signs[contrib] + h - 1) % 12] += 1
        out[planet] = row
    return out


def sav(bavs: dict) -> list:
    return [sum(bavs[p][s] for p in PLANETS7) for s in range(12)]


def ashtakavarga(sign_options: dict) -> dict:
    """sign_options: contributor -> list of possible signs (from birth-time uncertainty).
    Returns {"bav": {planet: [(min, max)]*12}, "sav": [(min, max)]*12, "certain": bool,
    "lagna_known": bool}. A missing Lagna means it could be in any sign."""
    opts = {k: v for k, v in sign_options.items() if k in CONTRIBUTORS}
    lagna_known = "Lagna" in opts
    if not lagna_known:
        opts["Lagna"] = list(range(12))
    names = list(opts)
    lo_b = {p: [99] * 12 for p in PLANETS7}
    hi_b = {p: [0] * 12 for p in PLANETS7}
    lo_s, hi_s = [999] * 12, [0] * 12
    for combo in product(*(opts[n] for n in names)):
        b = bav(dict(zip(names, combo)))
        s = sav(b)
        for p in PLANETS7:
            for i in range(12):
                lo_b[p][i] = min(lo_b[p][i], b[p][i])
                hi_b[p][i] = max(hi_b[p][i], b[p][i])
        for i in range(12):
            lo_s[i], hi_s[i] = min(lo_s[i], s[i]), max(hi_s[i], s[i])
    return {"bav": {p: list(zip(lo_b[p], hi_b[p])) for p in PLANETS7},
            "sav": list(zip(lo_s, hi_s)),
            "certain": all(len(v) == 1 for v in opts.values()), "lagna_known": lagna_known}


def fmt_range(r) -> str:
    return str(r[0]) if r[0] == r[1] else f"{r[0]}–{r[1]}"


def verdict(r) -> str:
    """Transit support from a planet's own BAV bindus in a sign."""
    lo, hi = r
    if lo >= 4:
        return "supported" if lo >= 5 else "average"
    if hi <= 3:
        return "weak"
    return "depends on birth time"
