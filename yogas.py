"""
yogas.py — rule-based yoga detection on the sidereal Rashi chart (whole-sign houses),
plus Kuja (Mangal) dosha.

Every rule is evaluated for each possible Lagna / Moon sign allowed by the birth-time
uncertainty, so a yoga is reported as "present" (in every case) or "depends on birth
time" (in some). The rules are the common textbook forms; classical texts add further
conditions (strength, combustion, aspects) that are not applied here, and schools differ.
"""
from __future__ import annotations

from itertools import product

LORDS = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury", "Venus", "Mars", "Jupiter",
         "Saturn", "Saturn", "Jupiter"]
EXALT = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3, "Venus": 11, "Saturn": 6}
DEBIL = {p: (s + 6) % 12 for p, s in EXALT.items()}
OWN = {"Sun": {4}, "Moon": {3}, "Mars": {0, 7}, "Mercury": {2, 5}, "Jupiter": {8, 11},
       "Venus": {1, 6}, "Saturn": {9, 10}}
SPECIAL = {"Mars": (4, 8), "Jupiter": (5, 9), "Saturn": (3, 10)}
SEVEN = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
KENDRA, TRIKONA, DUSTHANA = {1, 4, 7, 10}, {1, 5, 9}, {6, 8, 12}
MAHAPURUSHA = {"Mars": "Ruchaka", "Mercury": "Bhadra", "Jupiter": "Hamsa", "Venus": "Malavya", "Saturn": "Sasa"}


def house(sign: int, ref: int) -> int:
    return (sign - ref) % 12 + 1


