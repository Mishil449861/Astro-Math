"""
Checks for the AI guard rails. No model is called: a fake model returns fixed answers.
Run:  python -m pytest tests
"""
import os
import re
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import astro_engine as ae  # noqa: E402
import interpret_ai as ia  # noqa: E402
import vedic as vd  # noqa: E402

SID = ae.Chart("sidereal")
START, END, LABEL = ae.period_bounds("Month", date(2026, 11, 1), "UTC")
# 3 Jan 1990, time unknown: the Moon moves from Aquarius into Pisces that day
NATAL = ae.compute_natal(SID, vd.GRAHAS, date(1990, 1, 3), None, 0, timedelta(0), 0.0, 0.0)
REPORT = vd.analyze_vedic(SID, NATAL, START, END, "UTC")
FS = ia.vedic_facts(NATAL, REPORT, LABEL)
MOON = next(i for i, f in enumerate(FS.facts, 1) if f.startswith("Birth chart: Moon"))
SATURN = next(i for i, f in enumerate(FS.facts, 1) if f.startswith("Transit: Saturn"))


def test_fact_sheet_keeps_uncertainty():
    assert FS.uncertain == {"Moon": {10, 11}}
    assert "either in Kumbha (Aquarius) or Meena (Pisces)" in FS.facts[MOON - 1]
    assert any("could instead be" in f for f in FS.facts)          # dasha alternatives listed
    assert not any("illness" in f for f in FS.facts)               # softened house theme


def test_good_reading_passes():
    text = (f"Your birth Moon is either in Aquarius or Pisces, so read this as a range [F{MOON}]. "
            f"Saturn transits Pisces this month [F{SATURN}].")
    assert ia.check(text, FS) == []


def test_invented_and_overconfident_claims_fail():
    cases = {
        f"Your birth Moon is in Capricorn [F{MOON}].": "not on the fact sheet",
        f"Your birth Moon is in Aquarius [F{MOON}].": "stated as certain",
        "Jupiter enters Gemini this month [F1].": "Jupiter in Gemini",
        # a real transit, but credited to the birth-chart fact: caught by the citation check
        f"Your natal Saturn sits in Pisces [F{MOON}].": "not in the facts it cites",
        "Saturn in the 7th house tests partnerships [F1].": "7th house",
        "Your Sun in Pisces makes you dreamy.": "without a fact citation",
        "Something big happens on 3 March 2026 [F1].": "date",
        "Mars is strong [F999].": "F999",
        "The Pushya energy is strong [F1].": "Pushya",
        "A great month to invest in property [F1].": "financial advice",
        "Watch out for accidents [F1].": "accidents",
    }
    for text, expected in cases.items():
        problems = ia.check(text, FS)
        assert any(expected in p for p in problems), (text, problems)


def test_declining_a_banned_question_is_allowed_but_predictions_are_not():
    q = "Am I going to have an accident?"
    polite = ("I don't have enough information to say whether you'll have an accident. "
              "Astrology readings don't typically predict accidents.")
    assert ia.check(polite, FS, q) == []
    sneaky = polite + " Still, an accident will likely come late in the month."
    assert any("accidents" in p for p in ia.check(sneaky, FS, q))
    # not asked about: naming the topic is a problem even in a polite sentence
    assert any("accidents" in p for p in ia.check("Avoid accidents this month [F1].", FS))
    assert ia.check("These are traditional associations, not guarantees.", FS) == []


def test_summary_sentence_takes_citations_from_its_paragraph():
    dated = next(i for i, f in enumerate(FS.facts, 1) if f.startswith("Event on "))
    day = FS.facts[dated - 1].split("Event on ")[1].split(":")[0]           # e.g. "09 November 2026"
    text = f"Watch {day.lstrip('0')}. That day brings an event [F{dated}]."
    assert ia.check(text, FS) == []
    assert any("without a fact citation" in p for p in ia.check(f"Watch {day.lstrip('0')}.", FS))


