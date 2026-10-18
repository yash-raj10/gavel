"""
One-off accuracy check for the laya judge against our demo dataset.
Hand-labels each ticket for two questions (angry / wants to cancel), runs
the real judge, and reports accuracy at a 0.5 cutoff.

    python check_accuracy.py
"""

from judge import judge_rows

# ticket_id -> (body, is_angry, wants_to_cancel) hand-labeled from seed.py
LABELED = {
    "cust-jane-t0": ("I am extremely angry about this. You have ignored my refund request three times now and it is completely unacceptable.", True, False),
    "cust-jane-t1": ("Hi, could you point me to where I can download past invoices? Thanks!", False, False),
    "cust-mo-t0": ("This is unacceptable. AI culling has been crashing on every wedding shoot for two days and nobody has responded. I am furious.", True, False),
    "cust-sam-t0": ("Would be great to have a dark mode option in the editing workspace.", False, False),
    "cust-sam-t1": ("Can you confirm which plan we're currently on? No rush.", False, False),
    "cust-priya-t0": ("I want to cancel my subscription immediately, this product no longer works for us.", False, True),
    "cust-peter-t0": ("Just wanted to say the support team resolved my issue really fast yesterday. Appreciate it!", False, False),
    "cust-peter-t1": ("Exporting a full wedding gallery takes a very long time, sometimes timing out. Not urgent but would love a fix.", False, False),
    "cust-lena-t0": ("I am really frustrated. AI culling keeps rejecting the sharpest shots from my shoots and I have to redo everything by hand.", True, False),
    "cust-lena-t1": ("Hi, where can I export my color grading presets to share with my second shooter?", False, False),
    "cust-arun-t0": ("I want to cancel my subscription. I have decided to switch to a competitor because the culling accuracy is not good enough.", False, True),
    "cust-tom-t0": ("The latest update made culling so much faster. Really happy with it!", False, False),
    "cust-tom-t1": ("Can I add a second editor to my plan? Just checking pricing, no rush.", False, False),
    "cust-ingrid-t0": ("I am furious. The app has crashed three times today while importing a wedding shoot and I almost lost my edits.", True, False),
    "cust-noor-t0": ("I want to cancel immediately. This software no longer fits my workflow and I am done paying for it.", False, True),
    "cust-noor-t1": ("Small thing: the thumbnail grid flickers sometimes when scrolling fast. Not a big deal.", False, False),
    "cust-victor-t0": ("Thanks for walking me through the batch export settings on the call, really appreciated it.", False, False),
    "cust-dana-t0": ("This is completely unacceptable. The app has been down all weekend during peak wedding season and I am extremely angry about it.", True, False),
    "cust-dana-t1": ("Does the export support TIFF alongside JPEG? Just curious.", False, False),
    "cust-felix-t0": ("When does my next billing cycle start? Just want to plan ahead.", False, False),
    "cust-maya-t0": ("I want to cancel my subscription. The new pricing is too high for how often I actually use the tool.", False, True),
    "cust-maya-t1": ("Would love a keyboard shortcut for flagging photos during culling.", False, False),
    "cust-owen-t0": ("Just wanted to say the editing workflow has saved me hours every week. Thank you!", False, False),
    "cust-ravi-t0": ("I am furious, cloud sync keeps failing halfway through and I lose track of which photos uploaded.", True, False),
    "cust-ravi-t1": ("How much cloud storage comes with the current plan?", False, False),
    "cust-hana-t0": ("Quick thanks to support for resolving my login issue within minutes.", False, False),
    "cust-carla-t0": ("Frustrated that culling is still letting through photos where the subject clearly blinked. Feels like it needs work.", True, False),
    "cust-carla-t1": ("Could you send me a copy of last month's invoice for my records?", False, False),
    "cust-ben-t0": ("I want to cancel my plan. I am switching to a different editing tool that fits my style better.", False, True),
    "cust-zara-t0": ("The latest release fixed the lag I was having. Great work, really happy with it.", False, False),
    "cust-zara-t1": ("Is there a mobile companion app planned, or is this desktop only for now?", False, False),
    "cust-leo-t0": ("I am extremely angry, the app crashed twice while exporting a client gallery and I nearly missed my delivery deadline.", True, False),
    "cust-wendy-t0": ("The watermark placement tool is confusing to use, took me ages to get it right. Not angry, just a usability complaint.", False, False),
    "cust-wendy-t1": ("Batch export has been a lifesaver for my delivery workflow. Thank you!", False, False),
    "cust-kabir-t0": ("I want to cancel my subscription. Too many bugs in the last few releases and I have lost confidence in the product.", False, True),
    "cust-greta-t0": ("I am furious, the app froze while showing a client their gallery live and it looked completely unprofessional.", True, False),
    "cust-greta-t1": ("Does Aftershoot have a referral program for studios like mine?", False, False),
    "cust-oscar-t0": ("The onboarding walkthrough was clear and quick, really well done.", False, False),
    "cust-sofia-t0": ("I want to cancel my plan this month. The cost no longer makes sense for my current shoot volume.", False, True),
    "cust-sofia-t1": ("Would be nice to have shareable client gallery links built in.", False, False),
    "cust-milo-t0": ("I am extremely frustrated. Sync errors keep corrupting my edit history and I have had to redo work twice this week.", True, False),
}

ANGRY_Q = "which tickets sound angry?"
CANCEL_Q = "which tickets sound like the customer wants to cancel?"


def score(question: str, label_index: int) -> None:
    rows = {tid: body for tid, (body, *_labels) in LABELED.items()}
    predictions = judge_rows(question, rows)

    correct = 0
    false_pos, false_neg = [], []
    for tid, (_, is_angry, wants_cancel) in LABELED.items():
        truth = is_angry if label_index == 0 else wants_cancel
        pred = predictions[tid] >= 0.5
        if pred == truth:
            correct += 1
        elif pred and not truth:
            false_pos.append((tid, predictions[tid]))
        elif truth and not pred:
            false_neg.append((tid, predictions[tid]))

    total = len(LABELED)
    print(f"\n=== {question!r} ===")
    print(f"accuracy: {correct}/{total} = {correct/total:.1%}")
    if false_pos:
        print(f"false positives ({len(false_pos)}): {false_pos}")
    if false_neg:
        print(f"false negatives ({len(false_neg)}): {false_neg}")


if __name__ == "__main__":
    score(ANGRY_Q, 0)
    score(CANCEL_Q, 1)