def nth(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def aspects(p: str, from_sign: int, to_sign: int) -> bool:
    return house(to_sign, from_sign) in (7,) + SPECIAL.get(p, ())


def related(a: str, b: str, s: dict) -> str | None:
    """How two planets are connected: conjunction, sign exchange or mutual aspect."""
    if s[a] == s[b]:
        return "together"
    if LORDS[s[a]] == b and LORDS[s[b]] == a:
        return "exchange signs"
    if aspects(a, s[a], s[b]) and aspects(b, s[b], s[a]):
        return "aspect each other"
    return None


def lord_of_house(h: int, lagna: int) -> str:
    return LORDS[(lagna + h - 1) % 12]


def detect(s: dict, lons: dict) -> list[tuple[str, str, str]]:
    """s: name -> sign (incl. 'Lagna' if known). Returns [(yoga, category, detail)]."""
    out = []
    moon = s["Moon"]
    lagna = s.get("Lagna")

    # --- Moon-based -----------------------------------------------------------
    if house(s["Jupiter"], moon) in KENDRA:
        out.append(("Gaja Kesari", "Moon", f"Jupiter in the {nth(house(s['Jupiter'], moon))} from the Moon: "
                                           "wisdom, reputation, lasting good fortune."))
    if s["Moon"] == s["Mars"] or house(s["Mars"], moon) == 7:
        out.append(("Chandra-Mangala", "Moon", "Moon and Mars together or opposite: drive to earn, "
                                               "sometimes through bold or unconventional means."))
    others = ["Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    in2 = [p for p in others if house(s[p], moon) == 2]
    in12 = [p for p in others if house(s[p], moon) == 12]
    if in2 and in12:
        out.append(("Durudhara", "Moon", f"{', '.join(in2)} 2nd and {', '.join(in12)} 12th from the Moon: "
                                         "resources and support from both sides."))
    elif in2:
        out.append(("Sunapha", "Moon", f"{', '.join(in2)} 2nd from the Moon: self-earned wealth and standing."))
    elif in12:
        out.append(("Anapha", "Moon", f"{', '.join(in12)} 12th from the Moon: good health, poise, reputation."))
    else:
        cancel = [p for p in others if house(s[p], moon) in KENDRA] + \
                 ([p for p in others if lagna is not None and house(s[p], lagna) in KENDRA])
        detail = "No planet in the 2nd or 12th from the Moon: periods of feeling unsupported."
        if cancel:
            detail += f" Traditionally cancelled here, since {', '.join(sorted(set(cancel)))} occupies a kendra."
        out.append(("Kemadruma" + (" (cancelled)" if cancel else ""), "Moon", detail))
    if all(house(s[p], moon) in (6, 7, 8) for p in ("Mercury", "Jupiter", "Venus")):
        out.append(("Adhi", "Moon", "All benefics 6th–8th from the Moon: leadership and comfort."))
    if sum(house(s[p], moon) in (3, 6, 10, 11) for p in ("Mercury", "Jupiter", "Venus")) >= 2:
        out.append(("Vasumati", "Moon", "Benefics in growth houses from the Moon: steady accumulation of wealth."))

    # --- conjunctions -----------------------------------------------------------
    if s["Sun"] == s["Mercury"]:
        out.append(("Budha-Aditya", "Conjunction", "Sun with Mercury: intelligence, skill with words."))
    if all(0 < (lons[p] - lons["Rahu"]) % 360 < 180 for p in SEVEN) or \
       all(180 < (lons[p] - lons["Rahu"]) % 360 < 360 for p in SEVEN):
        out.append(("Kala Sarpa", "Nodes", "All seven planets on one side of the Rahu–Ketu axis. A modern "
                                           "idea, not in the classical texts."))

    # --- debilitation cancelled ----------------------------------------------------
    for p in SEVEN:
        if s[p] == DEBIL[p]:
            disp = LORDS[s[p]]
            exalted_here = [q for q, e in EXALT.items() if e == s[p]]
            refs = [moon] + ([lagna] if lagna is not None else [])
            helpers = [q for q in [disp] + exalted_here if any(house(s[q], r) in KENDRA for r in refs)]
            if helpers:
                out.append(("Neecha Bhanga Raja", "Strength", f"{p} is debilitated, but {', '.join(helpers)} in a "
                                                              "kendra cancels it: setbacks that turn into rise."))

    if lagna is None:
        return out

    # --- Lagna-based -----------------------------------------------------------------
    for p, name in MAHAPURUSHA.items():
        if (s[p] in OWN[p] or s[p] == EXALT[p]) and house(s[p], lagna) in KENDRA:
            out.append((name, "Mahapurusha", f"{p} strong (own or exaltation sign) in a kendra."))
    for p in ("Jupiter", "Venus", "Mercury"):
        if house(s[p], lagna) == 10 or house(s[p], moon) == 10:
            out.append(("Amala", "Lagna", f"{p} in the 10th: a clean reputation and good deeds."))
            break

    kendra_lords = {h: lord_of_house(h, lagna) for h in KENDRA}
    trikona_lords = {h: lord_of_house(h, lagna) for h in TRIKONA}
    for p in SEVEN:
        ks = [h for h, l in kendra_lords.items() if l == p and h != 1]
        ts = [h for h, l in trikona_lords.items() if l == p and h != 1]
        if ks and ts:
            out.append(("Yogakaraka", "Raja", f"{p} rules both the {nth(ks[0])} (kendra) and {nth(ts[0])} (trikona) house."))
    seen = set()
    for kh, kl in kendra_lords.items():
        for th, tl in trikona_lords.items():
            pair = frozenset({kl, tl})
            if kl == tl or pair in seen:
                continue
            how = related(kl, tl, s)
            if how:
                seen.add(pair)
                out.append(("Raja", "Raja", f"{nth(kh)} lord {kl} and {nth(th)} lord {tl} {how}: authority and success."))
    wealth = {h: lord_of_house(h, lagna) for h in (2, 11)}
    for wh, wl in wealth.items():
        for th, tl in {**trikona_lords}.items():
            if wl != tl and related(wl, tl, s):
                out.append(("Dhana", "Wealth", f"{nth(wh)} lord {wl} and {nth(th)} lord {tl} {related(wl, tl, s)}: wealth."))
    for h, name in ((6, "Harsha"), (8, "Sarala"), (12, "Vimala")):
        l = lord_of_house(h, lagna)
        if house(s[l], lagna) in DUSTHANA:
            out.append((f"Viparita Raja ({name})", "Raja", f"{nth(h)} lord {l} placed in the {nth(house(s[l], lagna))}: "
                                                            "gains that come out of difficulty."))
    done = set()
    for a in SEVEN:
        for b in SEVEN:
            if a < b and LORDS[s[a]] == b and LORDS[s[b]] == a and (a, b) not in done:
                done.add((a, b))
                ha, hb = house(s[a], lagna), house(s[b], lagna)
                kind = "Dainya" if {ha, hb} & DUSTHANA else "Khala" if 3 in (ha, hb) else "Maha"
                out.append((f"Parivartana ({kind})", "Exchange", f"{a} and {b} exchange signs ({nth(ha)} and {nth(hb)} houses)."))
    return out


def kuja_dosha(s: dict) -> list[str]:
    """Mars in the 1st, 2nd, 4th, 7th, 8th or 12th, counted from Lagna, Moon and Venus
    (South Indian convention; North Indian charts often leave out the 2nd). Cancellation
    rules are not applied."""
    out = []
    for ref in ("Lagna", "Moon", "Venus"):
        if ref in s and house(s["Mars"], s[ref]) in (1, 2, 4, 7, 8, 12):
            out.append(f"from {ref} (Mars in the {nth(house(s['Mars'], s[ref]))})")
    return out


def evaluate(natal: dict) -> dict:
    """Yogas over every Lagna/Moon sign the birth-time uncertainty allows."""
    from astro_engine import SIGNS
    pts = natal["points"]
    base = {g: int(pts[g] // 30) for g in SEVEN + ["Rahu", "Ketu"]}
    moon_opts = [SIGNS.index(x) for x in natal["signs"]["Moon"]]
    if "Ascendant" in pts:
        lagna_opts = [SIGNS.index(x) for x in natal["signs"]["Ascendant"]]
    else:
        lagna_opts = [None]
    lons = {g: pts[g] for g in SEVEN + ["Rahu", "Ketu"]}
    counts, kuja = {}, {}
    scenarios = list(product(moon_opts, lagna_opts))
    for m, l in scenarios:
        s = dict(base, Moon=m)
        if l is not None:
            s["Lagna"] = l
        for key in set(detect(s, lons)):          # (name, category, detail)
            counts[key] = counts.get(key, 0) + 1
        for k in set(kuja_dosha(s)):
            kuja[k] = kuja.get(k, 0) + 1
    rows = [{"Yoga": n, "Type": cat, "Meaning": detail,
             "Status": "present" if c == len(scenarios) else "depends on birth time"}
            for (n, cat, detail), c in counts.items()]
    # the meaning breaks ties between yogas of the same name (several Raja yogas), so the order,
    # and the fact numbers built from it, are the same on every run
    rows.sort(key=lambda r: (r["Status"] != "present", r["Type"], r["Yoga"], r["Meaning"]))
    return {"rows": rows, "lagna_known": lagna_opts != [None],
            "kuja": [{"Counted": k, "Status": "present" if c == len(scenarios) else "depends on birth time"}
                     for k, c in sorted(kuja.items())]}
