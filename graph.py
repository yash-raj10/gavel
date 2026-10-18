"""
All FalkorDB access for the service lives here: one function per operation.
Nothing outside this file should write raw Cypher.
"""

import os
import time
import uuid

from dotenv import load_dotenv
from falkordb import FalkorDB

import embeddings

load_dotenv()

HOST = os.environ.get("FALKORDB_HOST", "localhost")
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
GRAPH_NAME = os.environ.get("FALKORDB_GRAPH", "judgment_memory")

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2
# FalkorDB's vector index score is a cosine *distance* (0 = identical,
# ~1 = unrelated). Two thresholds, not one -- "same question" and "related
# question" mean different things and must not be collapsed:
#   - SAME_QUESTION: close enough to literally reuse its answers, no new
#     judging at all (e.g. re-running the exact same question).
#   - RELATED_QUESTION: a different question, but close enough in meaning
#     that it's worth narrowing down to rows already flagged by the related
#     question before judging, instead of re-judging every row.
SAME_QUESTION_DISTANCE = 0.15
RELATED_QUESTION_DISTANCE = 0.45

_db: FalkorDB | None = None
_indexes_ready = False


def _get_graph():
    global _db, _indexes_ready
    if _db is None:
        _db = FalkorDB(host=HOST, port=PORT)
    g = _db.select_graph(GRAPH_NAME)
    if not _indexes_ready:
        _ensure_indexes(g)
        _indexes_ready = True
    return g


def reset_indexes() -> None:
    """
    Marks indexes as needing to be recreated. Must be called after anything
    that wipes the graph (e.g. g.delete() in seed.py) -- a wipe deletes the
    vector index along with everything else, but _indexes_ready would
    otherwise still say it exists, and every later vector query would fail.
    """
    global _indexes_ready
    _indexes_ready = False


def _ensure_indexes(g):
    try:
        g.query(
            "CREATE VECTOR INDEX FOR (q:Question) ON (q.embedding) "
            "OPTIONS {dimension: $dim, similarityFunction: 'cosine'}",
            {"dim": EMBEDDING_DIM},
        )
    except Exception:
        pass  # already exists


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


def get_all_tickets() -> list[dict]:
    """Returns every ticket with its text and current version."""
    g = _get_graph()
    res = g.query(
        "MATCH (t:Ticket) RETURN t.id, t.subject, t.body, t.version"
    )
    return [
        {"id": row[0], "subject": row[1], "body": row[2], "version": row[3]}
        for row in res.result_set
    ]


def update_ticket_body(ticket_id: str, new_body: str, new_subject: str | None = None) -> int:
    """Bumps a ticket's version and body (and optionally subject). Returns the new version."""
    g = _get_graph()
    res = g.query(
        """
        MATCH (t:Ticket {id: $id})
        SET t.body = $body,
            t.subject = coalesce($subject, t.subject),
            t.version = t.version + 1
        RETURN t.version
        """,
        {"id": ticket_id, "body": new_body, "subject": new_subject},
    )
    return res.result_set[0][0]


# ---------------------------------------------------------------------------
# Questions + similarity
# ---------------------------------------------------------------------------


def find_closest_question(question_text: str, exclude_id: str | None = None) -> dict | None:
    """
    Looks for the closest existing Question to `question_text`, optionally
    excluding one Question id (its own node, if it was already created).
    Returns {"id", "text", "distance"}, or None if nothing else exists.
    """
    g = _get_graph()
    vec = embeddings.embed(question_text)
    # Ask for 2 results so excluding "itself" still leaves a candidate.
    res = g.query(
        """
        CALL db.idx.vector.queryNodes('Question', 'embedding', 2, vecf32($vec))
        YIELD node, score
        WHERE node.id <> $exclude_id
        RETURN node.id, node.text, score
        ORDER BY score ASC
        LIMIT 1
        """,
        {"vec": vec, "exclude_id": exclude_id or ""},
    )
    if not res.result_set:
        return None
    qid, text, distance = res.result_set[0]
    return {"id": qid, "text": text, "distance": distance}


def find_same_question(question_text: str) -> dict | None:
    """Returns the closest Question only if it counts as the SAME question."""
    match = find_closest_question(question_text)
    if match and match["distance"] <= SAME_QUESTION_DISTANCE:
        return match
    return None


def find_related_question(question_text: str, exclude_id: str | None = None) -> dict | None:
    """
    Returns the closest Question if it's a *different but related* question
    (narrower than "same", wider than "unrelated"). Used to narrow down
    which rows to prioritize, not to reuse answers directly. Pass
    exclude_id with the question's own id if it may already exist in the
    graph, so it doesn't match itself at distance 0.
    """
    match = find_closest_question(question_text, exclude_id=exclude_id)
    if match and SAME_QUESTION_DISTANCE < match["distance"] <= RELATED_QUESTION_DISTANCE:
        return match
    return None


