"""
Gavel: exposes the judgment-memory service as MCP tools, so a chat client
(Claude Code, Claude Desktop, etc.) can plan and call them directly -- no
separate Python planner needed. The chat's own LLM plays the role
agent.py's Groq call plays for the CLI.

Same underlying logic as app.py (graph.py + judge.py) -- this is just a
different front door onto the same FalkorDB-backed memory.

Setup (Claude Code):
    claude mcp add gavel -- python3 /absolute/path/to/mcp_server.py

A project-scoped slash command is also included at
.claude/commands/gavel.md, so once the MCP server is added, you can just
run (from inside this project): /gavel find accounts at risk of cancelling

Without the slash command, plain chat also works:
"using gavel, find accounts at risk of cancelling"
"""

import sys

import embeddings
import graph
import jira_sync
import judge
import seed
from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="gavel",
    instructions=(
        "Tools for judging support tickets against plain-English yes/no "
        "questions, with memory across calls, and combining judgments per "
        "account. Always call check_data_source first in a new "
        "conversation -- if it reports no tickets, offer to call "
        "connect_demo_data (sample dataset) or connect_jira (the user's "
        "real Jira project, reads credentials from .env) before calling "
        "ask or ask_aggregate."
    ),
)


@server.tool()
def check_data_source() -> dict:
    """Checks whether any tickets are loaded yet. Call this first."""
    tickets = graph.get_all_tickets()
    if not tickets:
        return {
            "ready": False,
            "message": (
                "No tickets are loaded yet. Offer to call connect_demo_data "
                "for a sample dataset, or connect_jira to pull the user's "
                "real Jira tickets (requires JIRA_BASE_URL, JIRA_EMAIL, "
                "JIRA_API_TOKEN, JIRA_PROJECT_KEY already set in .env)."
            ),
        }
    return {"ready": True, "ticket_count": len(tickets)}


@server.tool()
def connect_demo_data() -> dict:
    """Loads the built-in sample dataset (wipes any existing graph data)."""
    seed.seed()
    tickets = graph.get_all_tickets()
    return {"connected": True, "source": "demo", "ticket_count": len(tickets)}


@server.tool()
def connect_jira() -> dict:
    """
    Pulls tickets from the Jira project configured in .env
    (JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY).
    Does not take credentials as arguments -- they must already be in
    .env, so a token never has to be typed into the chat.
    """
    missing = [
        name
        for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY")
        if not getattr(jira_sync, name)
    ]
    if missing:
        return {
            "connected": False,
            "error": (
                f"Missing {', '.join(missing)} in .env. Ask the user to set "
                "these (a Jira API token can be created at "
                "https://id.atlassian.com/manage-profile/security/api-tokens), "
                "then try again."
            ),
        }
    jira_sync.sync()
    tickets = graph.get_all_tickets()
    return {"connected": True, "source": "jira", "ticket_count": len(tickets)}


@server.tool()
def ask(question: str, agent: str = "mcp-client") -> dict:
    """
    Judges every ticket against a plain-English yes/no question, reusing
    memory where possible. Returns per-ticket answers plus how many were
    judged fresh vs. reused from memory.
    """
    q = graph.get_or_create_question(question)
    tickets = graph.get_all_tickets()
    ticket_ids = [t["id"] for t in tickets]

    fresh = graph.get_fresh_judgments(q["id"], ticket_ids)
    missing = [t for t in tickets if t["id"] not in fresh]

    narrowed_from = None
    if not q["reused"]:
        related = graph.find_related_question(question, exclude_id=q["id"])
        if related:
            flagged = graph.get_flagged_ticket_ids(related["id"])
            if flagged:
                narrowed_from = related["text"]
                missing.sort(key=lambda t: t["id"] not in flagged)

    new_results: dict[str, float] = {}
    if missing:
        rows = {t["id"]: f"{t['subject']}. {t['body']}" for t in missing}
        new_results = judge.judge_rows(question, rows)
        for t in missing:
            prob = new_results[t["id"]]
            graph.save_judgment(q["id"], t["id"], prob, t["version"], agent)

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

    return {
        "question_id": q["id"],
        "question_reused": q["reused"],
        "narrowed_from": narrowed_from,
        "answers": answers,
        "new_judgments": len(new_results),
        "reused_judgments": len(fresh),
    }


@server.tool()
def ask_aggregate(question: str) -> dict:
    """
    Combines already-saved judgments for a question per account, with zero
    new judging. The question must have been asked via `ask` already.
    """
    existing = graph.find_same_question(question)
    if not existing:
        return {
            "error": (
                "No existing judgments for a question like this yet. "
                "Call ask with this question first."
            )
        }
    results = graph.aggregate_by_account(existing["id"])
    return {"based_on_question": existing["text"], "accounts": results}


def _prewarm() -> None:
    """
    Loads the judge and embedding models eagerly at startup instead of on
    the first tool call. Without this, the first `ask` can take 7-10s
    (downloading/loading laya + sentence-transformers) which can exceed an
    MCP client's tool-call timeout and get reported as a failed connection
    even though the call would have succeeded given more time.
    """
    print("Gavel: warming up judge and embedding models...", file=sys.stderr)
    judge.judge_rows("warmup", {"warmup-row": "warmup text"})
    embeddings.embed("warmup")
    print("Gavel: ready.", file=sys.stderr)


if __name__ == "__main__":
    _prewarm()
    server.run()
