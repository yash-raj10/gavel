"""
Loads a small synthetic helpdesk dataset into FalkorDB:
  (:Account)<-[:BELONGS_TO]-(:Customer)<-[:FILED_BY]-(:Ticket)

Themed as Aftershoot (photo culling/editing software) support tickets:
accounts are photography studios, customers are photographers at those
studios, tickets are the kind of support requests they'd actually file.

Run this once before using the service:
    python seed.py
"""

import os

from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

HOST = os.environ.get("FALKORDB_HOST", "localhost")
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
GRAPH_NAME = os.environ.get("FALKORDB_GRAPH", "judgment_memory")

# Each account has a name and a handful of customers.
# Each customer has a handful of tickets. Ticket bodies are written so that
# some obviously read as angry / cancel-threatening, and some don't --
# that's what makes the demo results look convincing.
# Ticket bodies are written with explicit, unambiguous language on purpose.
# The local judge model (laya, zero-shot) picks up stated emotion/intent
# ("I am furious", "I want to cancel") far more reliably than implication
# ("we're looking at other tools") -- tested against the real model before
# writing these, see docs/PLAN.md section 6.
ACCOUNTS = [
    {
        "id": "acc-goldenhour",
        "name": "Golden Hour Studios",
        "customers": [
            {
                "id": "cust-jane",
                "name": "Jane Doe",
                "tickets": [
                    (
                        "Refund still not processed",
                        "I am extremely angry about this. You have ignored my "
                        "refund request three times now and it is completely "
                        "unacceptable.",
                    ),
                    (
                        "Question about invoices",
                        "Hi, could you point me to where I can download past invoices? Thanks!",
                    ),
                ],
            },
            {
                "id": "cust-mo",
                "name": "Mo Ibrahim",
                "tickets": [
                    (
                        "Culling is broken again",
                        "This is unacceptable. AI culling has been crashing on every "
                        "wedding shoot for two days and nobody has responded. I am furious.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-lensandlight",
        "name": "Lens & Light Photography",
        "customers": [
            {
                "id": "cust-sam",
                "name": "Sam Lee",
                "tickets": [
                    (
                        "Feature request: dark mode",
                        "Would be great to have a dark mode option in the editing workspace.",
                    ),
                    (
                        "Billing question",
                        "Can you confirm which plan we're currently on? No rush.",
                    ),
                ],
            },
            {
                "id": "cust-priya",
                "name": "Priya Nair",
                "tickets": [
                    (
                        "Please cancel my plan",
                        "I want to cancel my subscription immediately, this "
                        "product no longer works for us.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-candidframes",
        "name": "Candid Frames Co.",
        "customers": [
            {
                "id": "cust-peter",
                "name": "Peter Gibbons",
                "tickets": [
                    (
                        "Thanks for the quick fix",
                        "Just wanted to say the support team resolved my issue "
                        "really fast yesterday. Appreciate it!",
                    ),
                    (
                        "Export is slow",
                        "Exporting a full wedding gallery takes a very long time, "
                        "sometimes timing out. Not urgent but would love a fix.",
                    ),
                ],
            }
        ],
    },
    {
        "id": "acc-shutterstory",
        "name": "Shutter Story Studio",
        "customers": [
            {
                "id": "cust-lena",
                "name": "Lena Park",
                "tickets": [
                    (
                        "AI culling picked the wrong photos",
                        "I am really frustrated. AI culling keeps rejecting the sharpest "
                        "shots from my shoots and I have to redo everything by hand.",
                    ),
                    (
                        "How do I export presets",
                        "Hi, where can I export my color grading presets to share with my second shooter?",
                    ),
                ],
            },
            {
                "id": "cust-arun",
                "name": "Arun Mehta",
                "tickets": [
                    (
                        "Considering switching tools",
                        "I want to cancel my subscription. I have decided to switch to a "
                        "competitor because the culling accuracy is not good enough.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-framefables",
        "name": "Frame Fables",
        "customers": [
            {
                "id": "cust-tom",
                "name": "Tom Reyes",
                "tickets": [
                    (
                        "Love the new culling speed",
                        "The latest update made culling so much faster. Really happy with it!",
                    ),
                    (
                        "Question about team seats",
                        "Can I add a second editor to my plan? Just checking pricing, no rush.",
                    ),
                ],
            },
            {
                "id": "cust-ingrid",
                "name": "Ingrid Haas",
                "tickets": [
                    (
                        "App keeps crashing during import",
                        "I am furious. The app has crashed three times today while importing "
                        "a wedding shoot and I almost lost my edits.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-pixelandpose",
        "name": "Pixel & Pose",
        "customers": [
            {
                "id": "cust-noor",
                "name": "Noor Khan",
                "tickets": [
                    (
                        "Please cancel my account",
                        "I want to cancel immediately. This software no longer fits my workflow "
                        "and I am done paying for it.",
                    ),
                    (
                        "Minor UI glitch",
                        "Small thing: the thumbnail grid flickers sometimes when scrolling fast. Not a big deal.",
                    ),
                ],
            },
            {
                "id": "cust-victor",
                "name": "Victor Alonso",
                "tickets": [
                    (
                        "Great support call today",
                        "Thanks for walking me through the batch export settings on the call, "
                        "really appreciated it.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-everlight",
        "name": "Everlight Photography",
        "customers": [
            {
                "id": "cust-dana",
                "name": "Dana Whitfield",
                "tickets": [
                    (
                        "Unacceptable downtime",
                        "This is completely unacceptable. The app has been down all weekend "
                        "during peak wedding season and I am extremely angry about it.",
                    ),
                    (
                        "Export formats question",
                        "Does the export support TIFF alongside JPEG? Just curious.",
                    ),
                ],
            },
            {
                "id": "cust-felix",
                "name": "Felix Grant",
                "tickets": [
                    (
                        "Billing cycle question",
                        "When does my next billing cycle start? Just want to plan ahead.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-wildframe",
        "name": "Wildframe Collective",
        "customers": [
            {
                "id": "cust-maya",
                "name": "Maya Singh",
                "tickets": [
                    (
                        "Thinking about cancelling",
                        "I want to cancel my subscription. The new pricing is too high for "
                        "how often I actually use the tool.",
                    ),
                    (
                        "Keyboard shortcut request",
                        "Would love a keyboard shortcut for flagging photos during culling.",
                    ),
                ],
            },
            {
                "id": "cust-owen",
                "name": "Owen Brooks",
                "tickets": [
                    (
                        "Great experience overall",
                        "Just wanted to say the editing workflow has saved me hours every week. Thank you!",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-sunsetlane",
        "name": "Sunset Lane Studios",
        "customers": [
            {
                "id": "cust-ravi",
                "name": "Ravi Kumar",
                "tickets": [
                    (
                        "Sync keeps failing",
                        "I am furious, cloud sync keeps failing halfway through and I lose track "
                        "of which photos uploaded.",
                    ),
                    (
                        "Question about storage limits",
                        "How much cloud storage comes with the current plan?",
                    ),
                ],
            },
            {
                "id": "cust-hana",
                "name": "Hana Kobayashi",
                "tickets": [
                    (
                        "Support was fast and helpful",
                        "Quick thanks to support for resolving my login issue within minutes.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-brightlens",
        "name": "Bright Lens Co.",
        "customers": [
            {
                "id": "cust-carla",
                "name": "Carla Mendes",
                "tickets": [
                    (
                        "Culling missed obvious blinks",
                        "Frustrated that culling is still letting through photos where the subject "
                        "clearly blinked. Feels like it needs work.",
                    ),
                    (
                        "Invoice copy needed",
                        "Could you send me a copy of last month's invoice for my records?",
                    ),
                ],
            },
            {
                "id": "cust-ben",
                "name": "Ben Carter",
                "tickets": [
                    (
                        "I want to cancel",
                        "I want to cancel my plan. I am switching to a different editing tool "
                        "that fits my style better.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-mooncraft",
        "name": "Mooncraft Imagery",
        "customers": [
            {
                "id": "cust-zara",
                "name": "Zara Ahmed",
                "tickets": [
                    (
                        "Really happy with recent updates",
                        "The latest release fixed the lag I was having. Great work, really happy with it.",
                    ),
                    (
                        "Question about mobile app",
                        "Is there a mobile companion app planned, or is this desktop only for now?",
                    ),
                ],
            },
            {
                "id": "cust-leo",
                "name": "Leo Fontaine",
                "tickets": [
                    (
                        "Crashing on export, very angry",
                        "I am extremely angry, the app crashed twice while exporting a client gallery "
                        "and I nearly missed my delivery deadline.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-goldenaperture",
        "name": "Golden Aperture Studio",
        "customers": [
            {
                "id": "cust-wendy",
                "name": "Wendy Shaw",
                "tickets": [
                    (
                        "Watermark tool is clunky",
                        "The watermark placement tool is confusing to use, took me ages to get it right. "
                        "Not angry, just a usability complaint.",
                    ),
                    (
                        "Love the batch export",
                        "Batch export has been a lifesaver for my delivery workflow. Thank you!",
                    ),
                ],
            },
            {
                "id": "cust-kabir",
                "name": "Kabir Chatterjee",
                "tickets": [
                    (
                        "Cancelling due to repeated bugs",
                        "I want to cancel my subscription. Too many bugs in the last few releases "
                        "and I have lost confidence in the product.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-paperandlight",
        "name": "Paper & Light Co.",
        "customers": [
            {
                "id": "cust-greta",
                "name": "Greta Lindqvist",
                "tickets": [
                    (
                        "App froze during a client preview",
                        "I am furious, the app froze while showing a client their gallery live "
                        "and it looked completely unprofessional.",
                    ),
                    (
                        "Asking about referral program",
                        "Does Aftershoot have a referral program for studios like mine?",
                    ),
                ],
            },
            {
                "id": "cust-oscar",
                "name": "Oscar Dunn",
                "tickets": [
                    (
                        "Great onboarding experience",
                        "The onboarding walkthrough was clear and quick, really well done.",
                    ),
                ],
            },
        ],
    },
    {
        "id": "acc-hiddentrail",
        "name": "Hidden Trail Photography",
        "customers": [
            {
                "id": "cust-sofia",
                "name": "Sofia Delgado",
                "tickets": [
                    (
                        "Looking to cancel this month",
                        "I want to cancel my plan this month. The cost no longer makes sense for "
                        "my current shoot volume.",
                    ),
                    (
                        "Feature idea: client galleries",
                        "Would be nice to have shareable client gallery links built in.",
                    ),
                ],
            },
            {
                "id": "cust-milo",
                "name": "Milo Fischer",
                "tickets": [
                    (
                        "Extremely frustrated with sync errors",
                        "I am extremely frustrated. Sync errors keep corrupting my edit history "
                        "and I have had to redo work twice this week.",
                    ),
                ],
            },
        ],
    },
]


def seed():
    db = FalkorDB(host=HOST, port=PORT)
    g = db.select_graph(GRAPH_NAME)

    # Wipe this graph only, so re-running seed.py is safe.
    try:
        g.delete()
    except Exception:
        pass

    ticket_count = 0
    for account in ACCOUNTS:
        g.query(
            "MERGE (a:Account {id: $id}) SET a.name = $name",
            {"id": account["id"], "name": account["name"]},
        )
        for customer in account["customers"]:
            g.query(
                """
                MATCH (a:Account {id: $account_id})
                MERGE (c:Customer {id: $id})
                SET c.name = $name
                MERGE (c)-[:BELONGS_TO]->(a)
                """,
                {
                    "account_id": account["id"],
                    "id": customer["id"],
                    "name": customer["name"],
                },
            )
            for i, (subject, body) in enumerate(customer["tickets"]):
                ticket_id = f"{customer['id']}-t{i}"
                g.query(
                    """
                    MATCH (c:Customer {id: $customer_id})
                    MERGE (t:Ticket {id: $id})
                    SET t.subject = $subject, t.body = $body, t.version = 1
                    MERGE (t)-[:FILED_BY]->(c)
                    """,
                    {
                        "customer_id": customer["id"],
                        "id": ticket_id,
                        "subject": subject,
                        "body": body,
                    },
                )
                ticket_count += 1

    print(
        f"Seeded {len(ACCOUNTS)} accounts, "
        f"{sum(len(a['customers']) for a in ACCOUNTS)} customers, "
        f"{ticket_count} tickets into graph '{GRAPH_NAME}'."
    )


if __name__ == "__main__":
    seed()