def create_question(question_text: str) -> str:
    """Creates a new Question node, returns its id."""
    g = _get_graph()
    qid = str(uuid.uuid4())
    vec = embeddings.embed(question_text)
    g.query(
        "CREATE (:Question {id: $id, text: $text, embedding: vecf32($vec)})",
        {"id": qid, "text": question_text, "vec": vec},
    )
    return qid


def get_or_create_question(question_text: str) -> dict:
    """
    Returns {"id", "text", "reused": bool} -- reused=True if an existing,
    essentially identical Question was found instead of creating a new one.
    A merely *related* question (see find_related_question) is NOT reused
    here -- it still gets its own Question node, since it's a genuinely
    different question with its own answers.
    """
    existing = find_same_question(question_text)
    if existing:
        return {"id": existing["id"], "text": existing["text"], "reused": True}
    qid = create_question(question_text)
    return {"id": qid, "text": question_text, "reused": False}


# ---------------------------------------------------------------------------
# Judgments
# ---------------------------------------------------------------------------


def get_flagged_ticket_ids(question_id: str, min_probability: float = 0.5) -> set[str]:
    """Ticket ids with a non-stale judgment >= min_probability for this question."""
    g = _get_graph()
    res = g.query(
        """
        MATCH (t:Ticket)<-[:ABOUT]-(j:Judgment)-[:ANSWERS]->(q:Question {id: $qid})
        WHERE j.row_version = t.version AND j.probability >= $min_prob
        RETURN t.id
        """,
        {"qid": question_id, "min_prob": min_probability},
    )
    return {row[0] for row in res.result_set}


def get_fresh_judgments(question_id: str, ticket_ids: list[str]) -> dict[str, float]:
    """
    Returns {ticket_id: probability} for tickets that already have a
    judgment for this question AND that judgment is not stale (i.e. the
    ticket hasn't changed since it was judged).
    """
    if not ticket_ids:
        return {}
    g = _get_graph()
    res = g.query(
        """
        MATCH (t:Ticket)<-[:ABOUT]-(j:Judgment)-[:ANSWERS]->(q:Question {id: $qid})
        WHERE t.id IN $ticket_ids AND j.row_version = t.version
        RETURN t.id, j.probability
        """,
        {"qid": question_id, "ticket_ids": ticket_ids},
    )
    return {row[0]: row[1] for row in res.result_set}


def save_judgment(
    question_id: str,
    ticket_id: str,
    probability: float,
    row_version: int,
    agent: str,
) -> None:
    g = _get_graph()
    jid = str(uuid.uuid4())
    g.query(
        """
        MATCH (t:Ticket {id: $ticket_id}), (q:Question {id: $qid})
        CREATE (j:Judgment {
            id: $jid, probability: $prob, judged_at: $ts,
            agent: $agent, row_version: $version
        })
        CREATE (j)-[:ANSWERS]->(q)
        CREATE (j)-[:ABOUT]->(t)
        """,
        {
            "ticket_id": ticket_id,
            "qid": question_id,
            "jid": jid,
            "prob": probability,
            "ts": time.time(),
            "agent": agent,
            "version": row_version,
        },
    )


# ---------------------------------------------------------------------------
# Aggregation (account risk) + trail
# ---------------------------------------------------------------------------


def aggregate_by_account(question_id: str) -> list[dict]:
    """
    For a given Question, walks Account -> Customer -> Ticket -> Judgment
    and returns the highest judgment probability per account (no new model
    calls -- pure graph read), plus enough info to build a trail.
    """
    g = _get_graph()
    res = g.query(
        """
        MATCH (a:Account)<-[:BELONGS_TO]-(c:Customer)<-[:FILED_BY]-(t:Ticket)
              <-[:ABOUT]-(j:Judgment)-[:ANSWERS]->(q:Question {id: $qid})
        WHERE j.row_version = t.version
        WITH a, c, t, j
        ORDER BY j.probability DESC
        WITH a, collect({
            ticket_id: t.id, subject: t.subject, customer: c.name,
            probability: j.probability, agent: j.agent, judged_at: j.judged_at
        })[0] AS top
        RETURN a.id, a.name, top.probability, top
        ORDER BY top.probability DESC
        """,
        {"qid": question_id},
    )
    return [
        {
            "account_id": row[0],
            "account_name": row[1],
            "risk_score": row[2],
            "trail": row[3],
        }
        for row in res.result_set
    ]
