"""
A small CLI agent. Takes one plain-English goal, decides which questions to
ask the memory service, calls it as its only tools, and acts on the result.

Usage:
    python agent.py "check all tickets"
    python agent.py "check Golden Hour Studios"

The "brain" (plan_steps) calls an LLM (Groq, free tier) to decide which
questions to ask -- GROQ_API_KEY is required, there is no hardcoded fallback
plan. The LLM is not told which questions to prefer; it reads the goal and
the shape of the data (tickets with a subject/body, filed by a customer, who
belongs to an account) and decides what's worth asking from scratch.
"""

import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8000"
AGENT_NAME = "risk-agent"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "openai/gpt-oss-20b"

PLANNER_SYSTEM_PROMPT = """You are the planner for an agent that investigates \
support tickets. Each ticket has a subject and a body, was filed by a \
customer, and each customer belongs to an account (a company/studio).

You have two tools:
  {"action": "ask", "question": "<a yes/no question about a ticket>"}
    -- judges every ticket against this question (e.g. "does this ticket
       sound angry?", "is this about billing?", "is this a bug report?").
  {"action": "aggregate", "question": "<must be the exact text of an earlier ask question>"}
    -- combines already-asked judgments per account into a ranked score,
       using existing answers only (no new judging).

Given a goal in plain English, decide for yourself which yes/no questions are
actually worth asking to achieve that goal, and whether the result should be
combined per account. There is no fixed or preferred set of questions --
invent whatever questions fit the goal.

Reply with ONLY a JSON array of steps, no other text, e.g.:
[{"action": "ask", "question": "..."}, {"action": "aggregate", "question": "..."}]

Rules:
- Every "aggregate" step's question must exactly match an earlier "ask" step's question.
- Include at least one "ask" step before any "aggregate" step.
- Only include an "aggregate" step if the goal calls for a per-account view
  (e.g. "who is at risk", "rank accounts") -- a goal just asking to find or
  list specific tickets doesn't need one.
"""


def plan_steps(goal: str) -> list[dict]:
    """
    Decides what to do for a goal, as a list of steps:
      {"action": "ask", "question": "..."}
      {"action": "aggregate", "question": "..."}

    Always LLM-driven (Groq) -- GROQ_API_KEY must be set.
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is not set. This agent requires a real LLM to plan "
            "its steps -- get a free key at https://console.groq.com/keys "
            "and put it in .env."
        )
    return _plan_with_llm(goal)


def _plan_with_llm(goal: str) -> list[dict]:
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Goal: {goal}"},
            ],
            "temperature": 0,
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    # Models sometimes wrap JSON in a code fence despite instructions.
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    steps = json.loads(content)
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"planner returned no usable steps: {content!r}")
    return steps


def _extract_account_name(goal: str) -> str | None:
    """Pulls an account name out of a goal like 'check Golden Hour Studios'."""
    lowered = goal.lower()
    if not lowered.startswith("check "):
        return None
    name = goal[len("check "):].strip()
    return name if name and name.lower() not in ("all", "all tickets", "all accounts") else None


def act(step: dict, client: httpx.Client) -> dict:
    """Calls the memory service for one planned step."""
    if step["action"] == "ask":
        print(f"  -> asking: {step['question']!r}")
        r = client.post("/ask", json={"question": step["question"], "agent": AGENT_NAME})
        r.raise_for_status()
        data = r.json()
        if data["narrowed_from"]:
            print(f"     (narrowed from a related question: {data['narrowed_from']!r})")
        print(f"     {data['new_judgments']} judged fresh, {data['reused_judgments']} reused from memory")
        return data

    if step["action"] == "aggregate":
        print(f"  -> combining existing judgments by account, based on: {step['question']!r}")
        r = client.post("/ask_aggregate", json={"question": step["question"]})
        r.raise_for_status()
        return r.json()

    # The LLM planner is asked for only "ask"/"aggregate" steps, but models
    # can still return something unexpected -- skip it rather than crash
    # the whole run over one bad step.
    print(f"  (skipping unrecognized step: {step!r})")
    return {}


def summarize_and_decide(goal: str, results: list[dict]) -> None:
    """The 'act on what the graph shows' step: print a decision, not just data."""
    aggregate_results = [r for r in results if "accounts" in r]
    if not aggregate_results:
        print("\nNo per-account result to summarize (goal didn't ask to combine by account).")
        return

    agg = aggregate_results[-1]
    accounts = agg["accounts"]
    question = agg.get("based_on_question", "")
    if not accounts:
        print(f"\nNo accounts matched {question!r}.")
        return

    account_name = _extract_account_name(goal)
    if account_name:
        match = next(
            (a for a in accounts if a["account_name"].lower() == account_name.lower()),
            None,
        )
        if not match:
            print(f"\nNo data found for account: {account_name!r}")
            return
        if match["risk_score"] >= 0.5:
            _flag(match, question)
        else:
            print(
                f"\n{match['account_name']} scores low on {question!r} "
                f"({match['risk_score']:.2f}). Most relevant ticket: "
                f"{match['trail']['subject']!r} from {match['trail']['customer']}."
            )
        return

    print(f"\nAccounts ranked on {question!r}:")
    for a in accounts:
        print(f"  {a['risk_score']:.3f}  {a['account_name']}")

    top = accounts[0]
    if top["risk_score"] >= 0.5:
        _flag(top, question)
    else:
        print(f"\nNo account scores clearly high on {question!r} right now (highest: {top['account_name']} at {top['risk_score']:.2f}).")


def _flag(account: dict, question: str) -> None:
    trail = account["trail"]
    print(
        f"\n🚩 {account['account_name']} flagged on {question!r} "
        f"(score {account['risk_score']:.2f}).\n"
        f"   Reason: ticket {trail['ticket_id']!r} ({trail['subject']!r}) from "
        f"{trail['customer']}, judged {trail['probability']:.2f} by "
        f"{trail['agent']}."
    )


def main():
    if len(sys.argv) < 2:
        print('Usage: python agent.py "check all tickets"  OR  python agent.py "check <Account Name>"')
        sys.exit(1)

    goal = sys.argv[1]
    print(f"Goal: {goal!r}")

    steps = plan_steps(goal)
    print(f"Plan: {len(steps)} step(s)")

    results = []
    with httpx.Client(base_url=BASE_URL, timeout=120) as client:
        for step in steps:
            results.append(act(step, client))

    summarize_and_decide(goal, results)


if __name__ == "__main__":
    main()
