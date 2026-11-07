"""
astro_engine.py — shared calculation core for app.py (Western readings live here,
Vedic readings in vedic.py).

Planetary positions come from the Swiss Ephemeris (Moshier mode: no data files
needed, sub-arcsecond planets / few-arcsecond Moon for 3000 BC–3000 AD). Precession
and nutation are included; sidereal charts subtract the chosen ayanamsa.

The interpretations are traditional astrological associations, not validated
predictions.
"""
from __future__ import annotations

import math
import threading
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import swisseph as swe

FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED
KETU = -100  # pseudo body id: mean South Node (mean North Node + 180°)

# The Swiss Ephemeris keeps its sidereal mode (and other state) in C globals, and
# Streamlit serves every visitor on its own thread, so all calls go through one lock.
_SWE = threading.RLock()

AYANAMSAS = {"Lahiri (Chitrapaksha)": swe.SIDM_LAHIRI,
             "Raman": swe.SIDM_RAMAN,
             "Krishnamurti (KP)": swe.SIDM_KRISHNAMURTI}

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

# Transit search. Each body is sampled every SAMPLE_STEP days (small enough that it
# can never pass through an orb between two samples) from HORIZON days before the
# period to HORIZON days after it (long enough to hold a full retrograde triple pass).
SAMPLE_STEP = {"Moon": 1 / 24, "Sun": 0.5, "Mercury": 0.5, "Venus": 0.5, "Mars": 1.0,
               "Jupiter": 1.0, "Saturn": 2.0, "Uranus": 3.0, "Neptune": 3.0, "Pluto": 3.0,
               "North Node": 1.0}
HORIZON = {"Moon": 2, "Sun": 8, "Mercury": 100, "Venus": 160, "Mars": 260, "Jupiter": 420,
           "Saturn": 450, "Uranus": 1500, "Neptune": 1500, "Pluto": 1500, "North Node": 150}

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
    "Eclipse": "turning points: something starts, ends or comes into the open",
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

STATION_BODIES = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
INGRESS_BODIES = ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]

# Intensity = total influence weight per usable natal point, compared with cut points
# for Low / Moderate / High. The cut points are the tertiles measured by
# experiments/calibrate.py over random birth charts and dates; for other period
# lengths they are interpolated on log(days).
# (150 charts: per-point tertiles agree within ~5% with and without a birth time,
# whereas raw totals were ~35% lower without one.)
INTENSITY_CUTS = {1: (1.23, 1.62), 7: (1.59, 2.09), 30: (3.98, 4.60),
                  91: (9.61, 10.94), 182: (18.44, 20.15), 365: (35.04, 37.11)}

UNKNOWN_WINDOW = 12 * 60   # minutes either side of noon when the birth time is unknown
KEEP_SPREAD = 2.0          # a natal point that moves less than this across the possible
                           # birth-time window is used for timing as is;
WIDEN_SPREAD = 4.0         # up to this, it is used with the orb widened by half its spread
                           # (e.g. fast Mercury with an unknown time); beyond, it is left out
MAX_RANGE_DAYS = 366
NAK = 360 / 27             # one nakshatra, 13°20′


