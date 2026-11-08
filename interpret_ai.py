"""
interpret_ai.py — guard rails for AI-written readings.

A language model is never asked to work out astrology. The app does the calculations; this
module turns those results into a numbered list of facts, asks the model to write only from
that list, and checks its answer before anyone sees it:

  1. Fact sheet   every statement the model may use, numbered F1, F2, …; anything the
                  birth time leaves open is written as "either A or B".
  2. Rules        the system prompt: cite a fact for every claim, add nothing, keep both
                  options of an uncertain fact, no medical/financial/legal advice,
                  no predictions of death, illness or accidents.
  3. Checks       the answer is scanned for planet–sign and planet–house pairs, nakshatras,
                  dasha lords, dates and citations that are not on the fact sheet; for an
                  uncertain fact stated as certain; and for banned topics.
  4. Retry        on a failed check, the model gets one more try with the problems listed.
                  If that fails too, the app shows the plain fact list instead.

The model call itself is passed in as a function call(system, user) -> str, so any provider
can be plugged in.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from astro_engine import NAK, SIGNS, UNKNOWN_WINDOW

# ---------------------------------------------------------------------------
# Names the checks look for
# ---------------------------------------------------------------------------
BODIES = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune",
          "Pluto", "Rahu", "Ketu", "North Node", "Ascendant", "Lagna", "Midheaven"]
RASHI = ["Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya", "Tula",
         "Vrischika", "Dhanu", "Makara", "Kumbha", "Meena"]
SIGN_INDEX = {n.lower(): i for i, n in enumerate(SIGNS)} | {n.lower(): i for i, n in enumerate(RASHI)}
MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"])}
MONTHS |= {k[:3]: v for k, v in list(MONTHS.items())}

# Topics the reading must not touch. Word-boundary matches, case-insensitive.
BANNED = {
    r"\bdeath\b|\bdie\b|\bdies\b|\bdying\b|\bfatal\b|\blifespan\b|\blongevity\b": "death or lifespan",
    r"\baccident": "accidents",
    r"\bdiagnos|\bsurgery\b|\bmedicat|\bstop taking\b|\bdisease\b|\billness\b": "medical claims",
    r"\binvest(?:ing|ment)? in\b|\bbuy (?:stocks?|shares|crypto)\b|\blottery\b|\bgambl": "financial advice",
    r"\blawsuit\b|\bsue\b|\blegal action\b": "legal advice",
    r"\b(?:is|are|it's|will be) guaranteed\b|\bguarantees? (?:you|that|success|a)\b|\bdefinitely will\b|"
    r"\bwill certainly\b|\bwithout (?:a )?doubt\b|\bis destined\b": "certainty",
}
SOFTEN = {"illness, debts and rivals": "health habits, debts and rivals"}
NATAL_WORDS = re.compile(r"\bbirth|\bnatal\b|\bborn\b|\bnatally\b", re.I)
TRANSIT_WORDS = re.compile(r"\btransit|\bcurrently\b|\bnow\b|\bthis (?:day|week|month|period|year)\b|"
                           r"\benters\b|\bentering\b|\bmoves? into\b", re.I)
NOT_ON_SHEET = re.compile(r"\b(?:not|isn't|no)\b[^.]{0,40}\b(?:fact sheet|the facts|your facts)\b|"
                          r"(?:does not|doesn't|do not|don't) (?:mention|show|list|include)", re.I)
REFUSAL = re.compile(r"\b(?:can't|cannot|can not|unable to|not able to|won't predict|no substitute|"
                     r"not a substitute|outside the scope|(?:does not|doesn't|do not|don't) (?:mention|show|"
                     r"say|cover|include|provide|indicate|predict)|not enough information|don't have enough|no indication|"
                     r"not reflected|can't be determined|cannot be determined|not something that can|"
                     r"not possible to|impossible to|no way to)\b", re.I)
# A sentence that predicts: blocks a banned topic even inside a polite answer
PREDICTS = re.compile(r"\bwill\b(?!\s+not)|\blikely\b|\bexpect|\bbound to\b", re.I)
# Words that keep an uncertain placement open. "may" and "might" don't count: they soften a
# meaning, not a fact.
HEDGES = re.compile(r"\bor\b|\beither\b|\buncertain|\bdepend|\bpossibl|\bnot certain\b|\bif (?:your|the) (?:birth|natal|Moon)|"
                    r"\bcan't be sure\b|\bassum", re.I)
MOON_HOUSE = re.compile(r"from (?:your |the )?(?:natal |birth )?Moon", re.I)
# Vedic-only ideas: a Western reading may name them only to say they don't apply
VEDIC_ONLY = re.compile(r"\bSade Sati\b|\bdashas?\b|\bmahadasha|\bantardasha|\bnakshatras?\b|\byogas?\b|"
                        r"\bgochara\b|\bLagna\b|\bashtakavarga\b|\bKuja\b|\bRahu\b|\bKetu\b", re.I)
NOT_APPLY = re.compile(REFUSAL.pattern + r"|\bnot (?:part of|used|included|appl)|\bdoesn't apply|"
                       r"\bdoes not apply|\bdon't apply|\bdo not apply", re.I)
# "the reading doesn't use nakshatras" rules a Vedic idea out too
RULED_OUT = re.compile(NOT_APPLY.pattern + r"|\bVedic\b|\b(?:don't|do not|doesn't|does not) use\b|"
                       r"\b(?:aren't|isn't|not) used\b", re.I)
# Presiding deity of each nakshatra (classical list), so the model needn't invent lore
NAK_DEITIES = ["the Ashwini Kumaras", "Yama", "Agni", "Brahma (Prajapati)", "Soma", "Rudra", "Aditi",
               "Brihaspati", "the Nagas", "the Pitris (ancestors)", "Bhaga", "Aryaman", "Savitar",
               "Tvashtar (Vishvakarma)", "Vayu", "Indra and Agni", "Mitra", "Indra", "Nirriti",
               "Apas (the waters)", "the Vishvadevas", "Vishnu", "the Vasus", "Varuna", "Aja Ekapada",
               "Ahir Budhnya", "Pushan"]
# "Saturn's position isn't specified in the facts": wrong if the sheet gives it
MISSING = re.compile(r"\bnot (?:specified|given|listed|included|mentioned|shown|provided|available|stated)\b|"
                     r"\b(?:isn't|aren't) (?:given|listed|shown|specified|stated)\b|"
                     r"\b(?:doesn't|does not|don't|do not) (?:show|mention|list|include|give|say)\b", re.I)
POSITION_WORDS = re.compile(r"\bposition|\bplacement|\btransit|\bwhere\b|\bwhich sign\b|\bsign\b|\bin the sky\b", re.I)
SADE_SATI_DEF = ("Sade Sati is the time transiting Saturn spends in the 12th, 1st and 2nd signs from the "
                 "natal Moon sign.")
SADE_SATI_PHASE = {
    "rising": "traditionally the phase when Saturn's pressure begins to build",
    "peak": "traditionally the most intense phase, with Saturn over the Moon sign itself",
    "setting": "traditionally the easing phase, as Saturn's pressure lifts",
}

SYSTEM_RULES = """You write short, warm astrology readings for a free app used by friends.

