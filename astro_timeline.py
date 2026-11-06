"""
astro_timeline.py — natal chart + transit timeline with traditional interpretations.

Computes (via Swiss Ephemeris, precession & nutation included):
  * natal positions (tropical or sidereal), Ascendant, Midheaven
  * exact transit dates: slow planets aspecting natal points (handles retrograde re-passes)
  * retrograde / direct stations
  * sign ingresses
and attaches the traditional astrological theme for each event from a rule table.

The interpretations are what astrological tradition associates with each
configuration — not empirically validated predictions.

Usage:
  pip install pyswisseph
  python astro_timeline.py --birth "1990-06-15 14:30" --tz America/New_York \
      --lat 40.71 --lon -74.01 --start 2026-01-01 --end 2027-12-31 \
      [--zodiac tropical|sidereal] [--ayanamsa lahiri|fagan_bradley|krishnamurti|raman] \
      [--orb 1.0] [--csv out.csv]
"""
import argparse
import csv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

# Moshier ephemeris needs no data files (~1 arcsec accuracy, 3000 BC–3000 AD).
# For full Swiss Ephemeris precision, download the .se1 files, call
# swe.set_ephe_path(path) and use swe.FLG_SWIEPH instead.
BASE_FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra",
         "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

PLANETS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY, "Venus": swe.VENUS,
    "Mars": swe.MARS, "Jupiter": swe.JUPITER, "Saturn": swe.SATURN,
    "Uranus": swe.URANUS, "Neptune": swe.NEPTUNE, "Pluto": swe.PLUTO,
    "North Node": swe.TRUE_NODE,
}
# Transiting bodies scanned for transits (fast ones like the Moon produce noise).
TRANSITING = ["Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto", "North Node"]
STATION_BODIES = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]

AYANAMSAS = {
    "lahiri": swe.SIDM_LAHIRI,
    "fagan_bradley": swe.SIDM_FAGAN_BRADLEY,
    "krishnamurti": swe.SIDM_KRISHNAMURTI,
    "raman": swe.SIDM_RAMAN,
}

ASPECTS = {  # angle: (name, tone)
    0: ("conjunct", "intensified, direct"),
    60: ("sextile", "opportunity, easy"),
    90: ("square", "friction, challenge"),
    120: ("trine", "flowing, supportive"),
    180: ("opposite", "tension with others, polarisation"),
}

# ---- Rule table: traditional themes (edit / extend freely) -------------------
TRANSIT_THEMES = {
    "Mars": "energy, drive, conflict, haste, physical activity",
    "Jupiter": "expansion, opportunity, growth, optimism, excess",
    "Saturn": "pressure, responsibility, delays, tests, restructuring",
    "Uranus": "sudden change, disruption, breakthroughs, independence",
    "Neptune": "confusion, idealism, dissolving boundaries, inspiration",
    "Pluto": "deep transformation, power dynamics, endings and rebirth",
    "North Node": "fated encounters, direction-setting, karmic themes",
}
NATAL_AREAS = {
    "Sun": "identity, vitality, purpose",
    "Moon": "emotions, home, family",
    "Mercury": "communication, thinking, contracts, travel",
    "Venus": "relationships, love, money, values",
    "Mars": "ambition, assertiveness, conflict",
    "Jupiter": "beliefs, luck, growth",
    "Saturn": "duty, structure, long-term commitments",
    "Uranus": "freedom, innovation",
    "Neptune": "dreams, spirituality",
    "Pluto": "control, intensity",
    "North Node": "life direction",
    "Ascendant": "body, self-presentation, new beginnings",
    "Midheaven": "career, reputation, public life",
}
STATION_THEMES = {
    "R": "themes of {p} turn inward — review, revisiting, delays",
    "D": "themes of {p} move forward again — resumption, clarity",
}
PLANET_DOMAINS = {
    "Mercury": "communication & plans", "Venus": "relationships & money",
    "Mars": "action & conflict", "Jupiter": "growth & opportunity",
    "Saturn": "responsibility & structure", "Uranus": "change",
    "Neptune": "ideals & illusions", "Pluto": "power & transformation",
}


# ---- Astronomy helpers -------------------------------------------------------
def to_jd(dt_utc: datetime) -> float:
    h = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, h)


def jd_to_str(jd: float) -> str:
    y, m, d, h = swe.revjul(jd)
    hh = int(h)
    mm = int(round((h - hh) * 60))
    if mm == 60:
        hh, mm = hh + 1, 0
    return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d} UT"


