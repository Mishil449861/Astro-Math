"""
Astro calendar — Streamlit app

Run:
  pip install streamlit pyswisseph pandas geopy timezonefinder
  streamlit run app.py
(keep astro_engine.py in the same folder)
"""
import calendar
from datetime import date, time, timedelta
from zoneinfo import available_timezones

import pandas as pd
import streamlit as st

from astro_engine import (NATAL_AREAS, SIGN_KEYWORDS, SIGN_SYMBOLS, Chart, analyze,
                          compute_natal, fmt_pos, period_bounds, sign_of)

st.set_page_config(page_title="Astro Calendar", page_icon="🔭", layout="centered")

TONE_ICON = {"supportive": "🟢", "challenging": "🔴", "neutral": "🟣"}


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
def run_reading(bdate, btime, tz, lat, lon, system, kind, anchor, view_tz):
    chart = Chart("sidereal" if system.startswith("Vedic") else "tropical")
    natal = compute_natal(chart, bdate, btime, tz, lat, lon)
    start, end, label = period_bounds(kind, anchor, view_tz)
    report = analyze(chart, natal, kind, start, end, view_tz)
    return natal, report, label


def fmt_when(dt, kind):
    return dt.strftime("%a %b %d, %I:%M %p") if kind == "Day" else dt.strftime("%a %b %d")


def fmt_window(inf, kind):
    if kind == "Day" or inf["body"] == "Moon":
        span = f"{inf['start']:%b %d %I:%M %p} – {inf['end']:%b %d %I:%M %p}"
    else:
        span = f"{inf['start']:%b %d, %Y} – {inf['end']:%b %d, %Y}"
    exact = ", ".join(e.strftime("%b %d") for e in inf["exact"])
    return f"In effect {span}" + (f" · exact {exact}" if exact else "")


# ---------------------------------------------------------------------------
# Step 1 — birth details
# ---------------------------------------------------------------------------
st.title("🔭 Astro Calendar")
st.write("Enter your birth details, then pick a **day, week or month** to see what the planets are doing for you.")

st.subheader("1 · Your birth details")
c1, c2 = st.columns(2)
bdate = c1.date_input("Date of birth", value=date(1995, 1, 1),
                      min_value=date(1900, 1, 1), max_value=date.today())
unknown_time = c2.checkbox("I don't know my birth time")
btime = c2.time_input("Time of birth", value=time(12, 0), step=300, disabled=unknown_time)
place = st.text_input("Place of birth", placeholder="City, country — e.g. Mumbai, India")

tz_list = sorted(available_timezones())
with st.expander("More options"):
    system = st.radio("Astrology system", ["Western (tropical)", "Vedic (sidereal, Lahiri)"], horizontal=True)
    view_tz_choice = st.selectbox("Show dates and times in", ["Birthplace timezone"] + tz_list)
    manual = st.checkbox("Enter birth location manually")
    if manual:
        m1, m2 = st.columns(2)
        m_lat = m1.number_input("Latitude", -90.0, 90.0, 40.7128, format="%.4f")
        m_lon = m2.number_input("Longitude (west is negative)", -180.0, 180.0, -74.0060, format="%.4f")
        m_tz = st.selectbox("Birth timezone", tz_list, index=tz_list.index("America/New_York"))

location = None
if manual:
    location = {"name": "Manual location", "lat": m_lat, "lon": m_lon, "tz": m_tz}
elif place.strip():
    with st.spinner("Looking up place…"):
        location, err = find_place(place.strip())
    if err:
        st.warning(err)
if location:
    st.caption(f"📍 {location['name']} · {location['lat']:.2f}, {location['lon']:.2f} · {location['tz']}")

