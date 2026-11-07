"""
matching.py — Ashtakoota (Guna Milan) compatibility, 36 points, from the two Moons.

Traditional tables are read bride → groom. Sources:
  * Varna, Tara, Graha Maitri, Bhakoot, Nadi: standard rules
  * Vashya groups and points, Gana points, nakshatra → Yoni animal, same-Yoni (4) and the
    seven enemy pairs (0): onlinejyotish.com koota articles
  * Yoni 1–3 point values for other animal pairs: the table commonly used in Indian
    matching software. Commentaries differ by about a point for some pairs.
Cancellations (dosha parihara) of Nadi and Bhakoot are listed but not applied.
"""
from __future__ import annotations

from itertools import product

from astro_engine import NAK, SIGNS
from vedic import NAKSHATRAS
from yogas import LORDS

VARNA_RANK = {0: 3, 4: 3, 8: 3, 1: 2, 5: 2, 9: 2, 2: 1, 6: 1, 10: 1, 3: 4, 7: 4, 11: 4}
VARNA_NAME = {4: "Brahmin", 3: "Kshatriya", 2: "Vaishya", 1: "Shudra"}

VASHYA_GROUPS = ["Chatushpada", "Nara", "Jalachara", "Vanachara", "Keeta"]
# rows: bride, columns: groom
VASHYA_POINTS = [[2, 1, 1, 0, 1],
                 [1, 2, 0.5, 0, 1],
                 [1, 0.5, 2, 1, 1],
                 [0, 0, 1, 2, 0],
                 [1, 0, 1, 0, 2]]

YONI_ANIMALS = ["Horse", "Elephant", "Sheep", "Serpent", "Dog", "Cat", "Rat", "Cow", "Buffalo",
                "Tiger", "Deer", "Monkey", "Mongoose", "Lion"]
YONI_OF = ["Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat", "Sheep", "Cat", "Rat",
           "Rat", "Cow", "Buffalo", "Tiger", "Buffalo", "Tiger", "Deer", "Deer", "Dog", "Monkey",
           "Mongoose", "Monkey", "Lion", "Horse", "Lion", "Cow", "Elephant"]
YONI_POINTS = [
    # Hor Ele She Ser Dog Cat Rat Cow Buf Tig Dee Mon Mgs Lio
    [4, 2, 2, 3, 2, 2, 2, 1, 0, 1, 3, 3, 2, 1],   # Horse
    [2, 4, 3, 3, 2, 2, 2, 2, 3, 1, 2, 3, 2, 0],   # Elephant
    [2, 3, 4, 2, 1, 2, 1, 3, 3, 1, 2, 0, 3, 1],   # Sheep
    [3, 3, 2, 4, 2, 1, 1, 1, 1, 2, 2, 2, 0, 2],   # Serpent
    [2, 2, 1, 2, 4, 2, 1, 2, 2, 1, 0, 2, 1, 1],   # Dog
    [2, 2, 2, 1, 2, 4, 0, 2, 2, 1, 3, 3, 2, 1],   # Cat
    [2, 2, 1, 1, 1, 0, 4, 2, 2, 2, 2, 2, 1, 2],   # Rat
    [1, 2, 3, 1, 2, 2, 2, 4, 3, 0, 3, 2, 2, 1],   # Cow
    [0, 3, 3, 1, 2, 2, 2, 3, 4, 1, 2, 2, 2, 1],   # Buffalo
    [1, 1, 1, 2, 1, 1, 2, 0, 1, 4, 1, 1, 2, 1],   # Tiger
    [3, 2, 2, 2, 0, 3, 2, 3, 2, 1, 4, 2, 2, 1],   # Deer
    [3, 3, 0, 2, 2, 3, 2, 2, 2, 1, 2, 4, 3, 2],   # Monkey
    [2, 2, 3, 0, 1, 2, 1, 2, 2, 2, 2, 3, 4, 2],   # Mongoose
    [1, 0, 1, 2, 1, 1, 2, 1, 1, 1, 1, 2, 2, 4],   # Lion
]
GANA_OF = ["Deva", "Manushya", "Rakshasa", "Manushya", "Deva", "Manushya", "Deva", "Deva", "Rakshasa",
           "Rakshasa", "Manushya", "Manushya", "Deva", "Rakshasa", "Deva", "Rakshasa", "Deva", "Rakshasa",
           "Rakshasa", "Manushya", "Manushya", "Deva", "Rakshasa", "Rakshasa", "Manushya", "Manushya", "Deva"]
GANAS = ["Deva", "Manushya", "Rakshasa"]
GANA_POINTS = [[6, 6, 0],     # bride Deva:     groom Deva, Manushya, Rakshasa
               [5, 6, 0],     # bride Manushya
               [1, 0, 6]]     # bride Rakshasa
NADI = ["Adi", "Madhya", "Antya"]

FRIENDS = {"Sun": {"Moon", "Mars", "Jupiter"}, "Moon": {"Sun", "Mercury"},
           "Mars": {"Sun", "Moon", "Jupiter"}, "Mercury": {"Sun", "Venus"},
           "Jupiter": {"Sun", "Moon", "Mars"}, "Venus": {"Mercury", "Saturn"},
           "Saturn": {"Mercury", "Venus"}}
