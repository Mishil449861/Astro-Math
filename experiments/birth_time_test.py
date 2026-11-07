"""
Birth-time experiment on real, publicly documented charts.

Albert Einstein — 14 Mar 1879, 11:30 local mean time, Ulm (48.3986 N, 9.9911 E).
  Rodden rating AA (Ulm civil birth register, entry 224). Published tropical chart
  (Astrotheme / Astro-Databank data): Asc 11°38′ Cancer, MC 12°50′ Pisces,
  Moon 14°32′ Sagittarius. Published Lahiri chart (PanchangBodh): Lagna ≈19.6° Gemini,
  Moon 22.36° Scorpio, Jyeshtha pada 2, Mercury dasha balance to Dec 1888.

Mohandas K. Gandhi — 2 Oct 1869, Porbandar (21.6417 N, 69.6293 E).
  The time is disputed: 07:45 LMT (traditional) vs 07:08 (Starkman rectification,
  Rodden C). A good test of the "approximate time" option.

The experiment pretends we know less and less about Einstein's birth time and checks
what the app still reports, compared with the reading from the recorded time.

Run:  python experiments/birth_time_test.py
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import astro_engine as ae  # noqa: E402
import vedic as vd  # noqa: E402

E_DATE, E_TIME, E_LAT, E_LON, E_TZ = date(1879, 3, 14), time(11, 30), 48.3986, 9.9911, "Europe/Berlin"
G_DATE, G_LAT, G_LON, G_TZ = date(1869, 10, 2), 21.6417, 69.6293, "Asia/Kolkata"

PERIODS = {  # (label, start, end-inclusive)
    "Nov 1915 (general relativity field equations)": (date(1915, 11, 1), date(1915, 11, 30)),
    "May 1919 (eclipse that confirmed relativity)": (date(1919, 5, 1), date(1919, 5, 31)),
    "1921 (Nobel Prize year)": (date(1921, 1, 1), date(1921, 12, 31)),
}


def key(inf):
    return inf["title"].replace(" (retrograde)", "")


def reading(chart, natal, start, end):
    s = datetime.combine(start, time(0), tzinfo=timezone.utc)
    e = datetime.combine(end + timedelta(days=1), time(0), tzinfo=timezone.utc)
    return ae.analyze(chart, natal, s, e, "UTC")


def section(title):
    print("\n" + title + "\n" + "-" * len(title))


def main():
    trop, sid = ae.Chart("tropical"), ae.Chart("sidereal")

    # ------------------------------------------------------------------ 1
    section("1. Old-date clock check (Einstein)")
    clk = ae.check_birth_clock(E_DATE, E_TIME, E_TZ, E_LON)
    print(f"Database offset for {E_TZ} on {E_DATE}: {ae.fmt_offset(clk['db_offset'])} ({clk['abbr']})")
    print(f"Local Mean Time at Ulm:                  {ae.fmt_offset(clk['lmt_offset'])}")
    for label, off in (("database", clk["db_offset"]), ("Ulm LMT", clk["lmt_offset"])):
        n = ae.compute_natal(trop, ae.PLANETS, E_DATE, E_TIME, 0, off, E_LAT, E_LON)
        print(f"  {label:9} -> Asc {ae.fmt_pos(n['points']['Ascendant'])}, MC {ae.fmt_pos(n['points']['Midheaven'])},"
              f" Moon {ae.fmt_pos(n['points']['Moon'])}   (published: Asc 11°38′ Cancer, MC 12°50′ Pisces,"
              f" Moon 14°32′ Sagittarius)")

    off = clk["lmt_offset"]
    vn = ae.compute_natal(sid, vd.GRAHAS, E_DATE, E_TIME, 0, off, E_LAT, E_LON)
    vs = vd.natal_summary(vn)
    md0 = vs["dashas"][0]
    print(f"  Vedic: Lagna {ae.fmt_pos(vn['points']['Ascendant'])}, Moon {ae.fmt_pos(vn['points']['Moon'])},"
          f" {vs['nakshatra']} pada {vs['pada']}, first dasha {md0['lord']} ends "
          f"{ae.from_jd(md0['end'], 'UTC'):%d %b %Y}   (published: Lagna 19.57° Gemini, Moon 22.36° Scorpio,"
          f" Jyeshtha 2, Mercury to 12 Dec 1888)")

    # ------------------------------------------------------------------ 2
    section("2. How much birth-time precision does a reading need? (Einstein)")
    levels = [("exact", E_TIME, 0), ("±15 min", E_TIME, 15), ("±30 min", E_TIME, 30),
              ("±1 h", E_TIME, 60), ("±2 h", E_TIME, 120), ("±4 h", E_TIME, 240), ("unknown", None, 0)]
    natals = {name: ae.compute_natal(trop, ae.PLANETS, E_DATE, t, w, off, E_LAT, E_LON)
              for name, t, w in levels}
    print(f"{'certainty':10} | points dropped from timing      | Moon sign(s)              | Ascendant sign(s)")
    for name, _, _ in levels:
        n = natals[name]
        dropped = sorted(set(ae.PERSONAL_POINTS) - n["usable"])
        asc = " or ".join(n["signs"].get("Ascendant", ["(not computed)"]))
        print(f"{name:10} | {', '.join(dropped) or '-':31} | {' or '.join(n['signs']['Moon']):25} | {asc}")

    for plabel, (a, b) in PERIODS.items():
        print(f"\n  {plabel}")
        base = reading(trop, natals["exact"], a, b)
        base_keys = {key(i) for i in base["influences"]}
        print(f"  {'certainty':10} | influences | kept from exact | wrong extras | per-point | intensity")
        for name, _, _ in levels:
            r = reading(trop, natals[name], a, b)
            ks = {key(i) for i in r["influences"]}
            kept = len(ks & base_keys)
            print(f"  {name:10} | {len(ks):10} | {kept:3}/{len(base_keys):<3} {kept / max(len(base_keys), 1):5.0%}"
                  f"   | {len(ks - base_keys):12} | {r['per_point']:9.2f} | {r['intensity']}")

    # ------------------------------------------------------------------ 3
    section("3. Vedic dasha vs birth-time precision (Einstein)")
    for name, t, w in levels:
        n = ae.compute_natal(sid, vd.GRAHAS, E_DATE, t, w, off, E_LAT, E_LON)
        s = vd.natal_summary(n)
        shift = s["dasha_shift_days"]
        shift_txt = "0" if not n["window"] else ("lords differ" if shift == float("inf") else f"{shift / 30.44:.1f} months")
        cur = []
        for plabel, (a, b) in PERIODS.items():
            v = vd.analyze_vedic(sid, n, datetime.combine(a, time(0), tzinfo=timezone.utc),
                                 datetime.combine(b, time(0), tzinfo=timezone.utc), "UTC")
            d = v["dasha"]
            cur.append(f"{d['md']}–{d['ad']}" + (f" (or {', '.join(d['alternatives'])})" if d["alternatives"] else ""))
        print(f"{name:10} | nakshatra {' or '.join(s['nak_options']):18} | dasha dates can shift by {shift_txt:13} | "
              + " ; ".join(cur))

    # ------------------------------------------------------------------ 4
    section("4. A disputed birth time (Gandhi: 07:08 vs 07:45 local mean time)")
    clk = ae.check_birth_clock(G_DATE, time(7, 45), G_TZ, G_LON)
    print(f"Database offset for {G_TZ} on {G_DATE}: {ae.fmt_offset(clk['db_offset'])} ({clk['abbr']}),"
          f" Porbandar LMT {ae.fmt_offset(clk['lmt_offset'])} -> the database would be "
          f"{clk['gap_minutes']:.0f} minutes off for a local-time record")
    goff = clk["lmt_offset"]
    for label, t, w in (("07:08", time(7, 8), 0), ("07:45", time(7, 45), 0), ("07:27 ±20 min", time(7, 27), 20)):
        tn = ae.compute_natal(trop, ae.PLANETS, G_DATE, t, w, goff, G_LAT, G_LON)
        sn = ae.compute_natal(sid, vd.GRAHAS, G_DATE, t, w, goff, G_LAT, G_LON)
        s = vd.natal_summary(sn)
        print(f"  {label:14} tropical Asc {ae.fmt_pos(tn['points']['Ascendant']):18} "
              f"({' or '.join(tn['signs']['Ascendant'])}), usable for timing: {'Ascendant' in tn['usable']}; "
              f"Lagna {' or '.join(sn['signs']['Ascendant'])}; Moon {' or '.join(sn['signs']['Moon'])}, "
              f"{' or '.join(s['nak_options'])}; first dasha {s['dashas'][0]['lord']}")
    sn = ae.compute_natal(sid, vd.GRAHAS, G_DATE, time(7, 27), 20, goff, G_LAT, G_LON)
    v = vd.analyze_vedic(sid, sn, datetime(1930, 3, 12, tzinfo=timezone.utc),
                         datetime(1930, 4, 7, tzinfo=timezone.utc), "Asia/Kolkata")
    d = v["dasha"]
    print(f"  Salt March (12 Mar – 6 Apr 1930): dasha {d['md']}–{d['ad']}"
          + (f" (or {', '.join(d['alternatives'])})" if d["alternatives"] else "")
          + f"; Saturn: {v['saturn'].get('status') or 'no Sade Sati'}; gochara {v['overall']} ({v['score']:+.2f})")


if __name__ == "__main__":
    main()
