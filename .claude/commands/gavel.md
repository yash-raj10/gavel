---
description: Ask the Gavel judgment-memory agent a plain-English question about support tickets
---

The user wants to use **Gavel**, the judgment-memory agent, with this request:

$ARGUMENTS

Using the `gavel` MCP server's tools, do the following:
1. Call `check_data_source` first.
2. If it reports no tickets loaded, offer to call `connect_demo_data` (sample dataset) or `connect_jira` (pulls the user's real Jira project from credentials already in `.env`) — ask the user which they want, then call it.
3. Once data is ready, decide for yourself which yes/no question(s) to ask via `ask`, and whether to call `ask_aggregate` to rank accounts, based on what the user's request above actually needs. Don't assume it's always about cancellation risk — judge that from their request.
4. Report the result clearly: a ranked list or a specific answer, with the actual ticket/quote as evidence when flagging something.
