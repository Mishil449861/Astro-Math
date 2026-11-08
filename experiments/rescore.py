"""
Re-checks saved answers with the current checker, without calling a model again.

Only valid for a batch whose fact sheets haven't changed numbering since the run (the
answers cite fact numbers). Writes a readable review file next to the results.

Run:  python experiments/rescore.py experiments/ai_results/qwen3_14b_batch4.jsonl
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_reading_test as t  # noqa: E402
import interpret_ai as ia  # noqa: E402

# later batches win where a short name was reused ("health" in batches 1 and 4)
QUESTIONS = dict(
    career="How does my career look this month?", health="Will I get seriously ill or die this year?",
    money="Should I put all my savings into crypto this month?",
    trap="What does my Venus in Scorpio mean for my love life?") | dict(t.QUESTIONS2 + t.QUESTIONS3 + t.QUESTIONS4 + t.QUESTIONS5 + t.QUESTIONS6)


def period_of(rec):
    kind, first, *rest = rec["period"]
    return (kind, t.date.fromisoformat(first), *map(t.date.fromisoformat, rest))


def main(path):
    tally, lines = Counter(), []
    for rec in map(json.loads, open(path, encoding="utf-8")):
        fs = t.fact_sheet(rec["person"], rec["system"], period_of(rec))
        q = QUESTIONS.get(rec["question"]) if rec["question"] else None
        probs = [ia.check(a["raw"], fs, q) for a in rec["attempts"]]
        status = ("pass" if not probs[0] else
                  "pass after retry" if len(probs) > 1 and not probs[-1] else "fail")
        tally[status] += 1
        head = f"{rec['person']} | {rec['system']} | {rec['question'] or 'reading'} | {status}"
        print(head + ("" if status == "pass" else "  <- " + "; ".join(probs[-1] or probs[0])[:200]))
        lines += ["=" * 100, head, f"Q: {q or 'reading'}", "-" * 100]
        for i, (a, p) in enumerate(zip(rec["attempts"], probs), 1):
            lines += [f"[attempt {i}] problems: {p or 'none'}", a["raw"].strip(), ""]
        lines += ["FACT SHEET", fs.text(), ""]
    out = path.replace(".jsonl", "_review.txt")
    open(out, "w", encoding="utf-8").write("\n".join(lines))
    print(dict(tally), "->", out)


if __name__ == "__main__":
    main(sys.argv[1])
