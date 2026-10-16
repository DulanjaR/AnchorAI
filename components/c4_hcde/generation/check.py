"""Check the student's own answer, with feedback that respects their assistance tier.

1. Reference: the model writes a full solution once (EMERGENCY tier), stored server-side, never shown
   unless the student is at EMERGENCY.
2. Deterministic checks first: Python answers are compiled, so syntax errors are reported with the exact
   line (no model guesswork).
3. Grading: the model compares the answer with the reference and returns STRUCTURED fields:
   result (pass/partial/fail), where (location), what (the problem), fix (how to fix), why (why a correct
   answer works).
4. Feedback is ASSEMBLED from those fields by tier, so how much is revealed is controlled by code, not by
   the model: Human First/Hint get only *where*, Guided gets *where + what*, Shared adds *the fix idea*,
   Emergency gets everything including the reference.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass

from . import ollama_client

GRADER = (
    "You check a student's answer to a task against a reference solution. The reference is for you only. "
    "Accept any correct method, not just the reference's. Reply with JSON only:\n"
    '{"result": "pass" | "partial" | "fail",\n'
    ' "where": "the part of the student answer that is wrong (quote a few words or name the line/section); empty if pass",\n'
    ' "what": "what is wrong, in one sentence, without giving the corrected answer; empty if pass",\n'
    ' "fix": "how to fix it, in one or two sentences (may name the correction); empty if pass",\n'
    ' "why": "one sentence on why a correct answer works"}\n'
    "pass = fully correct for the task; partial = right idea with a mistake or missing part; fail = wrong approach.\n"
    "Different but equivalent answers are correct (another valid method, other names, equivalent conditions). "
    "Only report a problem you can point to concretely. If execution evidence is given, trust it."
)

CODE_BLOCK = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


@dataclass
class CheckResult:
    result: str             # pass / partial / fail
    feedback: str           # what the student sees (tier-calibrated)
    where: str = ""
    what: str = ""
    fix: str = ""
    why: str = ""
    syntax_error: str = ""  # deterministic check (Python)

    def to_dict(self) -> dict:
        return asdict(self)


def python_syntax(answer: str, context: str) -> str:
    """Exact syntax error for Python answers ('' if fine or not Python)."""
    if context != "python":
        return ""
    blocks = [b for lang, b in CODE_BLOCK.findall(answer) if lang in ("", "python", "py")]
    code = "\n".join(blocks) if blocks else answer
    if not re.search(r"\bdef |\bfor |\bwhile |\bif |=|\breturn\b|print\(", code):
        return ""  # prose answer, nothing to compile
    try:
        ast.parse(code)
        return ""
    except SyntaxError as e:
        return f"line {e.lineno}: {e.msg}"


def grade(task: str, reference: str, answer: str, call=None, evidence: str = "") -> dict:
    call = call or ollama_client.chat
    msg = f"Task:\n{task}\n\nReference solution (do not reveal):\n{reference}\n\nStudent answer:\n{answer}"
    if evidence:
        msg += f"\n\nExecution evidence: {evidence}"
    text = call([{"role": "system", "content": GRADER}, {"role": "user", "content": msg}], temperature=0.0)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    r = str(d.get("result", "")).lower().strip()
    if r not in ("pass", "partial", "fail"):
        r = "fail" if "fail" in text.lower() else "partial"
    return {k: str(d.get(k, "") or "").strip() for k in ("where", "what", "fix", "why")} | {"result": r}


def feedback_for(tier: str, g: dict, reference: str, syntax_error: str = "") -> str:
    """Assemble what the student sees. More of the diagnosis is revealed only at higher tiers."""
    if g["result"] == "pass":
        return "✅ Correct. " + (g.get("why") or "Well done.")
    head = "◐ Partly right." if g["result"] == "partial" else "✗ Not yet."
    where, what, fix = g.get("where"), g.get("what"), g.get("fix")
    lines = [head]
    if syntax_error:
        lines.append(f"Your code does not run yet: {syntax_error}.")
    if tier in ("HUMAN_FIRST", "HINT"):
        lines.append(f"Look again at: {where.rstrip('.;: ')}." if where else "Re-read what the task asks for and compare it with your answer.")
        lines.append("What would happen if you traced it through with a small example?")
    elif tier == "GUIDED":
        if where:
            lines.append(f"Look at: {where.rstrip('.;: ')}.")
        if what:
            lines.append(what)
        lines.append("Try fixing that part, then check again.")
    elif tier == "SHARED":
        for x in (f"Look at: {where.rstrip('.;: ')}." if where else "", what, f"Idea for the fix: {fix}" if fix else ""):
            if x:
                lines.append(x)
        lines.append("Make the change yourself and check again.")
    else:  # EMERGENCY: full correction
        for x in (what, fix):
            if x:
                lines.append(x)
        lines.append("A correct version:\n\n" + reference)
    return "\n\n".join(lines)


def check(task: str, tier: str, context: str, reference: str, answer: str, call=None,
          sql_schema: str | None = None) -> tuple[CheckResult, str | None]:
    """Returns (result, sql test schema to cache). SQL answers are executed against the reference first."""
    syntax = python_syntax(answer, context)
    evidence, executed = "", None
    if context == "sql":
        from .sql_check import compare
        executed, sql_schema = compare(task, reference, answer, sql_schema, call=call)
        if executed.status == "equal":  # proven by execution: no model judgement needed
            why = "Your query " + executed.evidence + "."
            g = {"result": "pass", "where": "", "what": "", "fix": "", "why": why}
            return CheckResult(result="pass", feedback=feedback_for(tier, g, reference), why=why), sql_schema
        if executed.status in ("different", "error"):
            evidence = executed.evidence
        if executed.status == "error" and not syntax:
            syntax = executed.evidence.replace("your query does not run: ", "")
    g = grade(task, reference, answer, call=call, evidence=evidence)
    if (syntax or (executed and executed.status in ("different", "error"))) and g["result"] == "pass":
        g["result"] = "partial"  # it cannot be correct if it does not run or returns the wrong rows
    if executed and executed.status in ("different", "error") and not g["what"]:
        g["what"] = evidence[0].upper() + evidence[1:] + "."
    if syntax and not g["where"]:
        g["where"] = syntax
    res = CheckResult(result=g["result"], feedback=feedback_for(tier, g, reference, syntax), where=g["where"],
                      what=g["what"], fix=g["fix"], why=g["why"], syntax_error=syntax)
    if executed and executed.status != "inconclusive":
        res.feedback += "\n\n_Checked by running your query on test data._" if tier != "EMERGENCY" else ""
    return res, sql_schema
