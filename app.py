"""
Astro calendar — Streamlit app

Run:
  pip install -r requirements.txt
  streamlit run app.py
(keep astro_engine.py and vedic.py in the same folder)
"""
import calendar
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import available_timezones

import pandas as pd
import streamlit as st

import ashtakavarga as avg
import astro_engine as ae
import matching
import panchanga
import strength
import vargas
import vedic as vd
import yogas

st.set_page_config(page_title="Astro Calendar", page_icon="🔭", layout="centered")

TONE_ICON = {"supportive": "🟢", "challenging": "🔴", "neutral": "🟣"}
SYSTEMS = ["Western (tropical)", "Vedic (sidereal)"]


# ---------------------------------------------------------------------------
# Cached helpers
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=86400)
def find_place(query: str):
    """City name -> (lat, lon, timezone). Returns (result, error)."""
    try:
        from geopy.geocoders import Nominatim
        from timezonefinder import TimezoneFinder
    except ImportError:
        return None, "Install geopy and timezonefinder to look up places by name, or enter the location manually under More options."
    try:
        loc = Nominatim(user_agent="astro-calendar-streamlit").geocode(query, timeout=10)
    except Exception:
        return None, "The place lookup service didn't respond. Try again, or enter the location manually under More options."
    if loc is None:
        return None, "Couldn't find that place. Try adding the country, e.g. “Springfield, Illinois, USA”."
    tz = TimezoneFinder().timezone_at(lng=loc.longitude, lat=loc.latitude)
    if tz is None:
        return None, "Found the place but not its timezone. Enter the location manually under More options."
    return {"name": loc.address, "lat": loc.latitude, "lon": loc.longitude, "tz": tz}, None


@st.cache_data(show_spinner=False)
def natal_chart(system, ayanamsa, bdate, btime, window, offset_s, lat, lon, constraint_key):
    off = timedelta(seconds=offset_s)
    if system.startswith("Vedic"):
        chart, planets = ae.Chart("sidereal", ayanamsa), vd.GRAHAS
    else:
        chart, planets = ae.Chart("tropical"), ae.PLANETS
    return ae.compute_natal(chart, planets, bdate, btime, window, off, lat, lon, dict(constraint_key))


@st.cache_data(show_spinner=False)
def run_reading(system, ayanamsa, bdate, btime, window, offset_s, lat, lon, constraint_key,
                kind, anchor, end_date, view_tz):
    natal = natal_chart(system, ayanamsa, bdate, btime, window, offset_s, lat, lon, constraint_key)
    start, end, label = ae.period_bounds(kind, anchor, view_tz, end_date)
    if system.startswith("Vedic"):
        report = vd.analyze_vedic(ae.Chart("sidereal", ayanamsa), natal, start, end, view_tz)
    else:
        report = ae.analyze(ae.Chart("tropical"), natal, start, end, view_tz)
    return natal, report, label, start.date(), end.date()


@st.cache_data(show_spinner=False)
def vedic_birth_extras(ayanamsa, bdate, btime, window, offset_s, lat, lon, constraint_key, tz):
    """Everything about the Vedic birth chart that doesn't depend on the period."""
    natal = natal_chart("Vedic", ayanamsa, bdate, btime, window, offset_s, lat, lon, constraint_key)
    chart = ae.Chart("sidereal", ayanamsa)
    table = vargas.varga_table(natal)
    has_lagna = "Ascendant" in natal["points"]
    out = {"vargas": table, "reliability": vargas.reliability(table, has_lagna), "tolerance": None,
           "yogas": yogas.evaluate(natal), "panchanga": panchanga.birth_panchanga(chart, natal, lat, lon, tz),
           "strength": None}
    if natal["time_known"] and has_lagna:
        out["tolerance"] = vargas.time_tolerance(chart, natal["jd"], lat, lon, vd.GRAHAS["Moon"])
    if has_lagna and natal["half_window"] <= 60:
        out["strength"] = strength.strengths(chart, natal, lat, lon)
    return out


@st.cache_data(show_spinner=False)
def daily_panchanga(ayanamsa, start, end, lat, lon, tz, janma_nak, moon_sign):
    return panchanga.daily_panchanga(ae.Chart("sidereal", ayanamsa), start, end, lat, lon, tz,
                                     janma_nak, moon_sign)


def moon_samples(natal):
    """The Moon's possible positions across the birth-time window, every 0.5°."""
    lo, _ = natal["range"]["Moon"]
    spread = natal["spread"]["Moon"]
    n = max(1, int(spread / 0.5)) if spread > 0 else 0
    return [(lo + spread * i / n) % 360 for i in range(n + 1)] if n else [natal["points"]["Moon"]]


@st.cache_data(show_spinner=False)
def zodiac_table(utc, lat, lon, ayanamsa, with_angles):
    return ae.compare_zodiacs(utc, lat, lon, ayanamsa, with_angles)


@st.cache_data(show_spinner=False)
def ayanamsa_today():
    jd = ae.to_jd(datetime.now().astimezone())
    return {name: ae.Chart("sidereal", name).ayanamsa(jd) for name in ae.AYANAMSAS}


def parse_offset(text: str):
    m = re.fullmatch(r"\s*(?:UTC)?\s*([+\-−])?\s*(\d{1,2})(?::?(\d{2}))?(?::(\d{2}))?\s*", text)
    if not m:
        return None
    sign = -1 if m.group(1) in ("-", "−") else 1
    secs = int(m.group(2)) * 3600 + int(m.group(3) or 0) * 60 + int(m.group(4) or 0)
    return timedelta(seconds=sign * secs) if secs <= 15 * 3600 else None


def fmt_date(dt, with_year=True):
    return dt.strftime("%b %d, %Y" if with_year else "%b %d")


def fmt_when(dt, days):
    return dt.strftime("%a %b %d, %I:%M %p") if days <= 3 else dt.strftime("%a %b %d, %Y")