def test_retry_then_fallback():
    good = f"Saturn transits Pisces this month [F{SATURN}]."
    answers = iter(["Saturn transits Gemini this month [F1].", good])
    out = ia.interpret(FS, lambda system, user: next(answers))
    assert out["ok"] and out["text"] == "Saturn transits Pisces this month."
    assert out["cited"][0].startswith(f"F{SATURN}. Transit: Saturn")

    seen = []
    out = ia.interpret(FS, lambda system, user: seen.append(user) or "Mars is strong [F999].")
    assert not out["ok"] and len(seen) == 2
    assert "IT BROKE THESE RULES" in seen[1]                        # problems were fed back


def test_prompt_contains_rules_and_facts():
    system, user = ia.build_prompt(FS, "How is my career?")
    assert "Use only the fact sheet" in system and "either A or B" in system
    assert user.startswith("FACT SHEET\nF1. ") and user.endswith("How is my career?")


def test_moon_houses_need_a_caveat_when_the_moon_sign_is_uncertain():
    fact = FS.facts[SATURN - 1]                                  # "... 2nd house from the natal Moon ..."
    nth = fact.split(", ")[1].split(" house")[0]
    flat = f"Saturn transits the {nth} house from your Moon [F{SATURN}]."
    assert any("uncertain Moon sign" in p for p in ia.check(flat, FS))
    hedged = f"Saturn transits the {nth} house from your Moon, if your Moon is in that sign [F{SATURN}]."
    assert not any("uncertain Moon sign" in p for p in ia.check(hedged, FS))


def test_lists_of_planets_are_all_checked():
    assert {b for b, _ in ia._pairs_in("Your Sun, Moon, and Mercury in Capricorn")} == {"Sun", "Moon", "Mercury"}


def test_birth_time_wording():
    approx = ae.compute_natal(SID, vd.GRAHAS, date(1990, 1, 3), __import__("datetime").time(12, 0), 20,
                              timedelta(0), 0.0, 0.0)
    fs = ia.vedic_facts(approx, vd.analyze_vedic(SID, approx, START, END, "UTC"), LABEL)
    assert any("approximate, known to within about ±20 minutes" in f for f in fs.facts)
    assert not any("birth time is unknown" in f for f in fs.facts)
    assert any("birth time is unknown" in f for f in FS.facts)


TROP = ae.Chart("tropical")
W_NATAL = ae.compute_natal(TROP, ae.PLANETS, date(1990, 1, 3), None, 0, timedelta(0), 0.0, 0.0)
W_FS = ia.western_facts(W_NATAL, ae.analyze(TROP, W_NATAL, START, END, "UTC"), LABEL)


def test_western_reading_may_only_name_vedic_ideas_to_rule_them_out():
    assert "not part of a Western reading" in W_FS.facts[0]
    assert any("Vedic idea (Sade Sati)" in p
               for p in ia.check("Your Sade Sati makes this a heavy month [F1].", W_FS))
    assert ia.check("Sade Sati is a Vedic idea and is not part of this Western reading [F1].", W_FS) == []
    # an uncited definition is fine when the answer goes on to decline
    assert ia.check("Sade Sati is a long Saturn transit over the Moon. It does not apply to "
                    "this reading.", W_FS) == []
    assert ia.check("Your Sade Sati is heavy now.", W_FS) != []                  # no decline anywhere


def test_sade_sati_fact_names_the_phase_meaning():
    for when in (date(2020, 6, 1), date(2023, 6, 1), date(2025, 6, 1)):
        s, e, lab = ae.period_bounds("Month", when, "UTC")
        fs = ia.vedic_facts(NATAL, vd.analyze_vedic(SID, NATAL, s, e, "UTC"), lab)
        for f in fs.facts:
            if "Sade Sati from" in f:
                assert "traditionally" in f and "phase" in f, f


def _num(fs, start):
    return next(i for i, f in enumerate(fs.facts, 1) if f.startswith(start))


