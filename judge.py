"""
Thin wrapper around a judgment model. Answers one yes/no question about many
rows of text at once.

Backend: laya (local, free, no API key). Swappable later for real Jev or
Claude -- nothing outside this file should know which backend is in use.
"""

from laya import Router

_router: Router | None = None


def _get_router() -> Router:
    global _router
    if _router is None:
        _router = Router()
    return _router


def judge_rows(question: str, rows: dict[str, str]) -> dict[str, float]:
    """
    Ask `question` (a yes/no question in plain English) about each row of text.

    rows: {row_id: text}
    returns: {row_id: probability_of_yes}
    """
    router = _get_router()
    answers: dict[str, float] = {}

    for row_id, text in rows.items():
        result = router.predict(text, {"q": {"type": "noul", "instructions": question}})
        answers[row_id] = float(result["answers"]["q"]["noul"])

    return answers


if __name__ == "__main__":
    # Quick manual check: python judge.py
    sample = {
        "t1": "I have asked three times now. Just cancel my subscription.",
        "t2": "Could you point me to where I download past invoices? Thanks!",
    }
    print(judge_rows("Is the customer angry?", sample))