You receive a numbered FACT SHEET calculated by the app. Follow these rules exactly:

1. Use only the fact sheet. Do not add planets, signs, houses, nakshatras, aspects, yogas,
   dashas or dates that are not on it, and do not calculate anything yourself.
2. End every sentence that makes an astrological claim with the facts it relies on, such
   as [F3] or [F3][F7]. Never cite a fact number that is not on the sheet.
3. Some facts say "either A or B" because the birth time is uncertain. Keep both options
   whenever you use such a fact; never pick one.
4. Describe meanings as traditional associations ("traditionally linked with",
   "astrologers read this as"), not as things that will certainly happen.
5. Never mention death, lifespan, illness, accidents or surgery. Give no medical,
   financial or legal advice; if the person asks for it, say an astrologer's reading
   is no substitute for a professional.
6. If the question can't be answered from the fact sheet, say what is missing instead of
   guessing. If the question assumes something the fact sheet doesn't show (a placement,
   a retrograde, an aspect), say so plainly instead of agreeing.
7. Plain English, no emojis, no headings unless asked. Keep it under {words} words."""


# ---------------------------------------------------------------------------
# Fact sheet
# ---------------------------------------------------------------------------
class FactSheet:
    """Numbered facts plus the structured values the checks compare against."""

    def __init__(self):
        self.facts: list[str] = []
        self.natal_pairs: set[tuple[str, int]] = set()   # (body, sign index) in the birth chart
        self.pairs: set[tuple[str, int]] = set()         # (body, sign index) in transits and events
        self.natal_houses: set[tuple[str, int]] = set()  # (body, house number) at birth
        self.houses: set[tuple[str, int]] = set()        # (body, house number) in transit
        self.uncertain: dict[str, set[int]] = {}         # natal body -> possible signs
        self.nakshatras: set[str] = set()
        self.dasha_lords: set[str] = set()
        self.dates: set[tuple[int, int]] = set()         # (month, day)
        self.years: set[int] = set()
        self.system = ""

    def add(self, text: str) -> str:
        # Facts are worded so that repeating them never breaks a rule
        for old, new in SOFTEN.items():
            text = text.replace(old, new)
        self.facts.append(text)
        return f"F{len(self.facts)}"

    def date(self, d) -> str:
        """Record a date (± 1 day for time-zone edges) and return it formatted."""
        if d is None:
            return "unknown"
        for k in (-1, 0, 1):
            x = d + timedelta(days=k)
            self.dates.add((x.month, x.day))
            self.years.add(x.year)
        return f"{d:%d %B %Y}"

    def pair(self, body: str, sign: int, natal: bool = False):
        (self.natal_pairs if natal else self.pairs).add((_canon(body), sign % 12))

    def text(self) -> str:
        return "\n".join(f"F{i + 1}. {f}" for i, f in enumerate(self.facts))


def _canon(body: str) -> str:
    return "Ascendant" if body in ("Lagna", "Ascendant") else body


def _sign_word(i: int, vedic: bool) -> str:
    return f"{RASHI[i]} ({SIGNS[i]})" if vedic else SIGNS[i]


def _natal_facts(fs: FactSheet, natal: dict, vedic: bool, bodies: list[str],
                 house_notes: dict | None = None):
    from vedic import NAKSHATRAS
    house_notes = house_notes or {}
    for b in bodies:
        if b not in natal["points"]:
            continue
        opts = [SIGNS.index(s) for s in natal["signs"][b]]
        for s in opts:
            fs.pair(b, s, natal=True)
        label = "Lagna (ascendant)" if vedic and b == "Ascendant" else b
        if len(opts) == 1:
            line = f"Birth chart: {label} is in {_sign_word(opts[0], vedic)}."
        else:
            fs.uncertain[_canon(b)] = set(opts)
            line = (f"Birth chart: {label} is either in " +
                    " or ".join(_sign_word(s, vedic) for s in opts) +
                    "; the birth time leaves this open.")
        if vedic and b not in ("Ascendant", "Midheaven"):
            lo, hi = natal["range"][b]
            naks = []
            for x in (lo, natal["points"][b], hi):
                n = NAKSHATRAS[int(x // NAK) % 27]
                if n not in naks:
                    naks.append(n)
            fs.nakshatras.update(naks)
            line += (f" Nakshatra: {naks[0]}." if len(naks) == 1 else
                     f" Nakshatra: either {' or '.join(naks)}.")
            if b == "Moon":                          # the birth nakshatra: give its lord and deity
                from vedic import DASHA_LORDS
                lore = [f"{n} is ruled by {DASHA_LORDS[NAKSHATRAS.index(n) % 9]}, deity "
                        f"{NAK_DEITIES[NAKSHATRAS.index(n)]}" for n in naks]
                line += " Nakshatra lore: " + "; ".join(lore) + "."
        if b in house_notes:
            line += " " + house_notes[b]
        if natal["retro"].get(b) and b not in ("Rahu", "Ketu", "North Node"):
            line += " Retrograde at birth."
        fs.add(line)
    # time_known means exact; an unknown time is a whole-day window (UNKNOWN_WINDOW)
    half = natal["half_window"]
    if natal["time_known"]:
        fs.add("The birth time is known exactly.")
    elif natal["window"] < UNKNOWN_WINDOW:
        fs.add(f"The birth time is approximate, known to within about ±{half:.0f} minutes, so placements "
               f"marked 'either' could be one or the other.")
    elif natal["constrained"]:
        fs.add(f"The birth time is unknown, but what the person knows of their chart narrows it to a "
               f"window of about ±{half:.0f} minutes.")
    else:
        fs.add("The birth time is unknown, so the ascendant and houses from it are not used.")


def vedic_facts(natal: dict, report: dict, label: str, yogas: dict | None = None,
                max_events: int = 12) -> FactSheet:
    from vedic import GRAHAS, house_from
    fs = FactSheet()
    fs.system = "Vedic"
    vs = report["natal"]
    fs.add(f"System: Vedic (sidereal), {natal['ayanamsa_name']} ayanamsa. Period: {label}.")
    # Birth houses, written into each graha's fact so a house claim can be traced to it.
    # From the Moon they are counted from every sign the Moon could be in.
    moon_opts = [SIGNS.index(s) for s in natal["signs"]["Moon"]]
    notes = {}
    for g in GRAHAS:
        s = int(natal["points"][g] // 30)
        parts = []
        if vs["lagna_sign"] is not None:
            h = house_from(s, vs["lagna_sign"])
            fs.natal_houses.add((g, h))
            parts.append(f"the {_ord(h)} house from the Lagna")
        if g != "Moon":
            hs = sorted({house_from(s, m) for m in moon_opts})
            fs.natal_houses.update((g, h) for h in hs)
            parts.append(("the " if len(hs) == 1 else "either the ") + " or ".join(map(_ord, hs)) + " from the Moon")
        if parts:
            notes[g] = "In " + " and ".join(parts) + "."
    _natal_facts(fs, natal, True, ["Ascendant"] + list(GRAHAS), notes)

    d = report["dasha"]
    if d["md"]:
        fs.dasha_lords.update([d["md"], d["ad"]])
        line = (f"Current Vimshottari dasha: {d['md']} mahadasha "
                f"({fs.date(d['md_span'][0])} to {fs.date(d['md_span'][1])}), "
                f"{d['ad']} antardasha ({fs.date(d['ad_span'][0])} to {fs.date(d['ad_span'][1])}).")
        if d["alternatives"]:
            for alt in d["alternatives"]:
                fs.dasha_lords.update(alt.split("–"))
            line += (" Because of the birth-time uncertainty it could instead be " +
                     " or ".join(d["alternatives"]) + ".")
        fs.add(line)

    fs.add(f"Overall gochara (transits from the Moon) for the period: {report['overall']}.")
    if len(natal["signs"]["Moon"]) > 1:
        assumed = _sign_word(vs["moon_sign"], True)
        fs.add(f"Because the birth Moon's sign is uncertain, the transit houses counted from the Moon below "
               f"assume the Moon in {assumed}; with the other sign they would all shift by one.")
    others = [m for m in moon_opts if m != vs["moon_sign"]]
    for g in report["gochara"]:
        s = SIGN_INDEX[g["Transit sign"].split(" (")[0].lower()]
        fs.pair(g["Graha"], s)
        h = int(re.match(r"\d+", g["From Moon"]).group())
        fs.houses.add((g["Graha"], h))
        if isinstance(g["From Lagna"], int):
            fs.houses.add((g["Graha"], g["From Lagna"]))
        a, b = g["When"]
        # with an uncertain Moon both counts go in the line itself, so a sentence copied from it
        # keeps the caveat
        house = f"{g['From Moon']} house from the natal Moon ({g['Theme']})"
        if others:
            alt = [house_from(s, m) for m in others]
            fs.houses.update((g["Graha"], x) for x in alt)
            house += (f" if the Moon is in {SIGNS[vs['moon_sign']]}, or the " +
                      " or ".join(_ord(x) for x in alt) + f" if it is in {' or '.join(SIGNS[m] for m in others)}")
        # the last segment ends at midnight after the period; a minute earlier is the last day in it
        fs.add(f"Transit: {g['Graha']} in {g['Transit sign']}, {house}, "
               f"{fs.date(a)} to {fs.date(b - timedelta(minutes=1))}. "
               f"Traditional verdict: {g['Verdict']}" + (f" (counting from the Moon in {SIGNS[vs['moon_sign']]})"
                                                         if others else "") + ". "
               f"Ashtakavarga support: {g['Bindu support']}.")

    sat = report["saturn"]
    if sat.get("status"):
        phase = sat.get("phase") or ""
        meaning = SADE_SATI_PHASE.get(phase.split()[0], "") if phase else ""
        fs.add(f"Saturn: {sat['status']} from {fs.date(sat['start'])} to {fs.date(sat['end'])}" +
               (f"; this period falls in its {phase} phase, {meaning}." if phase else ".") +
               (f" {SADE_SATI_DEF}" if sat["status"] == "Sade Sati" else ""))
    elif sat.get("next_sade_sati"):
        fs.add(f"Saturn: not in Sade Sati now; the next Sade Sati starts {fs.date(sat['next_sade_sati'])}. "
               f"{SADE_SATI_DEF}")
    for dr in report["drishti"]:
        fs.add(f"Aspect: transiting {dr['Graha']} casts its {dr['Aspect']} aspect on the natal "
               f"{dr['Falls on your']} ({dr['Nature']}).")
    for e in report["events"][:max_events]:
        fs.add(f"Event on {fs.date(e['when'])}: {e['event']}. {e['meaning']}")
    if yogas:
        for y in yogas["rows"]:
            status = "" if y["Status"] == "present" else " (only if the birth time falls a certain way)"
            fs.add(f"Yoga: {y['Yoga']}{status}. {y['Meaning']}")
        for k in yogas["kuja"]:
            status = "" if k["Status"] == "present" else " (depends on the birth time)"
            fs.add(f"Kuja dosha counted {k['Counted']}{status}.")
    _event_entities(fs, report["events"])
    return fs


def western_facts(natal: dict, report: dict, label: str, max_influences: int = 10,
                  max_events: int = 12) -> FactSheet:
    from astro_engine import PLANETS
    fs = FactSheet()
    fs.system = "Western"
    fs.add(f"System: Western (tropical). Period: {label}. Overall tone: {report['overall']}; "
           f"intensity: {report['intensity']}. Vedic ideas such as Sade Sati, dashas, nakshatras and "
           f"yogas are not part of a Western reading.")
    _natal_facts(fs, natal, False, list(PLANETS) + ["Ascendant", "Midheaven"])
    for a in report["areas"][:5]:
        fs.add(f"Life area in focus: {a['Life area']} (tone: {a['Tone']}, relative focus {a['Focus']:.2f}).")
    sky = []
    for row in report["sky"]:
        sign = next(s for s in SIGNS if row["Position"].endswith(s))
        fs.pair(row["Planet"], SIGNS.index(sign))
        sky.append(f"{row['Planet']} {row['Position']}{' (retrograde)' if row['Retrograde'] else ''}")
    fs.add("Sky in the middle of the period: " + ", ".join(sky) + ".")
    for inf in report["influences"][:max_influences]:
        when = (f"exact on {', '.join(fs.date(x) for x in inf['exact_in_period'])}"
                if inf["exact_in_period"] else
                f"in effect {fs.date(inf['start'])} to {fs.date(inf['end'])}")
        fs.add(f"Transit: {inf['title']}, {when}. {inf['meaning']}")
    for e in report["events"][:max_events]:
        fs.add(f"Event on {fs.date(e['when'])}: {e['event']}. {e['meaning']}")
    _event_entities(fs, report["events"])
    if report.get("moon"):
        fs.add(f"The Moon is in {report['moon']['sign']}, {report['moon']['phase']}.")
        fs.pair("Moon", SIGNS.index(report["moon"]["sign"]))
    return fs


def _event_entities(fs: FactSheet, events: list[dict]):
    """Planet–sign pairs and nakshatras named in event lines are allowed too."""
    from vedic import NAKSHATRAS
    for e in events:
        for body, sign in _pairs_in(e["event"]):
            fs.pairs.add((body, sign))
        if re.search(r"New Moon|Full Moon|Amavasya|Purnima", e["event"]):
            for m in re.finditer(rf"\b({_SIGN})\b", e["event"]):
                fs.pairs.add(("Moon", SIGN_INDEX[m.group(1).lower()]))
                if re.search(r"New Moon|Amavasya", e["event"]):
                    fs.pairs.add(("Sun", SIGN_INDEX[m.group(1).lower()]))
        for n in NAKSHATRAS:
            if n in e["event"]:
                fs.nakshatras.add(n)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
_BODY = "|".join(sorted(map(re.escape, BODIES), key=len, reverse=True))
_BODIES = rf"((?:{_BODY})(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*)(?:{_BODY}))*)"   # "Sun, Moon and Mercury"
_SIGN = "|".join(sorted(map(re.escape, SIGNS + RASHI), key=len, reverse=True))
_VERB = (r"(?:is in|in|into|enters|entering|re-enters|through|transits|transiting|transit|"
         r"occupies|occupying|returns? to|returning to|moves? to|moving to|moves? into|moving into|"
         r"touch(?:es|ing)?|falls? in|falling in|sits? in|sitting in|placed in|located in)")
_ONE_SIGN = rf"(?:{_SIGN})(?:\s*\((?:{_SIGN})\))?"                 # "Dhanu (Sagittarius)"
# a list after one verb: "through Sagittarius [F14] and Libra [F18]" pairs the body with each sign
_SIGN_LIST = (rf"({_ONE_SIGN}(?:\s*(?:\[F\d+\]\s*)*(?:,\s*(?:and\s+|or\s+)?|\s+and\s+|\s+or\s+)"
              rf"{_ONE_SIGN})*)")
# up to three words may sit between a planet and its verb, but never another planet's name:
# in "Saturn–Ketu, astrologers interpret Saturn in your 2nd" the 2nd belongs to Saturn
_GAP = rf"(?:\W+(?!(?:{_BODY})\b)\w+){{0,3}}?"
PAIR_RE = re.compile(rf"\b{_BODIES}\b{_GAP}\W+{_VERB}\W+(?:the sign of\W+)?{_SIGN_LIST}", re.I)
# "Sun in Cancer (8th house from the Moon)" / "Sun in Cancer, the 8th house"
HOUSE_PAREN = re.compile(rf"\b{_BODIES}\b\s+(?:is\s+)?in\s+{_ONE_SIGN}\s*(?:\(|,\s*)(?:in\s+)?(?:the\s+)?"
                         rf"(\d{{1,2}})(?:st|nd|rd|th)\b", re.I)
HOUSE_RE = re.compile(rf"\b{_BODIES}\b{_GAP}\W+{_VERB}\W+(?:your\W+)?(?:the\W+)?"
                      rf"(\d{{1,2}})(?:st|nd|rd|th)\b", re.I)
DASHA_RE = re.compile(rf"\b({_BODY})\b(?:[\s–-]+(?:{_BODY}))?\s+(?:maha|antar)?dasha", re.I)
# Month names must be capitalised, so "the 13th may bring" is not read as a date
_MON = "|".join(sorted([m.title() for m in MONTHS] + ["Sept"], key=len, reverse=True))
DATE_RE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\b\.?|"
                     rf"\b({_MON})\b\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b")
YEAR_RE = re.compile(r"\b(1[89]\d\d|20\d\d|21\d\d)\b")
CITE_RE = re.compile(r"\[F(\d+)\]")
ITS_HOUSE = re.compile(r"\bits\b(?:\W+\w+){0,3}?\W+(?:in|into|occupies|occupying|falls in)\W+(?:your\W+)?(?:the\W+)?"
                       r"(\d{1,2})(?:st|nd|rd|th)\b", re.I)
# "on the 25th": a day of the period's month(s); not "the 8th house" or "the 8th from"
BARE_DAY = re.compile(r"\b(?:on|by|around|until|till|before|after|from) the (\d{1,2})(?:st|nd|rd|th)\b"
                      r"(?!\s+(?:house|from|sign|lord|aspect|of (?:the|your)))", re.I)
# "Mercury is retrograde", "Mercury is not retrograde", "retrograde Mercury"
RETRO_RE = re.compile(rf"\b({_BODY})\b([^.;]{{0,40}}?)\bretrograde\b|\bretrograde\s+({_BODY})\b", re.I)
NEGATED = re.compile(r"\bnot\b|n't\b|\bnever\b|\bno longer\b", re.I)
# "No conflicting transits on this day": wrong if the facts list a tense or unfavourable one
NO_TENSION = re.compile(r"\bno (?:conflicting|tense|challenging|difficult|negative|harsh|hard|unfavou?rable) "
                        r"(?:transits?|aspects?|contacts?|influences?|placements?|energ)|"
                        r"\bnothing (?:tense|challenging|difficult|negative)\b|"
                        r"\bonly (?:positive|harmonious|favou?rable|supportive|good)\b", re.I)
TENSE_FACT = re.compile(r"A tense contact|verdict: unfavou?rable|\(heavy, testing\)")
# Aspect claims: the cited facts must name the same kind of contact
ASPECTS = {
    "conjunct": (r"\bconjunct(?:s|ion)?\b", r"\bconjunct"),
    "sextile": (r"\bsextiles?\b|\bsextiling\b", r"\bsextile"),
    "square": (r"\bsquares?\b(?! one)|\bsquaring\b", r"\bsquare"),
    "trine": (r"\btrines?\b|\btrining\b", r"\btrine"),
    "opposition": (r"\bopposes?\b|\bopposing\b|\bopposition\b|\bopposite (?:your|the|to)\b", r"\bopposit"),
    "aspect": (r"\baspected\b|\bcasts?\b[^.]{0,30}\baspect\b|\baspects (?:your|the)\b|"
               r"\b\d+(?:st|nd|rd|th) (?:sign )?aspect\b|\bdrishti\b|'s aspect\b",
               r"\baspect\b|\bdrishti\b"),
}
# a clause like ", which helps with talking and thinking," hides "Mercury ... is in Capricorn"
APPOSITIVE = re.compile(r",\s*(?:which|who|the planet of|the ruler of|ruler of)\b[^,]{0,80},", re.I)


def _title(body: str) -> str:
    return next(b for b in BODIES if b.lower() == body.lower())


def _bodies(group: str) -> list[str]:
    # word boundaries, so "Sunapha" is not the Sun
    return [_canon(_title(b)) for b in re.findall(rf"\b(?:{_BODY})\b", group, re.I)]


def _pairs_in(text: str):
    for m in PAIR_RE.finditer(text):
        for body in _bodies(m.group(1)):
            for sign in _signs(m.group(2)):
                yield body, sign


def _pairs_neg(text: str, known: set | None = None):
    """(body, sign, negated) for each planet-sign claim; negated for "is not in Leo".

    "Sun, Mars and Mercury in Scorpio and Sagittarius" is a loose grouping, not every
    combination: with several planets and several signs, each planet is paired with the
    listed signs it is known to be in (all of them if none, so the claim still fails)."""
    for m in PAIR_RE.finditer(text):
        negated = bool(re.search(r"\bnot\b|n't\b|\bnever\b", m.group(0), re.I))
        bodies, signs = _bodies(m.group(1)), _signs(m.group(2))
        for body in bodies:
            mine = signs
            if len(bodies) > 1 and len(signs) > 1 and known is not None:
                mine = [s for s in signs if (body, s) in known] or signs
            for sign in mine:
                yield body, sign, negated


def _signs(group: str) -> list[int]:
    return list(dict.fromkeys(SIGN_INDEX[x.lower()] for x in re.findall(_SIGN, group, re.I)))


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _dates_in(text: str) -> set[tuple[int, int]]:
    out = set()
    for m in DATE_RE.finditer(text):
        day = int(m.group(1) or m.group(4))
        month = MONTHS[(m.group(2) or m.group(3)).lower()[:3]]
        if 1 <= day <= 31:
            out.add((month, day))
    return out


def _near(d: tuple[int, int], dates: set[tuple[int, int]]) -> bool:
    """Same date, or one day either side (time-zone edges)."""
    return any(m == d[0] and abs(x - d[1]) <= 1 for m, x in dates) or d in dates


def _mentions(fact: str, body: str) -> bool:
    fact = fact.split(" Nakshatra lore:")[0]          # "ruled by Venus" there isn't about Venus
    fact = re.sub(r"\(vedha by [^)]*\)", "", fact)    # nor is "obstructed (vedha by Mercury, Sun)"
    names = ["Lagna", "Ascendant", "ascendant"] if body in ("Ascendant", "Lagna") else [body]
    if body == "Sun":                                 # a New Moon is the Sun and Moon together
        names += ["New Moon", "Amavasya"]
    return any(re.search(rf"\b{re.escape(n)}\b", fact) for n in names)


def _norm_cites(text: str) -> str:
    """[F2, F19], [F2,F19] and [F2 and F19] -> [F2][F19], the form the checks read. A range
    such as [F19-F34] points at no fact in particular, so it is dropped (a claim resting on it
    then counts as uncited), and it can't be left showing in the text."""
    def split(m):
        return "".join(f"[F{n}]" for n in re.findall(r"\d+", m.group(0)))
    text = re.sub(r"\s*\[F\d+\s*[-–]\s*F?\d+\]", "", text)
    return re.sub(r"\[F\d+(?:\s*(?:,|and|&)\s*F?\d+)+\]", split, text)


