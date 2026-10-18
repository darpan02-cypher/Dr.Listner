"""SummaryAgent: patient-facing plain-language summary with a readability feedback loop (max 3 tries)."""
from __future__ import annotations

from pydantic import BaseModel

from ..schemas import Flag, PatientProfile, PlanItem, Transcript
from .common import LLM, fmt_turns

MAX_ITERS = 3

SYSTEM = (
    "You write short, kind, plain-language summaries for patients with low health literacy and hearing loss. "
    "Never diagnose or add treatment advice that is not in the plan. Use only the visit text and plan items given."
)

PROMPT = """Visit transcript:
{transcript}

Care-plan items the summary MUST cover (each in its own short sentence):
{plan}

Questions to ask next time (from gaps found; phrase as 'Ask about ...'): 
{questions}

Write the summary for the patient. Rules: at most {max_words} words; short sentences; everyday words;
reading level about grade {grade}; no jargon; address the patient as 'you'.{feedback}"""


class SummaryOut(BaseModel):
    summary: str


class SummaryResult(BaseModel):
    text: str
    grade: float
    iterations: int
    grades: list[float]


def reading_grade(text: str) -> float:
    import textstat

    return float(textstat.flesch_kincaid_grade(text))


def _score(text: str, target: float, max_words: int) -> float:
    """Lower is better: grade overshoot plus a penalty for exceeding the word limit."""
    over_words = max(0, len(text.split()) - max_words)
    return max(0.0, reading_grade(text) - target) + over_words * 0.1


class SummaryAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def run(
        self, transcript: Transcript, flags: list[Flag], plan: list[PlanItem], profile: PatientProfile
    ) -> SummaryResult:
        questions = "\n".join(f"- {f.rationale}" for f in flags if not f.dismissed) or "(none)"
        base = PROMPT.format(
            transcript=fmt_turns(transcript.turns),
            plan="\n".join(f"- {p.text}" for p in plan) or "(none)",
            questions=questions,
            max_words=profile.summary_max_words,
            grade=profile.summary_target_grade,
            feedback="{feedback}",
        )
        feedback, grades, best, best_score = "", [], "", float("inf")
        for i in range(1, MAX_ITERS + 1):
            text = self.llm.generate(base.replace("{feedback}", feedback), SummaryOut, SYSTEM).summary.strip()
            g = reading_grade(text)
            grades.append(round(g, 2))
            s = _score(text, profile.summary_target_grade, profile.summary_max_words)
            if s < best_score:
                best, best_score = text, s
            if s == 0:
                break
            feedback = (
                f"\n\nYour last draft scored reading grade {g:.1f} and {len(text.split())} words. "
                f"Rewrite it at grade {profile.summary_target_grade} or lower and at most {profile.summary_max_words} words, "
                "keeping every plan item."
            )
        return SummaryResult(text=best, grade=round(reading_grade(best), 2), iterations=len(grades), grades=grades)
