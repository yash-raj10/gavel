# Gavel

**Judge once. Remember forever.**

Gavel is a judgment-memory agent built on [FalkorDB](https://www.falkordb.com/). Point it at a pile of connected records — support tickets, pull requests, anything with text and relationships between items — and ask it plain-English questions like *"which of these look risky?"*, *"which ones are bug reports?"*, *"which customers are happy with the latest release?"*, or *"which PRs touch the payments code?"*. It judges each record with a local AI model, saves every verdict into a shared graph, and reuses that memory forever: the next question, the next person, the next day, nobody re-does work that's already been done.

**Jira is Gavel's first connector.** More are coming next — Linear, Intercom, and others — all following the same pattern: pull real records in, and everything downstream (judging, memory, aggregation) works unchanged.

Built for FalkorDB's **Graph Hacks** hackathon — Track 2 (Agent Memory and Coordination).

---

## Why this exists

Most "ask an LLM about your data" tools forget everything the moment the session ends, and nothing is shared between different users or agents. A plain cache doesn't help either — it only recognizes the *exact same* question asked twice, and it can't combine answers across rows to answer a brand-new question.

Gavel is different on four counts, all backed by a real graph, not a cache:

1. **Similar questions reuse answers.** A new question close in meaning to one already asked gets judged *first* on the rows most likely to matter — nothing is silently skipped, but nothing is re-done from scratch either.
2. **Answers aggregate along real relationships.** Ticket → Customer → Account. Ask "which accounts are at risk?" and Gavel walks the graph and combines ticket-level verdicts into an account-level score — **zero new AI calls**.
3. **Every answer has a trail.** Which agent asked, when, which ticket, which version of it. Nothing is a black box.
4. **Answers go stale on purpose.** Edit a ticket and its old verdict is invalidated automatically — the next question about it gets a fresh, correct answer instead of a stale one.

Remove FalkorDB and none of this works — it becomes a single, forgettable AI call. That's the point: **the graph is the product**, not a cache bolted onto one.

---

## Why it's fast: no LLM in the judging loop

Every single-record judgment in Gavel runs on **laya**, a small, open-source, zero-shot classification model — not a hosted LLM API. That's a deliberate architectural choice, not a cost-saving afterthought:

- **~166ms per record, fully local, zero network round-trips.** No rate limits, no waiting on an API, no per-call latency spikes. Judged 41 real tickets end-to-end in under 7 seconds on a laptop.
- **No tokens burned per judgment.** A full-fledged LLM call for every row, for every question, across thousands of records, gets expensive and slow fast. Laya runs the same yes/no judgment as a single forward pass, on CPU or GPU, for free, forever.
- **The LLM budget goes where it actually matters: planning, not judging.** Gavel only spends an LLM call (Groq, or the chat client's own model) once per *goal*, to decide which questions to ask — the actual grunt work of judging hundreds or thousands of rows never touches it. That split is what makes Gavel viable at real scale instead of just a cute demo.
- **Memory compounds the speed advantage.** Combine the sub-200ms judging with FalkorDB's memory layer, and most questions after the first one don't even need a fresh judgment at all — `ask_aggregate` answers in milliseconds with **zero model calls**, local or hosted.

---

## How it works, with a real example

Say someone wants to know which of their customers are at risk of churning, based on their support tickets. One person, asking progressively deeper questions, same graph:

**Step 1 — they ask: *"which tickets sound angry?"***
Gavel has never seen this question. It takes every ticket currently in the graph, and for each one, calls **laya** (a small, local, zero-shot judgment model — not a hosted API) with the ticket text and the question. Laya returns a probability per ticket (e.g. ticket `cust-mo-t0`, "Culling is broken again" → `0.92`). Gavel writes one `Judgment` node per ticket into FalkorDB, linked to that ticket and to a new `Question` node, tagged with who asked and the ticket's current version.

**Step 2 — they ask a *different* question: *"which tickets sound like the customer wants to cancel?"***
This wasn't asked before, so it's not a cache hit. But Gavel embeds the new question and finds it's *related* (not identical) to the "angry" question from Step 1, via a vector similarity search over `Question` nodes. So instead of judging all tickets in a random order, it prioritizes the ones Step 1 already flagged as angry — those are statistically the likeliest to also be cancel-risks — then judges everything else too, so nothing is skipped. Fresh `Judgment` nodes get saved for this new question.

**Step 3 — they ask: *"which accounts are at risk?"***
This is where the aggregation happens, and **no AI model is called at all**. Gavel looks up the Step 2 question's already-saved judgments, walks `Account ← Customer ← Ticket ← Judgment` in the graph, and for each account takes its highest-risk ticket as the account's score. Answer comes back in milliseconds, fully explainable: *"Lens & Light Photography, 0.92 risk, because of ticket `cust-priya-t0` ('Please cancel my plan') from Priya Nair."*

**Then:** if ticket `cust-priya-t0` gets resolved and its text is updated, its old judgment is immediately marked stale. The next time anyone asks a question that touches it, only *that one ticket* gets re-judged — everything else is still reused from memory.

### The "it's one shared graph, not a new one per question" part

This is the actual point of using FalkorDB instead of a cache: **every one of these steps reads and writes the same graph.** There's no separate graph per question or per person asking — it's one universal, company-wide graph of judgments. Concretely:

> Suppose an employee had already queried the graph last week — out of 1,000 tickets, 300 came back "angry," and that's saved. Next week, a manager asks "who's about to leave us?" Gavel doesn't start over or build a new graph for that question — it reuses what's already sitting there (the angry judgments, the account structure, everything), judges only the genuinely new angle, and combines it with what's already known. Every question any agent has ever asked becomes permanent, shared infrastructure for every question asked after it.

That compounding effect is the whole idea — the more the graph gets used, the less work (and the less laya/LLM calls) every future question costs.

### Your real data, via Jira — Gavel's first connector

`jira_sync.py` pulls issues from a real Jira Cloud project straight into the graph — a Jira **project** becomes an `Account`, an issue's **reporter** becomes a `Customer`, and each **issue** becomes a `Ticket` (matched by issue key, so re-syncing never duplicates). Once synced, every step above runs identically on real tickets. Jira is the first connector we built; **Linear, Intercom, and others are planned next**, all following this same pattern.

### Beyond tickets: any connected data works the same way

Nothing in Gavel's logic is actually ticket-specific — a "record" can be anything with text and a relationship to something else. That's what makes adding a new connector just a new loader script, not a rewrite: `app.py`, `agent.py`, `judge.py`, and `graph.py` never change.

For example, a future **repo connector** could pull in pull requests instead of tickets (PR → Author → Repository, instead of Ticket → Customer → Account). The exact same flow would apply: ask *"which open PRs look risky to merge?"*, Gavel judges each PR's diff/description with laya, remembers every verdict, and a later question like *"which repos have the most risky open PRs?"* aggregates them with zero new AI calls — same graph, same memory, just a different connector feeding it.

---

## Two ways to use it

### 1. Command line (`agent.py`)
A real planning agent — it doesn't run a fixed script. You give it a goal in plain English, and a free LLM (Groq) decides for itself which questions to ask and whether to aggregate them. Nothing about the questions is hardcoded.

```bash
python3 agent.py "find accounts at risk of cancelling"
python3 agent.py "check Golden Hour Studios"
```

### 2. Inside Claude Code, via MCP (`/gavel`)
No separate LLM key needed here — the chat's own model plans the steps. Once registered, just type:

```
/gavel find accounts at risk of cancelling
```

If no data is loaded yet, Gavel notices and offers to connect your Jira project (or load a sample dataset) — right there in the chat.

---

## Running it locally

```bash
# 1. Install
git clone https://github.com/yash-raj10/gavel.git
cd gavel
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# set GROQ_API_KEY (free, console.groq.com/keys) -- only needed for the CLI agent
# set JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN / JIRA_PROJECT_KEY
# to pull in your own real Jira tickets

# 3. Start FalkorDB
docker run -p 6379:6379 falkordb/falkordb

# 4. Load your data from Jira
python3 jira_sync.py

# 5. Start the memory service
uvicorn app:app --port 8000

# 6. Ask it something
python3 agent.py "find accounts at risk of cancelling"
```

No Jira project handy? `python3 seed.py` loads our own custom dataset instead (what we used to build and test Gavel) — everything downstream works identically either way.

**Using it inside Claude Code instead (no Groq key needed):**

```bash
claude mcp add gavel -- python3 "$(pwd)/mcp_server.py"
```
Then, inside this project directory, in any chat:
```
/gavel find accounts at risk of cancelling
```

Full setup details, the Jira field mapping, and every tool's exact behavior are in `docs/USAGE.md` (kept out of this repo for now, available separately).

**First install note:** `pip install` pulls ~600MB, mostly PyTorch (used by `laya` and `sentence-transformers`). One-time download, fully local and offline after that — no API key needed for judging or embeddings, ever.

---

## Architecture

```
       jira_sync.py (1st connector)  ──┐                 ┌── agent.py (CLI, Groq-planned)
                                        ├──> FalkorDB ── graph.py + judge.py ──┤
                           seed.py  ──┘                 └── mcp_server.py (MCP tools, used by /gavel or chat)
```

| File | Role |
|---|---|
| `graph.py` | All FalkorDB/Cypher access — one shared graph, one function per operation |
| `judge.py` | Wraps `laya`, a local zero-shot yes/no judgment model (no API key, no hosted calls) |
| `embeddings.py` | Question-similarity vectors via `sentence-transformers` |
| `app.py` | FastAPI service: `/ask`, `/ask_aggregate`, `/tickets/{id}/update` |
| `agent.py` | CLI agent — LLM-planned (Groq) goals over the memory service |
| `mcp_server.py` | Same logic, exposed as MCP tools for chat clients (`/gavel`) |
| `jira_sync.py` | **Gavel's first connector** — pulls a real Jira Cloud project into the graph |
| `seed.py` | Loads our own custom dataset, used to build and test Gavel |

### Why FalkorDB specifically

Every behavior above — reuse, aggregation, the trail, staleness — depends on judgments being nodes connected to real relationships (ticket → customer → account), queryable by both vector similarity (for questions) and graph traversal (for aggregation) in the same database. That combination is the actual reason this is a graph product, not a key-value cache with extra steps.

---

## What's honest about the current scope

- **Jira is the first connector we built.** Linear, Intercom, and others follow next, using the exact same loader pattern — not yet built, by design kept simple to add later.
