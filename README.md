# Astro Calendar

A free Streamlit app that turns a birth date, time and place into a personal astrology calendar for any day, week, month or custom date range, in **Western (tropical)** or **Vedic (sidereal)** astrology.

Planet positions come from the Swiss Ephemeris, so the astronomy is exact. The readings themselves are traditional astrological associations, not scientifically validated predictions.

## Features

**Both systems**
- Day, week, month or any custom range up to 366 days
- Eclipses (solar and lunar) with type, degree and node
- Retrograde stations, sign changes, New and Full Moons
- Birth-time certainty: *exact*, *approximate (± minutes)* or *unknown*. The app works out which parts of the chart that uncertainty affects and leaves out, or marks, anything it can't be sure of.
- "Already know part of your chart?": enter a known Moon sign, nakshatra, pada or ascendant from a family horoscope, and the app narrows the possible birth time to match.
- Old birth dates: shows the UTC offset it will use as you type, and offers local mean time, the regional clocks of Bombay and Calcutta, or an offset you enter yourself.

**Western (tropical)**
- Transits to your personal points, covering the whole transit including every pass of a retrograde loop
- Low / Moderate / High intensity, calibrated on random charts so it's fair with or without a birth time

**Vedic (sidereal)**
- Lahiri, Raman or KP ayanamsa; Rahu and Ketu as mean nodes
- Nakshatra and pada, whole-sign houses, North and South Indian chart diagrams
- All 16 divisional charts (D1–D60), each marked reliable or uncertain, with a *time margin* showing how far the birth time can be off before that chart changes
- Vimshottari dasha (mahadasha and antardasha)
- Gochara from the Moon with vedha (obstruction) and Ashtakavarga bindus
- Sade Sati, Ashtama and Kantaka Shani, with start and end dates
- Ashtakavarga (per-planet and Sarvashtakavarga)
- Daily panchanga: tithi, vara, nakshatra, yoga, karana, sunrise/sunset, Rahu Kaal, Yamaganda, Gulika, and a personal day rating from tara bala and chandra bala
- About 25 common yogas plus Kuja (Mangal) dosha
- Partial planetary strength (Shadbala)
- Guna Milan (Ashtakoota, 36 points) for match making

## Running it

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then enter a birth date, time and place. Everything else is optional.

To deploy on [Streamlit Community Cloud](https://streamlit.io/cloud), point it at this repository with `app.py` as the entry file.

## How accurate is it?

The calculations are checked against published data in `tests/`:

| Check | App | Published |
|---|---|---|
| Albert Einstein, Ascendant (birth register, Rodden AA) | 11°39′ Cancer | 11°38′ Cancer |
| Einstein, Midheaven / Moon | 12°50′ Pisces / 14°32′ Sagittarius | same |
| Einstein, Moon nakshatra and first dasha | Jyeshtha 2, Mercury to Dec 1888 | same |
| Einstein, Moon enters Jyeshtha | 01:45 | 01:45 |
| 2026 eclipses | 17 Feb, 3 Mar, 12 Aug, 28 Aug | same |
| London sunrise / sunset, 21 Jun 2026 | 04:42 / 21:21 | 04:43 / 21:21 |
| Ashtakavarga totals | 337 | 337 (fixed by the rules) |

What limits accuracy in practice is the **birth time**, not the maths:
- without a birth time, the Moon's sign is uncertain on about 44% of days and its nakshatra on about 96%;
- the navamsa (D9) Ascendant changes about every 13 minutes on average;
- the D60 Ascendant changes every couple of minutes.

The app shows these uncertainties rather than hiding them.

## Known limits

- **Strength is partial.** 7 of the Shadbala parts are left out because sources disagree on them, so the totals can't be compared with other software, and the classical "required strength" thresholds aren't applied.
- **Guna Milan:** the 1–3 point Yoni scores vary slightly between commentaries, and Nadi / Bhakoot cancellations are listed but not applied.
- **Yogas** use the common textbook versions, without the extra classical conditions (planet strength, combustion and so on).
- **Regional clocks** cover only Bombay and Calcutta, within 40 km of each city; towns near the edge get no automatic choice. The exact switch-over dates are unknown, so those years are flagged rather than decided.
- **Eclipses** are global dates; visibility from your location isn't checked.
- **Not modelled:** divisional-chart yogas, Rahu/Ketu aspects, dasha systems other than Vimshottari.

The app shows these limits next to the results.

## Project layout

| File | What it does |
|---|---|
| `app.py` | Streamlit interface |
| `astro_engine.py` | Ephemeris access, birth-time handling, old-date clocks, Western transits, eclipses |
| `vedic.py` | Nakshatras, dashas, gochara, Sade Sati, Vedic period reading |
| `vargas.py` | Divisional charts and chart diagrams |
| `ashtakavarga.py` | Ashtakavarga tables |
| `panchanga.py` | Birth and daily panchanga |
| `yogas.py` | Yoga and Kuja dosha detection |
| `strength.py` | Partial Shadbala |
| `matching.py` | Guna Milan |
| `tests/` | Checks against published charts and fixed rules |
| `experiments/` | Birth-time experiment (Einstein, Gandhi) and intensity calibration |

Run the tests with:

```bash
pip install pytest
python -m pytest tests
```

## Credits and sources

- Planetary positions: [Swiss Ephemeris](https://www.astro.com/swisseph/) by Astrodienst AG, via [pyswisseph](https://github.com/astrorigin/pyswisseph) (AGPL-3.0)
- Place search: [Nominatim](https://nominatim.org/), © OpenStreetMap contributors
- Time zones: the [IANA time zone database](https://www.iana.org/time-zones)
- Historical Indian clocks: the IANA database notes and [Time in India](https://en.wikipedia.org/wiki/Time_in_India)
- Guna Milan tables: [onlinejyotish.com](https://www.onlinejyotish.com/articles/marriage-matching/english/ashta-kootalu-intro.php) koota articles
- Reference charts: [Astrotheme](https://www.astrotheme.com/astrology/Albert_Einstein) and [PanchangBodh](https://panchangbodh.com/albert-einstein-kundali)

## License

[GNU Affero General Public License v3.0](LICENSE). You're free to use, share and change this app. If you share or host a modified version, you must make its source code available under the same licence. This matches the licence of the Swiss Ephemeris, which the app depends on.