def _kind(sent: str) -> str | None:
    """'natal' or 'transit' when the sentence says which, else None."""
    natal = re.search(r"\bbirth|\bnatal\b|\bborn\b", sent, re.I)
    transit = TRANSIT_WORDS.search(sent)
    return None if bool(natal) == bool(transit) else ("natal" if natal else "transit")


def _where(fs: "FactSheet", body: str, sign: int, kind: str | None) -> int | None:
    """The first fact of the same kind giving this planet in this sign, to point a retry at
    the right number. No hint when the sentence doesn't say birth or transit: pointing a
    transit claim at a birth fact would teach the model to mix them up."""
    if kind is None:
        return None
    for i, f in enumerate(fs.facts, 1):
        if (f.startswith("Birth chart:")) != (kind == "natal"):
            continue
        if _mentions(f, body) and re.search(rf"\b(?:{SIGNS[sign]}|{RASHI[sign]})\b", f):
            return i
    return None


def _house_ref(sent: str) -> dict[int, str]:
    """{house number: 'Lagna' | 'Moon'} for "the 9th house from your Lagna" and the like."""
    out = {}
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)(?:\s+house)?(?:\s+\w+){0,2}?\s+from\s+(?:your\s+|the\s+)?"
                         r"(?:natal\s+|birth\s+)?(Lagna|Ascendant|Moon)\b", sent, re.I):
        out[int(m.group(1))] = "Lagna" if m.group(2).lower() in ("lagna", "ascendant") else "Moon"
    return out


