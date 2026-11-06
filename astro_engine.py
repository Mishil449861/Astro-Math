"""
astro_engine.py — calculation engine for app.py

Planetary positions come from the Swiss Ephemeris (Moshier mode: no data files
needed, ~1 arcsecond accuracy for 3000 BC–3000 AD). Precession and nutation are
included; sidereal (Vedic) charts subtract the Lahiri ayanamsa.

The interpretations are traditional astrological associations, not validated
predictions.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED

# ---------------------------------------------------------------------------
# Reference tables (edit freely — this is the "rule table")
# ---------------------------------------------------------------------------
SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
SIGN_SYMBOLS = dict(zip(SIGNS, "♈♉♊♋♌♍♎♏♐♑♒♓"))
SIGN_KEYWORDS = {
    "Aries": "bold, direct, pioneering", "Taurus": "steady, sensual, persistent",
    "Gemini": "curious, talkative, adaptable", "Cancer": "nurturing, protective, sensitive",
    "Leo": "expressive, proud, warm", "Virgo": "analytical, practical, helpful",
    "Libra": "diplomatic, social, fair-minded", "Scorpio": "intense, private, determined",
    "Sagittarius": "adventurous, honest, philosophical", "Capricorn": "ambitious, disciplined, reserved",
    "Aquarius": "independent, inventive, idealistic", "Pisces": "imaginative, empathetic, dreamy",
}

PLANETS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY, "Venus": swe.VENUS,
    "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN,
    "Uranus": swe.URANUS, "Neptune": swe.NEPTUNE, "Pluto": swe.PLUTO,
    "North Node": swe.TRUE_NODE,
}
PLANET_ICONS = {"Sun": "☀️", "Moon": "🌙", "Mercury": "☿", "Venus": "♀", "Mars": "♂",
                "Jupiter": "♃", "Saturn": "♄", "Uranus": "♅", "Neptune": "♆",
                "Pluto": "♇", "North Node": "☊"}

ASPECTS = {0: "conjunct", 60: "sextile", 90: "square", 120: "trine", 180: "opposite"}
ASPECT_TONE = {60: "supportive", 120: "supportive", 90: "challenging", 180: "challenging"}
# Conjunctions take their tone from the planet doing the touching
CONJ_TONE = {"Jupiter": "supportive", "Venus": "supportive",
             "Sun": "neutral", "Moon": "neutral", "Mercury": "neutral", "North Node": "neutral",
             "Mars": "challenging", "Saturn": "challenging", "Uranus": "challenging",
             "Neptune": "challenging", "Pluto": "challenging"}

ORBS = {"Moon": 3, "Sun": 2, "Mercury": 2, "Venus": 2, "Mars": 2, "Jupiter": 2,
        "Saturn": 2, "Uranus": 1.5, "Neptune": 1.5, "Pluto": 1.5, "North Node": 1}
WEIGHTS = {"Moon": 0.5, "Sun": 1, "Mercury": 1, "Venus": 1, "Mars": 1.5, "Jupiter": 2,
           "Saturn": 3, "Uranus": 3, "Neptune": 3, "Pluto": 3, "North Node": 1}
# How far (days) to look either side when working out how long an influence lasts
WINDOW_LIMIT = {"Moon": 1, "Sun": 5, "Mercury": 40, "Venus": 60, "Mars": 120,
                "Jupiter": 400, "Saturn": 400, "Uranus": 800, "Neptune": 800,
                "Pluto": 800, "North Node": 200}

TRANSIT_THEMES = {
    "Moon": "moods and day-to-day feelings",
    "Sun": "attention, energy and visibility",
    "Mercury": "conversations, messages, plans and short trips",
    "Venus": "affection, pleasure, social life and spending",
    "Mars": "energy, drive, haste and arguments",
    "Jupiter": "growth, opportunity, optimism and sometimes excess",
    "Saturn": "pressure, responsibility, delays and restructuring",
    "Uranus": "sudden change, disruption and breakthroughs",
    "Neptune": "confusion, idealism, intuition and blurred boundaries",
    "Pluto": "deep transformation, power struggles, endings and renewal",
    "North Node": "significant meetings and shifts in direction",
}
NATAL_AREAS = {
    "Sun": "Self & vitality", "Moon": "Emotions & home", "Mercury": "Communication & plans",
    "Venus": "Love & money", "Mars": "Drive & conflict", "Jupiter": "Growth & beliefs",
    "Saturn": "Duties & commitments", "Uranus": "Freedom & change",
    "Neptune": "Dreams & intuition", "Pluto": "Power & transformation",
    "North Node": "Life direction", "Ascendant": "Self-image & health",
    "Midheaven": "Career & reputation",
}
TONE_PHRASE = {
    "supportive": "A harmonious contact, so this tends to work in your favour.",
    "challenging": "A tense contact, so this tends to bring friction that pushes change.",
    "neutral": "This puts a spotlight on the area.",
}
# Personal points only: slow outer planets / nodes in the birth chart are shared
# by everyone born within months or years, so transits to them are left out.
PERSONAL_POINTS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
                   "Ascendant", "Midheaven"]
DOMAINS = {"Mercury": "communication, travel & plans", "Venus": "relationships & money",
           "Mars": "action & conflict", "Jupiter": "growth & opportunity",
           "Saturn": "responsibility & structure", "Uranus": "change & freedom",
           "Neptune": "ideals & intuition", "Pluto": "power & transformation",
           "Sun": "focus & vitality", "Moon": "mood & emotional tone"}

PERIODS = {
    # step = sampling interval in days; Moon transits only make sense day-by-day
    "Day":   {"step": 1 / 24, "moon_transits": True,  "moon_ingress": True},
    "Week":  {"step": 0.25,   "moon_transits": False, "moon_ingress": True},
    "Month": {"step": 1.0,    "moon_transits": False, "moon_ingress": False},
}
# Total-weight cut points for Low / Moderate / High (≈ tertiles over many sample charts)
INTENSITY_CUTS = {"Day": (10.5, 13.5), "Week": (13.0, 18.0), "Month": (33.5, 40.0)}
STATION_BODIES = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
INGRESS_BODIES = ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def to_jd(dt: datetime) -> float:
    u = dt.astimezone(timezone.utc)
    return swe.julday(u.year, u.month, u.day, u.hour + u.minute / 60 + u.second / 3600)


def from_jd(jd: float, tz: str) -> datetime:
    y, m, d, h = swe.revjul(jd)
    return (datetime(int(y), int(m), int(d), tzinfo=timezone.utc) + timedelta(hours=h)).astimezone(ZoneInfo(tz))


def sign_of(lon: float) -> str:
    return SIGNS[int(lon // 30) % 12]


def fmt_pos(lon: float) -> str:
    deg = lon % 30
    return f"{int(deg)}°{int((deg % 1) * 60):02d}′ {sign_of(lon)}"


def _wrap(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


def _bisect(f, a: float, b: float, iters: int = 40) -> float:
    fa = f(a)
    for _ in range(iters):
        m = (a + b) / 2
        fm = f(m)
        if (fa < 0) == (fm < 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


def _extend(f, jd: float, orb: float, step: float, limit: float) -> float:
    """Walk from jd in steps while the aspect stays within orb."""
    t, travelled = jd, 0.0
    while travelled < limit and abs(f(t + step)) <= orb:
        t += step
        travelled += abs(step)
    return t


def moon_phase(sun_lon: float, moon_lon: float) -> str:
    e = (moon_lon - sun_lon) % 360
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
             "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    return names[int(((e + 22.5) % 360) // 45)]


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------
class Chart:
    def __init__(self, zodiac: str = "tropical"):
        self.sidereal = zodiac == "sidereal"
        self.flags = FLAGS
        if self.sidereal:
            swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
            self.flags |= swe.FLG_SIDEREAL

    def pos(self, jd: float, body: int):
        xx, _ = swe.calc_ut(jd, body, self.flags)
        return xx[0] % 360.0, xx[3]

    def angles(self, jd: float, lat: float, lon: float):
        # Placidus fails above ~66° latitude; Ascendant/MC don't depend on the house system
        for hsys in (b"P", b"O"):
            try:
                _, ascmc = swe.houses_ex(jd, lat, lon, hsys, self.flags)
                return ascmc[0] % 360.0, ascmc[1] % 360.0
            except Exception:
                continue
        raise ValueError("Could not compute Ascendant for this location")


def compute_natal(chart: Chart, birth_date: date, birth_time: time | None,
                  tz: str, lat: float, lon: float) -> dict:
    time_known = birth_time is not None
    local = datetime.combine(birth_date, birth_time or time(12, 0)).replace(tzinfo=ZoneInfo(tz))
    jd = to_jd(local)

    points, retro = {}, {}
    for name, body in PLANETS.items():
        points[name], speed = chart.pos(jd, body)
        retro[name] = speed < 0 and name != "North Node"
    if time_known:
        points["Ascendant"], points["Midheaven"] = chart.angles(jd, lat, lon)

    return {
        "points": points, "retro": retro, "time_known": time_known,
        "ayanamsa": swe.get_ayanamsa_ut(jd) if chart.sidereal else None,
        "utc": local.astimezone(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Period analysis
# ---------------------------------------------------------------------------
def period_bounds(kind: str, anchor: date, tz: str):
    z = ZoneInfo(tz)
    if kind == "Day":
        start = anchor
        end = anchor + timedelta(days=1)
        label = anchor.strftime("%A, %B %d, %Y")
    elif kind == "Week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=7)
        label = f"Week of {start:%b %d} – {(end - timedelta(days=1)):%b %d, %Y}"
    else:
        start = anchor.replace(day=1)
        days = calendar.monthrange(start.year, start.month)[1]
        end = start + timedelta(days=days)
        label = start.strftime("%B %Y")
    return (datetime.combine(start, time(0)).replace(tzinfo=z),
            datetime.combine(end, time(0)).replace(tzinfo=z), label)


def analyze(chart: Chart, natal: dict, kind: str, start: datetime, end: datetime, tz: str) -> dict:
    cfg = PERIODS[kind]
    jd0, jd1 = to_jd(start), to_jd(end)
    n = max(2, int(round((jd1 - jd0) / cfg["step"])))
    grid = [jd0 + i * (jd1 - jd0) / n for i in range(n + 1)]
    pos = {name: [chart.pos(j, b) for j in grid] for name, b in PLANETS.items()}

    targets = {k: natal["points"][k] for k in PERSONAL_POINTS
               if k in natal["points"] and (natal["time_known"] or k != "Moon")}  # Moon unreliable without birth time
    bodies = [b for b in PLANETS if b != "Moon" or cfg["moon_transits"]]

    # ---- active transits -------------------------------------------------
    influences = []
    for tname in bodies:
        body, orb = PLANETS[tname], ORBS[tname]
        lons = [p[0] for p in pos[tname]]
        for nname, nlon in targets.items():
            for angle, aname in ASPECTS.items():
                if tname == "North Node" and angle not in (0, 180):
                    continue
                for tgt in ((angle,) if angle in (0, 180) else (angle, -angle)):
                    d = [_wrap(l - nlon - tgt) for l in lons]
                    i_min = min(range(len(d)), key=lambda i: abs(d[i]))
                    cross = [i for i in range(len(d) - 1)
                             if (d[i] < 0) != (d[i + 1] < 0) and abs(d[i]) < 20 and abs(d[i + 1]) < 20]
                    if abs(d[i_min]) > orb and not cross:
                        continue

                    f = (lambda jd, b=body, nl=nlon, t=tgt: _wrap(chart.pos(jd, b)[0] - nl - t))
                    exact = [_bisect(f, grid[i], grid[i + 1]) for i in cross]
                    peak = exact[0] if exact else grid[i_min]
                    closeness = 0.0 if exact else abs(d[i_min])
                    wstep = 1 / 24 if tname == "Moon" else 1.0
                    ws = _extend(f, peak, orb, -wstep, WINDOW_LIMIT[tname])
                    we = _extend(f, peak, orb, wstep, WINDOW_LIMIT[tname])
                    tone = CONJ_TONE[tname] if angle == 0 else ASPECT_TONE[angle]
                    retro = chart.pos(peak, body)[1] < 0 and tname != "North Node"
                    natal_label = "natal Node" if nname == "North Node" else nname
                    influences.append({
                        "body": tname, "natal": nname, "area": NATAL_AREAS[nname], "tone": tone,
                        "title": f"{tname}{' (retrograde)' if retro else ''} {aname} your {natal_label}",
                        "meaning": (f"{tname} brings {TRANSIT_THEMES[tname]} to your "
                                    f"{NATAL_AREAS[nname].lower()}. {TONE_PHRASE[tone]}"),
                        "weight": WEIGHTS[tname] * (1 - 0.5 * closeness / orb),
                        "exact": [from_jd(j, tz) for j in exact],
                        "start": from_jd(ws, tz), "end": from_jd(we, tz),
                    })
    influences.sort(key=lambda x: -x["weight"])

    # ---- dated events inside the period ------------------------------------
    events = []
    for inf in influences:
        for when in inf["exact"]:
            events.append({"when": when, "event": f"Exact: {inf['title']}", "meaning": inf["meaning"],
                           "tone": inf["tone"]})

    for name in STATION_BODIES:
        sp = [p[1] for p in pos[name]]
        for i in range(len(sp) - 1):
            if (sp[i] < 0) != (sp[i + 1] < 0):
                jd = _bisect(lambda x, b=PLANETS[name]: chart.pos(x, b)[1], grid[i], grid[i + 1])
                going_retro = sp[i + 1] < 0
                events.append({
                    "when": from_jd(jd, tz), "tone": "neutral",
                    "event": f"{name} turns {'retrograde' if going_retro else 'direct'} at "
                             f"{fmt_pos(chart.pos(jd, PLANETS[name])[0])}",
                    "meaning": (f"Traditionally a time to review and revisit {DOMAINS[name]}; delays are common."
                                if going_retro else
                                f"Traditionally {DOMAINS[name]} start moving forward again."),
                })

    for name in INGRESS_BODIES + (["Moon"] if cfg["moon_ingress"] else []):
        signs = [int(p[0] // 30) for p in pos[name]]
        for i in range(len(signs) - 1):
            if signs[i] != signs[i + 1]:
                a, b, s = grid[i], grid[i + 1], signs[i]
                for _ in range(40):
                    m = (a + b) / 2
                    if int(chart.pos(m, PLANETS[name])[0] // 30) == s:
                        a = m
                    else:
                        b = m
                new_sign = SIGNS[signs[i + 1]]
                events.append({
                    "when": from_jd(b, tz), "tone": "neutral",
                    "event": f"{name} enters {new_sign}",
                    "meaning": f"The tone of {DOMAINS[name]} shifts to {new_sign}: "
                               f"{SIGN_KEYWORDS[new_sign]}.",
                })

    sun_l = [p[0] for p in pos["Sun"]]
    moon_l = [p[0] for p in pos["Moon"]]
    for tgt, lname in ((0, "New Moon"), (180, "Full Moon")):
        d = [_wrap(m - s - tgt) for m, s in zip(moon_l, sun_l)]
        for i in range(len(d) - 1):
            if (d[i] < 0) != (d[i + 1] < 0) and abs(d[i]) < 20 and abs(d[i + 1]) < 20:
                f = lambda jd, t=tgt: _wrap(chart.pos(jd, swe.MOON)[0] - chart.pos(jd, swe.SUN)[0] - t)
                jd = _bisect(f, grid[i], grid[i + 1])
                mlon = chart.pos(jd, swe.MOON)[0]
                meaning = ("Traditionally a time for fresh starts and setting intentions."
                           if tgt == 0 else
                           "Traditionally a time of culmination, release and heightened emotions.")
                hits = [p for p, l in targets.items() if abs(_wrap(mlon - l)) <= 3]
                if hits:
                    meaning += " It lands on your " + ", ".join(hits) + \
                               f", highlighting {', '.join(NATAL_AREAS[h].lower() for h in hits)}."
                events.append({"when": from_jd(jd, tz), "event": f"{lname} in {sign_of(mlon)}",
                               "meaning": meaning, "tone": "neutral"})
    events.sort(key=lambda e: e["when"])

    # ---- summaries ---------------------------------------------------------
    totals = {"supportive": 0.0, "challenging": 0.0, "neutral": 0.0}
    areas = {}
    for inf in influences:
        totals[inf["tone"]] += inf["weight"]
        a = areas.setdefault(inf["area"], {"supportive": 0.0, "challenging": 0.0, "neutral": 0.0})
        a[inf["tone"]] += inf["weight"]

    s, c, total = totals["supportive"], totals["challenging"], sum(totals.values())
    if total < 0.5:
        overall = ("Quiet", "🌤️")
    elif s > 1.5 * c:
        overall = ("Mostly supportive", "🟢")
    elif c > 1.5 * s:
        overall = ("Mostly challenging", "🔴")
    else:
        overall = ("Mixed", "🟡")
    lo, hi = INTENSITY_CUTS[kind]
    intensity = "Low" if total < lo else "Moderate" if total < hi else "High"

    area_rows = []
    for name, t in areas.items():
        sup, chal = t["supportive"], t["challenging"]
        if sup == chal == 0:
            tone = "🟣 spotlight"
        elif sup > 1.5 * chal:
            tone = "🟢 supportive"
        elif chal > 1.5 * sup:
            tone = "🔴 testing"
        else:
            tone = "🟡 mixed"
        area_rows.append({"Life area": name, "Focus": sum(t.values()), "Tone": tone})
    area_rows.sort(key=lambda r: -r["Focus"])
    top_focus = max((r["Focus"] for r in area_rows), default=1) or 1
    for r in area_rows:
        r["Focus"] = round(r["Focus"] / top_focus, 2)

    jd_mid = (jd0 + jd1) / 2
    sky = []
    for name, body in PLANETS.items():
        lon, speed = chart.pos(jd_mid, body)
        sky.append({"Planet": f"{PLANET_ICONS[name]} {name}", "Position": fmt_pos(lon),
                    "Retrograde": "℞" if speed < 0 and name != "North Node" else ""})
    sun_mid, moon_mid = chart.pos(jd_mid, swe.SUN)[0], chart.pos(jd_mid, swe.MOON)[0]

    return {
        "overall": overall, "intensity": intensity, "influences": influences,
        "events": events, "areas": area_rows, "sky": sky,
        "moon": {"sign": sign_of(moon_mid), "phase": moon_phase(sun_mid, moon_mid)},
    }
