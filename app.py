"""
Streamlit front end for astro_timeline.py

Run:
  pip install streamlit pyswisseph pandas
  streamlit run app.py
(keep astro_timeline.py in the same folder)
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, available_timezones

import pandas as pd
import streamlit as st
import swisseph as swe

from astro_timeline import (
    AYANAMSAS, PLANETS, SIGNS, Ephemeris, find_ingresses, find_stations,
    find_transits, fmt_lon, jd_to_str, to_jd,
)

st.set_page_config(page_title="Astro Timeline", page_icon="✨", layout="wide")
st.title("✨ Birth chart & transit timeline")
st.caption("Positions are computed with the Swiss Ephemeris (precession and nutation included). "
           "Meanings are traditional astrological associations, not validated predictions.")

# ---- Sidebar inputs ----------------------------------------------------------
with st.sidebar:
    st.header("Birth data")
    b_date = st.date_input("Birth date", value=date(1990, 6, 15),
                           min_value=date(1800, 1, 1), max_value=date(2100, 12, 31))
    b_time = st.time_input("Birth time (local)", value=time(14, 30), step=60)
    tz_list = sorted(available_timezones())
    tz = st.selectbox("Birth timezone", tz_list, index=tz_list.index("America/New_York"))
    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", value=40.71, min_value=-90.0, max_value=90.0, format="%.4f")
    lon = c2.number_input("Longitude", value=-74.01, min_value=-180.0, max_value=180.0, format="%.4f",
                          help="East positive, west negative")

    st.header("Zodiac")
    zodiac = st.radio("System", ["tropical", "sidereal"], horizontal=True)
    ayanamsa = st.selectbox("Ayanamsa", list(AYANAMSAS), disabled=(zodiac == "tropical"))

    st.header("Timeline range")
    today = date.today()
    rng = st.date_input("From / to (past or future)",
                        value=(today, today + timedelta(days=365)),
                        min_value=date(1000, 1, 1), max_value=date(2999, 12, 31))

    st.header("Include")
    want_transits = st.checkbox("Transits to natal chart", value=True)
    want_stations = st.checkbox("Retrograde / direct stations", value=True)
    want_ingress = st.checkbox("Sign ingresses", value=False)

    run = st.button("Compute", type="primary", use_container_width=True)


# ---- Computation (cached) ----------------------------------------------------
@st.cache_data(show_spinner=False)
def compute(b_iso, tz, lat, lon, zodiac, ayanamsa, start_iso, end_iso,
            want_transits, want_stations, want_ingress):
    eph = Ephemeris(zodiac == "sidereal", ayanamsa)

    birth_local = datetime.fromisoformat(b_iso).replace(tzinfo=ZoneInfo(tz))
    jd_birth = to_jd(birth_local.astimezone(timezone.utc))

    natal = {n: eph.pos(jd_birth, b)[0] for n, b in PLANETS.items()}
    natal["Ascendant"], natal["Midheaven"] = eph.angles(jd_birth, lat, lon)
    retro = {n: eph.pos(jd_birth, b)[1] < 0 for n, b in PLANETS.items()}

    natal_rows = [{
        "Point": n,
        "Position": fmt_lon(l),
        "Sign": SIGNS[int(l // 30)],
        "Longitude°": round(l, 4),
        "Retrograde": "℞" if retro.get(n) else "",
    } for n, l in natal.items()]

    ayan = swe.get_ayanamsa_ut(jd_birth) if zodiac == "sidereal" else None

    jd0 = to_jd(datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc))
    jd1 = to_jd(datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc))

    events = []
    if want_transits:
        events += find_transits(eph, natal, jd0, jd1)
    if want_stations:
        events += find_stations(eph, jd0, jd1)
    if want_ingress:
        events += find_ingresses(eph, jd0, jd1)
    events.sort(key=lambda e: e["jd"])

    event_rows = [{
        "Date (UT)": jd_to_str(e["jd"]),
        "Type": e["type"],
        "Event": e["event"],
        "Traditional meaning": e["meaning"],
        "Transiting body": e["event"].split(" ")[0],
    } for e in events]

    return natal_rows, event_rows, ayan


# ---- Output ------------------------------------------------------------------
if not isinstance(rng, (list, tuple)) or len(rng) != 2:
    st.info("Pick both a start and an end date in the sidebar.")
    st.stop()

if run or "results" in st.session_state:
    if run:
        start, end = rng
        if end <= start:
            st.error("End date must be after start date.")
            st.stop()
        if (end - start).days > 365 * 20:
            st.warning("Long ranges take a while — consider 20 years or less.")
        with st.spinner("Calculating planetary positions…"):
            st.session_state["results"] = compute(
                datetime.combine(b_date, b_time).isoformat(), tz, lat, lon, zodiac, ayanamsa,
                start.isoformat(), end.isoformat(), want_transits, want_stations, want_ingress)
            st.session_state["label"] = zodiac + (f" · {ayanamsa}" if zodiac == "sidereal" else "")

    natal_rows, event_rows, ayan = st.session_state["results"]

    left, right = st.columns([1, 2])

    with left:
        st.subheader(f"Natal chart ({st.session_state['label']})")
        if ayan is not None:
            st.metric("Ayanamsa at birth", f"{ayan:.4f}°")
        st.dataframe(pd.DataFrame(natal_rows), hide_index=True, use_container_width=True)

    with right:
        st.subheader(f"Timeline — {len(event_rows)} events")
        df = pd.DataFrame(event_rows)
        if df.empty:
            st.info("No events in this range with the selected options.")
        else:
            f1, f2, f3 = st.columns(3)
            types = f1.multiselect("Type", sorted(df["Type"].unique()), default=sorted(df["Type"].unique()))
            bodies = f2.multiselect("Planet", sorted(df["Transiting body"].unique()),
                                    default=sorted(df["Transiting body"].unique()))
            query = f3.text_input("Search", placeholder="e.g. Saturn, Venus, square")

            view = df[df["Type"].isin(types) & df["Transiting body"].isin(bodies)]
            if query:
                mask = view.apply(lambda r: query.lower() in " ".join(map(str, r)).lower(), axis=1)
                view = view[mask]

            # events per month chart
            months = pd.to_datetime(view["Date (UT)"].str[:10]).dt.to_period("M").astype(str)
            if not view.empty:
                st.bar_chart(months.value_counts().sort_index(), height=180)

            st.dataframe(view.drop(columns=["Transiting body"]), hide_index=True,
                         use_container_width=True, height=520)

            st.download_button("Download CSV", view.to_csv(index=False).encode(),
                               file_name="astro_timeline.csv", mime="text/csv")
else:
    st.info("Enter birth data in the sidebar and press **Compute**.")