def _gives_house(f: str, body: str, h: int, ref: str | None) -> bool:
    if not (_mentions(f, body) and re.search(rf"\b{_ord(h)}\b", f)):
        return False
    if ref == "Lagna":
        return bool(re.search(rf"\b{_ord(h)} house from the Lagna\b", f))
    if ref == "Moon":
        return bool(re.search(rf"\b{_ord(h)}\b[^.;]{{0,40}}\bMoon\b|\bor the {_ord(h)} if it is in\b", f))
    return True


def _retro_in(fact: str, body: str) -> bool:
    """Does this fact say that this body (not another one in the same fact) is retrograde?"""
    if fact.startswith(f"Birth chart: {body} "):
        return "Retrograde at birth" in fact
    return bool(re.search(rf"\b{re.escape(body)}\b[^,;.]{{0,30}}?retrograde|"
                          rf"\b{re.escape(body)} turns (?:direct|retrograde)", fact, re.I))


def _paragraphs(text: str):
    """(sentence, citations in its paragraph) pairs."""
    for para in re.split(r"\n\s*\n", text):
        cites = CITE_RE.findall(para)
        for sent in _sentences(para):
            yield sent, cites


def check(text: str, fs: FactSheet, question: str | None = None) -> list[str]:
    """Problems found in a reading; an empty list means it passed.

    Every planet-sign or planet-house claim must be on the fact sheet *and* in one of the
    facts cited with it, so a transit can't be passed off as a birth placement. Dates must
    come from the cited facts too. A banned topic may be named only when the person asked
    about it and the answer declines without predicting anything."""
    from vedic import NAKSHATRAS
    text = _norm_cites(text.replace("\u2019", "'"))  # curly apostrophes: can't; [F2, F19] -> [F2][F19]
    q = (question or "").replace("\u2019", "'")
    declines = bool(REFUSAL.search(text) or NOT_ON_SHEET.search(text))
    problems = []
    n_facts = len(fs.facts)

    def fact(c):
        return fs.facts[int(c) - 1] if 1 <= int(c) <= n_facts else None

    for c in CITE_RE.findall(text):
        if not fact(c):
            problems.append(f"Cites F{c}, which is not on the fact sheet.")
    all_pairs, all_houses = fs.natal_pairs | fs.pairs, fs.natal_houses | fs.houses
    # the period's own dates (e.g. a custom range "Jul 10 – Aug 20") need no citation
    period_dates = _dates_in(fs.facts[0]) if fs.facts else set()
    period_months = {MONTHS[m.lower()[:3]] for m in re.findall(rf"\b({_MON})\b", fs.facts[0])} if fs.facts else set()
    years = fs.years | {int(y) for y in YEAR_RE.findall(fs.facts[0] if fs.facts else "")}
    if (CITE_RE.search(text) is None and not declines and not NOT_APPLY.search(text) and
            (re.search(rf"\b(?:{_BODY})\b", text) or re.search(rf"\b(?:{_SIGN})\b", text))):
        problems.append("The answer makes astrological claims but cites no facts; every claim needs "
                        "a fact number such as [F3].")
    last_body = None                                # for "it" in "it's also retrograde"
    last_naks: list[str] = []                       # for "both are ruled by …"
    for sent, para_cites in _paragraphs(text):
        # "Saturn's position isn't specified in the facts" when the sheet gives it
        if MISSING.search(sent) and POSITION_WORDS.search(sent):
            now = re.search(r"\btransit|\bcurrent|\bnow\b|\bsky\b|\bthis (?:day|week|month|period)", sent, re.I)
            for body in dict.fromkeys(_bodies(APPOSITIVE.sub("", sent))):
                def gives(f, body=body):
                    if now:
                        return (f.startswith((f"Transit: {body} in", f"Transit: {body} (")) or
                                (f.startswith("Sky in the middle") and bool(re.search(rf"\b{body} \d", f))))
                    return f.startswith(f"Birth chart: {body} ")
                given = [i for i, f in enumerate(fs.facts, 1) if gives(f)]
                if given:
                    problems.append(f"Says {body}'s position is not on the fact sheet, but F{given[0]} gives it.")
        if NOT_ON_SHEET.search(sent) or (MISSING.search(sent) and re.search(r"\blisted\b|\bin the facts\b", sent)):
            # "Venus in Scorpio is not on your fact sheet": declining is what we want, unless
            # it is on the sheet ("a New Moon in Libra is not listed" when F35 lists it)
            known = fs.natal_pairs if re.search(r"\bbirth|\bnatal\b", sent, re.I) else all_pairs
            for body, sign, negated in _pairs_neg(APPOSITIVE.sub("", sent)):
                # backed by a fact cited in the same sentence, it isn't being denied ("it does
                # show a Full Moon in Aries, but not as an eclipse [F26]")
                own_facts = [f for f in map(fact, CITE_RE.findall(sent)) if f]
                if (body, sign) in known and not any(
                        _mentions(f, body) and re.search(rf"\b(?:{SIGNS[sign]}|{RASHI[sign]})\b", f)
                        for f in own_facts):
                    where = _where(fs, body, sign, _kind(sent))
                    problems.append(f"Says {body} in {SIGNS[sign]} is not on the fact sheet, but it is"
                                    + (f" (F{where})." if where else "."))
            continue
        own = CITE_RE.findall(sent)
        # a sentence without citations is checked against its paragraph's (a citation at the
        # end of a paragraph); the claim must still be in those facts
        ids = own or para_cites
        cited = [f for f in map(fact, ids) if f]
        para_facts = [f for f in map(fact, para_cites) if f]
        cited_ids = ", ".join(dict.fromkeys(f"F{c}" for c in ids))
        # "Venus in the 3rd from the Moon [F7], and Jupiter in the 6th": "from the Moon" is a
        # reference point, not the Moon placed somewhere, so it is masked for claim matching
        sent_m = re.sub(r"\bfrom\s+(?:your\s+|the\s+)?(?:natal\s+|birth\s+)?(Moon|Lagna|Ascendant)\b",
                        r"from the \1REF", APPOSITIVE.sub("", sent), flags=re.I)
        dates = _dates_in(sent)
        bare = {(m, int(d)) for d in BARE_DAY.findall(sent) for m in period_months}
        claims = (PAIR_RE.search(sent_m) or HOUSE_RE.search(sent_m) or HOUSE_PAREN.search(sent_m)
                  or DASHA_RE.search(sent_m))
        if claims and not cited:
            problems.append(f"Claim without a fact citation: \"{sent.strip()[:90]}\"")
        for body, sign, negated in _pairs_neg(sent_m, all_pairs):
            if negated:
                # "No, your Moon is not in Leo": fine unless the birth chart says it is
                if ((body, sign) in fs.natal_pairs and body not in fs.uncertain
                        and not TRANSIT_WORDS.search(sent)):
                    problems.append(f"Says {body} is not in {SIGNS[sign]}, but the birth chart puts it there.")
                continue
            if (body, sign) not in all_pairs:
                problems.append(f"{body} in {SIGNS[sign]} is not on the fact sheet.")
                continue
            def has_pair(f, body=body, sign=sign):
                return _mentions(f, body) and bool(re.search(rf"\b(?:{SIGNS[sign]}|{RASHI[sign]})\b", f))
            # supported by the sentence's citations, or failing that by a fact cited in the same
            # paragraph (true claim, citation one sentence off)
            support = [f for f in cited if has_pair(f)] or [f for f in para_facts if has_pair(f)]
            if cited and not support:
                where = _where(fs, body, sign, _kind(sent))
                problems.append(f"{body} in {SIGNS[sign]} is not in the facts it cites ({cited_ids})"
                                + (f"; the sheet has it in F{where}." if where else "."))
            # "either" must be about the sign ("is either in A or B"), not the houses
            elif support and all(re.search(r"\beither in\b", f) for f in support) and not HEDGES.search(sent):
                others = sorted(fs.uncertain.get(body, set()) - {sign})
                problems.append(f"{body}'s sign is uncertain" +
                                (f" ({SIGNS[sign]} or {', '.join(SIGNS[o] for o in others)})" if others else "") +
                                " but is stated as certain.")
        house_claims = [(body, int(m.group(2)), m.start(1))
                        for m in [*HOUSE_RE.finditer(sent_m), *HOUSE_PAREN.finditer(sent_m)]
                        for body in _bodies(m.group(1))]
        # "Jupiter is in Aquarius ... its transit in the 10th house": "its" is the last planet named
        for m in ITS_HOUSE.finditer(sent_m):
            before = _bodies(sent_m[:m.start()])
            if before or last_body:
                house_claims.append((before[-1] if before else last_body, int(m.group(1)), m.start()))
        refs = _house_ref(APPOSITIVE.sub("", sent))
        if re.search(r"\bSade Sati\b", sent) and re.search(r"\b12th,?\s+1st,?\s+(?:and|or)\s+2nd\b", sent):
            house_claims = []                       # restating the definition, not placing Saturn
        for body, h, start in house_claims:
                body = "Lagna" if body == "Ascendant" else body
                # the fact must give the same house counted from the same point (Lagna or Moon)
                ref = refs.get(h)
                support = ([f for f in cited if _gives_house(f, body, h, ref)] or
                           [f for f in para_facts if _gives_house(f, body, h, ref)])
                # "a Full Moon falls in the 9th from your Moon": a lunation, so only the
                # cited event has to give that house; a yoga fact ("exchange signs (9th and
                # 10th houses)") gives its own houses
                lunation = body == "Moon" and re.search(r"\b(?:New|Full)\s+$", sent_m[:start])
                from_yoga = any(f.startswith("Yoga:") for f in support)
                if (body, h) not in all_houses and not lunation and not from_yoga:
                    problems.append(f"{body} in the {_ord(h)} house is not on the fact sheet.")
                elif cited and not support:
                    kind = _kind(sent)
                    where = None if kind is None else next(
                        (i for i, f in enumerate(fs.facts, 1) if _gives_house(f, body, h, ref)
                         and f.startswith("Birth chart:") == (kind == "natal")), None)
                    problems.append(f"{body} in the {_ord(h)} house is not in the facts it cites ({cited_ids})"
                                    + (f"; the sheet has it in F{where}." if where else "."))
                elif "Moon" in fs.uncertain and MOON_HOUSE.search(sent) and not HEDGES.search(sent):
                    problems.append("Houses counted from the Moon depend on the uncertain Moon sign, but the "
                                    "sentence states them as certain.")
        for m in DASHA_RE.finditer(sent):
            for lord in re.findall(_BODY, m.group(0), re.I):
                if _title(lord) not in fs.dasha_lords:
                    problems.append(f"A {_title(lord)} dasha is not on the fact sheet.")
        # retrograde: "is retrograde" needs a cited fact saying so; "is not retrograde" must
        # not contradict a birth fact that says "Retrograde at birth"
        # "I can't confirm that Saturn squares your Sun" declines the claim: nothing to check
        declining = bool(NOT_APPLY.search(sent))
        # checked clause by clause, each against the citations that close it, so "It was
        # retrograde at birth [F5], and it's retrograde in the sky [F19]" checks F19 for the second
        pieces = re.split(r"((?:\s*\[F\d+\])+)", sent)
        for k in range(0, len(pieces), 2):
            clause = pieces[k]
            c_ids = CITE_RE.findall(pieces[k + 1]) if k + 1 < len(pieces) else []
            c_cited = [f for f in map(fact, c_ids) if f] or cited
            # the planet nearest the word: "planets in the 10th from the Moon, like Jupiter, are
            # retrograde" is about Jupiter
            found = [] if declining else [(_canon(_title(m.group(3))) if m.group(3) else
                                           _bodies(m.group(1) + m.group(2))[-1],
                                           bool(m.group(1) and NEGATED.search(m.group(2))))
                                          for m in RETRO_RE.finditer(clause)]
            pronoun = re.search(r"\bit(?:'s| is| was| has been)?\b([^.;]{0,30}?)\bretrograde\b", clause, re.I)
            if not found and pronoun and last_body and not declining:
                found = [(last_body, bool(NEGATED.search(pronoun.group(1))))]
            for body, negated in found:
                if negated:
                    natal = [f for f in fs.facts if f.startswith(f"Birth chart: {body} ")]
                    if any("Retrograde at birth" in f for f in natal) and re.search(r"\bbirth|\bnatal|\bchart\b", sent, re.I):
                        problems.append(f"Says {body} is not retrograde at birth, but the fact sheet says it is.")
                elif not c_cited:
                    problems.append(f"Claim without a fact citation: \"{sent.strip()[:90]}\"")
                elif not any(_retro_in(f, body) for f in c_cited):
                    problems.append(f"{body} retrograde is not in the facts it cites "
                                    f"({', '.join(dict.fromkeys('F' + c for c in c_ids)) or cited_ids}).")
            named = _bodies(clause)
            # "it forms a yoga with Mercury [F32]": the cited yoga must name Mercury
            clause_facts = [f for f in map(fact, c_ids) if f]
            if any(f.startswith("Yoga:") for f in clause_facts) and re.search(r"\byogas?\b", clause, re.I):
                for b in dict.fromkeys(named):
                    if not any(_mentions(f, b) for f in clause_facts):
                        problems.append(f"Ties {b} to a yoga whose cited fact doesn't name {b} "
                                        f"({', '.join('F' + c for c in dict.fromkeys(c_ids))}).")
            if named:
                last_body = named[-1]
        # aspects: the cited facts must name the same kind of contact, with one of the bodies
        bodies_here = set(_bodies(sent))
        for kind, (said, in_fact) in ASPECTS.items():
            if declining or not re.search(said, sent, re.I):
                continue
            if not cited:
                problems.append(f"Claim without a fact citation: \"{sent.strip()[:90]}\"")
                continue
            # "X squares your Y": a cited fact must name X and then Y (X may equal Y: "Sun
            # conjunct your Sun"). Without a clear X-aspect-Y phrase, a fact must name two of
            # the planets in the sentence (both ends of the contact).
            triples = [(_canon(_title(m.group(1))), _canon(_title(m.group(2))))
                       for m in re.finditer(rf"\b({_BODY})\b(?:'s)?{_GAP}\W+(?:{said})\W+(?:with\W+|to\W+|on\W+)?"
                                            rf"(?:your\W+|the\W+)?(?:natal\W+)?({_BODY})\b", sent, re.I)]
            if triples:
                for x, y in triples:
                    nx, ny = (("(?:Lagna|Ascendant)" if b == "Ascendant" else b) for b in (x, y))
                    # "Mars squares your Jupiter and opposes your Moon": the subject of "opposes"
                    # is Mars, so another planet named in the sentence may stand in for x
                    starts = [nx] + [b for b in bodies_here if b not in (x, y)]
                    if not any(re.search(in_fact, f, re.I) and
                               any(re.search(rf"\b{s}\b[^.]*?\b{ny}\b", f) for s in starts)
                               for f in cited):
                        problems.append(f"The {kind} between {x} and {y} is not in the facts it cites ({cited_ids}).")
                continue
            need = min(2, len(bodies_here))
            ok = [f for f in cited if re.search(in_fact, f, re.I) and
                  sum(_mentions(f, b) for b in bodies_here) >= need]
            if not ok:
                problems.append(f"The {kind} in \"{sent.strip()[:60]}\" is not in the facts it cites ({cited_ids}).")
        # a date must come from a cited fact (the sentence's own, or its paragraph's for a
        # summary sentence), so an event can't be moved to another event's date
        cited_dates = set().union(*map(_dates_in, cited)) if cited else set()
        for d in dates - {x for x in dates if _near(x, period_dates)}:
            name = f"{d[1]} {list(MONTHS)[d[0] - 1].title()}"
            if not _near(d, fs.dates):
                problems.append(f"The date {name} is not on the fact sheet.")
            elif not cited:
                problems.append(f"Claim without a fact citation: \"{sent.strip()[:90]}\"")
            elif not _near(d, cited_dates):
                problems.append(f"The date {name} does not belong to the facts cited with it.")
        if bare and not any(_near(d, period_dates) for d in bare):
            day = next(iter(bare))[1]
            if not any(_near(d, fs.dates) for d in bare):
                problems.append(f"The day {_ord(day)} is not on the fact sheet.")
            elif not cited:
                problems.append(f"Claim without a fact citation: \"{sent.strip()[:90]}\"")
            elif not any(_near(d, cited_dates) for d in bare):
                problems.append(f"The {_ord(day)} does not belong to the facts cited with it.")
        dates |= bare
        # "Sun, Mars and Mercury are favourable" when a cited transit says Mercury is unfavourable
        # judged clause by clause: "Sun is unfavourable, but Mercury offers support"
        for part in re.split(r",?\s+(?:but|while|whereas|although|though|however|yet)\b|;", sent):
            # "less favourable" / "not as favourable" mean unfavourable here
            part = re.sub(r"\b(?:less|not as|not very|hardly) favou?rable\b", "unfavourable", part, flags=re.I)
            says_bad = re.search(r"\bunfavou?rable\b", part, re.I)
            says_good = re.search(r"(?<!un)\bfavou?rable\b", part, re.I)
            if not (says_good or says_bad) or (says_good and says_bad) or NEGATED.search(part):
                continue
            for body in dict.fromkeys(_bodies(part)):
                verdicts = [f for f in cited if f.startswith((f"Transit: {body} in", f"Transit: {body} ("))]
                want = "unfavourable" if says_bad else "favourable"
                if verdicts and not any(re.search(rf"verdict: {want}", f) for f in verdicts):
                    problems.append(f"Calls {body}'s transit {want}, but the facts it cites say otherwise.")
        # nakshatra lord and deity must match the classical lists on the sheet
        from vedic import DASHA_LORDS
        naks_here = [n for n in NAKSHATRAS if re.search(rf"\b{re.escape(n)}\b", sent)] or (
            last_naks if re.search(r"\b(?:both|each|this nakshatra|these nakshatras)\b", sent, re.I) else [])
        if naks_here:
            lords = {DASHA_LORDS[NAKSHATRAS.index(n) % 9] for n in naks_here}
            for m in re.finditer(rf"\bruled by (?:the )?({_BODY})\b|\b({_BODY})-ruled\b", sent, re.I):
                lord = _title(m.group(1) or m.group(2))
                if lord not in lords:
                    problems.append(f"{' and '.join(naks_here)} {'is' if len(naks_here) == 1 else 'are'} not "
                                    f"ruled by {lord} (the lord is {' or '.join(sorted(lords))}).")
            for m in re.finditer(r"\b(?:god|goddess|deity|deities)\b(?:\s+(?:is|are|of|the|named))*\s+([A-Z][\w-]+)", sent):
                if not any(m.group(1) in f for f in fs.facts):
                    problems.append(f"The deity {m.group(1)} is not on the fact sheet.")
            last_naks = naks_here
        if NO_TENSION.search(sent):
            scope = [f for f in fs.facts if not dates or any(_near(d, _dates_in(f)) for d in dates)]
            tense = [i for i, f in enumerate(fs.facts, 1) if f in scope and TENSE_FACT.search(f)]
            if tense:
                problems.append(f"Says there is nothing tense or unfavourable, but the fact sheet lists some "
                                f"({', '.join(f'F{i}' for i in tense[:4])}).")
        for pattern, topic in BANNED.items():
            if not re.search(pattern, sent, re.I):
                continue
            asked = bool(q) and re.search(pattern, q, re.I)
            predicting = bool(dates) or (PREDICTS.search(sent) and not REFUSAL.search(sent))
            if REFUSAL.search(sent) or (asked and declines and not predicting):
                continue
            problems.append(f"Mentions a banned topic ({topic}).")
        # a sentence that cites facts must rule the idea out itself; an uncited one (a
        # definition) is fine when the answer as a whole declines
        if fs.system == "Western" and VEDIC_ONLY.search(sent) and not (
                RULED_OUT.search(sent) or (not own and RULED_OUT.search(text))):
            problems.append(f"Uses a Vedic idea ({VEDIC_ONLY.search(sent).group(0)}) in a Western reading.")
    for n in NAKSHATRAS:
        if re.search(rf"\b{re.escape(n)}\b", text) and n not in fs.nakshatras:
            problems.append(f"Nakshatra {n} is not on the fact sheet.")
    for y in YEAR_RE.findall(text):
        if int(y) not in years:
            problems.append(f"The year {y} is not on the fact sheet.")
    return list(dict.fromkeys(problems))