def fmt_window(inf, days):
    if inf["body"] == "Eclipse":
        return f"Eclipse on {fmt_date(inf['start'])}"
    short = days <= 3 or inf["body"] == "Moon"
    f = (lambda d: d.strftime("%b %d %I:%M %p")) if short else fmt_date
    span = f"{'(before) ' if inf['open_start'] else ''}{f(inf['start'])} – {f(inf['end'])}{' (or later)' if inf['open_end'] else ''}"
    parts = [f"In orb {span}"]
    if len(inf["passes"]) > 1:
        parts.append(f"{len(inf['passes'])} passes (retrograde loop): "
                     + "; ".join(f"{fmt_date(a, False)}–{fmt_date(b)}" for a, b in inf["passes"]))
    if inf["exact"]:
        parts.append("exact " + ", ".join(
            (f"**{fmt_date(e)}**" if e in inf["exact_in_period"] else fmt_date(e)) for e in inf["exact"]))
    return " · ".join(parts)


def signs_text(signs):
    return " or ".join(signs)


def rashi_text(signs):
    return " or ".join(vd.rashi_name(ae.SIGNS.index(s)) for s in signs)


# ---------------------------------------------------------------------------
# Step 1 — birth details
# ---------------------------------------------------------------------------
st.title("Astro Calendar")
st.write("Enter your birth details, then pick a **day, week, month or your own date range** "
         "to see what the planets are doing for you.")

st.subheader("1 · Your birth details")
c1, c2 = st.columns(2)
bdate = c1.date_input("Date of birth", value=date(1995, 1, 1),
                      min_value=date(1800, 1, 1), max_value=date.today())
certainty = c2.radio("How sure is the birth time?", ["Exact", "Approximate", "Unknown"], horizontal=True,
                     help="Exact: from a birth certificate or hospital record. Approximate: remembered or "
                          "rounded (\"around 7 in the morning\"). The app then leaves out anything that depends "
                          "on the time more than the uncertainty allows.")
btime = c2.time_input("Time of birth, as written on the record", value=time(12, 0), step=60,
                      disabled=certainty == "Unknown")
window = 0
if certainty == "Approximate":
    window = c2.select_slider("Could be off by up to", options=[10, 15, 30, 60, 120, 240], value=30,
                              format_func=lambda m: f"{m} min" if m < 60 else f"{m // 60} h")
birth_time = None if certainty == "Unknown" else btime
place = c1.text_input("Place of birth", placeholder="City, country, e.g. Mumbai, India")

tz_list = sorted(available_timezones())
with st.expander("More options"):
    system = st.radio("Astrology system", SYSTEMS, horizontal=True)
    ayanamsa = "Lahiri (Chitrapaksha)"
    if system.startswith("Vedic"):
        ayanamsa = st.selectbox("Ayanamsa (where the sidereal zodiac starts)", list(ae.AYANAMSAS),
                                help="Lahiri is the Indian government standard and the most widely used.")
    view_tz_choice = st.selectbox("Show dates and times in", ["Birthplace timezone"] + tz_list)
    manual = st.checkbox("Enter birth location manually")
    if manual:
        m1, m2 = st.columns(2)
        m_lat = m1.number_input("Latitude", -90.0, 90.0, 40.7128, format="%.4f")
        m_lon = m2.number_input("Longitude (west is negative)", -180.0, 180.0, -74.0060, format="%.4f")
        m_tz = st.selectbox("Birth timezone", tz_list, index=tz_list.index("America/New_York"))

with st.expander("Tropical or sidereal? What's the difference, and which should I use?"):
    ay = ayanamsa_today()
    st.markdown(f"""
Both zodiacs cut the Sun's yearly path into twelve signs of 30°. They differ only in **where they start counting**.

- **Tropical (Western astrology)** starts Aries where the Sun is at the March equinox, so the signs are tied to the **seasons**.
- **Sidereal (Vedic astrology)** starts Aries at a fixed point among the **stars**.

Earth's axis slowly wobbles, so the equinox slides backwards against the stars by about 1° every 72 years.
The gap between the two zodiacs (the *ayanamsa*) is now about **{ay['Lahiri (Chitrapaksha)']:.1f}°**.
A planet in the first {ay['Lahiri (Chitrapaksha)']:.0f}° or so of a tropical sign sits in the *previous* sign
in sidereal, which is why most people's Sun sign moves back one.

**In favour of sidereal**
- Its signs line up, roughly, with the constellations you can actually see.
- The whole Vedic toolkit is built on it: nakshatras, dashas (life periods) and gochara (transits from the Moon) only work with it.
- Dashas give specific dated periods that you can check against your own life.

**Against sidereal**
- There is no agreed starting point. Today Lahiri says {ay['Lahiri (Chitrapaksha)']:.2f}°, Raman
  {ay['Raman']:.2f}° and KP {ay['Krishnamurti (KP)']:.2f}°, so a planet near the edge of a sign can
  change sign depending on the choice.
- The real constellations are unequal in size while sidereal signs are all 30°, so the match with the stars is only approximate.
- Western sign descriptions were developed on the tropical zodiac. Reading them on sidereal signs mixes two
  systems, so this app keeps them apart: Western readings use tropical, Vedic readings use sidereal.

**What doesn't change:** the angles between planets are identical in both. Only the sign labels move.

**Which to choose?** Neither zodiac has scientific evidence behind its predictions; the choice is about which
tradition you want to follow. After your reading, *Your chart in both zodiacs* shows exactly which of your
placements change sign.
""")

is_vedic = system.startswith("Vedic")
with st.expander("Already know part of your chart? (optional)"):
    st.caption("From a family horoscope (janma patrika), the nakshatra chosen for a naming syllable, or an "
               "earlier reading. The app keeps only the birth times that agree with it, which narrows an "
               "approximate or unknown time, and it warns you if an exact time contradicts it. "
               + ("Use values from a sidereal (Vedic) chart made with the same ayanamsa." if is_vedic else
                  "Use values from a tropical (Western) chart."))
    k1, k2 = st.columns(2)
    constraints = {}
    if is_vedic:
        rashi_opts = ["Not sure"] + [vd.rashi_name(i) for i in range(12)]
        r_pick = k1.selectbox("Rashi (Moon sign)", rashi_opts)
        l_pick = k1.selectbox("Lagna (ascendant sign)", rashi_opts)
        n_pick = k2.selectbox("Nakshatra (birth star)", ["Not sure"] + vd.NAKSHATRAS)
        p_pick = k2.selectbox("Pada (quarter)", ["Not sure", 1, 2, 3, 4], disabled=n_pick == "Not sure")
        constraints["moon_sign"] = None if r_pick == "Not sure" else rashi_opts.index(r_pick) - 1
        constraints["lagna_sign"] = None if l_pick == "Not sure" else rashi_opts.index(l_pick) - 1
        if n_pick != "Not sure":
            n_idx = vd.NAKSHATRAS.index(n_pick)
            constraints["nakshatra"] = n_idx
            if p_pick != "Not sure":
                constraints["pada"] = n_idx * 4 + int(p_pick) - 1
    else:
        sign_opts = ["Not sure"] + ae.SIGNS
        m_pick = k1.selectbox("Moon sign", sign_opts)
        a_pick = k2.selectbox("Rising sign", sign_opts)
        constraints["moon_sign"] = None if m_pick == "Not sure" else sign_opts.index(m_pick) - 1
        constraints["lagna_sign"] = None if a_pick == "Not sure" else sign_opts.index(a_pick) - 1