# ---------------------------------------------------------------------------
# Step 2 — period
# ---------------------------------------------------------------------------
st.subheader("2 · Pick a time to look at")
kind = st.radio("Look at a", ["Day", "Week", "Month"], index=2, horizontal=True)
today = date.today()
if kind == "Day":
    anchor = st.date_input("Date", value=today, min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
elif kind == "Week":
    picked = st.date_input("Any day in the week", value=today,
                           min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
    monday = picked - timedelta(days=picked.weekday())
    st.caption(f"Week: {monday:%a %b %d} – {monday + timedelta(days=6):%a %b %d, %Y}")
    anchor = picked
else:
    p1, p2 = st.columns(2)
    months = list(calendar.month_name)[1:]
    month = p1.selectbox("Month", months, index=today.month - 1)
    year = p2.number_input("Year", min_value=1900, max_value=2100, value=today.year, step=1)
    anchor = date(int(year), months.index(month) + 1, 1)

if st.button("Show my reading", type="primary", disabled=location is None):
    st.session_state["started"] = True
if location is None:
    st.caption("Enter your place of birth to continue.")

if not (st.session_state.get("started") and location):
    st.stop()

# ---------------------------------------------------------------------------
# Results (recompute automatically when inputs change; cached)
# ---------------------------------------------------------------------------
view_tz = location["tz"] if view_tz_choice == "Birthplace timezone" else view_tz_choice
with st.spinner("Reading the sky…"):
    try:
        natal, report, label = run_reading(bdate, None if unknown_time else btime, location["tz"],
                                           location["lat"], location["lon"], system, kind, anchor, view_tz)
    except Exception as exc:  # show a friendly message instead of a stack trace
        st.error(f"Something went wrong while calculating: {exc}")
        st.stop()

st.divider()

# ---- birth chart summary -----------------------------------------------------
st.subheader("Your birth chart")
pts = natal["points"]
b1, b2, b3 = st.columns(3)
sun, moon = sign_of(pts["Sun"]), sign_of(pts["Moon"])
b1.metric("☀️ Sun · core self", f"{SIGN_SYMBOLS[sun]} {sun}")
b1.caption(SIGN_KEYWORDS[sun])
b2.metric("🌙 Moon · emotions", f"{SIGN_SYMBOLS[moon]} {moon}")
b2.caption(SIGN_KEYWORDS[moon] + ("" if natal["time_known"] else " (approximate: no birth time)"))
if natal["time_known"]:
    rising = sign_of(pts["Ascendant"])
    b3.metric("⬆️ Rising · first impression", f"{SIGN_SYMBOLS[rising]} {rising}")
    b3.caption(SIGN_KEYWORDS[rising])
else:
    b3.metric("⬆️ Rising", "—")
    b3.caption("Needs your birth time")

with st.expander("All birth placements"):
    rows = [{"Point": k, "Position": fmt_pos(v), "Area": NATAL_AREAS[k],
             "Retrograde": "℞" if natal["retro"].get(k) else ""} for k, v in pts.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    if natal["ayanamsa"] is not None:
        st.caption(f"Sidereal (Lahiri) — ayanamsa at birth {natal['ayanamsa']:.4f}°")

# ---- period reading --------------------------------------------------------------
st.divider()
st.header(f"📅 {label}")

word, icon = report["overall"]
o1, o2, o3 = st.columns(3)
o1.metric("Overall tone", f"{icon} {word}")
o2.metric("Intensity", report["intensity"])
o3.metric("Moon", f"{report['moon']['sign']}", report["moon"]["phase"], delta_color="off")

if report["areas"]:
    top = [a["Life area"].lower() for a in report["areas"][:2]]
    st.write(f"The strongest influences this {kind.lower()} touch your **{' and '.join(top)}**.")
    st.dataframe(
        pd.DataFrame(report["areas"]), hide_index=True,
        column_config={"Focus": st.column_config.ProgressColumn("Focus", min_value=0, max_value=1, format=" ")},
    )
else:
    st.write(f"No major planetary contacts to your chart this {kind.lower()}: a quiet stretch.")

tab1, tab2, tab3 = st.tabs(["Main influences", "Key dates", "Sky positions"])

with tab1:
    if not report["influences"]:
        st.info("Nothing significant in this period.")
    st.caption("🟢 supportive · 🔴 challenging · 🟣 spotlight. Longer-lasting influences are listed first.")
    def card(inf):
        with st.container(border=True):
            st.markdown(f"{TONE_ICON[inf['tone']]} **{inf['title']}**")
            st.write(inf["meaning"])
            st.caption(fmt_window(inf, kind))

    TOP_N = 6
    for inf in report["influences"][:TOP_N]:
        card(inf)
    rest = report["influences"][TOP_N:]
    if rest:
        with st.expander(f"Show {len(rest)} smaller influences"):
            for inf in rest:
                card(inf)

with tab2:
    if report["events"]:
        df = pd.DataFrame([{"When": fmt_when(e["when"], kind),
                            "Event": f"{TONE_ICON[e['tone']]} {e['event']}",
                            "Meaning": e["meaning"]} for e in report["events"]])
        st.dataframe(df, hide_index=True)
        st.download_button("Download key dates (CSV)", df.to_csv(index=False).encode(),
                           file_name=f"astro_{label.replace(' ', '_').replace(',', '')}.csv", mime="text/csv")
    else:
        st.info("No exact contacts, sign changes or lunations fall inside this period.")

with tab3:
    st.caption("Where the planets are at the middle of the period.")
    st.dataframe(pd.DataFrame(report["sky"]), hide_index=True)

st.divider()
st.caption("Planet positions are astronomically exact (Swiss Ephemeris, including precession). "
           "Readings are traditional astrological associations, not scientifically validated predictions.")
