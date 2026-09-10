"""
Compares every contestant's answer to the same question and picks a winner.

The judge is deliberately a separate model from the contestants (see
build_judge in providers.py) so the evaluation is independent rather than
a model grading its own answer.
"""

import json
from .providers import build_judge, ProviderError

JUDGE_PROMPT = """You are an impartial evaluator comparing answers from different AI models \
to the same question. Be concise and specific.

Question:
{question}

Candidate answers:
{answers_block}

Evaluate each candidate on accuracy, clarity, completeness, and usefulness.
A longer answer is not automatically better.

Return ONLY valid JSON, no markdown fences, in exactly this shape:
{{
  "evaluations": [
    {{"model": "<model id exactly as given>", "score": <integer 0-100>, "verdict": "<one short sentence>"}}
  ],
  "winner": "<model id of the single best answer>",
  "reason": "<2-3 sentences on why the winner beat the others>",
  "consensus": "<one sentence: do the models broadly agree, and on what>"
}}
"""


def _answers_block(responses):
    parts = []
    for r in responses:
        body = f"[ERROR: {r['error']}]" if r.get("error") else r.get("response", "")
        parts.append(f"### {r['model_id']} ({r['display_name']})\n{body}\n")
    return "\n".join(parts)


def _parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _fallback_judgment(usable):
    """Used only when no judge model is configured/reachable. Picks the
    most substantive answer as a rough, clearly-labelled proxy."""
    winner = max(usable, key=lambda r: len(r.get("response", "")))
    return {
        "evaluations": [
            {"model": r["model_id"], "score": None, "verdict": "Not evaluated - no judge model configured."}
            for r in usable
        ],
        "winner": winner["model_id"],
        "reason": "No judge model was configured, so the most substantive answer was picked as a fallback. Set JUDGE_MODEL in backend/.env for a real evaluation.",
        "consensus": "Unknown - judge model unavailable.",
    }


def judge_responses(question, responses):
    """
    responses: list of dicts with model_id, display_name, response, error.
    Returns a dict with evaluations / winner / reason / consensus.
    """
    usable = [r for r in responses if not r.get("error") and r.get("response")]
    if not usable:
        return {
            "evaluations": [],
            "winner": None,
            "reason": "Every contestant failed to respond.",
            "consensus": "No usable answers to compare.",
        }

    judge = build_judge()
    if judge is None:
        return _fallback_judgment(usable)

    prompt = JUDGE_PROMPT.format(question=question, answers_block=_answers_block(responses))

    try:
        raw = judge.generate(prompt)
        data = _parse_json(raw)
        data.setdefault("evaluations", [])
        data.setdefault("winner", usable[0]["model_id"])
        data.setdefault("reason", "")
        data.setdefault("consensus", "")
        return data
    except (ProviderError, json.JSONDecodeError, KeyError, TypeError):
        return _fallback_judgment(usable)
