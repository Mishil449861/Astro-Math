"""
panchanga.py — the five limbs of the Hindu almanac, at birth and for every day of a period.

  Tithi    lunar day: each 12° of Moon–Sun elongation (30 per lunar month)
  Vara     weekday, counted from sunrise to sunrise
  Nakshatra the Moon's sidereal nakshatra
  Yoga     sidereal Sun + Moon, in 13°20′ steps (27 yogas)
  Karana   half a tithi (6°): Kimstughna, 7 movable karanas ×8, Shakuni, Chatushpada, Naga

Sunrise/sunset use the Sun's upper limb with standard refraction (the modern almanac
convention). Rahu Kaal, Yamaganda and Gulika Kaal divide daylight into eighths.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import swisseph as swe

from astro_engine import NAK, Chart, _SWE, _bisect, _wrap, from_jd, to_jd

TITHI_NAMES = ["Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi", "Saptami",
               "Ashtami", "Navami", "Dashami", "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi"]
YOGA_NAMES = ["Vishkumbha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda", "Sukarma",
              "Dhriti", "Shoola", "Ganda", "Vriddhi", "Dhruva", "Vyaghata", "Harshana", "Vajra", "Siddhi",
              "Vyatipata", "Variyan", "Parigha", "Shiva", "Siddha", "Sadhya", "Shubha", "Shukla",
              "Brahma", "Indra", "Vaidhriti"]
MOVABLE_KARANAS = ["Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti (Bhadra)"]
VARAS = [("Ravivara", "Sunday", "Sun"), ("Somavara", "Monday", "Moon"), ("Mangalavara", "Tuesday", "Mars"),
         ("Budhavara", "Wednesday", "Mercury"), ("Guruvara", "Thursday", "Jupiter"),
         ("Shukravara", "Friday", "Venus"), ("Shanivara", "Saturday", "Saturn")]
# Which eighth of daylight (1–8) each period occupies, Sunday..Saturday
RAHU_KAAL = [8, 2, 7, 5, 6, 4, 3]
YAMAGANDA = [5, 4, 3, 2, 1, 7, 6]
GULIKA = [7, 6, 5, 4, 3, 2, 1]
RIKTA = {4, 9, 14}                  # Chaturthi, Navami, Chaturdashi: traditionally avoided for new starts
INAUSPICIOUS_YOGAS = {"Vishkumbha", "Atiganda", "Shoola", "Ganda", "Vyaghata", "Vajra",
                      "Vyatipata", "Parigha", "Vaidhriti"}


def elongation(chart: Chart, jd: float) -> float:
    return (chart.pos(jd, swe.MOON)[0] - chart.pos(jd, swe.SUN)[0]) % 360


def tithi_of(e: float) -> tuple[int, str]:
    """(1–30, name) from the Moon–Sun elongation."""
    i = int(e // 12) % 30
    if i == 14:
        name = "Purnima (Full Moon)"
    elif i == 29:
        name = "Amavasya (New Moon)"
    else:
        name = f"{'Shukla' if i < 15 else 'Krishna'} {TITHI_NAMES[i % 15]}"
    return i + 1, name


def karana_of(e: float) -> str:
    k = int(e // 6) % 60
    if k == 0:
        return "Kimstughna"
    if k >= 57:
        return ["Shakuni", "Chatushpada", "Naga"][k - 57]
    return MOVABLE_KARANAS[(k - 1) % 7]


def yoga_index(chart: Chart, jd: float) -> int:
    return int(((chart.pos(jd, swe.SUN)[0] + chart.pos(jd, swe.MOON)[0]) % 360) // NAK) % 27


def sun_event(jd_start: float, lat: float, lon: float, rise: bool) -> float | None:
    """Next sunrise (or sunset) after jd_start; None in polar day/night."""
    flag = swe.CALC_RISE if rise else swe.CALC_SET
    with _SWE:
        res, tret = swe.rise_trans(jd_start, swe.SUN, flag, (lon, lat, 0.0), 0.0, 0.0, swe.FLG_MOSEPH)
    return tret[0] if res == 0 else None


def _next_change(f, jd: float, size: float, horizon: float = 1.6) -> float | None:
    """When the quantity f (degrees, increasing) next crosses a multiple of `size`."""
    target = (int(f(jd) // size) + 1) * size
    g = lambda x: _wrap(f(x) - target)
    t, step = jd, 1 / 8
    while t < jd + horizon:
        if g(t) < 0 <= g(t + step):
            return _bisect(g, t, t + step, 25)
        t += step
    return None


def elements_at(chart: Chart, jd: float) -> dict:
    e = elongation(chart, jd)
    t_num, t_name = tithi_of(e)
    m = chart.pos(jd, swe.MOON)[0]
    from vedic import NAKSHATRAS  # local import avoids a cycle
    return {"tithi_num": t_num, "tithi": t_name, "nakshatra_idx": int(m // NAK) % 27,
            "nakshatra": NAKSHATRAS[int(m // NAK) % 27], "yoga": YOGA_NAMES[yoga_index(chart, jd)],
            "karana": karana_of(e), "moon_sign": int(m // 30)}


def vara_at(jd: float, lat: float, lon: float, tz: str):
    """Vedic weekday at jd: the day starts at sunrise, so before sunrise it is still the
    previous day's vara."""
    local = from_jd(jd, tz)
    midnight = datetime.combine(local.date(), time(0), tzinfo=ZoneInfo(tz))
    rise = sun_event(to_jd(midnight), lat, lon, True)
    d = local.date() if rise is None or jd >= rise else local.date() - timedelta(days=1)
    return VARAS[(d.weekday() + 1) % 7]


