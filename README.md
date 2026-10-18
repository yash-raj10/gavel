# Gavel

**Ask your data once. Every agent remembers the answer.**

Gavel is a judgment-memory agent built on [FalkorDB](https://www.falkordb.com/). Point it at a pile of support tickets — from a demo dataset, or your real Jira project — and ask it plain-English questions like *"which customers are about to cancel?"*. It judges each ticket with a local AI model, saves every verdict into a shared graph, and reuses that memory forever: the next question, the next agent, the next day, nobody re-does work that's already been done.

Built for FalkorDB's **Graph Hacks** hackathon — Track 2 (Agent Memory and Coordination), also fits Track 1 (Agents That Act on Connected Data).

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

## How it works, with a real example

Say Aftershoot (a photo culling/editing tool for photographers) has a pile of support tickets from its studio customers. Three different moments, same graph:

**Step 1 — A triage agent asks: *"which tickets sound angry?"***
Gavel has never seen this question. It takes every ticket currently in the graph, and for each one, calls **laya** (a small, local, zero-shot judgment model — not a hosted API) with the ticket text and the question. Laya returns a probability per ticket (e.g. ticket `cust-mo-t0`, "Culling is broken again" → `0.92`). Gavel writes one `Judgment` node per ticket into FalkorDB, linked to that ticket and to a new `Question` node, tagged with which agent asked and the ticket's current version.

**Step 2 — A retention agent asks a *different* question: *"which tickets sound like the customer wants to cancel?"***
This wasn't asked before, so it's not a cache hit. But Gavel embeds the new question and finds it's *related* (not identical) to the "angry" question from Step 1, via a vector similarity search over `Question` nodes. So instead of judging all tickets in a random order, it prioritizes the ones Step 1 already flagged as angry — those are statistically the likeliest to also be cancel-risks — then judges everything else too, so nothing is skipped. Fresh `Judgment` nodes get saved for this new question.

**Step 3 — A manager agent asks: *"which accounts are at risk?"***
This is where the aggregation happens, and **no AI model is called at all**. Gavel looks up the Step 2 question's already-saved judgments, walks `Account ← Customer ← Ticket ← Judgment` in the graph, and for each account takes its highest-risk ticket as the account's score. Answer comes back in milliseconds, fully explainable: *"Lens & Light Photography, 0.92 risk, because of ticket `cust-priya-t0` ('Please cancel my plan') from Priya Nair, judged by the retention agent."*

**Then:** if ticket `cust-priya-t0` gets resolved and its text is updated, its old judgment is immediately marked stale. The next time anyone asks a question that touches it, only *that one ticket* gets re-judged — everything else is still reused from memory.

### The "it's one shared graph, not a new one per question" part

This is the actual point of using FalkorDB instead of a cache: **every one of these steps reads and writes the same graph.** There's no "triage's graph" and "manager's graph" — it's one universal, company-wide graph of judgments. Concretely:

> Suppose an employee had already queried the graph last week — out of 1,000 tickets, 300 came back "angry," and that's saved. Next week, a manager asks "who's about to leave us?" Gavel doesn't start over or build a new graph for that question — it reuses what's already sitting there (the angry judgments, the account structure, everything), judges only the genuinely new angle, and combines it with what's already known. Every question any agent has ever asked becomes permanent, shared infrastructure for every question asked after it.

That compounding effect is the whole idea — the more the graph gets used, the less work (and the less laya/LLM calls) every future question costs.

### Bring your own real data: the Jira example

Everything above also works on real tickets, not just the demo dataset. `jira_sync.py` pulls issues from a real Jira Cloud project straight into the same graph shape — a Jira **project** becomes an `Account`, an issue's **reporter** becomes a `Customer`, and each **issue** becomes a `Ticket` (matched by issue key, so re-syncing never duplicates). Once synced, every step above runs identically — Gavel doesn't know or care whether a ticket came from the demo seed or from a live Jira board. That's deliberate: adding a new data source is just a new loader script; `app.py`, `agent.py`, `judge.py`, and `graph.py` never change.

---

## Three ways to use it

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

If no data is loaded yet, Gavel notices and offers to load the demo dataset or pull your real Jira project — right there in the chat.

### 3. Direct HTTP API (`app.py`)
`POST /ask`, `POST /ask_aggregate`, `POST /tickets/{id}/update` — for wiring Gavel into your own tooling.

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
# optionally set JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN / JIRA_PROJECT_KEY
# to use your own real Jira tickets instead of the demo dataset

# 3. Start FalkorDB
docker run -p 6379:6379 falkordb/falkordb

# 4. Load data -- demo dataset, or your own Jira project
python3 seed.py          # demo: 14 photography studios, 41 tickets
# python3 jira_sync.py   # OR: pull real tickets from Jira

# 5. Start the memory service
uvicorn app:app --port 8000

# 6. Ask it something
python3 agent.py "find accounts at risk of cancelling"
```

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
                 seed.py  ──┐                      ┌── agent.py (CLI, Groq-planned)
                             ├──> FalkorDB ── graph.py + judge.py ──┤
          jira_sync.py  ──┘                      └── mcp_server.py (MCP tools, used by /gavel or chat)
```

| File | Role |
|---|---|
| `graph.py` | All FalkorDB/Cypher access — one shared graph, one function per operation |
| `judge.py` | Wraps `laya`, a local zero-shot yes/no judgment model (no API key, no hosted calls) |
| `embeddings.py` | Question-similarity vectors via `sentence-transformers` |
| `app.py` | FastAPI service: `/ask`, `/ask_aggregate`, `/tickets/{id}/update` |
| `agent.py` | CLI agent — LLM-planned (Groq) goals over the memory service |
| `mcp_server.py` | Same logic, exposed as MCP tools for chat clients (`/gavel`) |
| `seed.py` | Demo dataset loader (Aftershoot-themed photography studio tickets) |
| `jira_sync.py` | Real-data loader — pulls a Jira Cloud project into the same graph shape |

### Why FalkorDB specifically

Every behavior above — reuse, aggregation, the trail, staleness — depends on judgments being nodes connected to real relationships (ticket → customer → account), queryable by both vector similarity (for questions) and graph traversal (for aggregation) in the same database. That combination is the actual reason this is a graph product, not a key-value cache with extra steps.

---

## What's honest about the current scope

- The judge model (`laya`) is zero-shot, not fine-tuned — it's accurate on tickets with explicit language ("I want to cancel", "I am furious") and less reliable on subtle implication. See `check_accuracy.py` for a real accuracy check against hand-labeled tickets (~88% on this dataset).
- Jira is the only real external connector today; more (Linear, Zendesk, etc.) are a natural extension of the same loader pattern, not yet built.
- `connect_jira` (used from chat) only reads credentials from `.env` — it never accepts a token as a chat argument, so secrets never land in chat history.