def test_retrograde_claims_must_match_the_facts():
    direct = next(i for i, f in enumerate(W_FS.facts, 1)
                  if f.startswith("Birth chart:") and "Retrograde" not in f and "Sun" not in f)
    body = W_FS.facts[direct - 1].split()[2]
    assert any("retrograde is not in the facts" in p
               for p in ia.check(f"Yes, your {body} is retrograde in your birth chart [F{direct}].", W_FS))
    retro = [i for i, f in enumerate(W_FS.facts, 1) if f.startswith("Birth chart:") and "Retrograde at birth" in f]
    if retro:
        b = W_FS.facts[retro[0] - 1].split()[2]
        assert ia.check(f"Your {b} was retrograde at birth [F{retro[0]}].", W_FS) == []
        assert any("not retrograde at birth" in p
                   for p in ia.check(f"Your {b} is not retrograde in your birth chart [F{retro[0]}].", W_FS))


def test_aspect_claims_need_the_same_aspect_in_the_cited_fact():
    tr = next((i for i, f in enumerate(W_FS.facts, 1) if f.startswith("Transit:") and " square your " in f), None)
    if tr:
        a, b = W_FS.facts[tr - 1].split("Transit: ")[1].split(",")[0].split(" square your ")
        assert ia.check(f"{a} squares your {b}, adding friction [F{tr}].", W_FS) == []
        assert any("opposition" in p for p in ia.check(f"{a} opposing your {b} adds friction [F{tr}].", W_FS))
    # an aspect pinned on a birth-chart fact that names none
    assert any("aspect" in p for p in ia.check(f"Your Moon is aspected by Saturn [F{MOON}].", FS))


def test_an_answer_with_claims_but_no_citations_fails():
    assert any("cites no facts" in p for p in ia.check("Jupiter brings luck and Venus brings love.", FS))
    assert ia.check("I can't tell you that; it isn't something the chart can answer.", FS) == []


def test_clauses_and_custom_periods():
    # ", which ..." no longer hides the claim
    assert any("Capricorn" in p for p in ia.check("Your Moon, which rules feelings, is in Capricorn [F1].", FS))
    # the period's own dates need no citation
    s, e, lab = ae.period_bounds("Custom", date(2026, 11, 3), "UTC", date(2026, 12, 9))
    fs = ia.vedic_facts(NATAL, vd.analyze_vedic(SID, NATAL, s, e, "UTC"), lab)
    assert ia.check("This period runs from November 3 to December 9.", fs) == []


def test_bare_days_are_checked_against_the_period():
    dated = _num(FS, "Event on ")
    day = int(FS.facts[dated - 1].split("Event on ")[1].split()[0])
    other = next(d for d in range(1, 29) if all(abs(d - x) > 1 for m, x in FS.dates if m == 11))
    assert ia.check(f"On the {ia._ord(day)} an event arrives [F{dated}].", FS) == []
    assert any("not on the fact sheet" in p for p in ia.check(f"On the {ia._ord(other)} an event arrives [F{dated}].", FS))
    # "the 8th house" / "the 8th from" are houses, not days
    assert not ia.BARE_DAY.search("from the 8th house") and not ia.BARE_DAY.search("on the 8th from your Moon")


def test_sign_either_is_not_house_either():
    fs = ia.FactSheet()
    fs.add("Birth chart: Jupiter is in Simha (Leo). In either the 9th or 10th from the Moon.")
    fs.pair("Jupiter", 4, natal=True)
    assert ia.check("Your Jupiter is in Leo [F1].", fs) == []


def test_declining_an_aspect_or_retrograde_is_not_a_claim():
    assert ia.check("I cannot confirm that Saturn squares your Sun from these facts [F1].", FS) == []
    assert ia.check("The facts don't show Venus as retrograde.", FS) == []


def test_lunation_houses_come_from_the_event():
    ev = next((i for i, f in enumerate(FS.facts, 1) if "Purnima" in f or "Amavasya" in f), None)
    if ev:
        h = re.search(r"Falls in the (\d+)\w\w from your Moon", FS.facts[ev - 1]).group(1)
        ok = f"A Full Moon falls in the {h}th house from your Moon, or the next if your Moon is in the other sign [F{ev}]."
        assert not any("not on the fact sheet" in p for p in ia.check(ok, FS))


