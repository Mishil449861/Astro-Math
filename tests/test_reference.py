"""
Reference checks against published data. Run:  python -m pytest tests
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import astro_engine as ae  # noqa: E402
import vedic as vd  # noqa: E402

E_LAT, E_LON = 48.3986, 9.9911  # Ulm


def arcmin(a, b):
    return abs(ae._wrap(a - b)) * 60


def dms(deg, minute, sign):
    return ae.SIGNS.index(sign) * 30 + deg + minute / 60


def einstein(chart, planets, t=time(11, 30), window=0):
    off = ae.check_birth_clock(date(1879, 3, 14), t, "Europe/Berlin", E_LON)["lmt_offset"]
    return ae.compute_natal(chart, planets, date(1879, 3, 14), t, window, off, E_LAT, E_LON)


def test_einstein_tropical_matches_published():
    n = einstein(ae.Chart("tropical"), ae.PLANETS)["points"]
    # Astrotheme / Astro-Databank, Rodden AA
    assert arcmin(n["Sun"], dms(23, 30, "Pisces")) < 2
    assert arcmin(n["Moon"], dms(14, 32, "Sagittarius")) < 2
    assert arcmin(n["Ascendant"], dms(11, 38, "Cancer")) < 3
    assert arcmin(n["Midheaven"], dms(12, 50, "Pisces")) < 3


def test_einstein_lmt_beats_database_offset():
    clk = ae.check_birth_clock(date(1879, 3, 14), time(11, 30), "Europe/Berlin", E_LON)
    assert clk["mean_time"] and clk["abbr"] == "LMT"          # Berlin's mean time, not Ulm's
    assert abs(clk["gap_minutes"] - 13.5) < 0.5
    chart, published = ae.Chart("tropical"), dms(11, 38, "Cancer")
    asc = {k: ae.compute_natal(chart, ae.PLANETS, date(1879, 3, 14), time(11, 30), 0, clk[k], E_LAT, E_LON)
           ["points"]["Ascendant"] for k in ("db_offset", "lmt_offset")}
    assert arcmin(asc["lmt_offset"], published) < 3
    assert arcmin(asc["db_offset"], published) > 150                 # ~2°50′ off with the database


def test_einstein_vedic_matches_published():
    chart = ae.Chart("sidereal")
    n = einstein(chart, vd.GRAHAS)
    s = vd.natal_summary(n)
    assert (s["nakshatra"], s["pada"]) == ("Jyeshtha", 2)
    assert abs(n["points"]["Moon"] - (210 + 22.36)) < 0.05          # PanchangBodh, Lahiri
    assert ae.sign_of(n["points"]["Ascendant"]) == "Gemini"
    first = s["dashas"][0]
    assert first["lord"] == "Mercury"
    end = ae.from_jd(first["end"], "UTC").date()
    assert abs((end - date(1888, 12, 12)).days) <= 3                 # published: 12 Dec 1888
    assert [m["lord"] for m in s["dashas"][1:4]] == ["Ketu", "Venus", "Sun"]
    assert n["ayanamsa"] == chart.ayanamsa(n["jd"])                   # the true (applied) ayanamsa


def test_rahu_is_mean_node():
    chart = ae.Chart("sidereal")
    jd = ae.to_jd(datetime(2000, 6, 1, tzinfo=timezone.utc))
    assert abs(chart.pos(jd, vd.GRAHAS["Rahu"])[0] - chart.pos(jd, ae.swe.MEAN_NODE)[0]) < 1e-9
    assert abs(ae._wrap(chart.pos(jd, vd.GRAHAS["Ketu"])[0] - chart.pos(jd, vd.GRAHAS["Rahu"])[0])) == 180


def test_2026_eclipses():
    ecl = ae.find_eclipses(ae.Chart("tropical"), ae.to_jd(datetime(2026, 1, 1, tzinfo=timezone.utc)),
                           ae.to_jd(datetime(2027, 1, 1, tzinfo=timezone.utc)))
    got = [(e["kind"], e["type"], ae.from_jd(e["jd"], "UTC").date()) for e in ecl]
    assert got == [("Solar", "Annular", date(2026, 2, 17)), ("Lunar", "Total", date(2026, 3, 3)),
                   ("Solar", "Total", date(2026, 8, 12)), ("Lunar", "Partial", date(2026, 8, 28))]
    # Lunar eclipse of 3 Mar 2026: Moon in Virgo, i.e. at the South Node
    assert ecl[1]["near_node"].startswith("South")


def test_transit_series_covers_retrograde_passes():
    """A slow-planet transit inside one month must report its whole multi-pass series."""
    chart = ae.Chart("tropical")
    natal = einstein(chart, ae.PLANETS)
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    r = ae.analyze(chart, natal, start, start + timedelta(days=30), "UTC")
    multi = [i for i in r["influences"] if len(i["passes"]) > 1]
    assert multi, "expected at least one retrograde triple pass"
    for i in multi:
        assert i["start"] < start and i["end"] > start + timedelta(days=30) or i["exact"]
        assert not i["open_start"] and not i["open_end"]


def test_unknown_time_never_invents_influences():
    chart = ae.Chart("tropical")
    exact = einstein(chart, ae.PLANETS)
    off = exact["utc_offset"]
    unknown = ae.compute_natal(chart, ae.PLANETS, date(1879, 3, 14), None, 0, off, E_LAT, E_LON)
    start = datetime(1919, 5, 1, tzinfo=timezone.utc)
    a = ae.analyze(chart, exact, start, start + timedelta(days=31), "UTC")
    b = ae.analyze(chart, unknown, start, start + timedelta(days=31), "UTC")
    key = lambda i: i["title"].replace(" (retrograde)", "")
    assert {key(i) for i in b["influences"]} <= {key(i) for i in a["influences"]}


def test_dst_checks():
    # 2021-03-14 02:30 never happened in New York; 2021-11-07 01:30 happened twice
    gap = ae.check_birth_clock(date(2021, 3, 14), time(2, 30), "America/New_York", -74.0)
    twice = ae.check_birth_clock(date(2021, 11, 7), time(1, 30), "America/New_York", -74.0)
    assert gap["nonexistent"] and not gap["ambiguous"]
    assert twice["ambiguous"] and twice["db_offset"] != twice["db_offset_alt"]


def test_merged_zone_is_flagged():
    assert ae.zone_history_note("Europe/Oslo")          # pre-1970 history copied from Berlin
    assert ae.zone_history_note("Asia/Kolkata") is None


def test_custom_range_limits():
    s, e, _ = ae.period_bounds("Custom", date(2026, 1, 1), "UTC", date(2026, 12, 31))
    assert (e - s).days == 365
    try:
        ae.period_bounds("Custom", date(2026, 1, 1), "UTC", date(2027, 6, 1))
        raise AssertionError("expected a ValueError")
    except ValueError:
        pass
