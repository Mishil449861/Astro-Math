"""
Checks for the Vedic feature modules. Run:  python -m pytest tests
"""
import os
import random
import sys
from datetime import date, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ashtakavarga as avg  # noqa: E402
import astro_engine as ae  # noqa: E402
import matching  # noqa: E402
import panchanga  # noqa: E402
import strength  # noqa: E402
import vargas  # noqa: E402
import vedic as vd  # noqa: E402
import yogas  # noqa: E402

LAT, LON = 48.3986, 9.9911             # Ulm
OFF = ae.lmt_offset(LON)
SID = ae.Chart("sidereal")


def einstein(t=time(11, 30), window=0, constraints=None):
    return ae.compute_natal(SID, vd.GRAHAS, date(1879, 3, 14), t, window, OFF, LAT, LON, constraints)


# ---- item 1: what the person knows narrows the window ----------------------------
def test_known_nakshatra_and_lagna_narrow_unknown_time():
    n = einstein(None, constraints={"nakshatra": 17, "lagna_sign": 2})     # Jyeshtha, Gemini
    (a, b), = n["intervals"]
    real = einstein()["jd"]
    assert a < real < b
    assert (b - a) * 24 < 2.5                                              # down from 24 h
    assert n["signs"]["Ascendant"] == ["Gemini"] and n["signs"]["Moon"] == ["Scorpio"]


def test_moon_enters_jyeshtha_at_published_time():
    n = einstein(None, constraints={"nakshatra": 17})
    start = ae.from_jd(n["intervals"][0][0], "UTC") + OFF                   # Ulm local mean time
    assert (start.hour, start.minute) in ((1, 45), (1, 44))                 # PanchangBodh: 01:45


def test_contradiction_is_reported():
    try:
        einstein(constraints={"moon_sign": 0})                             # Moon was not in Aries
        raise AssertionError("expected BirthDataError")
    except ae.BirthDataError:
        pass


def test_fast_mercury_kept_with_wider_orb():
    # find a day when Mercury moves > 2°/day, then check an unknown birth time keeps it
    chart = ae.Chart("tropical")
    for d in range(400):
        day = date(2000, 1, 1).toordinal() + d
        n = ae.compute_natal(chart, ae.PLANETS, date.fromordinal(day), None, 0, OFF, LAT, LON)
        if n["spread"]["Mercury"] > ae.KEEP_SPREAD:
            assert "Mercury" in n["widened"]
            mid, half = n["widened"]["Mercury"]
            lo, hi = n["range"]["Mercury"]
            assert abs(ae._wrap(mid - lo)) <= half + 1e-6 and abs(ae._wrap(hi - mid)) <= half + 1e-6
            return
    raise AssertionError("no fast-Mercury day found")


# ---- item 2: divisional charts -----------------------------------------------------
def test_varga_rules_spot_checks():
    vs = vargas.varga_sign
    assert vs(0.0, 9) == 0 and vs(30.0, 9) == 9 and vs(60.0, 9) == 6        # Aries/Taurus/Gemini start
    assert vs(15.0, 2) == 3 and vs(45.0, 2) == 4                            # odd: Sun then Moon hora
    assert vs(35.0, 3) == 1 and vs(45.0, 3) == 5                            # Taurus 2nd decanate = Virgo
    assert vs(31.0, 10) == 9                                                # even sign starts from 9th
    assert vs(4.9, 30) == 0 and vs(34.9, 30) == 1 and vs(44.0, 30) == 11    # Parashari trimshamsha
    for d in vargas.VARGAS:                                                 # every varga returns 0–11
        for _ in range(200):
            assert 0 <= vs(random.uniform(0, 360), d) < 12


def test_d9_lagna_needs_precise_time():
    tol = vargas.time_tolerance(SID, einstein()["jd"], LAT, LON, vd.GRAHAS["Moon"])
    assert min(tol[9]) < 15 and min(tol[60]) < 3 and min(tol[1]) > 30


# ---- item 3: Ashtakavarga and panchanga ---------------------------------------------
def test_ashtakavarga_totals_are_fixed():
    rnd = random.Random(3)
    for _ in range(50):
        signs = {c: rnd.randrange(12) for c in avg.CONTRIBUTORS}
        b = avg.bav(signs)
        assert {p: sum(b[p]) for p in b} == avg.BAV_TOTALS
        assert sum(avg.sav(b)) == 337