def test_retrograde_belongs_to_the_planet_named():
    fs = ia.FactSheet()
    fs.add("Sky in the middle of the period: Venus 11°08′ Leo, Saturn 10°49′ Taurus (retrograde).")
    fs.add("Event on 24 January 2028: Mercury turns retrograde at 19°42′ Aquarius.")
    assert any("Venus retrograde" in p for p in ia.check("Venus is retrograde in the sky now [F1].", fs))
    assert ia.check("Saturn is retrograde in the sky now [F1].", fs) == []
    assert ia.check("Mercury goes retrograde this month [F2].", fs) == []


def test_saying_nothing_is_tense_when_something_is():
    fs = ia.FactSheet()
    fs.add("Transit: Mercury (retrograde) square your Venus, exact on 30 January 2028. A tense contact.")
    fs.add("Event on 30 January 2028: Exact: Venus sextile your Jupiter. A harmonious contact.")
    fs.date(date(2028, 1, 30))
    assert any("nothing tense" in p for p in ia.check("No conflicting transits are noted on this day.", fs))
    assert ia.check("Venus sextile Jupiter is a harmonious contact on 30 January [F2].", fs) == []


def test_retrograde_with_it_is_checked_clause_by_clause():
    fs = ia.FactSheet()
    fs.add("Birth chart: Venus is in Scorpio. Retrograde at birth.")
    fs.add("Sky in the middle of the period: Venus 11°08′ Leo, Saturn 10°49′ Taurus (retrograde).")
    fs.pair("Venus", 7, natal=True)
    text = "Yes, your Venus is retrograde. It was retrograde at birth [F1], and it's also retrograde in the sky [F2]."
    assert any("Venus retrograde is not in the facts it cites (F2)" in p for p in ia.check(text, fs))
    assert ia.check("Yes, your Venus is retrograde. It was retrograde at birth [F1].", fs) == []


def test_moon_fact_carries_real_nakshatra_lore_and_claims_must_match_it():
    moon = FS.facts[MOON - 1]
    assert "Nakshatra lore:" in moon and "ruled by" in moon and "deity" in moon
    nak = moon.split("Nakshatra lore: ")[1].split(" is ruled by ")[0]
    lord = moon.split(f"{nak} is ruled by ")[1].split(",")[0]
    wrong = next(b for b in ("Saturn", "Mars", "Venus") if b != lord)
    assert ia.check(f"{nak} is ruled by {lord} [F{MOON}].", FS) == []
    assert any("not ruled by" in p for p in ia.check(f"{nak} is ruled by {wrong} [F{MOON}].", FS))
    assert any("deity Durga" in p for p in ia.check(f"{nak} is linked with the goddess Durga [F{MOON}].", FS))


def test_false_missing_wrong_partner_and_wrong_verdict():
    fs = ia.FactSheet()
    fs.add("Transit: Saturn in Mesha (Aries), 5th house from the natal Moon. Traditional verdict: unfavourable.")
    fs.add("Transit: Mercury in Makara (Capricorn), 3rd house from the natal Moon. Traditional verdict: unfavourable.")
    fs.add("Transit: Sun in Makara (Capricorn), 3rd house from the natal Moon. Traditional verdict: favourable.")
    fs.add("Transit: Sun trine your Sun, exact on 30 January 2028. A harmonious contact.")
    assert any("F1 gives it" in p for p in
               ia.check("Saturn's current position is not specified in the facts [F1].", fs))
    assert any("favourable" in p for p in
               ia.check("The Sun and Mercury transits are traditionally favourable [F3][F2].", fs))
    assert ia.check("The Sun's transit is traditionally favourable [F3].", fs) == []
    assert any("trine" in p for p in ia.check("Jupiter makes a harmonious trine with the Sun [F4].", fs))
    assert ia.check("The Sun makes a harmonious trine with your Sun [F4].", fs) == []


def test_verdicts_are_read_per_clause():
    fs = ia.FactSheet()
    fs.add("Transit: Sun in Simha (Leo), 7th house from the natal Moon. Traditional verdict: unfavourable.")
    fs.add("Transit: Mercury in Kanya (Virgo), 8th house from the natal Moon. Traditional verdict: favourable.")
    assert ia.check("The Sun is in an unfavourable position, but Mercury offers support [F1][F2].", fs) == []