# ---------------------------------------------------------------------------
# Running it
# ---------------------------------------------------------------------------
def build_prompt(fs: FactSheet, question: str | None = None, words: int = 250) -> tuple[str, str]:
    system = SYSTEM_RULES.format(words=words)
    ask = question.strip() if question else "Write a reading of this period for me."
    user = f"FACT SHEET\n{fs.text()}\n\nREQUEST\n{ask}"
    return system, user


def interpret(fs: FactSheet, call, question: str | None = None, words: int = 250,
              retries: int = 1) -> dict:
    """Ask the model, check the answer, retry once with the problems listed.

    Returns {"ok", "text" (citations removed), "cited" (fact texts used), "problems",
    "raw"}. When ok is False the app should show the fact list instead of "text"."""
    system, user = build_prompt(fs, question, words)
    raw, problems = "", []
    for attempt in range(retries + 1):
        prompt = user if attempt == 0 else (
            f"{user}\n\nYOUR PREVIOUS ANSWER\n{raw}\n\nIT BROKE THESE RULES\n- " + "\n- ".join(problems) +
            "\n\nWrite it again, fixing every point and using only the fact sheet.")
        raw = _norm_cites(call(system, prompt))
        problems = check(raw, fs, question)
        if not problems:
            break
    cited = sorted({int(c) for c in CITE_RE.findall(raw) if 1 <= int(c) <= len(fs.facts)})
    clean = re.sub(r"\s*(?:\[F\d+\])+", "", raw).strip()
    return {"ok": not problems, "text": clean, "raw": raw, "problems": problems,
            "cited": [f"F{i}. {fs.facts[i - 1]}" for i in cited]}
