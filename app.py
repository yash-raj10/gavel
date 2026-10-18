"""
The memory service. Two endpoints:

  POST /ask            -- judge individual tickets against a plain-English
                           question, reusing memory where possible.
  POST /ask_aggregate   -- combine existing judgments along the graph
                           (Account -> Customer -> Ticket) with zero new
                           model calls.
  POST /tickets/{id}/update -- edit a ticket's text, which stales its
                           existing judgments.
"""

from fastapi import FastAPI
from pydantic import BaseModel

import graph
import judge

app = FastAPI(title="Judgment Memory")


class AskRequest(BaseModel):
    question: str
    agent: str = "unknown-agent"


class AskResponse(BaseModel):
    question_id: str
    question_reused: bool
    narrowed_from: str | None
    answers: list[dict]
    new_judgments: int
    reused_judgments: int


class AggregateRequest(BaseModel):
    question: str  # the question whose saved judgments to aggregate


class UpdateTicketRequest(BaseModel):
    body: str
    subject: str | None = None


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    q = graph.get_or_create_question(req.question)
    tickets = graph.get_all_tickets()
    ticket_ids = [t["id"] for t in tickets]

    # Behavior #1, part A: an essentially identical question -> reuse its
    # answers outright, no new judging.
    fresh = graph.get_fresh_judgments(q["id"], ticket_ids)

    missing = [t for t in tickets if t["id"] not in fresh]

    # Behavior #1, part B: a *related* (but different) question -> judge the
    # rows the related question already flagged FIRST (that's the priority
    # order a real agent would want), but still cover every other row too --
    # narrowing only skips rows when there's actual reuse to be had
    # elsewhere; it must never silently drop a row from consideration.
    narrowed_from = None
    if not q["reused"]:
        related = graph.find_related_question(req.question, exclude_id=q["id"])
        if related:
            flagged = graph.get_flagged_ticket_ids(related["id"])
            if flagged:
                narrowed_from = related["text"]
                missing.sort(key=lambda t: t["id"] not in flagged)

    new_results: dict[str, float] = {}
    if missing:
        rows = {t["id"]: f"{t['subject']}. {t['body']}" for t in missing}
        new_results = judge.judge_rows(req.question, rows)
        for t in missing:
            prob = new_results[t["id"]]
            graph.save_judgment(q["id"], t["id"], prob, t["version"], req.agent)

    answers = []
    for t in tickets:
        prob = fresh.get(t["id"], new_results.get(t["id"]))
        source = "cached" if t["id"] in fresh else "judged"
        answers.append({
            "ticket_id": t["id"],
            "subject": t["subject"],
            "probability": prob,
            "source": source,
        })
    answers.sort(key=lambda a: a["probability"], reverse=True)

    return AskResponse(
        question_id=q["id"],
        question_reused=q["reused"],
        narrowed_from=narrowed_from,
        answers=answers,
        new_judgments=len(new_results),
        reused_judgments=len(fresh),
    )


@app.post("/ask_aggregate")
def ask_aggregate(req: AggregateRequest):
    """
    Looks up an existing question's judgments (must already have been asked
    via /ask) and combines them per account. No new model calls.
    """
    existing = graph.find_same_question(req.question)
    if not existing:
        return {
            "error": (
                "No existing judgments for a question like this yet. "
                "Call /ask with this question first."
            )
        }
    results = graph.aggregate_by_account(existing["id"])
    return {"based_on_question": existing["text"], "accounts": results}


@app.post("/tickets/{ticket_id}/update")
def update_ticket(ticket_id: str, req: UpdateTicketRequest):
    new_version = graph.update_ticket_body(ticket_id, req.body, req.subject)
    return {"ticket_id": ticket_id, "new_version": new_version}


@app.get("/health")
def health():
    return {"status": "ok"}