constraint_key = tuple(sorted((k, v) for k, v in constraints.items() if v is not None))

location = None
if manual:
    location = {"name": "Manual location", "lat": m_lat, "lon": m_lon, "tz": m_tz}
elif place.strip():
    with st.spinner("Looking up place…"):
        location, err = find_place(place.strip())
    if err:
        st.warning(err)

# ---- birth clock: local time -> UTC (re-checked whenever the inputs change) ----
offset = None
if location:
    st.caption(f"{location['name']} · {location['lat']:.2f}, {location['lon']:.2f} · {location['tz']}"
               + ("" if manual else " · Place search © OpenStreetMap contributors (Nominatim)"))
    clk = ae.check_birth_clock(bdate, birth_time, location["tz"], location["lon"], location["lat"])
    rc = clk["regional"]
    with st.container(border=True):
        st.markdown("**Converting the birth time to world time (UTC)**")
        opts = {}
        if rc:
            opts["regional"] = f"{rc['name']}, the local clock time then: {ae.fmt_offset(rc['offset'])}"
        opts["db"] = f"Time zone records: {ae.fmt_offset(clk['db_offset'])} ({clk['abbr']})"
        if clk["ambiguous"]:
            opts["db_alt"] = (f"Time zone records, second time the clock showed this: "
                              f"{ae.fmt_offset(clk['db_offset_alt'])} ({clk['abbr_alt']})")
        opts["lmt"] = f"Local mean (sun) time at the birthplace: {ae.fmt_offset(clk['lmt_offset'])}"
        opts["custom"] = "I know the offset"
        default = clk["default"]
        choice = st.radio("Convert using", list(opts), format_func=opts.get, index=list(opts).index(default),
                          key=f"clock-{location['tz']}-{default}-{clk['ambiguous']}")
        if choice == "custom":
            text = st.text_input("Offset from UTC, e.g. +05:30 or -04:56:02", value=ae.fmt_offset(clk["db_offset"])[3:])
            offset = parse_offset(text)
            if offset is None:
                st.error("Couldn't read that offset. Use a form like +05:30 or -08:00.")
        else:
            offset = {"db": clk["db_offset"], "db_alt": clk["db_offset_alt"], "lmt": clk["lmt_offset"],
                      "regional": rc["offset"] if rc else None}[choice]

        gap = abs(clk["gap_minutes"])
        if rc:
            diff = abs((clk["db_offset"] - rc["offset"]).total_seconds()) / 60
            st.info(f"After India adopted IST in 1906, this city kept its own **{rc['name']}** "
                    f"({ae.fmt_offset(rc['offset'])}) for civil use, so it is selected. The time zone records "
                    f"say {ae.fmt_offset(clk['db_offset'])}, a difference of **{diff:.0f} minutes** "
                    f"(about {diff / 4:.0f}° of Ascendant). If the record says IST, switch to the time zone records.")
            for note in rc["notes"]:
                st.warning(note[0].upper() + note[1:] + ".")
        elif clk["mean_time"]:
            st.info(f"For {bdate.year} the time zone records give **{clk['abbr']}**, the mean sun time of the "
                    f"zone's reference city, not of the birthplace. Records from that era normally used local time, "
                    f"so the birthplace's own mean time is selected. The two differ by **{gap:.0f} minutes**, "
                    f"which moves the Ascendant by roughly {gap / 4:.0f}°.")
        elif clk["pre1970"]:
            st.caption(f"Time zone records before 1970 can be incomplete or regionally wrong. If the record states "
                       f"local time, or clocks there were set differently, switch the option. (Local mean time "
                       f"differs from the records by {gap:.0f} minutes, about {gap / 4:.0f}° of Ascendant.)")
        if location["tz"] == "Asia/Kolkata" and clk["pre1970"] and not rc:
            st.caption("Only Bombay Time and Calcutta Time are recognised automatically, within 40 km of each "
                       "city. If this town kept its own local time, choose local mean time or enter the offset.")
        if clk["zone_note"] and clk["pre1970"]:
            st.warning(clk["zone_note"])
        if clk["nonexistent"]:
            st.warning("This clock time didn't exist on that date: clocks jumped forward for daylight saving. "
                       "Check the record, or enter the offset yourself.")
        if clk["ambiguous"]:
            st.warning("This clock time happened twice that night because the clocks went back. "
                       "Choose which one, if the record says.")
        if offset is not None and birth_time is not None:
            utc = datetime.combine(bdate, birth_time) - offset
            st.caption(f"Birth moment used: {utc:%d %b %Y, %H:%M:%S} UTC")

# ---------------------------------------------------------------------------
# Step 2 — period
# ---------------------------------------------------------------------------
st.subheader("2 · Pick a time to look at")
kind = st.radio("Look at a", ["Day", "Week", "Month", "Custom range"], index=2, horizontal=True)
kind_key = "Custom" if kind == "Custom range" else kind
today = date.today()
end_date = None
lo_d, hi_d = date(1800, 1, 1), date(2100, 12, 31)
if kind == "Day":
    anchor = st.date_input("Date", value=today, min_value=lo_d, max_value=hi_d)
elif kind == "Week":
    picked = st.date_input("Any day in the week", value=today, min_value=lo_d, max_value=hi_d)
    monday = picked - timedelta(days=picked.weekday())
    st.caption(f"Week: {monday:%a %b %d} – {monday + timedelta(days=6):%a %b %d, %Y}")
    anchor = picked
