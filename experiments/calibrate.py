"""
Calibrate the Low / Moderate / High intensity cut points (Western) and the
Favourable / Mixed / Challenging score cut points (Vedic).

Random birth charts (1940–2005, random time, a spread of cities) are read over
random periods (2020–2030) of several lengths. For each length we report the
tertiles of
  * Western: total influence weight per usable natal point, with the birth time
    known and with it unknown — to check that normalising per point removes the
    bias against unknown birth times;
  * Vedic: the gochara score.

Run:  python experiments/calibrate.py [n_charts]
"""
import os
import random
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import astro_engine as ae  # noqa: E402
import vedic as vd  # noqa: E402

CITIES = [(40.71, -74.01), (51.51, -0.13), (19.08, 72.88), (28.61, 77.21), (35.68, 139.69),
          (-33.87, 151.21), (-23.55, -46.63), (55.76, 37.62), (30.04, 31.24), (6.52, 3.38),
          (34.05, -118.24), (48.86, 2.35), (1.35, 103.82), (59.33, 18.07), (-34.60, -58.38)]
LENGTHS = [1, 7, 30, 91, 182, 365]


def one_chart(seed: int):
    rng = random.Random(seed)
    bdate = date(1940, 1, 1) + timedelta(days=rng.randrange(65 * 365))
    btime = time(rng.randrange(24), rng.randrange(60))
    lat, lon = rng.choice(CITIES)
    off = timedelta(0)  # birth time treated as UTC: the offset doesn't matter for calibration
    trop, sid = ae.Chart("tropical"), ae.Chart("sidereal")
    known = ae.compute_natal(trop, ae.PLANETS, bdate, btime, 0, off, lat, lon)
    unknown = ae.compute_natal(trop, ae.PLANETS, bdate, None, 0, off, lat, lon)
    vnat = ae.compute_natal(sid, vd.GRAHAS, bdate, btime, 0, off, lat, lon)
    out = []
    for days in LENGTHS:
        anchor = date(2020, 1, 1) + timedelta(days=rng.randrange(10 * 365))
        start = datetime.combine(anchor, time(0), tzinfo=timezone.utc)
        end = start + timedelta(days=days)
        k = ae.analyze(trop, known, start, end, "UTC")
        u = ae.analyze(trop, unknown, start, end, "UTC")
        v = vd.analyze_vedic(sid, vnat, start, end, "UTC")
        out.append((days, k["per_point"], u["per_point"],
                    sum(i["weight"] for i in k["influences"]), sum(i["weight"] for i in u["influences"]),
                    v["score"]))
    return out


def tertiles(xs):
    q = statistics.quantiles(xs, n=3)
    return round(q[0], 2), round(q[1], 2)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    with ProcessPoolExecutor() as ex:
        results = [row for rows in ex.map(one_chart, range(n)) for row in rows]
    print(f"{n} random charts\n")
    print(f"{'days':>5} | {'per point, time known':>22} | {'per point, time unknown':>24} | "
          f"{'raw total known':>16} | {'raw total unknown':>18} | {'vedic score':>14}")
    for days in LENGTHS:
        rows = [r for r in results if r[0] == days]
        cols = [tertiles([r[i] for r in rows]) for i in range(1, 6)]
        print(f"{days:>5} | {str(cols[0]):>22} | {str(cols[1]):>24} | {str(cols[2]):>16} | "
              f"{str(cols[3]):>18} | {str(cols[4]):>14}")
    pooled = tertiles([r[5] for r in results])
    print(f"\nVedic score tertiles, all lengths pooled: {pooled}")
    k = [r[1] for r in results]
    u = [r[2] for r in results]
    print(f"Mean per-point, known {statistics.mean(k):.2f} vs unknown {statistics.mean(u):.2f}")


if __name__ == "__main__":
    main()