def test_denials_nearest_retrograde_yoga_houses_and_its():
    fs = ia.FactSheet()
    fs.add("Birth chart: Moon is in Simha (Leo).")
    fs.add("Birth chart: Jupiter is in Mesha (Aries). In the 10th from the Moon. Retrograde at birth.")
    fs.add("Yoga: Parivartana (Maha). Jupiter and Saturn exchange signs (9th and 10th houses).")
    fs.add("Birth chart: Saturn is in Meena (Pisces). In the 10th house from the Lagna.")
    fs.pair("Moon", 4, natal=True); fs.pair("Jupiter", 0, natal=True); fs.pair("Saturn", 11, natal=True)
    fs.natal_houses |= {("Jupiter", 10), ("Saturn", 10)}
    assert ia.check("No, your Moon is not in Virgo [F1].", fs) == []
    assert any("not in Leo" in p for p in ia.check("No, your Moon is not in Leo [F1].", fs))
    assert ia.check("Planets in the 10th from the Moon, like Jupiter, are retrograde at birth [F2].", fs) == []
    assert ia.check("Jupiter's exchange with Saturn in the 9th and 10th houses brings authority [F3].", fs) == []
    assert any("9th house" in p for p in
               ia.check("Saturn is in Pisces, and its placement in the 9th house matters [F4].", fs))


def test_uncertain_moon_transit_lines_carry_both_counts():
    line = next(f for f in FS.facts if f.startswith("Transit:"))
    assert " if the Moon is in " in line and ", or the " in line and " if it is in " in line


def test_sign_lists_bracketed_houses_and_yoga_members():
    fs = ia.FactSheet()
    fs.add("Transit: Sun in Dhanu (Sagittarius), 11th house from the natal Moon.")
    fs.add("Transit: Jupiter in Tula (Libra), 9th house from the natal Moon.")
    fs.add("Yoga: Amala. Jupiter in the 10th: a clean reputation and good deeds.")
    fs.add("Birth chart: Moon is either in Dhanu (Sagittarius) or Makara (Capricorn).")
    fs.pair("Sun", 8); fs.pair("Jupiter", 6); fs.houses |= {("Sun", 11), ("Jupiter", 9)}
    fs.uncertain["Moon"] = {8, 9}
    assert any("Sun in Libra" in p for p in
               ia.check("The Sun's transit through Sagittarius [F1] and Libra [F2] supports growth.", fs))
    assert any("uncertain Moon" in p for p in
               ia.check("The Sun in Sagittarius (11th house from the Moon) brings gains [F1].", fs))
    assert any("Ties Mercury to a yoga" in p for p in
               ia.check("Jupiter forms a yoga with Mercury, bringing a clean reputation [F3].", fs))
    assert ia.check("The Amala yoga with Jupiter brings a clean reputation [F3].", fs) == []


def test_grouped_planets_and_signs_and_word_boundaries():
    fs = ia.FactSheet()
    fs.add("Transit: Sun in Vrischika (Scorpio), 1st house from the natal Moon.")
    fs.add("Transit: Mars in Dhanu (Sagittarius), 2nd house from the natal Moon.")
    fs.add("Transit: Mercury in Vrischika (Scorpio), 1st house from the natal Moon.")
    fs.add("Yoga: Sunapha. Saturn 2nd from the Moon: self-earned wealth and standing.")
    fs.pair("Sun", 7); fs.pair("Mars", 8); fs.pair("Mercury", 7)
    assert ia.check("The Sun, Mars and Mercury in Scorpio and Sagittarius bring challenges [F1][F2][F3].", fs) == []
    assert ia.check("The Sunapha yoga suggests self-earned wealth [F4].", fs) == []
    assert ia._bodies("Sunapha yoga") == []