elif kind == "Month":
    p1, p2 = st.columns(2)
    months = list(calendar.month_name)[1:]
    month = p1.selectbox("Month", months, index=today.month - 1)
    year = p2.number_input("Year", min_value=1800, max_value=2100, value=today.year, step=1)
    anchor = date(int(year), months.index(month) + 1, 1)
else:
    r1, r2 = st.columns(2)
    anchor = r1.date_input("From", value=today, min_value=lo_d, max_value=hi_d)
    end_date = r2.date_input("To (inclusive)", value=today + timedelta(days=89), min_value=lo_d, max_value=hi_d)
    n_days = (end_date - anchor).days + 1
    if n_days < 1:
        st.error("The end date is before the start date.")
    elif n_days > ae.MAX_RANGE_DAYS:
        st.error(f"Please pick at most {ae.MAX_RANGE_DAYS} days ({n_days} selected).")
    else:
        st.caption(f"{n_days} days. Short ranges (up to 3 days) include the Moon's transits; "
                   f"up to 14 days include its sign changes.")

panch_place = None
if is_vedic:
    here = st.text_input("Where are you for the daily panchanga? (optional)",
                         placeholder="Leave empty to use the birthplace",
                         help="Sunrise, and so the panchanga of each day, depends on where you are.")
    if here.strip():
        with st.spinner("Looking up place…"):
            panch_place, perr = find_place(here.strip())
        if perr:
            st.warning(perr)

range_ok = kind != "Custom range" or 1 <= (end_date - anchor).days + 1 <= ae.MAX_RANGE_DAYS
ready = location is not None and offset is not None and range_ok
if st.button("Show my reading", type="primary", disabled=not ready):
    st.session_state["started"] = True
if location is None:
    st.caption("Enter your place of birth to continue.")

if not (st.session_state.get("started") and ready):
    st.stop()

# ---------------------------------------------------------------------------
# Results (recompute automatically when inputs change; cached)
# ---------------------------------------------------------------------------
view_tz = location["tz"] if view_tz_choice == "Birthplace timezone" else view_tz_choice
offset_s = int(offset.total_seconds())
with st.spinner("Reading the sky…"):
    try:
        natal, report, label, p_start, p_end = run_reading(
            system, ayanamsa, bdate, birth_time, window, offset_s, location["lat"], location["lon"],
            constraint_key, kind_key, anchor, end_date, view_tz)
    except ae.BirthDataError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:  # show a friendly message instead of a stack trace
        st.error(f"Something went wrong while calculating: {exc}")
        st.stop()

st.divider()
days = report["days"]


def certainty_note(names):
    """Explain which time-sensitive points were left out of timing, and what a stated
    Rashi / Nakshatra / Lagna did to the birth-time window."""
    if natal["constrained"] and not natal["time_known"]:
        # show the window in the same clock the birth time was entered in
        clock = lambda j: ae.from_jd(j, "UTC").replace(tzinfo=None) + natal["utc_offset"]
        spans = "; ".join(f"{clock(a):%d %b %H:%M} – {clock(b):%d %b %H:%M}" for a, b in natal["intervals"])
        full = ae.UNKNOWN_WINDOW if birth_time is None else window
        if natal["half_window"] < full - 1:
            st.success(f"What you know about your chart narrows the possible birth time to {spans} "
                       f"(clock time at {ae.fmt_offset(natal['utc_offset'])}, as entered).")
        else:
            st.caption("What you entered under 'Already know' holds for the whole possible birth-time window, "
                       "so it confirms the chart but doesn't narrow the time.")
    if natal["time_known"]:
        return
    w = (f"±{natal['half_window'] / 60:.1f} hours" if natal["half_window"] >= 90
         else f"±{natal['half_window']:.0f} minutes")
    dropped = [k for k in names if k in natal["points"] and k not in natal["usable"]
               and k not in natal["widened"]]
    widened = [k for k in names if k in natal["widened"]]
    missing = [] if "Ascendant" in natal["points"] else ["Ascendant", "Midheaven"]
    parts = [f"{k} (could be anywhere in {natal['spread'][k]:.0f}°)" for k in dropped]
    msg = f"Birth time uncertainty {w}. "
    if parts or missing:
        msg += ("Left out of the timing because they move too much in that window: "
                + ", ".join(parts + [f"{m} (needs a birth time)" for m in missing]) + ". ")
    if widened:
        msg += ("Kept with a wider orb, so their dates are approximate: "
                + ", ".join(f"{k} ({natal['spread'][k]:.1f}° span)" for k in widened) + ". ")
    msg += "Everything shown holds for any time in the window; you just see fewer contacts."
    st.info(msg)


# ---- Vedic birth-chart tabs ------------------------------------------------------
LIMITS_MD = """
- **Strength is partial.** 7 of the Shadbala parts are left out because sources disagree on them, so the
  totals can't be compared with other software, and the classical "required strength" thresholds aren't applied.
  Use it only to compare your own planets with each other.
- **Guna Milan:** the 1–3 point Yoni scores vary slightly between commentaries, and Nadi / Bhakoot
  cancellations are listed but not applied. Expect other calculators to differ by a point or two.
- **Yogas** use the common textbook versions, without the extra classical conditions (planet strength,
  combustion and so on). A yoga listed here is a starting point, not a verdict.
- **Regional clocks** cover only Bombay and Calcutta, within 40 km of each city; towns near the edge get no
  automatic choice. The exact switch-over dates are unknown, so those years are flagged rather than decided.
- **Birth time:** anything marked "depends on birth time", "?" or shown as a range is genuinely uncertain
  for the time you gave.
"""
BIRTH_TABS =["Charts", "Ashtakavarga", "Yogas", "Strength", "Birth panchanga", "Match making"]
SIGN3 = [s[:3] for s in ae.SIGNS]


def _sign_cell(opts):
    return "/".join(SIGN3[o] for o in opts) if len(opts) <= 3 else "?"


def _draw(table, d, natal, style, key):
    row = table[d]
    if "Ascendant" in row:
        ref, label = row["Ascendant"][0], "Lagna" + ("?" if len(row["Ascendant"]) > 1 else "")
    else:
        ref, label = row["Moon"][0], "Moon"
    name = f"D{d} {vargas.VARGAS[d][0]}"
    draw = vargas.north_indian if style == "North Indian" else vargas.south_indian
    st.markdown(draw(row, natal["retro"], ref, name, label), unsafe_allow_html=True)


