"""
vedic.py — Vedic (Jyotish) readings on the sidereal zodiac.

What is modelled:
  * 9 grahas (Sun–Saturn plus Rahu/Ketu as the MEAN lunar nodes); no Uranus/Neptune/Pluto
  * Rashi, nakshatra and pada; whole-sign houses from the Lagna
  * Vimshottari dasha (mahadasha + antardasha), 365.25-day years
  * Gochara: transits counted in signs from the natal Moon, with the classical
    favourable houses and vedha (obstruction) table; Sun–Saturn and Moon–Mercury
    never obstruct each other; the nodes are not treated as obstructers
  * Sade Sati, Ashtama Shani and Kantaka (4th-house) Shani
  * Sign-based graha drishti of the slow grahas onto the natal Moon sign and Lagna
  * Tara bala and Chandra bala for short periods
  * Eclipses, sign changes, stations, Amavasya/Purnima, dasha changes

Not modelled: Ashtakavarga bindus, divisional charts, yogas, Rahu/Ketu drishti,
other dasha systems. Interpretations are traditional associations, not validated
predictions.
"""
from __future__ import annotations

from datetime import datetime

import swisseph as swe

from astro_engine import (KETU, NAK, SIGNS, Chart, _bisect_bool, _wrap, find_eclipses,
                          find_ingresses, find_lunations, fmt_pos, from_jd, make_grid,
                          period_config, to_jd)

from ashtakavarga import ashtakavarga, fmt_range
from ashtakavarga import verdict as av_verdict

RASHI = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula",
         "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"]
GRAHAS = {"Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
          "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN,
          "Rahu": swe.MEAN_NODE, "Ketu": KETU}

NAKSHATRAS = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu",
              "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta",
              "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha",
              "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha", "Purva Bhadrapada",
              "Uttara Bhadrapada", "Revati"]
DASHA_LORDS = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
DASHA_YEARS = {"Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18,
               "Jupiter": 16, "Saturn": 19, "Mercury": 17}
YEAR = 365.25

# Gochara from the natal Moon: favourable houses, and for each one the vedha house
# that obstructs it when another graha transits there.
GOOD_HOUSES = {"Sun": {3, 6, 10, 11}, "Moon": {1, 3, 6, 7, 10, 11}, "Mars": {3, 6, 11},
               "Mercury": {2, 4, 6, 8, 10, 11}, "Jupiter": {2, 5, 7, 9, 11},
               "Venus": {1, 2, 3, 4, 5, 8, 9, 11, 12}, "Saturn": {3, 6, 11},
               "Rahu": {3, 6, 11}, "Ketu": {3, 6, 11}}
VEDHA = {"Sun": {3: 9, 6: 12, 10: 4, 11: 5},
         "Moon": {1: 5, 3: 9, 6: 12, 7: 2, 10: 4, 11: 8},
         "Mars": {3: 12, 6: 9, 11: 5},
         "Mercury": {2: 5, 4: 3, 6: 9, 8: 1, 10: 8, 11: 12},
         "Jupiter": {2: 12, 5: 4, 7: 3, 9: 10, 11: 8},
         "Venus": {1: 8, 2: 7, 3: 1, 4: 10, 5: 9, 8: 5, 9: 11, 11: 3, 12: 6},
         "Saturn": {3: 12, 6: 9, 11: 5}, "Rahu": {3: 12, 6: 9, 11: 5}, "Ketu": {3: 12, 6: 9, 11: 5}}
NO_VEDHA = {frozenset({"Sun", "Saturn"}), frozenset({"Moon", "Mercury"})}
OBSTRUCTERS = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
GOCHARA_WEIGHT = {"Sun": 1, "Moon": 0.5, "Mars": 1.5, "Mercury": 1, "Jupiter": 3,
                  "Venus": 1, "Saturn": 3, "Rahu": 2, "Ketu": 2}
