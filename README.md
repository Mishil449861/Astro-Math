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

**Both systems (optional)**
- A written reading and answers to your questions from an AI model (a free Gemini key or a free local model), allowed to use only the app's calculated facts and checked before it's shown (see [Written reading](#written-reading-optional))

## Run it on your own computer (no technical knowledge needed)

This takes about 20 minutes the first time, most of it waiting for downloads. Afterwards, starting the app is a double-click.

### Step 1: Install Python (once)

1. Go to [python.org/downloads](https://www.python.org/downloads/) and click the big yellow **Download Python** button.
2. Open the downloaded file.
   - **Windows:** on the first screen, tick **"Add python.exe to PATH"** at the bottom, then click **Install Now**.
   - **Mac:** click **Continue** through the installer and enter your password when asked.

### Step 2: Download the app (once)

1. On this page on GitHub, click the green **Code** button, then **Download ZIP**.
2. Find the ZIP in your Downloads folder and unzip it: on Windows, right-click it and choose **Extract All**; on a Mac, double-click it.
3. Move the unzipped folder somewhere easy to find, such as your Desktop.

### Step 3: Start the app

Open the folder and double-click:
- **Windows:** `start_app_windows.bat`. If a blue "Windows protected your PC" box appears, click **More info**, then **Run anyway**.
- **Mac:** `start_app_mac.command`. If the Mac says it can't be opened, right-click the file, choose **Open**, then click **Open** again. This is only needed the first time.

A black window opens. The first time, it spends a few minutes installing what the app needs. Then the app opens in your web browser. If the black window asks for an email address, just press **Enter**.

Keep the black window open while you use the app. Close it when you're done. Next time, just double-click the same file again.

### Step 4 (optional): Add the AI reading with a free local model

This lets the app write readings and answer questions using an AI model that runs entirely on your computer. Nothing is sent over the internet and nothing is paid for.

1. **Check your computer.** Find how much memory (RAM) it has: on Windows, open **Settings → System → About**; on a Mac, open **Apple menu → About This Mac**.

   | Memory (RAM) | Model to download | Download size |
   |---|---|---|
   | 16 GB or more | `qwen3:14b` (best) | about 9 GB |
   | 8 GB | `qwen3:4b` (simpler writing, fails the fact check more often) | about 2.5 GB |
   | Less than 8 GB | Skip this step; the rest of the app works without it | |

2. **Install Ollama.** Go to [ollama.com/download](https://ollama.com/download), download the version for your computer, and install it like any other program. It then runs quietly in the background: you'll see a small llama icon in the taskbar (Windows) or the menu bar (Mac).
3. **Download the model.** Open a command window:
   - **Windows:** press the Windows key, type `cmd` and press Enter.
   - **Mac:** press Cmd + Space, type `Terminal` and press Enter.

   Type this line exactly (use the model name from the table) and press Enter:

   ```
   ollama pull qwen3:14b
   ```

   Wait until it says **success**. You can then close the command window.
4. **Start the app** as in Step 3. At the bottom of each reading, a **Written reading** section appears with a **Write my reading** button. The app finds the model by itself.

On a laptop with a graphics card, a reading takes under a minute; without one, it can take a few minutes. If the Written reading section doesn't appear, check that the llama icon is showing (open **Ollama** from your programs to start it), then reload the browser page. The 14B model needs most of a 16 GB computer's memory, so close other large programs while using it.

**No powerful computer?** A free Gemini key works instead and needs no download: see [Free Gemini key](#free-gemini-key) below. Readings then take a few seconds, but the reading's facts are sent to Google.

### For developers

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
streamlit run app.py
python -m pytest tests          # after: pip install pytest
```

To deploy on [Streamlit Community Cloud](https://streamlit.io/cloud), point it at this repository with `app.py` as the entry file.

## Written reading (optional)

The app can turn its results into a short written reading and answer questions such as "how does my career look this month?". It works only when a language model is available:

1. **API key.** In the `.streamlit` folder, copy `secrets.example.toml` to a new file named `secrets.toml` and paste one key into it: Gemini or Groq (both have free tiers) or Anthropic (paid). On Streamlit Community Cloud, paste the same text into the app's **Settings → Secrets**. `secrets.toml` is listed in `.gitignore`, so the key is never uploaded.
2. **Local model.** With no key, the app uses [Ollama](https://ollama.com) if it is running on the same computer: `qwen3:14b` if installed, otherwise the best model it finds (see Step 4 above).
3. **Neither.** The section is hidden.

### Free Gemini key

Get one at [aistudio.google.com/apikey](https://aistudio.google.com/apikey). No credit card is needed, and without one you can't be charged; you just get "usage limit reached" messages when a limit is hit.

- **Daily limit.** The free tier allows about **20 requests a day** on `gemini-3.5-flash`, and a reading uses one or two. When that runs out (or Google's servers are busy), the app moves on to `gemini-3.5-flash-lite` and then `gemini-3.1-flash-lite`, which have their own allowances, and says so under the reading. Limits reset at midnight Pacific time. Your own numbers are at [aistudio.google.com/rate-limit](https://aistudio.google.com/rate-limit).
- **Privacy.** On the free tier Google may use what is sent to improve its products. The app says this next to the reading.
- **More readings.** For a public app with many users, attach billing in AI Studio (Flash is inexpensive), or use a Groq or Anthropic key.

### How the answer is checked

The model never calculates anything. `interpret_ai.py` gives it a numbered list of the facts the app worked out (including, when the birth time is uncertain, both options for every placement and house), requires a cited fact for every claim, and checks the answer before anyone sees it:

- planet–sign and planet–house claims must be on the sheet *and* in the facts cited with them, counted from the same point (Lagna or Moon), so a transit can't pass as a birth placement;
- retrograde claims, aspects (both planets and the kind of contact), favourable or unfavourable verdicts, dates (including "on the 25th"), dashas, nakshatras and their lords and deities, and yogas must match the cited facts;
- uncertain placements must not be stated as certain; "nothing tense this week" must not contradict a tense fact; "that isn't on your sheet" must not deny something that is;
- Vedic ideas may appear in a Western reading only to say they don't apply;
- no death, illness, accident, medical, financial or legal predictions or advice (a question about them may be declined politely).

A failed answer gets one retry with the problems listed and pointers to the right facts; if that fails too, the app shows the plain facts instead. Only the facts and the question are sent, not a name, birth date or place.

The checks catch invented or misattributed facts, not every odd interpretation (for example, describing a transit's life area loosely), so treat the text as a summary of the tables.

### Testing it

`experiments/ai_reading_test.py` runs batches of 30 questions (readings, false premises, best dates, safety questions, prompt injection) on the charts of Einstein, Gandhi, Billie Eilish, Greta Thunberg, Emma Raducanu, Coco Gauff and Lamine Yamal, and saves every answer. Each batch was then read by hand to find what the checks missed, the checks were fixed, and the next batch used new periods. With the local `qwen3:14b` model, the errors the checks missed fell from 6 in 30 answers (batch 5) to 1 minor one (batch 8), where 28 of 30 answers passed first time and the other 2 were real errors that the checks caught.

On the same 30 batch-8 questions, the free Gemini key (`gemini-3.5-flash`, then `gemini-3.5-flash-lite` after the daily limit) passed 28 first time and 1 after a retry, with no errors found by reading the answers, at about 10 seconds per answer instead of 20–60. The lite model is just as careful but writes more mechanically.

```bash
python experiments/ai_reading_test.py --batch 8              # the model the app would use
python experiments/ai_reading_test.py --batch 8 qwen3:14b    # a specific local model
python experiments/rescore.py experiments/ai_results/qwen3_14b_batch8.jsonl   # re-check saved answers
```

A stopped run carries on where it left off when started again.

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
| `interpret_ai.py` | Fact sheet, rules and checks for the written reading |
| `ai_provider.py` | Picks the model: API key if set, else local Ollama; Gemini falls back to lite models at the daily limit |
| `start_app_windows.bat`, `start_app_mac.command` | Double-click launchers |
| `.streamlit/secrets.example.toml` | Template for API keys (copy to `secrets.toml`) |
| `tests/` | Checks against published charts and fixed rules |
| `experiments/` | Birth-time experiment (Einstein, Gandhi), intensity calibration, and the AI reading tests (`ai_reading_test.py`, `rescore.py`, saved answers in `ai_results/`) |

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
