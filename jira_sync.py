"""
Pulls real issues from a Jira Cloud project into FalkorDB, in the same
graph shape seed.py uses:
  (:Account)<-[:BELONGS_TO]-(:Customer)<-[:FILED_BY]-(:Ticket)

Mapping:
  Jira project  -> Account
  Issue reporter -> Customer
  Issue (summary + description) -> Ticket (id = issue key, e.g. "SUP-123")

This only loads data -- app.py/agent.py/judge.py are unchanged and work on
whatever is in FalkorDB, Jira or seeded demo data alike.

Setup (Jira Cloud):
  1. Get an API token: https://id.atlassian.com/manage-profile/security/api-tokens
  2. Add to .env:
       JIRA_BASE_URL=https://your-domain.atlassian.net
       JIRA_EMAIL=you@yourcompany.com
       JIRA_API_TOKEN=...
       JIRA_PROJECT_KEY=SUP

Run:
    python jira_sync.py

Safe to re-run: existing tickets are matched by issue key and updated
(version bumped) rather than duplicated, same as update_ticket_body.
"""

import os
import sys

import httpx
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

FALKORDB_HOST = os.environ.get("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
FALKORDB_GRAPH = os.environ.get("FALKORDB_GRAPH", "judgment_memory")

JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "")

PAGE_SIZE = 50


def _extract_text(description) -> str:
    """Jira Cloud descriptions are Atlassian Document Format (nested JSON),
    not plain text. Walks it and joins any text nodes found."""
    if description is None:
        return ""
    if isinstance(description, str):
        return description
    parts = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(node.get("text", ""))
            for child in node.get("content", []) or []:
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(description)
    return " ".join(parts)


def fetch_issues(client: httpx.Client, project_key: str) -> list[dict]:
    """Pages through every issue in a Jira project via the search API."""
    issues = []
    start_at = 0
    while True:
        resp = client.get(
            "/rest/api/3/search",
            params={
                "jql": f"project = {project_key} ORDER BY created ASC",
                "startAt": start_at,
                "maxResults": PAGE_SIZE,
                "fields": "summary,description,reporter,project",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        issues.extend(data["issues"])
        start_at += PAGE_SIZE
        if start_at >= data["total"]:
            break
    return issues


def sync():
    if not all([JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY]):
        print(
            "Missing Jira config. Set JIRA_BASE_URL, JIRA_EMAIL, "
            "JIRA_API_TOKEN, and JIRA_PROJECT_KEY in .env -- see the "
            "docstring at the top of jira_sync.py for how to get a token."
        )
        sys.exit(1)

    db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    g = db.select_graph(FALKORDB_GRAPH)

    with httpx.Client(
        base_url=JIRA_BASE_URL,
        auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        headers={"Accept": "application/json"},
        timeout=30,
    ) as client:
        issues = fetch_issues(client, JIRA_PROJECT_KEY)

    if not issues:
        print(f"No issues found in project '{JIRA_PROJECT_KEY}'.")
        return

    project_name = issues[0]["fields"]["project"]["name"]
    account_id = f"jira-{JIRA_PROJECT_KEY}"
    g.query(
        "MERGE (a:Account {id: $id}) SET a.name = $name",
        {"id": account_id, "name": project_name},
    )

    seen_customers = set()
    ticket_count = 0
    for issue in issues:
        fields = issue["fields"]
        reporter = fields.get("reporter") or {}
        customer_id = reporter.get("accountId", "unknown-reporter")
        customer_name = reporter.get("displayName", "Unknown Reporter")

        if customer_id not in seen_customers:
            g.query(
                """
                MATCH (a:Account {id: $account_id})
                MERGE (c:Customer {id: $id})
                SET c.name = $name
                MERGE (c)-[:BELONGS_TO]->(a)
                """,
                {"account_id": account_id, "id": customer_id, "name": customer_name},
            )
            seen_customers.add(customer_id)

        ticket_id = issue["key"]  # e.g. "SUP-123" -- stable, used to dedupe on re-sync
        subject = fields.get("summary", "")
        body = _extract_text(fields.get("description"))

        g.query(
            """
            MATCH (c:Customer {id: $customer_id})
            MERGE (t:Ticket {id: $id})
            ON CREATE SET t.version = 1
            ON MATCH SET t.version = t.version + 1
            SET t.subject = $subject, t.body = $body
            MERGE (t)-[:FILED_BY]->(c)
            """,
            {
                "customer_id": customer_id,
                "id": ticket_id,
                "subject": subject,
                "body": body,
            },
        )
        ticket_count += 1

    print(
        f"Synced {ticket_count} issues from Jira project '{JIRA_PROJECT_KEY}' "
        f"into account '{project_name}' ({len(seen_customers)} reporters)."
    )


if __name__ == "__main__":
    sync()