# Gochara score cut points (tertiles from experiments/calibrate.py). Because most
# grahas are favourable in only a few houses, a typical score is negative; the
# labels compare a period with what is typical, not with zero.
SCORE_CUTS = (-0.52, -0.30)

HOUSE_THEMES = {1: "self, health and temperament", 2: "money, family and speech",
                3: "courage, siblings and initiatives", 4: "home, mother, property and peace of mind",
                5: "children, creativity and judgement", 6: "illness, debts and rivals (and beating them)",
                7: "partners, marriage and travel", 8: "obstacles, sudden events and hidden matters",
                9: "luck, father, teachers and long journeys", 10: "career, status and work",
                11: "gains, income and friends", 12: "expenses, losses, sleep and foreign places"}
SPECIAL_DRISHTI = {"Mars": (4, 8), "Jupiter": (5, 9), "Saturn": (3, 10)}
DRISHTI_NATURE = {"Jupiter": "protective, expansive", "Saturn": "heavy, testing",
                  "Mars": "heated, pushy"}
TARAS = ["Janma", "Sampat", "Vipat", "Kshema", "Pratyari", "Sadhaka", "Vadha", "Mitra", "Parama Mitra"]
TARA_QUALITY = {"Janma": "mixed", "Sampat": "good", "Vipat": "bad", "Kshema": "good",
                "Pratyari": "bad", "Sadhaka": "good", "Vadha": "bad", "Mitra": "good",
                "Parama Mitra": "good"}


def rashi_name(idx: int) -> str:
    return f"{RASHI[idx % 12]} ({SIGNS[idx % 12]})"


