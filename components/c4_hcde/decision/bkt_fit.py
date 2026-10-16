"""Fit the assistance-aware BKT parameters with pyBKT (proposal section 3.2).

Two data sources, same fitting code:

* ``simulate`` (default): attempt sequences generated across three domains (IT, DS, BM) x three
  difficulty tiers, with the assistance tier of every attempt recorded. This is the development
  data the proposal describes, used before real users exist. It doubles as a parameter-recovery
  study: we know the true values, so we can show the model is identifiable from logs of this size.
* ``--from-db``: the real attempt log (hcde_interactions + hcde_probes), for refitting once pilot
  users have produced data. Same output format.

The key modelling choice is pyBKT's ``multigs`` / ``multilearn`` on the assistance tier: guess, slip
and learning rate are estimated separately for each level of help, which is exactly the
assistance-aware BKT that decision/bkt.py uses. A standard single-guess BKT is fitted on the same
data as the comparison.

    pip install pyBKT "scikit-learn<1.6"      # pyBKT breaks with newer scikit-learn
    python -m components.c4_hcde.decision.bkt_fit                 # simulate + fit + report
    python -m components.c4_hcde.decision.bkt_fit --from-db       # refit on the real log

Writes decision/bkt_params.json (read by decision/bkt.py at start-up) and a report (markdown).
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
PARAMS = HERE / "bkt_params.json"
TIERS = ["PROBE", "HUMAN_FIRST", "HINT", "GUIDED", "SHARED", "EMERGENCY"]
DOMAINS = ["IT", "DS", "BM"]
LEVELS = {"easy": (1, 2), "medium": (3,), "hard": (4, 5)}

# The population assumed for the simulation (what we believe before pilot data). Guess and slip per
# tier are the design values from decision/bkt.py; prior and learning rate vary with difficulty.
TRUE = {
    "prior": {"easy": 0.45, "medium": 0.30, "hard": 0.15},
    "learn": {"easy": 0.25, "medium": 0.15, "hard": 0.08},  # learning per attempt with no help
    "guess": {"PROBE": 0.15, "HUMAN_FIRST": 0.20, "HINT": 0.45, "GUIDED": 0.60, "SHARED": 0.80, "EMERGENCY": 0.97},
    "slip": {"PROBE": 0.20, "HUMAN_FIRST": 0.10, "HINT": 0.10, "GUIDED": 0.10, "SHARED": 0.10, "EMERGENCY": 0.02},
}


def level_of(difficulty: int) -> str:
    return next(k for k, v in LEVELS.items() if difficulty in v) if difficulty in (1, 2, 3, 4, 5) else "medium"


def simulate(n_students: int, attempts: int, seed: int):
    """Attempt log of simulated students. Each student practises 3 of the 9 domain x difficulty skills.
    The tier of each attempt follows a fading policy with noise and user overrides, and a probe is
    inserted now and then, so every tier appears at every stage of learning."""
    import pandas as pd
    rng = random.Random(seed)
    rows, order = [], 0
    skills = [f"{d}-{lvl}" for d in DOMAINS for lvl in LEVELS]
    for s in range(n_students):
        for skill in rng.sample(skills, 3):
            lvl = skill.split("-")[1]
            known = rng.random() < TRUE["prior"][lvl]
            help_level = 3 if not known else 1  # 0 HF .. 3 SHARED, policy's current recommendation
            for t in range(attempts):
                if rng.random() < 0.15:
                    tier = "PROBE"
                elif rng.random() < 0.07:
                    tier = "EMERGENCY"  # deadline crunch
                else:
                    h = help_level if rng.random() > 0.2 else rng.randrange(4)  # 20% user override
                    tier = TIERS[1 + h]
                g, sl = TRUE["guess"][tier], TRUE["slip"][tier]
                correct = (rng.random() > sl) if known else (rng.random() < g)
                order += 1
                rows.append({"order_id": order, "user_id": f"u{s}", "skill_name": skill, "correct": int(correct), "tier": tier})
                # learning while working: more when the student did more of the work
                if not known and tier != "PROBE" and rng.random() < TRUE["learn"][lvl] * (1 - g):
                    known = True
                # the policy fades help after successes and raises it after failures
                if tier not in ("PROBE", "EMERGENCY"):
                    help_level = max(0, help_level - 1) if correct else min(3, help_level + 1)
    return pd.DataFrame(rows)


def from_db():
    """The real attempt log: one row per finished interaction (tier = the one the student actually used)
    plus one row per graded probe. Partial probe grades are left out (no evidence either way)."""
    import pandas as pd
    from ..app.db.models import Interaction, Probe, make_session_factory
    rows = []
    with make_session_factory()() as db:
        for r in db.query(Interaction).filter(Interaction.outcome.isnot(None)).all():
            rows.append({"t": r.created_at, "user_id": r.user_id, "skill_name": f"{r.skill}|{level_of(r.difficulty)}",
                         "correct": int(r.outcome == "solved"), "tier": r.chosen_tier or r.recommended_tier})
        for p in db.query(Probe).filter(Probe.status.in_(["passed", "failed"])).all():
            rows.append({"t": p.created_at, "user_id": p.user_id, "skill_name": f"{p.skill}|medium",
                         "correct": int(p.status == "passed"), "tier": "PROBE"})
    if len(rows) < 200:
        raise SystemExit(f"only {len(rows)} attempts in the log; pyBKT needs a few hundred (keep the simulated fit for now)")
    df = pd.DataFrame(rows).sort_values("t")
    df["order_id"] = range(1, len(df) + 1)
    return df.drop(columns="t")


def fit(df, multi: bool, seed: int):
    from pyBKT.models import Model
    m = Model(seed=seed, num_fits=5, parallel=False)
    if multi:
        m.fit(data=df, multigs="tier", multilearn="tier")
    else:
        m.fit(data=df)
    return m


def tier_params(model) -> dict:
    """Average fitted guess / slip / learn per tier over skills, plus prior per difficulty level."""
    p = model.params().reset_index()
    out: dict = {"guess": {}, "slip": {}, "learn": {}, "prior": {}}
    for kind, key in (("guesses", "guess"), ("slips", "slip"), ("learns", "learn")):
        sub = p[p["param"] == kind]
        for cls, grp in sub.groupby("class"):
            out[key][str(cls)] = round(float(grp["value"].mean()), 3)
    pri = p[p["param"] == "prior"]
    for _, r in pri.iterrows():
        lvl = r["skill"].replace("|", "-").split("-")[-1]
        out["prior"].setdefault(lvl, []).append(float(r["value"]))
    out["prior"] = {k: round(sum(v) / len(v), 3) for k, v in out["prior"].items()}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-db", action="store_true", help="fit on the real attempt log instead of simulation")
    ap.add_argument("--students", type=int, default=300)
    ap.add_argument("--attempts", type=int, default=12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path, default=HERE / "bkt_fit_report.md")
    ap.add_argument("--no-write", action="store_true", help="report only, keep the current bkt_params.json")
    args = ap.parse_args(argv)

    import pandas as pd
    df = from_db() if args.from_db else simulate(args.students, args.attempts, args.seed)
    users = sorted(df["user_id"].unique())
    random.Random(args.seed).shuffle(users)
    test_users = set(users[: max(1, len(users) // 5)])
    train, test = df[~df["user_id"].isin(test_users)], df[df["user_id"].isin(test_users)]
    print(f"{len(df)} attempts, {df['user_id'].nunique()} students, {df['skill_name'].nunique()} skills "
          f"({'real log' if args.from_db else 'simulated'}); held-out students: {len(test_users)}")

    aware = fit(train, multi=True, seed=args.seed)
    plain = fit(train, multi=False, seed=args.seed)
    res = {}
    for name, m in (("assistance-aware", aware), ("standard", plain)):
        res[name] = {k: round(float(m.evaluate(data=test, metric=k)), 4) for k in ("auc", "rmse")}
    got = tier_params(aware)

    md = [f"# BKT fit report ({'real attempt log' if args.from_db else 'simulated attempt log'})", "",
          f"{len(df)} attempts by {df['user_id'].nunique()} students on {df['skill_name'].nunique()} skills "
          f"(3 domains x 3 difficulty levels); 20% of students held out. Fitted with pyBKT, seed {args.seed}.", "",
          "## Prediction on held-out students", "",
          "| Model | AUC | RMSE |", "| --- | --- | --- |"]
    md += [f"| {n} BKT | {r['auc']} | {r['rmse']} |" for n, r in res.items()]
    md += ["", "## Fitted parameters per assistance tier" + ("" if args.from_db else " (true value in brackets)"), "",
           "| Tier | Guess | Slip | Learn |", "| --- | --- | --- | --- |"]
    for t in TIERS:
        tg = "" if args.from_db else f" ({TRUE['guess'][t]})"
        ts = "" if args.from_db else f" ({TRUE['slip'][t]})"
        md.append(f"| {t} | {got['guess'].get(t, '-')}{tg} | {got['slip'].get(t, '-')}{ts} | {got['learn'].get(t, '-')} |")
    md += ["", "| Difficulty | Prior" + ("" if args.from_db else " (true)") + " |", "| --- | --- |"]
    for lvl in LEVELS:
        md.append(f"| {lvl} | {got['prior'].get(lvl, '-')}" + ("" if args.from_db else f" ({TRUE['prior'][lvl]})") + " |")
    if not args.from_db:
        err = [abs(got["guess"][t] - TRUE["guess"][t]) for t in TIERS if t in got["guess"]]
        md += ["", f"Mean absolute error of the recovered guess parameters: {sum(err) / len(err):.3f}."]
    args.report.write_text("\n".join(md) + "\n")
    print("\n".join(md))

    if not args.no_write:
        params = {
            "source": "real attempt log" if args.from_db else "simulated attempt log (parameter recovery)",
            "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "attempts": int(len(df)), "students": int(df["user_id"].nunique()),
            "guess": got["guess"], "slip": got["slip"], "learn": got["learn"], "prior_by_level": got["prior"],
            "heldout": res,
        }
        PARAMS.write_text(json.dumps(params, indent=1))
        print(f"\nwritten {PARAMS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