def fmt_lon(lon: float) -> str:
    s = int(lon // 30)
    deg = lon - s * 30
    return f"{int(deg):2d}°{int((deg % 1) * 60):02d}' {SIGNS[s]}"


def wrap180(x: float) -> float:
    return (x + 180.0) % 360.0 - 180.0


class Ephemeris:
    def __init__(self, sidereal: bool, ayanamsa: str):
        self.flags = BASE_FLAGS
        if sidereal:
            swe.set_sid_mode(AYANAMSAS[ayanamsa], 0, 0)
            self.flags |= swe.FLG_SIDEREAL

    def pos(self, jd: float, body: int):
        xx, _ = swe.calc_ut(jd, body, self.flags)
        return xx[0] % 360.0, xx[3]  # longitude, speed (deg/day)

    def angles(self, jd: float, lat: float, lon: float):
        _, ascmc = swe.houses_ex(jd, lat, lon, b"P", self.flags)
        return ascmc[0] % 360.0, ascmc[1] % 360.0


def bisect(f, a: float, b: float, iters: int = 40) -> float:
    fa = f(a)
    for _ in range(iters):
        m = (a + b) / 2
        fm = f(m)
        if (fa < 0) == (fm < 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


# ---- Event finders -----------------------------------------------------------
def find_transits(eph, natal, jd0, jd1, step=1.0):
    events = []
    for tname in TRANSITING:
        body = PLANETS[tname]
        for nname, nlon in natal.items():
            for angle, (aname, tone) in ASPECTS.items():
                targets = {angle} if angle in (0, 180) else {angle, -angle}
                for tgt in targets:
                    f = lambda jd: wrap180(eph.pos(jd, body)[0] - nlon - tgt)
                    t, ft = jd0, f(jd0)
                    while t < jd1:
                        t2 = min(t + step, jd1)
                        ft2 = f(t2)
                        # sign change near zero (ignore the ±180 wrap jump)
                        if (ft < 0) != (ft2 < 0) and abs(ft) < 20 and abs(ft2) < 20:
                            jd_exact = bisect(f, t, t2)
                            retro = eph.pos(jd_exact, body)[1] < 0
                            events.append({
                                "jd": jd_exact, "type": "transit",
                                "event": f"{tname}{' (R)' if retro else ''} {aname} natal {nname}",
                                "meaning": (f"{TRANSIT_THEMES[tname]} — in the area of "
                                            f"{NATAL_AREAS[nname]} ({tone})"),
                            })
                        t, ft = t2, ft2
    return events


def find_stations(eph, jd0, jd1, step=1.0):
    events = []
    for pname in STATION_BODIES:
        body = PLANETS[pname]
        f = lambda jd: eph.pos(jd, body)[1]
        t, ft = jd0, f(jd0)
        while t < jd1:
            t2 = min(t + step, jd1)
            ft2 = f(t2)
            if (ft < 0) != (ft2 < 0):
                jd_exact = bisect(f, t, t2)
                kind = "R" if ft2 < 0 else "D"
                lon = eph.pos(jd_exact, body)[0]
                events.append({
                    "jd": jd_exact, "type": "station",
                    "event": f"{pname} stations {'retrograde' if kind == 'R' else 'direct'} at {fmt_lon(lon)}",
                    "meaning": STATION_THEMES[kind].format(p=PLANET_DOMAINS[pname]),
                })
            t, ft = t2, ft2
    return events


def find_ingresses(eph, jd0, jd1, step=0.5):
    events = []
    for pname in ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
                  "Uranus", "Neptune", "Pluto"]:
        body = PLANETS[pname]
        sign = lambda jd: int(eph.pos(jd, body)[0] // 30)
        t, s = jd0, sign(jd0)
        while t < jd1:
            t2 = min(t + step, jd1)
            s2 = sign(t2)
            if s2 != s:
                a, b = t, t2
                for _ in range(40):
                    m = (a + b) / 2
                    if sign(m) == s:
                        a = m
                    else:
                        b = m
                events.append({
                    "jd": b, "type": "ingress",
                    "event": f"{pname} enters {SIGNS[s2]}",
                    "meaning": f"collective shift in {PLANET_DOMAINS.get(pname, 'vitality & focus')}",
                })
            t, s = t2, s2
    return events


# ---- Main --------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--birth", required=True, help='local birth time "YYYY-MM-DD HH:MM"')
    ap.add_argument("--tz", required=True, help="IANA timezone of birth place, e.g. Asia/Kolkata")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True, help="east positive, west negative")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD (past or future)")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--zodiac", choices=["tropical", "sidereal"], default="tropical")
    ap.add_argument("--ayanamsa", choices=list(AYANAMSAS), default="lahiri")
    ap.add_argument("--no-ingress", action="store_true", help="skip sign ingresses")
    ap.add_argument("--csv", help="also write events to this CSV file")
    args = ap.parse_args()

    eph = Ephemeris(args.zodiac == "sidereal", args.ayanamsa)

    birth_local = datetime.strptime(args.birth, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(args.tz))
    jd_birth = to_jd(birth_local.astimezone(timezone.utc))

    natal = {name: eph.pos(jd_birth, body)[0] for name, body in PLANETS.items()}
    natal["Ascendant"], natal["Midheaven"] = eph.angles(jd_birth, args.lat, args.lon)

    label = args.zodiac + (f" ({args.ayanamsa})" if args.zodiac == "sidereal" else "")
    print(f"NATAL CHART — {label}")
    if args.zodiac == "sidereal":
        print(f"  ayanamsa at birth: {swe.get_ayanamsa_ut(jd_birth):.4f}°")
    for name, lon in natal.items():
        print(f"  {name:11s} {fmt_lon(lon)}")

    jd0 = to_jd(datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc))
    jd1 = to_jd(datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc))

    events = find_transits(eph, natal, jd0, jd1) + find_stations(eph, jd0, jd1)
    if not args.no_ingress:
        events += find_ingresses(eph, jd0, jd1)
    events.sort(key=lambda e: e["jd"])

    print(f"\nTIMELINE {args.start} → {args.end}  ({len(events)} events)")
    print("(meanings = traditional astrological associations, not validated predictions)\n")
    for e in events:
        print(f"{jd_to_str(e['jd'])}  [{e['type']}] {e['event']}")
        print(f"    → {e['meaning']}")

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["date_ut", "type", "event", "meaning"])
            w.writeheader()
            for e in events:
                w.writerow({"date_ut": jd_to_str(e["jd"]), "type": e["type"],
                            "event": e["event"], "meaning": e["meaning"]})
        print(f"\nWrote {args.csv}")


if __name__ == "__main__":
    main()