class BirthDataError(ValueError):
    """The birth details contradict each other (e.g. a stated Moon sign that the Moon
    never occupied during the possible birth-time window)."""


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
    lon %= 360.0
    total = int(round(lon * 60))            # whole arcminutes, rounded
    sign, deg, minute = (total // 1800) % 12, (total % 1800) // 60, total % 60
    return f"{deg}°{minute:02d}′ {SIGNS[sign]}"


def fmt_offset(td: timedelta) -> str:
    s = int(round(td.total_seconds()))
    sign, s = ("+" if s >= 0 else "−"), abs(s)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"UTC{sign}{h}:{m:02d}" + (f":{sec:02d}" if sec else "")


def _wrap(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


def _bisect(f, a: float, b: float, iters: int = 40) -> float:
    """Root of f in [a, b], given that f changes sign there."""
    fa = f(a)
    for _ in range(iters):
        m = (a + b) / 2
        fm = f(m)
        if (fa < 0) == (fm < 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


def _bisect_bool(f, a: float, b: float, iters: int = 40) -> float:
    """Point where boolean f flips between a and b."""
    fa = f(a)
    for _ in range(iters):
        m = (a + b) / 2
        if f(m) == fa:
            a = m
        else:
            b = m
    return b


def moon_phase(sun_lon: float, moon_lon: float) -> str:
    e = (moon_lon - sun_lon) % 360
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
             "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"]
    return names[int(((e + 22.5) % 360) // 45)]


def period_config(days: float) -> dict:
    """Sampling rules by period length. The Moon changes sign every ~2.5 days, so its
    transits and sign changes are only listed for short periods."""
    if days <= 3:
        return {"step": 1 / 24, "moon_transits": True, "moon_ingress": True}
    if days <= 14:
        return {"step": 0.25, "moon_transits": False, "moon_ingress": True}
    return {"step": 1.0, "moon_transits": False, "moon_ingress": False}


def intensity_cuts(days: float) -> tuple[float, float]:
    keys = sorted(INTENSITY_CUTS)
    days = min(max(days, keys[0]), keys[-1])
    for a, b in zip(keys, keys[1:]):
        if a <= days <= b:
            w = (math.log(days) - math.log(a)) / (math.log(b) - math.log(a))
            return tuple(INTENSITY_CUTS[a][k] + w * (INTENSITY_CUTS[b][k] - INTENSITY_CUTS[a][k]) for k in (0, 1))
    return INTENSITY_CUTS[keys[-1]]


# ---------------------------------------------------------------------------
# Chart (ephemeris access)
# ---------------------------------------------------------------------------
class Chart:
    def __init__(self, zodiac: str = "tropical", ayanamsa: str = "Lahiri (Chitrapaksha)"):
        self.sidereal = zodiac == "sidereal"
        self.ayanamsa_name = ayanamsa if self.sidereal else None
        self.sid_mode = AYANAMSAS[ayanamsa] if self.sidereal else None
        self.flags = FLAGS | (swe.FLG_SIDEREAL if self.sidereal else 0)

    def _prep(self):
        if self.sidereal:
            swe.set_sid_mode(self.sid_mode, 0, 0)

    def pos(self, jd: float, body: int):
        """(longitude, speed in °/day) in this chart's zodiac."""
        if body == KETU:
            lon, speed = self.pos(jd, swe.MEAN_NODE)
            return (lon + 180.0) % 360.0, speed
        with _SWE:
            self._prep()
            xx, _ = swe.calc_ut(jd, body, self.flags)
        return xx[0] % 360.0, xx[3]

    def ayanamsa(self, jd: float) -> float | None:
        """The ayanamsa actually applied to positions (true, i.e. including nutation)."""
        if not self.sidereal:
            return None
        with _SWE:
            self._prep()
            return swe.get_ayanamsa_ex_ut(jd, self.flags)[1]

    def angles(self, jd: float, lat: float, lon: float):
        # Placidus fails inside the polar circles; Ascendant/MC don't depend on the house system
        with _SWE:
            self._prep()
            for hsys in (b"P", b"O"):
                try:
                    _, ascmc = swe.houses_ex(jd, lat, lon, hsys, self.flags)
                    return ascmc[0] % 360.0, ascmc[1] % 360.0
                except Exception:
                    continue
        raise ValueError("Could not compute Ascendant for this location")


# ---------------------------------------------------------------------------
# Birth clock: local clock time -> UTC, with checks for old dates
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _tz_metadata():
    """(links, zone_tab, zone1970) from the IANA database files, if available."""
    def read(name):
        try:
            import importlib.resources as ir
            return (ir.files("tzdata") / "zoneinfo" / name).read_text(encoding="utf-8")
        except Exception:
            for base in ("/usr/share/zoneinfo", "/usr/lib/zoneinfo", "/usr/share/lib/zoneinfo"):
                try:
                    with open(f"{base}/{name}", encoding="utf-8") as fh:
                        return fh.read()
                except OSError:
                    continue
        return ""

    links = {}
    for line in read("tzdata.zi").splitlines():
        if line.startswith("L "):
            parts = line.split()
            if len(parts) >= 3:
                links[parts[2]] = parts[1]

    def zones(text):
        return {ln.split("\t")[2] for ln in text.splitlines()
                if ln and not ln.startswith("#") and len(ln.split("\t")) > 2}
    return links, zones(read("zone.tab")), zones(read("zone1970.tab"))


def zone_history_note(tz: str) -> str | None:
    links, zone_tab, zone1970 = _tz_metadata()
    target = links.get(tz)
    if target and tz in zone_tab and tz not in zone1970:
        return (f"The time zone database keeps no separate history for {tz}: before 1970 it "
                f"copies the clock rules of {target}, which may not match what clocks there "
                f"actually showed.")
    return None


def _is_mean_time(abbr: str) -> bool:
    return abbr == "LMT" or (abbr.endswith("MT") and abbr != "GMT")


def lmt_offset(lon: float) -> timedelta:
    """Local Mean Time: 4 minutes of clock time per degree of longitude."""
    return timedelta(seconds=round(lon * 240))


# Cities that kept their own clock time after India adopted IST (1906). The time zone
# database only records Asia/Kolkata (IST from 1906), and its own notes say Calcutta,
# Bombay and Karachi kept local time for civil use without giving dates. Offsets and end
# years: Wikipedia "Time in India" (Bombay Time UTC+4:51 until 1955; Calcutta Time
# UTC+5:53:20 until 1948). Exact switch-over dates and whether these cities also used
# 1942–45 War Time are undocumented, so those dates are flagged for the user to check.
REGIONAL_CLOCKS = [
    {"name": "Bombay Time", "lat": 18.94, "lon": 72.84, "radius_km": 40,
     "offset": timedelta(hours=4, minutes=51), "start": date(1884, 1, 1), "end": date(1955, 12, 31),
     "check_from": date(1955, 1, 1)},
    {"name": "Calcutta Time", "lat": 22.57, "lon": 88.36, "radius_km": 40,
     "offset": timedelta(hours=5, minutes=53, seconds=20), "start": date(1884, 1, 1), "end": date(1948, 12, 31),
     "check_from": date(1948, 1, 1)},
]
WAR_TIME_INDIA = (date(1942, 9, 1), date(1945, 10, 15))


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def regional_clock(birth_date: date, lat: float | None, lon: float) -> dict | None:
    if lat is None:
        return None
    for rc in REGIONAL_CLOCKS:
        if rc["start"] <= birth_date <= rc["end"] and _km(lat, lon, rc["lat"], rc["lon"]) <= rc["radius_km"]:
            notes = []
            if birth_date >= rc["check_from"]:
                notes.append(f"{rc['name']} was given up during {rc['check_from'].year}; the exact date isn't "
                              f"documented, so check whether the record uses it or IST")
            if WAR_TIME_INDIA[0] <= birth_date <= WAR_TIME_INDIA[1]:
                notes.append("India was on War Time (IST + 1 h) from Sep 1942 to Oct 1945; whether local "
                             f"{rc['name']} clocks were also put forward isn't documented")
            return {"name": rc["name"], "offset": rc["offset"], "notes": notes}
    return None


def check_birth_clock(birth_date: date, birth_time: time | None, tz: str, lon: float,
                      lat: float | None = None) -> dict:
    """What the time zone database says about a local birth time, and alternatives."""
    z = ZoneInfo(tz)
    naive = datetime.combine(birth_date, birth_time or time(12, 0))
    a, b = naive.replace(tzinfo=z, fold=0), naive.replace(tzinfo=z, fold=1)
    nonexistent = a.astimezone(timezone.utc).astimezone(z).replace(tzinfo=None) != naive
    ambiguous = not nonexistent and a.utcoffset() != b.utcoffset()
    abbr = a.tzname() or ""
    lmt = lmt_offset(lon)
    regional = regional_clock(birth_date, lat, lon)
    return {
        "db_offset": a.utcoffset(), "db_offset_alt": b.utcoffset() if ambiguous else None,
        "abbr": abbr, "abbr_alt": b.tzname() if ambiguous else None,
        "mean_time": _is_mean_time(abbr), "lmt_offset": lmt,
        "gap_minutes": (a.utcoffset() - lmt).total_seconds() / 60,
        "pre1970": birth_date.year < 1970, "nonexistent": nonexistent, "ambiguous": ambiguous,
        "zone_note": zone_history_note(tz), "regional": regional,
        "default": "regional" if regional else "lmt" if _is_mean_time(abbr) else "db",
    }


# ---------------------------------------------------------------------------
# Birth chart (with birth-time uncertainty)
# ---------------------------------------------------------------------------
def _matches(chart: Chart, x: float, lat: float, lon: float, c: dict) -> bool:
    """Does moment x agree with what the person says they know about their chart?"""
    if c.keys() & {"moon_sign", "nakshatra", "pada"}:
        m = chart.pos(x, swe.MOON)[0]
        if "moon_sign" in c and int(m // 30) != c["moon_sign"]:
            return False
        if "nakshatra" in c and int(m // NAK) % 27 != c["nakshatra"]:
            return False
        if "pada" in c and int(m // (NAK / 4)) % 108 != c["pada"]:
            return False
    if "lagna_sign" in c and int(chart.angles(x, lat, lon)[0] // 30) != c["lagna_sign"]:
        return False
    return True


def allowed_intervals(chart: Chart, jd_a: float, jd_b: float, lat: float, lon: float,
                      constraints: dict) -> list[tuple[float, float]]:
    """Parts of [jd_a, jd_b] that agree with the constraints (checked every minute,
    edges refined by bisection)."""
    ok = lambda x: _matches(chart, x, lat, lon, constraints)
    n = max(2, math.ceil((jd_b - jd_a) * 1440))
    grid = [jd_a + i * (jd_b - jd_a) / n for i in range(n + 1)]
    flags = [ok(x) for x in grid]
    out, i = [], 0
    while i <= n:
        if flags[i]:
            j = i
            while j < n and flags[j + 1]:
                j += 1
            # _bisect_bool returns the first point past the flip; step back a hair (~0.1 s)
            # at the end so the interval's last moment still satisfies the constraints
            a = grid[i] if i == 0 else _bisect_bool(ok, grid[i - 1], grid[i])
            b = grid[j] if j == n else _bisect_bool(ok, grid[j], grid[j + 1]) - 1e-6
            out.append((a, b))
            i = j + 1
        else:
            i += 1
    return out


def compute_natal(chart: Chart, planets: dict, birth_date: date, birth_time: time | None,
                  window_min: float, utc_offset: timedelta, lat: float, lon: float,
                  constraints: dict | None = None) -> dict:
    """Birth chart. `birth_time=None` means unknown (noon, ±12 h). `window_min` is how far
    the recorded time could be off. `constraints` holds what the person already knows
    (moon_sign / lagna_sign as 0–11, nakshatra 0–26, pada 0–107, in this chart's zodiac):
    only the parts of the window that agree with it are kept.

    Every point is sampled across the remaining window so we know how far it could have
    moved, which signs it could be in, and whether it is precise enough to time with."""
    if birth_time is None:
        birth_time, window_min = time(12, 0), UNKNOWN_WINDOW
    utc = (datetime.combine(birth_date, birth_time) - utc_offset).replace(tzinfo=timezone.utc)
    jd = to_jd(utc)
    w = window_min / 1440
    c = {k: v for k, v in (constraints or {}).items() if v is not None}
    if not c:
        intervals = [(jd - w, jd + w)]
    elif window_min == 0:
        if not _matches(chart, jd, lat, lon, c):
            raise BirthDataError("The birth time you entered doesn't agree with what you said you know about "
                                 "your chart. Check the time, the 'I already know' choices, or the ayanamsa.")
        intervals = [(jd, jd)]
    else:
        intervals = allowed_intervals(chart, jd - w, jd + w, lat, lon, c)
        if not intervals:
            m_signs = []
            for x in (jd - w, jd, jd + w):
                s_ = sign_of(chart.pos(x, swe.MOON)[0])
                if s_ not in m_signs:
                    m_signs.append(s_)
            raise BirthDataError(
                "At no time in the possible birth-time window does the chart match what you said you know "
                f"(that day the Moon was in {' and then '.join(m_signs)} in this zodiac). Check the date, the "
                "'I already know' choices, or the ayanamsa.")
    a, b = max(intervals, key=lambda iv: iv[1] - iv[0])
    jd_c = (a + b) / 2
    span = intervals[-1][1] - intervals[0][0]
    want_angles = span < 0.99 or "lagna_sign" in c

    def all_points(j):
        p = {name: chart.pos(j, body) for name, body in planets.items()}
        if want_angles:
            asc, mc = chart.angles(j, lat, lon)
            p["Ascendant"], p["Midheaven"] = (asc, 0.0), (mc, 0.0)
        return p

    center = all_points(jd_c)
    groups = []
    for a, b in intervals:
        n = max(2, math.ceil((b - a) * 1440 / 20)) if b > a else 0   # every ≤20 min
        groups.append([all_points(a + (b - a) * i / n) for i in range(n + 1)] if n else [all_points(a)])

    points, retro, spread, signs, rng, widened = {}, {}, {}, {}, {}, {}
    for name, (lon_, speed) in center.items():
        paths = [[r[name][0] for r in g] for g in groups]
        flat = [x for p in paths for x in p]
        spread[name] = sum(abs(_wrap(y - x)) for x, y in zip(flat, flat[1:]))
        seen = []
        for x in flat:
            if sign_of(x) not in seen:
                seen.append(sign_of(x))
        points[name], retro[name], signs[name], rng[name] = lon_, speed < 0, seen, (flat[0], flat[-1])
        if KEEP_SPREAD < spread[name] <= WIDEN_SPREAD:
            direction = 1 if _wrap(flat[-1] - flat[0]) >= 0 else -1
            widened[name] = ((flat[0] + direction * spread[name] / 2) % 360, spread[name] / 2)

    jd_lo, jd_hi = intervals[0][0], intervals[-1][1]
    return {
        "points": points, "retro": retro, "spread": spread, "signs": signs, "range": rng,
        "usable": {k for k in points if spread[k] <= KEEP_SPREAD}, "widened": widened,
        "window": window_min, "time_known": window_min == 0, "jd": jd_c,
        "jd_range": (jd_lo, jd_hi), "intervals": intervals, "constrained": bool(c),
        "half_window": (jd_hi - jd_lo) / 2 * 1440,
        "utc": (datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jd_c - 2451545.0)),
        "utc_offset": utc_offset,
        "ayanamsa": chart.ayanamsa(jd_c), "ayanamsa_name": chart.ayanamsa_name,
    }


def compare_zodiacs(natal_utc: datetime, lat: float, lon: float, ayanamsa: str,
                    with_angles: bool) -> list[dict]:
    """The same birth moment in both zodiacs — which placements change sign."""
    jd = to_jd(natal_utc)
    trop, sid = Chart("tropical"), Chart("sidereal", ayanamsa)
    rows = []
    names = list(PLANETS) + (["Ascendant"] if with_angles else [])
    for name in names:
        if name == "Ascendant":
            t, s = trop.angles(jd, lat, lon)[0], sid.angles(jd, lat, lon)[0]
        else:
            t, s = trop.pos(jd, PLANETS[name])[0], sid.pos(jd, PLANETS[name])[0]
        rows.append({"Point": name, "Tropical": fmt_pos(t), "Sidereal": fmt_pos(s),
                     "Changes sign": "yes" if sign_of(t) != sign_of(s) else ""})
    return rows


# ---------------------------------------------------------------------------
# Transit search
# ---------------------------------------------------------------------------
class SkyTable:
    """One body's positions on a regular grid, plus its stations."""

    def __init__(self, chart: Chart, body: int, jd_a: float, jd_b: float, step: float):
        n = max(2, math.ceil((jd_b - jd_a) / step))
        self.chart, self.body = chart, body
        self.t = [jd_a + i * (jd_b - jd_a) / n for i in range(n + 1)]
        p = [chart.pos(x, body) for x in self.t]
        self.lon = [q[0] for q in p]
        self.speed = [q[1] for q in p]
        self.stations = [
            _bisect(lambda x: chart.pos(x, body)[1], self.t[i], self.t[i + 1])
            for i in range(n) if (self.speed[i] < 0) != (self.speed[i + 1] < 0)
        ]


def find_episodes(table: SkyTable, target: float, orb: float, jd0: float, jd1: float) -> list[dict]:
    """Every transit 'series' of table.body to the point `target` that is within orb at some
    moment of [jd0, jd1]. Passes separated by a retrograde station are one series (the
    classic direct–retrograde–direct triple pass), so the dates cover the whole run."""
    chart, body, t = table.chart, table.body, table.t
    d = [_wrap(x - target) for x in table.lon]
    n = len(d)

    def f(x):
        return _wrap(chart.pos(x, body)[0] - target)

    def g(x):
        return abs(f(x)) - orb

    runs, i = [], 0
    while i < n:
        if abs(d[i]) <= orb:
            j = i
            while j + 1 < n and abs(d[j + 1]) <= orb:
                j += 1
            runs.append([i, j])
            i = j + 1
        else:
            i += 1

    series = []
    for r in runs:
        if series and any(t[series[-1][-1][1]] < s < t[r[0]] for s in table.stations):
            series[-1].append(r)
        else:
            series.append([r])

    out = []
    for runs_ in series:
        passes = []
        for i, j in runs_:
            a = t[i] if i == 0 else _bisect(g, t[i - 1], t[i])
            b = t[j] if j == n - 1 else _bisect(g, t[j], t[j + 1])
            passes.append((a, b))
        start, end = passes[0][0], passes[-1][1]
        if end < jd0 or start > jd1:
            continue
        i0, j1 = runs_[0][0], runs_[-1][1]
        exact = [_bisect(f, t[k], t[k + 1]) for k in range(max(i0 - 1, 0), min(j1 + 1, n - 1))
                 if (d[k] < 0) != (d[k + 1] < 0) and abs(d[k]) < 20 and abs(d[k + 1]) < 20]
        # Closest approach inside the period: at its ends, at an exact hit or at a station
        lo, hi = max(start, jd0), min(end, jd1)
        cands = [lo, hi] + [x for x in exact + table.stations if lo <= x <= hi]
        peak = min(cands, key=lambda x: abs(f(x)))
        closeness = abs(f(peak))
        if closeness > orb:          # the period falls between two passes
            continue
        out.append({"start": start, "end": end, "passes": passes, "exact": exact,
                    "peak": peak, "closeness": closeness,
                    "open_start": runs_[0][0] == 0, "open_end": runs_[-1][1] == n - 1})
    return out


# ---------------------------------------------------------------------------
# Events shared by both systems
# ---------------------------------------------------------------------------
def make_grid(jd0: float, jd1: float, step: float) -> list[float]:
    n = max(2, int(round((jd1 - jd0) / step)))
    return [jd0 + i * (jd1 - jd0) / n for i in range(n + 1)]


def find_ingresses(chart: Chart, body: int, grid: list[float], segment: float = 30.0) -> list[tuple]:
    """(jd, new_index, retrograde) whenever the body crosses a `segment`-degree boundary
    (30° for signs, 13°20′ for nakshatras)."""
    idx = [int(chart.pos(x, body)[0] // segment) for x in grid]
    out = []
    for i in range(len(idx) - 1):
        if idx[i] != idx[i + 1]:
            jd = _bisect_bool(lambda x, s=idx[i]: int(chart.pos(x, body)[0] // segment) == s,
                              grid[i], grid[i + 1])
            out.append((jd, idx[i + 1], chart.pos(jd, body)[1] < 0))
    return out


def find_lunations(chart: Chart, grid: list[float]) -> list[tuple]:
    """(jd, 'New Moon' | 'Full Moon', moon_longitude)."""
    sun = [chart.pos(x, swe.SUN)[0] for x in grid]
    moon = [chart.pos(x, swe.MOON)[0] for x in grid]
    out = []
    for tgt, name in ((0, "New Moon"), (180, "Full Moon")):
        d = [_wrap(m - s - tgt) for m, s in zip(moon, sun)]
        for i in range(len(d) - 1):
            if (d[i] < 0) != (d[i + 1] < 0) and abs(d[i]) < 20 and abs(d[i + 1]) < 20:
                f = (lambda x, t=tgt: _wrap(chart.pos(x, swe.MOON)[0] - chart.pos(x, swe.SUN)[0] - t))
                jd = _bisect(f, grid[i], grid[i + 1])
                out.append((jd, name, chart.pos(jd, swe.MOON)[0]))
    return sorted(out)


SOLAR_TYPES = [(swe.ECL_ANNULAR_TOTAL, "Hybrid"), (swe.ECL_TOTAL, "Total"),
               (swe.ECL_ANNULAR, "Annular"), (swe.ECL_PARTIAL, "Partial")]
LUNAR_TYPES = [(swe.ECL_TOTAL, "Total"), (swe.ECL_PARTIAL, "Partial"), (swe.ECL_PENUMBRAL, "Penumbral")]


def find_eclipses(chart: Chart, jd0: float, jd1: float) -> list[dict]:
    """Solar and lunar eclipses with maximum inside [jd0, jd1]."""
    out = []
    for kind, finder, types, body in (("Solar", swe.sol_eclipse_when_glob, SOLAR_TYPES, swe.SUN),
                                      ("Lunar", swe.lun_eclipse_when, LUNAR_TYPES, swe.MOON)):
        t = jd0
        while True:
            with _SWE:
                ret, tret = finder(t, swe.FLG_MOSEPH, 0, False)
            jd = tret[0]
            if jd > jd1:
                break
            lon = chart.pos(jd, body)[0]
            node = chart.pos(jd, swe.MEAN_NODE)[0]
            # the eclipsed body (Sun for solar, Moon for lunar) sits near one of the nodes
            near = "North Node (Rahu)" if abs(_wrap(lon - node)) < 90 else "South Node (Ketu)"
            out.append({"kind": kind, "type": next((n for flag, n in types if ret & flag), "Partial"),
                        "jd": jd, "lon": lon, "near_node": near})
            t = jd + 20
    return sorted(out, key=lambda e: e["jd"])


ECLIPSE_ORB = 3.0
ECLIPSE_WEIGHT = {"Total": 2.5, "Hybrid": 2.5, "Annular": 2.0, "Partial": 1.5, "Penumbral": 0.75}


# ---------------------------------------------------------------------------
# Western period analysis
# ---------------------------------------------------------------------------
def period_bounds(kind: str, anchor: date, tz: str, end_date: date | None = None):
    """kind: Day | Week | Month | Custom (anchor = first day, end_date = last day, inclusive)."""
    import calendar
    z = ZoneInfo(tz)
    if kind == "Day":
        start, end = anchor, anchor + timedelta(days=1)
        label = anchor.strftime("%A, %B %d, %Y")
    elif kind == "Week":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=7)
        label = f"Week of {start:%b %d} – {(end - timedelta(days=1)):%b %d, %Y}"
    elif kind == "Month":
        start = anchor.replace(day=1)
        end = start + timedelta(days=calendar.monthrange(start.year, start.month)[1])
        label = start.strftime("%B %Y")
    else:
        start, end = anchor, (end_date or anchor) + timedelta(days=1)
        if (end - start).days > MAX_RANGE_DAYS:
            raise ValueError(f"Please pick a range of at most {MAX_RANGE_DAYS} days.")
        label = f"{start:%b %d, %Y} – {(end - timedelta(days=1)):%b %d, %Y}"
    return (datetime.combine(start, time(0)).replace(tzinfo=z),
            datetime.combine(end, time(0)).replace(tzinfo=z), label)


def analyze(chart: Chart, natal: dict, start: datetime, end: datetime, tz: str) -> dict:
    jd0, jd1 = to_jd(start), to_jd(end)
    days = jd1 - jd0
    cfg = period_config(days)
    grid = make_grid(jd0, jd1, cfg["step"])

    # natal point -> (longitude, extra orb). Points whose position is a little uncertain
    # (fast Mercury with an unknown birth time, say) keep a widened orb instead of being dropped.
    targets = {}
    for k in PERSONAL_POINTS:
        if k in natal["usable"]:
            targets[k] = (natal["points"][k], 0.0)
        elif k in natal.get("widened", {}):
            targets[k] = natal["widened"][k]
    bodies = [b for b in PLANETS if b != "Moon" or cfg["moon_transits"]]
    tables = {b: SkyTable(chart, PLANETS[b], jd0 - HORIZON[b], jd1 + HORIZON[b], SAMPLE_STEP[b])
              for b in bodies}

    # ---- active transits -------------------------------------------------
    influences = []
    for tname in bodies:
        for nname, (nlon, extra) in targets.items():
            orb = ORBS[tname] + extra
            approx = (f" Exact dates are approximate: your birth time leaves natal {nname} somewhere in a "
                      f"{2 * extra:.1f}° span." if extra else "")
            for angle, aname in ASPECTS.items():
                if tname == "North Node" and angle not in (0, 180):
                    continue
                for tgt in ((angle,) if angle in (0, 180) else (angle, -angle)):
                    for ep in find_episodes(tables[tname], (nlon + tgt) % 360, orb, jd0, jd1):
                        tone = CONJ_TONE[tname] if angle == 0 else ASPECT_TONE[angle]
                        retro = chart.pos(ep["peak"], PLANETS[tname])[1] < 0 and tname != "North Node"
                        influences.append({
                            "body": tname, "natal": nname, "area": NATAL_AREAS[nname], "tone": tone,
                            "title": f"{tname}{' (retrograde)' if retro else ''} {aname} your {nname}",
                            "meaning": (f"{tname} brings {TRANSIT_THEMES[tname]} to your "
                                        f"{NATAL_AREAS[nname].lower()}. {TONE_PHRASE[tone]}{approx}"),
                            "approx": bool(extra),
                            "weight": WEIGHTS[tname] * (1 - 0.5 * ep["closeness"] / orb),
                            "exact": [from_jd(j, tz) for j in ep["exact"]],
                            "exact_in_period": [from_jd(j, tz) for j in ep["exact"] if jd0 <= j < jd1],
                            "passes": [(from_jd(a, tz), from_jd(b, tz)) for a, b in ep["passes"]],
                            "start": from_jd(ep["start"], tz), "end": from_jd(ep["end"], tz),
                            "open_start": ep["open_start"], "open_end": ep["open_end"],
                        })

    # ---- eclipses ----------------------------------------------------------
    eclipses = find_eclipses(chart, jd0, jd1)
    for ec in eclipses:
        ec["when"] = from_jd(ec["jd"], tz)
        ec["hits"] = []
        for nname, (nlon, extra) in targets.items():
            for tgt, aname in ((0, "on"), (180, "opposite")):
                sep = abs(_wrap(ec["lon"] - nlon - tgt))
                if sep <= ECLIPSE_ORB + extra:
                    ec["hits"].append(nname)
                    influences.append({
                        "body": "Eclipse", "natal": nname, "area": NATAL_AREAS[nname], "tone": "neutral",
                        "title": f"{ec['type']} {ec['kind'].lower()} eclipse {aname} your {nname}",
                        "meaning": (f"Eclipses traditionally mark {TRANSIT_THEMES['Eclipse']}; this one "
                                    f"falls on your {NATAL_AREAS[nname].lower()}, and is said to be felt "
                                    f"for weeks to months around the date."),
                        "weight": ECLIPSE_WEIGHT[ec["type"]] * (1 - 0.5 * sep / (ECLIPSE_ORB + extra)),
                        "approx": bool(extra),
                        "exact": [ec["when"]], "exact_in_period": [ec["when"]],
                        "passes": [(ec["when"], ec["when"])],
                        "start": ec["when"], "end": ec["when"], "open_start": False, "open_end": False,
                    })
    influences.sort(key=lambda x: -x["weight"])

    # ---- dated events inside the period ------------------------------------
    events = []
    for inf in influences:
        if inf["body"] == "Eclipse":
            continue
        for when in inf["exact_in_period"]:
            events.append({"when": when, "event": f"Exact: {inf['title']}", "meaning": inf["meaning"],
                           "tone": inf["tone"]})

    for name in STATION_BODIES:
        for jd in tables[name].stations:
            if not jd0 <= jd < jd1:
                continue
            going_retro = chart.pos(jd + 0.5, PLANETS[name])[1] < 0
            events.append({
                "when": from_jd(jd, tz), "tone": "neutral",
                "event": f"{name} turns {'retrograde' if going_retro else 'direct'} at "
                         f"{fmt_pos(chart.pos(jd, PLANETS[name])[0])}",
                "meaning": (f"Traditionally a time to review and revisit {DOMAINS[name]}; delays are common."
                            if going_retro else
                            f"Traditionally {DOMAINS[name]} start moving forward again."),
            })

    for name in INGRESS_BODIES + (["Moon"] if cfg["moon_ingress"] else []):
        for jd, s, retro in find_ingresses(chart, PLANETS[name], grid):
            new_sign = SIGNS[s % 12]
            verb = f"re-enters {new_sign} (retrograde)" if retro else f"enters {new_sign}"
            events.append({
                "when": from_jd(jd, tz), "tone": "neutral", "event": f"{name} {verb}",
                "meaning": f"The tone of {DOMAINS[name]} shifts to {new_sign}: {SIGN_KEYWORDS[new_sign]}.",
            })

    for jd, lname, mlon in find_lunations(chart, grid):
        meaning = ("Traditionally a time for fresh starts and setting intentions."
                   if lname == "New Moon" else
                   "Traditionally a time of culmination, release and heightened emotions.")
        hits = [p for p, (l, extra) in targets.items() if abs(_wrap(mlon - l)) <= 3 + extra]
        if hits:
            meaning += " It lands on your " + ", ".join(hits) + \
                       f", highlighting {', '.join(NATAL_AREAS[h].lower() for h in hits)}."
        events.append({"when": from_jd(jd, tz), "event": f"{lname} in {sign_of(mlon)}",
                       "meaning": meaning, "tone": "neutral"})

    for ec in eclipses:
        hit = f" It falls on your {', '.join(ec['hits'])}." if ec["hits"] else " It doesn't touch your personal points."
        events.append({"when": ec["when"], "tone": "neutral",
                       "event": f"{ec['type']} {ec['kind'].lower()} eclipse at {fmt_pos(ec['lon'])}",
                       "meaning": f"Near the {ec['near_node']}. Eclipses are traditionally turning points.{hit}"})
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
        overall = "Quiet"
    elif s > 1.5 * c:
        overall = "Mostly supportive"
    elif c > 1.5 * s:
        overall = "Mostly challenging"
    else:
        overall = "Mixed"
    per_point = total / max(len(targets), 1)
    lo, hi = intensity_cuts(days)
    intensity = "Low" if per_point < lo else "Moderate" if per_point < hi else "High"

    area_rows = []
    for name, t in areas.items():
        sup, chal = t["supportive"], t["challenging"]
        if sup == chal == 0:
            tone = "spotlight"
        elif sup > 1.5 * chal:
            tone = "supportive"
        elif chal > 1.5 * sup:
            tone = "testing"
        else:
            tone = "mixed"
        area_rows.append({"Life area": name, "Focus": sum(t.values()), "Tone": tone})
    area_rows.sort(key=lambda r: -r["Focus"])
    top_focus = max((r["Focus"] for r in area_rows), default=1) or 1
    for r in area_rows:
        r["Focus"] = round(r["Focus"] / top_focus, 2)

    jd_mid = (jd0 + jd1) / 2
    sky = []
    for name, body in PLANETS.items():
        lon, speed = chart.pos(jd_mid, body)
        sky.append({"Planet": name, "Position": fmt_pos(lon),
                    "Retrograde": "R" if speed < 0 and name != "North Node" else ""})
    sun_mid, moon_mid = chart.pos(jd_mid, swe.SUN)[0], chart.pos(jd_mid, swe.MOON)[0]

    return {
        "overall": overall, "intensity": intensity, "per_point": per_point,
        "influences": influences, "events": events, "areas": area_rows, "sky": sky,
        "eclipses": eclipses, "targets": list(targets), "days": days,
        "moon": {"sign": sign_of(moon_mid), "phase": moon_phase(sun_mid, moon_mid)} if days <= 1.5 else None,
    }