ENEMIES = {"Sun": {"Venus", "Saturn"}, "Moon": set(), "Mars": {"Mercury"}, "Mercury": {"Moon"},
           "Jupiter": {"Mercury", "Venus"}, "Venus": {"Sun", "Moon"}, "Saturn": {"Sun", "Moon", "Mars"}}
MAX = {"Varna": 1, "Vashya": 2, "Tara": 3, "Yoni": 4, "Graha Maitri": 5, "Gana": 6, "Bhakoot": 7, "Nadi": 8}


def vashya_group(lon: float) -> int:
    s, deg = int(lon // 30) % 12, lon % 30
    if s in (0, 1):
        return 0
    if s in (2, 5, 6, 10):
        return 1
    if s in (3, 11):
        return 2
    if s == 4:
        return 3
    if s == 7:
        return 4
    if s == 8:
        return 1 if deg < 15 else 0
    return 0 if deg < 15 else 2                 # Capricorn


def relation(a: str, b: str) -> str:
    return "friend" if b in FRIENDS[a] else "enemy" if b in ENEMIES[a] else "neutral"


def maitri_points(a: str, b: str) -> float:
    if a == b:
        return 5
    pair = sorted([relation(a, b), relation(b, a)])
    return {("friend", "friend"): 5, ("friend", "neutral"): 4, ("neutral", "neutral"): 3,
            ("enemy", "friend"): 1, ("enemy", "neutral"): 0.5, ("enemy", "enemy"): 0}[tuple(pair)]


def tara_ok(from_nak: int, to_nak: int) -> bool:
    return ((to_nak - from_nak) % 27 + 1) % 9 not in (3, 5, 7)


def kootas(bride_moon: float, groom_moon: float) -> dict:
    bn, gn = int(bride_moon // NAK) % 27, int(groom_moon // NAK) % 27
    bs, gs = int(bride_moon // 30) % 12, int(groom_moon // 30) % 12
    scores, notes = {}, {}
    scores["Varna"] = 1 if VARNA_RANK[gs] >= VARNA_RANK[bs] else 0
    notes["Varna"] = f"{VARNA_NAME[VARNA_RANK[bs]]} / {VARNA_NAME[VARNA_RANK[gs]]}"
    vb, vg = vashya_group(bride_moon), vashya_group(groom_moon)
    scores["Vashya"] = VASHYA_POINTS[vb][vg]
    notes["Vashya"] = f"{VASHYA_GROUPS[vb]} / {VASHYA_GROUPS[vg]}"
    scores["Tara"] = 1.5 * tara_ok(bn, gn) + 1.5 * tara_ok(gn, bn)
    notes["Tara"] = f"{NAKSHATRAS[bn]} / {NAKSHATRAS[gn]}"
    yb, yg = YONI_ANIMALS.index(YONI_OF[bn]), YONI_ANIMALS.index(YONI_OF[gn])
    scores["Yoni"] = YONI_POINTS[yb][yg]
    notes["Yoni"] = f"{YONI_OF[bn]} / {YONI_OF[gn]}"
    lb, lg = LORDS[bs], LORDS[gs]
    scores["Graha Maitri"] = maitri_points(lb, lg)
    notes["Graha Maitri"] = f"{lb} / {lg}"
    gb, gg = GANAS.index(GANA_OF[bn]), GANAS.index(GANA_OF[gn])
    scores["Gana"] = GANA_POINTS[gb][gg]
    notes["Gana"] = f"{GANA_OF[bn]} / {GANA_OF[gn]}"
    d1, d2 = (gs - bs) % 12 + 1, (bs - gs) % 12 + 1
    bad = {(2, 12), (12, 2), (5, 9), (9, 5), (6, 8), (8, 6)}
    scores["Bhakoot"] = 0 if (d1, d2) in bad else 7
    notes["Bhakoot"] = f"{SIGNS[bs]} / {SIGNS[gs]} ({d1}/{d2})"
    nb, ng = [0, 1, 2, 2, 1, 0][bn % 6], [0, 1, 2, 2, 1, 0][gn % 6]
    scores["Nadi"] = 0 if nb == ng else 8
    notes["Nadi"] = f"{NADI[nb]} / {NADI[ng]}"
    return {"scores": scores, "notes": notes, "total": sum(scores.values()),
            "nadi_dosha": nb == ng, "bhakoot_dosha": scores["Bhakoot"] == 0}


def match(bride_moons: list[float], groom_moons: list[float]) -> dict:
    """Each list holds the possible Moon positions for that person (one if the birth
    time is known; the two ends of the window otherwise)."""
    results = [kootas(b, g) for b, g in product(bride_moons, groom_moons)]
    base = results[0]
    rows = []
    for k in MAX:
        vals = sorted({r["scores"][k] for r in results})
        rows.append({"Koota": k, "Points": f"{vals[0]:g}" if len(vals) == 1 else f"{vals[0]:g}–{vals[-1]:g}",
                     "Out of": MAX[k], "Bride / groom": base["notes"][k],
                     "Certain": "yes" if len(vals) == 1 else "no"})
    totals = sorted(r["total"] for r in results)
    return {"rows": rows, "total": (totals[0], totals[-1]),
            "nadi_dosha": any(r["nadi_dosha"] for r in results),
            "bhakoot_dosha": any(r["bhakoot_dosha"] for r in results)}


def verdict(total: float) -> str:
    if total >= 28:
        return "excellent"
    if total >= 24:
        return "very good"
    if total >= 18:
        return "acceptable"
    return "below the usual 18-point threshold"