def birth_panchanga(chart: Chart, natal: dict, lat: float, lon: float, tz: str) -> list[dict]:
    """Panchanga at birth; every limb is checked at both ends of the birth-time window."""
    moments = [natal["jd"]] + ([natal["jd_range"][0], natal["jd_range"][1]] if natal["window"] else [])
    rows = []
    els = [elements_at(chart, j) for j in moments]
    varas = [vara_at(j, lat, lon, tz) for j in moments]
    for key, label in (("tithi", "Tithi"), ("nakshatra", "Nakshatra"), ("yoga", "Yoga"), ("karana", "Karana")):
        vals = []
        for e in els:
            if e[key] not in vals:
                vals.append(e[key])
        rows.append({"Limb": label, "Value": " or ".join(vals), "Certain": "yes" if len(vals) == 1 else "no"})
    vnames = []
    for v in varas:
        if f"{v[0]} ({v[1]})" not in vnames:
            vnames.append(f"{v[0]} ({v[1]})")
    rows.insert(0, {"Limb": "Vara", "Value": " or ".join(vnames), "Certain": "yes" if len(vnames) == 1 else "no"})
    return rows


def daily_panchanga(chart: Chart, start: date, end: date, lat: float, lon: float, tz: str,
                    janma_nak: int | None = None, moon_sign: int | None = None) -> list[dict]:
    """One row per civil day in [start, end): limbs at sunrise and when they end, sunrise /
    sunset, Rahu Kaal etc., and — given the birth nakshatra and Moon sign — the personal
    tara bala and chandra bala of the day."""
    from vedic import GOOD_HOUSES, TARA_QUALITY, TARAS, house_from
    z = ZoneInfo(tz)
    rows, d = [], start
    moon_lon = lambda x: chart.pos(x, swe.MOON)[0]
    elong = lambda x: elongation(chart, x)
    yoga_sum = lambda x: (chart.pos(x, swe.SUN)[0] + chart.pos(x, swe.MOON)[0]) % 360
    while d < end:
        jd_mid = to_jd(datetime.combine(d, time(0), tzinfo=z))
        rise = sun_event(jd_mid, lat, lon, True)
        if rise is None:
            rows.append({"Date": d, "Note": "No sunrise (polar day/night)"})
            d += timedelta(days=1)
            continue
        sset = sun_event(rise, lat, lon, False)
        el = elements_at(chart, rise)
        vara = VARAS[(d.weekday() + 1) % 7]
        wd = (d.weekday() + 1) % 7
        row = {
            "Date": d, "Vara": f"{vara[0]} ({vara[1][:3]})",
            "Sunrise": from_jd(rise, tz), "Sunset": from_jd(sset, tz) if sset else None,
            "Tithi": el["tithi"], "Tithi until": _fmt_end(_next_change(elong, rise, 12), tz),
            "Nakshatra": el["nakshatra"], "Nakshatra until": _fmt_end(_next_change(moon_lon, rise, NAK), tz),
            "Yoga": el["yoga"], "Yoga until": _fmt_end(_next_change(yoga_sum, rise, NAK), tz),
            "Karana": el["karana"],
        }
        if sset:
            part = (sset - rise) / 8
            for key, table in (("Rahu Kaal", RAHU_KAAL), ("Yamaganda", YAMAGANDA), ("Gulika", GULIKA)):
                a = rise + (table[wd] - 1) * part
                row[key] = f"{from_jd(a, tz):%H:%M}–{from_jd(a + part, tz):%H:%M}"
        cautions = []
        if (el["tithi_num"] - 1) % 15 + 1 in RIKTA:
            cautions.append("Rikta tithi")
        if el["karana"].startswith("Vishti"):
            cautions.append("Vishti karana")
        if el["yoga"] in INAUSPICIOUS_YOGAS:
            cautions.append(f"{el['yoga']} yoga")
        if el["tithi_num"] == 30:
            cautions.append("Amavasya")
        row["General cautions"] = ", ".join(cautions)
        if janma_nak is not None and moon_sign is not None:
            tara = TARAS[(el["nakshatra_idx"] - janma_nak) % 9]
            chandra_good = house_from(el["moon_sign"], moon_sign) in GOOD_HOUSES["Moon"]
            tq = TARA_QUALITY[tara]
            score = (tq == "good") + chandra_good - (tq == "bad")
            row["Tara"] = f"{tara} ({tq})"
            row["Chandra bala"] = "good" if chandra_good else "weak"
            # good: both personal indicators favourable and no general caution;
            # avoid: both unfavourable (bad tara and weak chandra bala); otherwise mixed
            row["For you"] = ("good" if score >= 2 and not cautions else
                              "avoid new starts" if score < 0 else "mixed")
        rows.append(row)
        d += timedelta(days=1)
    return rows


def _fmt_end(jd: float | None, tz: str) -> str:
    if jd is None:
        return "—"
    return from_jd(jd, tz).strftime("%a %H:%M")