def render_charts(extras, natal, vs):
    table, rel, tol = extras["vargas"], extras["reliability"], extras["tolerance"]
    s1, s2 = st.columns(2)
    style = s1.radio("Chart style", ["North Indian", "South Indian"], horizontal=True, key="chart_style")
    pick = s2.selectbox("Second chart", [d for d in vargas.VARGAS if d != 1], index=4, key="varga_pick",
                        format_func=lambda d: f"D{d} {vargas.VARGAS[d][0]} ({vargas.VARGAS[d][1]})")
    c1, c2 = st.columns(2)
    with c1:
        _draw(table, 1, natal, style, "d1")
    with c2:
        _draw(table, pick, natal, style, "dx")
    if "Ascendant" not in natal["points"]:
        st.caption("No birth time, so houses are counted from the Moon (Chandra kundali).")
    st.caption("As = Lagna, R = retrograde, ? = sign depends on the exact birth time.")

    names = list(next(iter(table.values())))
    rows = []
    for name in names:
        rows.append({"Point": "Lagna" if name == "Ascendant" else name,
                     **{f"D{d}": _sign_cell(table[d][name]) for d in vargas.VARGAS}})
    rows.append({"Point": "Reliable?", **{f"D{d}": rel[d] for d in vargas.VARGAS}})
    if tol:
        rows.append({"Point": "Time margin", **{f"D{d}": f"−{a:.0f} / +{b:.0f} min" if max(a, b) < 240 else "> 4 h"
                                                for d, (a, b) in tol.items()}})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    st.caption("**Time margin**: how many minutes earlier / later the birth time could be before that chart's "
               "Lagna or Moon changes sign. A chart is only as trustworthy as the birth time is precise: "
               "D9 usually needs it within about 10 minutes, D60 within a minute or two."
               if tol else
               "With an uncertain birth time, charts where any point shows two signs are marked uncertain.")


def render_ashtakavarga(av, vs):
    rows = []
    for p in avg.PLANETS7:
        rows.append({"Planet": p, **{SIGN3[i]: avg.fmt_range(av["bav"][p][i]) for i in range(12)},
                     "Total": avg.BAV_TOTALS[p]})
    rows.append({"Planet": "SAV (all)", **{SIGN3[i]: avg.fmt_range(av["sav"][i]) for i in range(12)},
                 "Total": 337})
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    strong = [ae.SIGNS[i] for i in range(12) if av["sav"][i][0] >= 28]
    weak = [ae.SIGNS[i] for i in range(12) if av["sav"][i][1] < 25]
    st.write(f"**Strong signs for you** (28+ bindus): {', '.join(strong) or 'none for certain'}. "
             f"**Weaker signs** (under 25): {', '.join(weak) or 'none for certain'}.")
    st.caption("Bindus each planet receives in each sign from the seven planets and the Lagna "
               "(Parashara's tables). Transits through signs with more bindus are traditionally easier. "
               + ("" if av["certain"] else "Ranges like 3–5 mean the value depends on the exact birth time "
                                           "(the Lagna, and sometimes the Moon, could be in more than one sign)."))


def render_yogas(y):
    if y["rows"]:
        st.dataframe(pd.DataFrame(y["rows"]), hide_index=True)
    else:
        st.write("None of the yogas checked here are formed.")
    if y["kuja"]:
        st.write("**Kuja (Mangal) dosha** counted " + "; ".join(
            f"{k['Counted']}" + (" (depends on birth time)" if k["Status"] != "present" else "") for k in y["kuja"]) + ".")
    else:
        st.write("**Kuja (Mangal) dosha**: not present.")
    st.caption("Textbook forms of about 25 common yogas on the Rashi chart. Classical texts add conditions "
               "(planet strength, combustion, aspects) and schools differ, so treat this as a starting list. "
               + ("" if y["lagna_known"] else "Lagna-based yogas need a birth time and are not checked."))


def render_strength(rows):
    if not rows:
        st.info("Planetary strength needs the birth time to within about an hour (it depends on the Lagna, "
                "the Midheaven and the hour of birth).")
        return
    df = pd.DataFrame(rows).sort_values("Rank")
    st.dataframe(df.round(1), hide_index=True)
    st.caption("Partial Shadbala in virupas (60 = 1 rupa): 10 sub-components with single agreed formulas. "
               "Saptavargaja, Abda/Masa, Tribhaga, Ayana, Yuddha, Cheshta and Drik bala are left out because "
               "texts and software disagree on them, so totals are lower than full Shadbala and the classical "
               "'required rupas' don't apply. Use it to compare your planets with each other.")