def test_batch7_gaps():
    fs = ia.FactSheet()
    fs.add("Event on 07 October 2029: New Moon in Libra. Traditionally a time for fresh starts.")
    fs.add("Transit: Jupiter in Tula (Libra), 5th house from the natal Moon. Traditional verdict: favourable, "
           "but obstructed (vedha by Mercury, Sun).")
    fs.add("Transit: Saturn in Mesha (Aries), 3rd house from the natal Moon. Traditional verdict: favourable.")
    fs.add("Transit: Mercury in Mesha (Aries), 3rd house from the natal Moon. Traditional verdict: unfavourable.")
    fs.add("Transit: Sun in Tula (Libra), 5th house from the natal Moon. Traditional verdict: unfavourable.")
    fs.pair("Moon", 6); fs.pair("Sun", 6); fs.pair("Jupiter", 6); fs.pair("Saturn", 0); fs.pair("Mercury", 0)
    fs.houses |= {("Jupiter", 5), ("Saturn", 3), ("Mercury", 3), ("Sun", 5)}
    fs.date(date(2029, 10, 7))
    assert any("is not on the fact sheet, but it is" in p for p in
               ia.check("A New Moon in Libra is not listed in the facts.", fs))
    # "vedha by Mercury, Sun" is not a fact about the Sun; a transit claim gets a transit hint
    assert any("Sun in the 5th house is not in the facts it cites (F2); the sheet has it in F5" in p for p in
               ia.check("Transiting Mercury and Sun in the 5th house bring obstacles [F2].", fs))
    # "less favourable" is unfavourable: wrong for Saturn, right for Mercury
    probs = ia.check("The 3rd house is under less favourable influence from Mercury and Saturn [F4][F3].", fs)
    assert any("Saturn's transit unfavourable" in p for p in probs)
    assert not any("Mercury's transit" in p for p in probs)
    # a true claim whose fact is cited elsewhere in the paragraph passes
    assert ia.check("Jupiter brings growth [F2]. Jupiter in Libra is also obstructed [F3].", fs) == []


def test_house_reference_point_and_hint_kind():
    fs = ia.FactSheet()
    fs.add("Birth chart: Jupiter is in Kumbha (Aquarius). In the 9th house from the Lagna and the 4th from the Moon.")
    fs.add("Transit: Jupiter in Simha (Leo), 10th house from the natal Moon (career). Traditional verdict: unfavourable.")
    fs.add("Birth chart: Sun is in Tula (Libra).")
    fs.add("Transit: Sun in Dhanu (Sagittarius), 11th house from the natal Moon.")
    fs.pair("Jupiter", 10, natal=True); fs.pair("Jupiter", 4); fs.pair("Sun", 6, natal=True); fs.pair("Sun", 8)
    fs.natal_houses |= {("Jupiter", 9), ("Jupiter", 4)}; fs.houses |= {("Jupiter", 10), ("Sun", 11)}
    # 10th from the Lagna is wrong even though another cited fact has a 10th from the Moon
    probs = ia.check("Jupiter's transit is unfavourable [F2]. Jupiter is in Aquarius, and its placement is in "
                     "the 10th house from your Lagna [F1].", fs)
    assert any("10th house" in p for p in probs), probs
    assert ia.check("Jupiter is in the 9th house from your Lagna [F1].", fs) == []
    # no birth-chart hint for a transit claim
    probs = ia.check("The Sun's transit through Libra brings balance [F4].", fs)
    assert probs and not any("F3" in p for p in probs)


def test_batch8_gaps():
    fs = ia.FactSheet()
    fs.add("Birth chart: Jupiter is in Vrischika (Scorpio). In the 6th from the Moon.")
    fs.add("Birth chart: Venus is in Simha (Leo). In the 3rd from the Moon.")
    fs.add("Event on 04 March 2030: Amavasya (New Moon) in Kumbha (Aquarius). Falls in the 9th from your Moon.")
    fs.pair("Jupiter", 7, natal=True); fs.pair("Venus", 4, natal=True); fs.pair("Sun", 10); fs.pair("Moon", 10)
    fs.natal_houses |= {("Jupiter", 6), ("Venus", 3)}; fs.houses |= {("Sun", 9)}
    fs.date(date(2030, 3, 4))
    # "from the Moon" is a reference point, not the Moon in a house
    assert ia.check("This is supported by Venus in the 3rd from the Moon [F2], and Jupiter in the 6th "
                    "from the Moon [F1].", fs) == []
    # a New Moon puts the Sun in that sign
    assert ia.check("The Sun in Aquarius, on the New Moon day, falls in the 9th house from your Moon [F3].", fs) == []
    sat = [f for f in FS.facts if f.startswith("Saturn:")]
    assert sat and all("12th, 1st and 2nd signs" in f for f in sat)