def nakshatra_of(lon: float):
    i = int(lon // NAK) % 27
    return NAKSHATRAS[i], int((lon % NAK) // (NAK / 4)) + 1, DASHA_LORDS[i % 9], i


def house_from(sign_idx: int, ref_idx: int) -> int:
    return (sign_idx - ref_idx) % 12 + 1


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ---------------------------------------------------------------------------
# Vimshottari dasha
# ---------------------------------------------------------------------------
def vimshottari(moon_lon: float, birth_jd: float) -> list[dict]:
    i = int(moon_lon // NAK) % 27
    frac = (moon_lon % NAK) / NAK
    k = i % 9
    t = birth_jd - frac * DASHA_YEARS[DASHA_LORDS[k]] * YEAR
    out = []
    while t < birth_jd + 125 * YEAR:
        lord = DASHA_LORDS[k % 9]
        span = DASHA_YEARS[lord] * YEAR
        subs, s = [], t
        for m in range(9):
            sub = DASHA_LORDS[(k + m) % 9]
            dur = span * DASHA_YEARS[sub] / 120
            subs.append({"lord": sub, "start": s, "end": s + dur})
            s += dur
        out.append({"lord": lord, "start": t, "end": t + span, "subs": subs})
        t += span
        k += 1
    return out


def dasha_at(dashas: list[dict], jd: float):
    for md in dashas:
        if md["start"] <= jd < md["end"]:
            for ad in md["subs"]:
                if ad["start"] <= jd < ad["end"]:
                    return md, ad
    return None, None


# ---------------------------------------------------------------------------
# Saturn cycles relative to the Moon sign
# ---------------------------------------------------------------------------
def saturn_house(chart: Chart, jd: float, moon_sign: int) -> int:
    return house_from(int(chart.pos(jd, swe.SATURN)[0] // 30), moon_sign)


def saturn_span(chart: Chart, jd: float, moon_sign: int, houses: set, bridge: float = 300):
    """Start/end of Saturn's stay in `houses` (from the Moon) around jd. Brief retrograde
    exits shorter than `bridge` days are bridged, as Sade Sati is usually quoted."""
    inside = lambda x: saturn_house(chart, x, moon_sign) in houses
    if not inside(jd):
        return None
    ends = []
    for direction in (-1, 1):
        x, last_in, out_for = jd, jd, 0.0
        while out_for < bridge and abs(x - jd) < 12 * YEAR:
            x += 10 * direction
            if inside(x):
                last_in, out_for = x, 0.0
            else:
                out_for += 10
        ends.append(_bisect_bool(inside, last_in, last_in + 10 * direction))
    return ends[0], ends[1]


def next_saturn_entry(chart: Chart, jd: float, moon_sign: int, houses: set, years: float = 32):
    x = jd
    while x < jd + years * YEAR:
        x += 15
        if saturn_house(chart, x, moon_sign) in houses:
            return _bisect_bool(lambda y: saturn_house(chart, y, moon_sign) in houses, x - 15, x)
    return None


# ---------------------------------------------------------------------------
# Natal summary
# ---------------------------------------------------------------------------
def natal_summary(natal: dict) -> dict:
    pts = natal["points"]
    moon = pts["Moon"]
    nak, pada, lord, _ = nakshatra_of(moon)
    lagna_known = "Ascendant" in natal["usable"] or ("Ascendant" in pts and len(natal["signs"]["Ascendant"]) == 1)
    lagna_sign = int(pts["Ascendant"] // 30) if lagna_known else None
    moon_sign = int(moon // 30)

    rows = []
    for name in GRAHAS:
        lon = pts[name]
        n, p, _, _ = nakshatra_of(lon)
        rows.append({"Graha": name, "Position": fmt_pos(lon), "Rashi": rashi_name(int(lon // 30)),
                     "Nakshatra": f"{n} (pada {p})",
                     "House from Lagna": house_from(int(lon // 30), lagna_sign) if lagna_known else "—",
                     "House from Moon": house_from(int(lon // 30), moon_sign),
                     "Retrograde": "R" if natal["retro"][name] and name not in ("Rahu", "Ketu") else ""})
    if "Ascendant" in pts:
        n, p, _, _ = nakshatra_of(pts["Ascendant"])
        rows.insert(0, {"Graha": "Lagna", "Position": fmt_pos(pts["Ascendant"]),
                        "Rashi": " or ".join(RASHI[SIGNS.index(s)] + f" ({s})" for s in natal["signs"]["Ascendant"]),
                        "Nakshatra": f"{n} (pada {p})", "House from Lagna": 1 if lagna_known else "—",
                        "House from Moon": house_from(int(pts["Ascendant"] // 30), moon_sign), "Retrograde": ""})

    # Dasha uncertainty: Moon at both ends of the birth-time window
    lo, hi = natal["range"]["Moon"]
    j_lo, j_hi = natal["jd_range"]
    dashas = vimshottari(moon, natal["jd"])
    edges = [vimshottari(lo, j_lo), vimshottari(hi, j_hi)] if natal["window"] else []
    shift_days = 0.0
    if edges:
        for a, b in zip(edges[0][:12], edges[1][:12]):
            if a["lord"] == b["lord"]:
                shift_days = max(shift_days, abs(a["start"] - b["start"]))
            else:
                shift_days = float("inf")
                break
    nak_options = []
    for x in (lo, moon, hi):
        name = nakshatra_of(x)[0]
        if name not in nak_options:
            nak_options.append(name)
    return {
        "rows": rows, "moon_sign": moon_sign, "moon_signs": natal["signs"]["Moon"],
        "lagna_sign": lagna_sign, "nakshatra": nak, "pada": pada, "nak_lord": lord,
        "nak_options": nak_options, "janma_nak_idx": int(moon // NAK) % 27,
        "dashas": dashas, "dasha_edges": edges, "dasha_shift_days": shift_days,
    }


def natal_ashtakavarga(natal: dict) -> dict:
    """Ashtakavarga over every sign the Lagna and planets could occupy."""
    opts = {g: [SIGNS.index(x) for x in natal["signs"][g]]
            for g in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")}
    if "Ascendant" in natal["points"]:
        opts["Lagna"] = [SIGNS.index(x) for x in natal["signs"]["Ascendant"]]
    return ashtakavarga(opts)


# ---------------------------------------------------------------------------
# Period analysis
# ---------------------------------------------------------------------------
def analyze_vedic(chart: Chart, natal: dict, start: datetime, end: datetime, tz: str) -> dict:
    vs = natal_summary(natal)
    moon_sign, lagna_sign = vs["moon_sign"], vs["lagna_sign"]
    jd0, jd1 = to_jd(start), to_jd(end)
    days = jd1 - jd0
    cfg = period_config(days)
    grid = make_grid(jd0, jd1, cfg["step"])
    grahas = [g for g in GRAHAS if g != "Moon" or days <= 3]
    obstructers = [o for o in OBSTRUCTERS if o != "Moon" or days <= 3]
    av = natal_ashtakavarga(natal)

    # ---- gochara timeline --------------------------------------------------
    signs_at = [{g: int(chart.pos(x, GRAHAS[g])[0] // 30) for g in GRAHAS} for x in grid]
    gochara, score_num, score_den = [], 0.0, 0.0
    for g in grahas:
        segs = []
        for i, x in enumerate(grid):
            s = signs_at[i][g]
            h = house_from(s, moon_sign)
            good = h in GOOD_HOUSES[g]
            blockers = []
            if good:
                vh = VEDHA[g].get(h)
                blockers = [o for o in obstructers if o != g and frozenset({g, o}) not in NO_VEDHA
                            and house_from(signs_at[i][o], moon_sign) == vh]
            if segs and segs[-1]["sign"] == s:
                seg = segs[-1]
            else:
                seg = {"sign": s, "house": h, "good": good, "from": x, "n": 0, "blocked": 0, "by": set()}
                segs.append(seg)
            seg["to"] = x
            seg["n"] += 1
            if blockers:
                seg["blocked"] += 1
                seg["by"].update(blockers)
        g_score = 0.0
        for seg in segs:
            frac_time = seg["n"] / len(grid)
            obstructed = seg["good"] and seg["blocked"] > seg["n"] / 2
            val = 0.0 if obstructed else (1.0 if seg["good"] else -1.0)
            g_score += val * frac_time
            verdict = ("favourable, but obstructed (vedha by " + ", ".join(sorted(seg["by"])) + ")"
                       if obstructed else "favourable" if seg["good"] else "unfavourable")
            gochara.append({
                "Graha": g, "Transit sign": rashi_name(seg["sign"]),
                "From Moon": ordinal(seg["house"]),
                "From Lagna": house_from(seg["sign"], lagna_sign) if lagna_sign is not None else "—",
                "Verdict": verdict,
                "Bindus": (fmt_range(av["bav"][g][seg["sign"]]) if g in av["bav"] else "—"),
                "Bindu support": (av_verdict(av["bav"][g][seg["sign"]]) if g in av["bav"] else "—"),
                "SAV": fmt_range(av["sav"][seg["sign"]]),
                "Theme": HOUSE_THEMES[seg["house"]],
                "When": (from_jd(seg["from"], tz), from_jd(seg["to"], tz)),
                "tone": "neutral" if obstructed else ("supportive" if seg["good"] else "challenging"),
            })
        score_num += GOCHARA_WEIGHT[g] * g_score
        score_den += GOCHARA_WEIGHT[g]
    score = score_num / score_den
    overall = ("Favourable" if score > SCORE_CUTS[1] else
               "Challenging" if score < SCORE_CUTS[0] else "Mixed")

    # ---- Saturn: Sade Sati / Ashtama / Kantaka -----------------------------
    jd_mid = (jd0 + jd1) / 2
    sh = saturn_house(chart, jd_mid, moon_sign)
    saturn = {"house": sh}
    if sh in (12, 1, 2):
        span = saturn_span(chart, jd_mid, moon_sign, {12, 1, 2})
        saturn.update(status="Sade Sati", phase={12: "rising (first)", 1: "peak (second)", 2: "setting (third)"}[sh],
                      start=from_jd(span[0], tz), end=from_jd(span[1], tz))
    elif sh in (8, 4):
        span = saturn_span(chart, jd_mid, moon_sign, {sh})
        saturn.update(status="Ashtama Shani" if sh == 8 else "Kantaka Shani (4th)",
                      start=from_jd(span[0], tz), end=from_jd(span[1], tz))
    else:
        saturn["status"] = None
        nxt = next_saturn_entry(chart, jd_mid, moon_sign, {12})
        saturn["next_sade_sati"] = from_jd(nxt, tz) if nxt else None

    # ---- drishti of slow grahas on Moon sign / Lagna -----------------------
    drishti = []
    for g in ("Jupiter", "Saturn", "Mars"):
        s = int(chart.pos(jd_mid, GRAHAS[g])[0] // 30)
        for h in (7,) + SPECIAL_DRISHTI[g]:
            target = (s + h - 1) % 12
            for label, ref in (("Moon sign", moon_sign), ("Lagna", lagna_sign)):
                if ref is not None and target == ref:
                    drishti.append({"Graha": g, "Aspect": f"{ordinal(h)} sign", "Falls on your": label,
                                    "Nature": DRISHTI_NATURE[g]})

    # ---- dasha -------------------------------------------------------------
    md, ad = dasha_at(vs["dashas"], jd_mid)
    dasha = {"md": md["lord"] if md else None, "ad": ad["lord"] if ad else None,
             "md_span": (from_jd(md["start"], tz), from_jd(md["end"], tz)) if md else None,
             "ad_span": (from_jd(ad["start"], tz), from_jd(ad["end"], tz)) if ad else None,
             "alternatives": []}
    for edge in vs["dasha_edges"]:
        m2, a2 = dasha_at(edge, jd_mid)
        if m2 and (m2["lord"], a2["lord"]) != (dasha["md"], dasha["ad"]):
            alt = f"{m2['lord']}–{a2['lord']}"
            if alt not in dasha["alternatives"]:
                dasha["alternatives"].append(alt)

    # ---- tara bala / chandra bala (short periods) --------------------------
    tara = []
    if days <= 14:
        cuts = [jd0] + [jd for jd, _, _ in find_ingresses(chart, swe.MOON, grid, NAK)] + [jd1]
        for a, b in zip(cuts, cuts[1:]):
            mlon = chart.pos((a + b) / 2, swe.MOON)[0]
            n_idx = int(mlon // NAK) % 27
            t_name = TARAS[(n_idx - vs["janma_nak_idx"]) % 9]
            ch = house_from(int(mlon // 30), moon_sign)
            tara.append({"From": from_jd(a, tz), "To": from_jd(b, tz),
                         "Moon nakshatra": NAKSHATRAS[n_idx], "Tara": t_name,
                         "Tara quality": TARA_QUALITY[t_name],
                         "Moon from natal Moon": ch,
                         "Chandra bala": "good" if ch in GOOD_HOUSES["Moon"] else "weak"})

    # ---- events --------------------------------------------------------------
    events = []
    for g in grahas:
        if g == "Moon" and days > 3:
            continue
        for jd, s, retro in find_ingresses(chart, GRAHAS[g], grid):
            h = house_from(s, moon_sign)
            verb = "re-enters" if retro and g not in ("Rahu", "Ketu") else "enters"
            good = h in GOOD_HOUSES[g]
            events.append({"when": from_jd(jd, tz), "tone": "supportive" if good else "challenging",
                           "event": f"{g} {verb} {rashi_name(s)}",
                           "meaning": f"{ordinal(h)} from your Moon ({HOUSE_THEMES[h]}): traditionally "
                                      f"{'favourable' if good else 'unfavourable'} for {g}."})
    for g in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
        sp = [chart.pos(x, GRAHAS[g])[1] for x in grid]
        for i in range(len(sp) - 1):
            if (sp[i] < 0) != (sp[i + 1] < 0):
                jd = _bisect_bool(lambda x, b=GRAHAS[g]: chart.pos(x, b)[1] < 0, grid[i], grid[i + 1])
                events.append({"when": from_jd(jd, tz), "tone": "neutral",
                               "event": f"{g} turns {'retrograde (vakri)' if sp[i + 1] < 0 else 'direct (margi)'}"
                                        f" in {rashi_name(int(chart.pos(jd, GRAHAS[g])[0] // 30))}",
                               "meaning": "A retrograde graha is traditionally strong but erratic in results."})
    for jd, name, mlon in find_lunations(chart, grid):
        vname = "Amavasya (New Moon)" if name == "New Moon" else "Purnima (Full Moon)"
        events.append({"when": from_jd(jd, tz), "tone": "neutral",
                       "event": f"{vname} in {NAKSHATRAS[int(mlon // NAK) % 27]}, {rashi_name(int(mlon // 30))}",
                       "meaning": f"Falls in the {ordinal(house_from(int(mlon // 30), moon_sign))} from your Moon."})
    eclipses = find_eclipses(chart, jd0, jd1)
    for ec in eclipses:
        ec["when"] = from_jd(ec["jd"], tz)
        n_idx = int(ec["lon"] // NAK) % 27
        h = house_from(int(ec["lon"] // 30), moon_sign)
        notes = []
        if n_idx == vs["janma_nak_idx"]:
            notes.append("it falls in your birth nakshatra, which tradition treats as a sensitive eclipse "
                         "(remedies and rest are advised)")
        if h == 1:
            notes.append("it falls in your Moon sign")
        if lagna_sign is not None and int(ec["lon"] // 30) == lagna_sign:
            notes.append("it falls in your Lagna sign")
        ec["notes"] = notes
        events.append({"when": ec["when"], "tone": "challenging" if notes else "neutral",
                       "event": f"{ec['type']} {ec['kind'].lower()} eclipse (grahan) in {NAKSHATRAS[n_idx]}, {rashi_name(int(ec['lon'] // 30))}",
                       "meaning": f"With {ec['near_node'].split('(')[1].rstrip(')')}; {ordinal(h)} from your Moon"
                                  + (": " + "; ".join(notes) + "." if notes else ".")})
    for md_ in vs["dashas"]:
        for ad_ in md_["subs"]:
            if jd0 <= ad_["start"] < jd1:
                is_md = ad_["start"] == md_["start"]
                events.append({"when": from_jd(ad_["start"], tz), "tone": "neutral",
                               "event": (f"{md_['lord']} mahadasha begins" if is_md else
                                         f"{md_['lord']}–{ad_['lord']} antardasha begins"),
                               "meaning": "Dasha changes shift the planet whose themes lead your life."
                                          + (" (Timing depends on the exact birth time.)" if natal["window"] else "")})
    events.sort(key=lambda e: e["when"])

    sky = []
    for g, b in GRAHAS.items():
        lon, sp = chart.pos(jd_mid, b)
        n, p, _, _ = nakshatra_of(lon)
        sky.append({"Graha": g, "Position": fmt_pos(lon), "Rashi": rashi_name(int(lon // 30)),
                    "Nakshatra": f"{n} ({p})",
                    "From your Moon": house_from(int(lon // 30), moon_sign),
                    "Retrograde": "R" if sp < 0 and g not in ("Rahu", "Ketu") else ""})

    return {"natal": vs, "overall": overall, "score": score, "gochara": gochara, "ashtakavarga": av,
            "saturn": saturn, "drishti": drishti, "dasha": dasha, "tara": tara,
            "events": events, "eclipses": eclipses, "sky": sky, "days": days}