def test_unknown_lagna_gives_ranges_not_wrong_numbers():
    av = vd.natal_ashtakavarga(einstein(None))
    exact = vd.natal_ashtakavarga(einstein())
    for p in avg.PLANETS7:
        for i in range(12):
            lo, hi = av["bav"][p][i]
            assert lo <= exact["bav"][p][i][0] <= hi


def test_panchanga_new_moon_and_sunrise():
    rows = panchanga.daily_panchanga(SID, date(2026, 2, 17), date(2026, 2, 18), 28.61, 77.21, "Asia/Kolkata")
    assert rows[0]["Tithi"].startswith("Amavasya")                          # new Moon 17 Feb 2026
    london = panchanga.daily_panchanga(SID, date(2026, 6, 21), date(2026, 6, 22), 51.5074, -0.1278,
                                       "Europe/London")[0]
    assert london["Sunrise"].strftime("%H:%M") in ("04:42", "04:43")         # published 04:43 BST
    assert london["Sunset"].strftime("%H:%M") in ("21:21", "21:22")


def test_einstein_birth_vara_is_friday():
    rows = {r["Limb"]: r["Value"] for r in panchanga.birth_panchanga(SID, einstein(), LAT, LON, "Europe/Berlin")}
    assert rows["Vara"].startswith("Shukravara")                            # 14 Mar 1879 was a Friday


# ---- item 4: regional clocks -----------------------------------------------------------
def test_regional_clocks():
    c = ae.check_birth_clock(date(1950, 5, 5), time(10), "Asia/Kolkata", 72.88, 19.07)
    assert c["default"] == "regional" and c["regional"]["name"] == "Bombay Time" and not c["regional"]["notes"]
    assert ae.check_birth_clock(date(1955, 6, 1), time(10), "Asia/Kolkata", 72.88, 19.07)["regional"]["notes"]
    assert ae.check_birth_clock(date(1943, 1, 1), time(10), "Asia/Kolkata", 72.88, 19.07)["regional"]["notes"]
    assert ae.check_birth_clock(date(1930, 1, 1), time(10), "Asia/Kolkata", 88.36, 22.57)["regional"]["name"] == "Calcutta Time"
    assert ae.check_birth_clock(date(1950, 1, 1), time(10), "Asia/Kolkata", 77.21, 28.61)["regional"] is None
    assert ae.check_birth_clock(date(1960, 1, 1), time(10), "Asia/Kolkata", 72.88, 19.07)["regional"] is None


# ---- item 5: matching, yogas, strength ----------------------------------------------------
def test_guna_milan_rules():
    m = matching.kootas(232.0, 232.0)                                       # same Moon
    assert m["scores"]["Nadi"] == 0 and m["scores"]["Bhakoot"] == 7 and m["scores"]["Yoni"] == 4
    # 6/8 Moon signs -> Bhakoot 0
    assert matching.kootas(5.0, 155.0)["scores"]["Bhakoot"] == 0
    # enemy yonis score 0: Ashwini (Horse) vs Swati (Buffalo)
    assert matching.kootas(5.0, 190.0)["scores"]["Yoni"] == 0
    for a in range(len(matching.YONI_POINTS)):                               # matrix is symmetric
        for b in range(len(matching.YONI_POINTS)):
            assert matching.YONI_POINTS[a][b] == matching.YONI_POINTS[b][a]
    rnd = random.Random(5)
    for _ in range(300):
        t = matching.kootas(rnd.uniform(0, 360), rnd.uniform(0, 360))["total"]
        assert 0 <= t <= 36


def test_einstein_yogas():
    names = {r["Yoga"] for r in yogas.evaluate(einstein())["rows"]}
    assert "Malavya" in names                    # Venus exalted in Pisces, 10th from a Gemini Lagna
    assert "Budha-Aditya" in names               # Sun and Mercury both in Pisces
    assert "Neecha Bhanga Raja" in names         # debilitated Mercury / Moon with cancellation


def test_strength_runs_and_ranks():
    rows = strength.strengths(SID, einstein(), LAT, LON)
    assert sorted(r["Rank"] for r in rows) == list(range(1, 8))
    venus = next(r for r in rows if r["Planet"] == "Venus")
    assert venus["Uchcha"] > 55                  # Venus at 24°49′ Pisces, near its 27° exaltation