def test_a_claim_belongs_to_the_nearest_planet_and_facts_are_stable():
    pairs = [(m.group(1), m.group(2)) for m in ia.HOUSE_RE.finditer(
        "If your dasha is Saturn–Ketu, astrologers interpret Saturn in your 2nd house")]
    assert pairs == [("Saturn", "2")]
    # yoga facts come out in the same order every run (several yogas share the name "Raja")
    import yogas
    rows = yogas.evaluate(NATAL)["rows"]
    keys = [(r["Status"] != "present", r["Type"], r["Yoga"], r["Meaning"]) for r in rows]
    assert keys == sorted(keys)


def test_gemini_phrasings():
    fs = ia.FactSheet()
    fs.add("Saturn: not in Sade Sati now; the next Sade Sati starts 17 April 2030. " + ia.SADE_SATI_DEF)
    fs.add("Transit: Saturn in Mesha (Aries), 11th house from the natal Moon.")
    fs.add("Transit: Sun conjunct your Sun, exact on 03 January 2030. This puts a spotlight on the area.")
    fs.add("Event on 22 October 2029: Full Moon in Aries. Traditionally a time of culmination.")
    fs.pair("Saturn", 0); fs.pair("Moon", 0); fs.houses |= {("Saturn", 11)}
    fs.date(date(2030, 1, 3)); fs.date(date(2029, 10, 22))
    # restating the Sade Sati definition is not placing Saturn in the 12th
    assert ia.check("Sade Sati is the time transiting Saturn spends in the 12th, 1st and 2nd signs from "
                    "the natal Moon sign [F1].", fs) == []
    # "[F1, F2]" is read like "[F1][F2]"
    assert ia.check("Transiting Saturn is in Mesha (Aries) [F1, F2].", fs) == []
    assert ia._norm_cites("x [F2, F19] y [F3 and F4]") == "x [F2][F19] y [F3][F4]"
    # a planet aspecting itself names one planet
    assert ia.check("The Sun conjunct your Sun on January 3 brings visibility [F3].", fs) == []
    # citing the fact while saying it isn't an eclipse is not a denial
    assert ia.check("It does show a Full Moon in Aries, but this event is not listed as an eclipse [F4].", fs) == []


def test_aspect_partners_are_read_per_phrase():
    fs = ia.FactSheet()
    fs.add("Aspect: transiting Saturn casts its 7th sign aspect on the natal Lagna (heavy, testing).")
    fs.add("Transit: Venus opposite your Sun, exact on 20 August 2028. A tense contact.")
    assert ia.check("Transiting Saturn aspects the Lagna, a heavy influence [F1].", fs) == []
    assert any("opposition between Mars and Sun" in p for p in
               ia.check("Mars opposite your Sun adds tension [F2].", fs))
    assert ia.check("Venus opposite your Sun adds tension [F2].", fs) == []


def test_coordinated_aspect_verbs():
    fs = ia.FactSheet()
    fs.add("Transit: Mars square your Jupiter, in effect 26 January 2028 to 31 January 2028. A tense contact.")
    fs.add("Transit: Mars opposite your Moon, in effect 26 January 2028 to 31 January 2028. A tense contact.")
    assert ia.check("Mars squares your Jupiter and opposes your Moon, bringing tension [F1][F2].", fs) == []


def test_citation_ranges_are_dropped_and_never_shown():
    assert ia._norm_cites("No eclipse is listed [F1][F19-F34].") == "No eclipse is listed [F1]."
    out = ia.interpret(FS, lambda s, u: "I can't say whether there is an eclipse; none is listed [F1-F9].")
    assert "[F" not in out["text"]