@st.cache_data(show_spinner=False)
def partner_moon(ayanamsa, p_date, p_time, lat, lon, tz):
    clk = ae.check_birth_clock(p_date, p_time, tz, lon, lat)
    off = {"regional": clk["regional"]["offset"] if clk["regional"] else None,
           "lmt": clk["lmt_offset"], "db": clk["db_offset"]}[clk["default"]]
    chart = ae.Chart("sidereal", ayanamsa)
    n = ae.compute_natal(chart, vd.GRAHAS, p_date, p_time, 0, off, lat, lon)
    s = {g: int(n["points"][g] // 30) for g in ("Moon", "Mars", "Venus")}
    if "Ascendant" in n["points"] and len(n["signs"]["Ascendant"]) == 1:
        s["Lagna"] = int(n["points"]["Ascendant"] // 30)
    return moon_samples(n), yogas.kuja_dosha(s), clk["default"], off


def render_matching(natal):
    st.caption("Ashtakoota (Guna Milan): eight comparisons of the two birth Moons, 36 points in all. The "
               "traditional tables are read bride → groom.")
    with st.form("match_form"):
        role = st.radio("In those tables, you are the", ["Bride", "Groom"], horizontal=True)
        m1, m2 = st.columns(2)
        p_date = m1.date_input("Partner's date of birth", value=date(1995, 1, 1),
                               min_value=date(1800, 1, 1), max_value=date.today())
        p_place = m1.text_input("Partner's place of birth", placeholder="City, country")
        p_unknown = m2.checkbox("Partner's birth time is unknown")
        p_time = m2.time_input("Partner's time of birth", value=time(12, 0), step=60)
        go = st.form_submit_button("Check compatibility")
    if go:
        st.session_state["match_args"] = (role, p_date, None if p_unknown else p_time, p_place.strip())
    args = st.session_state.get("match_args")
    if not args:
        return
    role, p_date, p_time, p_place = args
    if not p_place:
        st.warning("Enter the partner's place of birth.")
        return
    ploc, perr = find_place(p_place)
    if perr:
        st.warning(perr)
        return
    p_moons, p_kuja, p_clock, p_off = partner_moon(ayanamsa, p_date, p_time, ploc["lat"], ploc["lon"], ploc["tz"])
    mine = moon_samples(natal)
    bride, groom = (mine, p_moons) if role == "Bride" else (p_moons, mine)
    res = matching.match(bride, groom)
    lo, hi = res["total"]
    total = f"{lo:g}" if lo == hi else f"{lo:g}–{hi:g}"
    st.metric("Guna Milan", f"{total} / 36", matching.verdict(lo) if lo == hi else
              f"{matching.verdict(lo)} to {matching.verdict(hi)}", delta_color="off")
    st.dataframe(pd.DataFrame(res["rows"]), hide_index=True)
    if res["nadi_dosha"]:
        st.warning("Nadi dosha (same Nadi, 0 of 8). Texts list cancellations, e.g. same Moon sign with different "
                   "nakshatras, or same nakshatra with different padas; they are not applied here.")
    if res["bhakoot_dosha"]:
        st.warning("Bhakoot dosha (2/12, 5/9 or 6/8 Moon signs). Cancellations exist, e.g. when both Moon signs "
                   "share a lord or the lords are friends; they are not applied here.")
    yours = extras["yogas"]["kuja"]
    st.write("**Kuja (Mangal) dosha**: you " + (", ".join(k["Counted"] for k in yours) if yours else "none")
             + "; partner " + (", ".join(p_kuja) if p_kuja else "none") + ". Traditionally it matters most when "
             "only one of the two has it.")
    st.caption(f"Partner's time converted with {ae.fmt_offset(p_off)} ({p_clock} setting) at "
               f"{ploc['name'].split(',')[0]}. "
               + ("Ranges appear because a birth time is unknown, so the Moon's nakshatra may be uncertain. "
                  if lo != hi else "")
               + "How to judge this score: Yoni scores between 1 and 3 vary slightly between commentaries, and "
                 "the traditional Nadi and Bhakoot cancellations are not applied, so other calculators can differ "
                 "by a point or two, and a dosha shown here may be cancelled in a full reading.")


# ===========================================================================
# WESTERN
# ===========================================================================
if not system.startswith("Vedic"):
    st.subheader("Your birth chart")
    pts, signs = natal["points"], natal["signs"]
    b1, b2, b3 = st.columns(3)
    sun = ae.sign_of(pts["Sun"])
    b1.metric("Sun · core self", sun)
    b1.caption(ae.SIGN_KEYWORDS[sun])
    b2.metric("Moon · emotions", signs_text(signs["Moon"]))
    b2.caption(ae.SIGN_KEYWORDS[signs["Moon"][0]] if len(signs["Moon"]) == 1 else "Depends on the birth time")
    if "Ascendant" in pts:
        b3.metric("Rising · first impression", signs_text(signs["Ascendant"]))
        b3.caption(ae.SIGN_KEYWORDS[signs["Ascendant"][0]] if len(signs["Ascendant"]) == 1
                   else "Depends on the birth time")
    else:
        b3.metric("Rising", "—")
        b3.caption("Needs your birth time")
    certainty_note(ae.PERSONAL_POINTS)

    with st.expander("All birth placements"):
        rows = []
        for k, v in pts.items():
            lo, hi = natal["range"][k]
            rows.append({"Point": k, "Position": ae.fmt_pos(v),
                         "Possible range": "" if natal["time_known"] else f"{ae.fmt_pos(lo)} – {ae.fmt_pos(hi)}",
                         "Used for timing": "yes" if k in natal["usable"] else "no",
                         "Area": ae.NATAL_AREAS[k],
                         "Retrograde": "R" if natal["retro"].get(k) and k != "North Node" else ""})
        st.dataframe(pd.DataFrame(rows), hide_index=True)

    with st.expander("Your chart in both zodiacs"):
        comp = zodiac_table(natal["utc"], location["lat"], location["lon"], ayanamsa, "Ascendant" in pts)
        moved = [r["Point"] for r in comp if r["Changes sign"]]
        st.write(f"{len(moved)} of {len(comp)} placements change sign in the sidereal zodiac"
                 + (f": {', '.join(moved)}." if moved else "."))
        st.dataframe(pd.DataFrame(comp), hide_index=True)

    st.divider()
    st.header(label)
    o1, o2, o3 = st.columns(3)
    o1.metric("Overall tone", report["overall"])
    o2.metric("Intensity", report["intensity"],
              help="Total strength of all contacts per birth-chart point used, compared with what is "
                   "typical for a period of this length (calibrated on random charts). Fair to compare "
                   "with and without a birth time.")
    if report["moon"]:
        o3.metric("Moon", report["moon"]["sign"], report["moon"]["phase"], delta_color="off")
    else:
        o3.metric("Eclipses", len(report["eclipses"]))

    if report["areas"]:
        top = [a["Life area"].lower() for a in report["areas"][:2]]
        st.write(f"The strongest influences in this period touch your **{' and '.join(top)}**.")
        st.dataframe(pd.DataFrame(report["areas"]), hide_index=True,
                     column_config={"Focus": st.column_config.ProgressColumn("Focus", min_value=0, max_value=1, format=" ")})
    else:
        st.write("No major planetary contacts to your chart in this period: a quiet stretch.")

    tab1, tab2, tab3, tab4 = st.tabs(["Main influences", "Key dates", "Eclipses", "Sky positions"])
    with tab1:
        if not report["influences"]:
            st.info("Nothing significant in this period.")
        st.caption("🟢 supportive · 🔴 challenging · 🟣 spotlight. Strongest first. Dates cover the whole "
                   "transit, including retrograde passes; exact dates inside this period are in bold.")

        def card(inf):
            with st.container(border=True):
                st.markdown(f"{TONE_ICON[inf['tone']]} **{inf['title']}**")
                st.write(inf["meaning"])
                st.caption(fmt_window(inf, days))

        TOP_N = 6
        for inf in report["influences"][:TOP_N]:
            card(inf)
        rest = report["influences"][TOP_N:]
        if rest:
            with st.expander(f"Show {len(rest)} smaller influences"):
                if len(rest) <= 30:
                    for inf in rest:
                        card(inf)
                else:
                    st.dataframe(pd.DataFrame([{
                        "Tone": TONE_ICON[i["tone"]], "Influence": i["title"],
                        "From": fmt_date(i["start"]), "To": fmt_date(i["end"]),
                        "Exact": ", ".join(fmt_date(e) for e in i["exact"])} for i in rest]), hide_index=True)

    events = report["events"]
    with tab3:
        if report["eclipses"]:
            st.dataframe(pd.DataFrame([{
                "Date": fmt_date(e["when"]), "Eclipse": f"{e['type']} {e['kind'].lower()}",
                "Position": ae.fmt_pos(e["lon"]), "Near": e["near_node"],
                "Touches your": ", ".join(e["hits"]) or "—"} for e in report["eclipses"]]), hide_index=True)
            st.caption("Eclipses happen in pairs or threes every ~6 months, near the lunar nodes. "
                       "Global dates; visibility depends on where you are.")
        else:
            st.info("No eclipses in this period. Try a longer range (eclipse seasons come every ~6 months).")
    with tab4:
        st.caption("Where the planets are at the middle of the period.")
        st.dataframe(pd.DataFrame(report["sky"]), hide_index=True)

# ===========================================================================
# VEDIC
# ===========================================================================
else:
    vs = report["natal"]
    with st.container(border=True):
        st.markdown("**How to judge this reading: known limits**")
        st.markdown(LIMITS_MD)
    st.subheader("Your birth chart (Vedic)")
    b1, b2, b3 = st.columns(3)
    if vs["lagna_sign"] is not None:
        b1.metric("Lagna (ascendant)", vd.rashi_name(vs["lagna_sign"]))
    elif "Ascendant" in natal["points"]:
        b1.metric("Lagna (ascendant)", rashi_text(natal["signs"]["Ascendant"]))
        b1.caption("Depends on the birth time")
    else:
        b1.metric("Lagna", "—")
        b1.caption("Needs your birth time")
    b2.metric("Rashi (Moon sign)", rashi_text(vs["moon_signs"]))
    b3.metric("Nakshatra", " or ".join(vs["nak_options"]),
              f"pada {vs['pada']}, lord {vs['nak_lord']}" if len(vs["nak_options"]) == 1 else None,
              delta_color="off")
    certainty_note(["Moon", "Ascendant"])
    if len(vs["moon_signs"]) > 1:
        st.warning(f"On that day the Moon moved from {vs['moon_signs'][0]} into {vs['moon_signs'][-1]}. "
                   f"The readings below assume {vd.rashi_name(vs['moon_sign'])}, where it was at the given "
                   f"(or midday) time.")
    if natal["window"]:
        sh = vs["dasha_shift_days"]
        st.caption("Dasha dates depend on the Moon's exact degree. With this uncertainty they "
                   + ("can follow a completely different sequence (the birth nakshatra itself is uncertain)."
                      if sh == float("inf") else f"can shift by up to {sh / 30.44:.1f} months."))

    with st.expander("All grahas"):
        st.dataframe(pd.DataFrame(vs["rows"]), hide_index=True)
        st.caption(f"Sidereal zodiac, {natal['ayanamsa_name']} ayanamsa {natal['ayanamsa']:.4f}° at birth. "
                   "Rahu/Ketu are the mean nodes; whole-sign houses.")

    with st.expander("Vimshottari dasha timeline"):
        mrows = []
        for md in vs["dashas"]:
            if md["end"] < natal["jd"]:
                continue
            s_ = ae.from_jd(max(md["start"], natal["jd"]), view_tz)
            mrows.append({"Mahadasha": md["lord"], "From": fmt_date(s_), "To": fmt_date(ae.from_jd(md["end"], view_tz)),
                          "Years": vd.DASHA_YEARS[md["lord"]]})
        st.dataframe(pd.DataFrame(mrows), hide_index=True)
        st.caption("The first period is the balance remaining at birth. Years of 365.25 days.")

    with st.expander("Your chart in both zodiacs"):
        comp = zodiac_table(natal["utc"], location["lat"], location["lon"], ayanamsa, "Ascendant" in natal["points"])
        moved = [r["Point"] for r in comp if r["Changes sign"]]
        st.write(f"{len(moved)} of {len(comp)} placements change sign between tropical and sidereal"
                 + (f": {', '.join(moved)}." if moved else "."))
        st.dataframe(pd.DataFrame(comp), hide_index=True)

    extras = vedic_birth_extras(ayanamsa, bdate, birth_time, window, offset_s, location["lat"],
                                location["lon"], constraint_key, location["tz"])
    bt = dict(zip(BIRTH_TABS, st.tabs(BIRTH_TABS)))
    with bt["Charts"]:
        render_charts(extras, natal, vs)
    with bt["Ashtakavarga"]:
        render_ashtakavarga(report["ashtakavarga"], vs)
    with bt["Yogas"]:
        render_yogas(extras["yogas"])
    with bt["Strength"]:
        render_strength(extras["strength"])
    with bt["Birth panchanga"]:
        st.dataframe(pd.DataFrame(extras["panchanga"]), hide_index=True)
        st.caption("The Vedic day (vara) runs from sunrise to sunrise, so a birth before sunrise belongs to "
                   "the previous weekday. Limbs marked 'no' change within your birth-time window.")
    with bt["Match making"]:
        render_matching(natal)

    st.divider()
    st.header(label)
    d = report["dasha"]
    o1, o2, o3 = st.columns(3)
    o1.metric("Gochara (transits)", report["overall"],
              help="Time-weighted share of grahas in their favourable houses from your Moon (vedha "
                   "obstructions count as neutral), compared with what is typical.")
    o2.metric("Dasha", f"{d['md']}–{d['ad']}" if d["md"] else "—")
    sat = report["saturn"]
    o3.metric("Saturn", sat["status"] or "Clear")
    if d["alternatives"]:
        st.caption(f"With your birth-time uncertainty the dasha could also be {', '.join(d['alternatives'])}.")
    if d["md"]:
        st.write(f"**{d['md']} mahadasha** ({fmt_date(d['md_span'][0])} – {fmt_date(d['md_span'][1])}), "
                 f"**{d['ad']} antardasha** ({fmt_date(d['ad_span'][0])} – {fmt_date(d['ad_span'][1])}).")
    if sat["status"] == "Sade Sati":
        st.info(f"**Sade Sati, {sat['phase']} phase.** Saturn is transiting the {vd.ordinal(sat['house'])} "
                f"sign from your Moon. The 7½-year period runs about {fmt_date(sat['start'])} – "
                f"{fmt_date(sat['end'])} (retrograde exits included). Traditionally a time of pressure, "
                f"responsibility and slow, lasting change.")
    elif sat["status"]:
        st.info(f"**{sat['status']}**: Saturn in the {vd.ordinal(sat['house'])} from your Moon, about "
                f"{fmt_date(sat['start'])} – {fmt_date(sat['end'])}. Traditionally a testing transit.")
    elif sat.get("next_sade_sati"):
        st.caption(f"No Sade Sati now. The next one begins around {sat['next_sade_sati']:%B %Y}.")
    for dr in report["drishti"]:
        st.write(f"- **{dr['Graha']}** casts its {dr['Aspect']} aspect on your **{dr['Falls on your']}** "
                 f"({dr['Nature']}).")

    tabs = ["Gochara", "Key dates", "Panchanga"] + (["Tara bala"] if report["tara"] else []) + \
        ["Eclipses", "Sky positions"]
    tab_objs = dict(zip(tabs, st.tabs(tabs)))
    with tab_objs["Gochara"]:
        st.caption("Each graha's sign, counted from your Moon sign (and Lagna), with the classical verdict. "
                   "Vedha: a favourable transit is blocked when another graha sits in its obstruction house. "
                   "Bindus: the graha's own Ashtakavarga points in that sign (4+ supports it, 0–3 weakens it); "
                   "SAV: the sign's total (28+ is strong).")
        st.dataframe(pd.DataFrame([{
            "": TONE_ICON[g["tone"]], "Graha": g["Graha"], "Sign": g["Transit sign"],
            "From Moon": g["From Moon"], "From Lagna": g["From Lagna"], "Verdict": g["Verdict"],
            "Bindus": g["Bindus"], "Bindu support": g["Bindu support"], "SAV": g["SAV"],
            "About": g["Theme"],
            "When": f"{fmt_when(g['When'][0], days)} – {fmt_when(g['When'][1], days)}"} for g in report["gochara"]]),
            hide_index=True)
    with tab_objs["Panchanga"]:
        pl = panch_place or location
        with st.spinner("Working out each day's panchanga…"):
            prow = daily_panchanga(ayanamsa, p_start, p_end, pl["lat"], pl["lon"], pl["tz"],
                                   vs["janma_nak_idx"], vs["moon_sign"])
        st.caption(f"For {pl['name'].split(',')[0]}, times in {pl['tz']}. Limbs are taken at sunrise, with the "
                   f"time each one ends. **For you** combines tara bala and chandra bala (from your birth "
                   f"nakshatra and Moon sign) with the general cautions.")
        st.dataframe(pd.DataFrame([{
            **{k: v for k, v in r.items() if k not in ("Sunrise", "Sunset", "Date")},
            "Date": r["Date"].strftime("%a %d %b %Y"),
            "Sunrise": r["Sunrise"].strftime("%H:%M") if r.get("Sunrise") else "—",
            "Sunset": r["Sunset"].strftime("%H:%M") if r.get("Sunset") else "—"} for r in prow]),
            hide_index=True, column_order=["Date", "For you", "Vara", "Sunrise", "Sunset", "Tithi", "Tithi until",
                                           "Nakshatra", "Nakshatra until", "Yoga", "Karana", "Rahu Kaal",
                                           "Yamaganda", "Gulika", "Tara", "Chandra bala", "General cautions"])
    if "Tara bala" in tab_objs:
        with tab_objs["Tara bala"]:
            st.caption("Tara bala counts the Moon's daily nakshatra from your birth nakshatra; Chandra bala "
                       "checks the Moon's sign from your Moon sign. Used to pick good days.")
            st.dataframe(pd.DataFrame([{
                "From": fmt_when(t["From"], 1), "To": fmt_when(t["To"], 1), "Moon in": t["Moon nakshatra"],
                "Tara": f"{t['Tara']} ({t['Tara quality']})", "Chandra bala": t["Chandra bala"]}
                for t in report["tara"]]), hide_index=True)
    with tab_objs["Eclipses"]:
        if report["eclipses"]:
            st.dataframe(pd.DataFrame([{
                "Date": fmt_date(e["when"]), "Grahan": f"{e['type']} {e['kind'].lower()}",
                "Position": ae.fmt_pos(e["lon"]),
                "Nakshatra": vd.nakshatra_of(e["lon"])[0],
                "Notes": "; ".join(e["notes"]) or "—"} for e in report["eclipses"]]), hide_index=True)
        else:
            st.info("No eclipses in this period. Try a longer range (eclipse seasons come every ~6 months).")
    with tab_objs["Sky positions"]:
        st.caption("Where the grahas are at the middle of the period (sidereal).")
        st.dataframe(pd.DataFrame(report["sky"]), hide_index=True)
    events = report["events"]
    tab2 = tab_objs["Key dates"]

# ---- key dates (both systems) -------------------------------------------------
with tab2:
    if events:
        df = pd.DataFrame([{"When": fmt_when(e["when"], days),
                            "Event": f"{TONE_ICON[e['tone']]} {e['event']}",
                            "Meaning": e["meaning"]} for e in events])
        st.dataframe(df, hide_index=True)
        st.download_button("Download key dates (CSV)", df.to_csv(index=False).encode(),
                           file_name=f"astro_{label.replace(' ', '_').replace(',', '')}.csv", mime="text/csv")
    else:
        st.info("No exact contacts, sign changes, lunations or eclipses fall inside this period.")

st.divider()
st.caption("Planet positions are astronomically exact (Swiss Ephemeris, including precession). "
           "Readings are traditional astrological associations, not scientifically validated predictions.")
st.caption("Source code: [github.com/Mishil449861/Astro-Math](https://github.com/Mishil449861/Astro-Math). "
           "Uses the Swiss Ephemeris by Astrodienst AG via pyswisseph (AGPL-3.0). "
           "Place search © OpenStreetMap contributors.")
