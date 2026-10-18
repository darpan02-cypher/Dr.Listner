"""Phrase pools for the eval set. Each pool has an even length >= 4.

Dev draws from the first half of a pool, test from the second half, so the two
splits share no phrasing. Item-specific words must stay inside that item's own
pool (checked by LINT in eval_build and tests) so deleting a Q&A cannot leave
the item covered elsewhere.
"""
from __future__ import annotations

import re

# (question variants, answer variants, mishearing replies [dev, test], repeat requests)
ITEMS: dict[str, dict] = {
    "nature": {
        "q": ["What does the pain feel like?", "Can you describe the pain for me?", "What kind of sensation is it?", "How would you describe what you feel in your chest?"],
        "a": ["It feels like a heavy weight sitting on my chest.", "It is a tight squeezing feeling in the middle.", "It is more of a dull ache.", "It feels like burning right behind the breastbone."],
        "wrong": ["Pane? The window pane in the kitchen is cracked, I need to call someone.", "My niece sent me a card, it has a picture of a bird on it."],
    },
    "onset": {
        "q": ["When did this start?", "How long have you been having it?", "When did you first notice it?", "Did it begin suddenly or slowly?"],
        "a": ["It began yesterday afternoon.", "About three days ago, I think.", "This morning, while I was making tea.", "It came on slowly last night."],
        "wrong": ["Start? The car would not start last week, the neighbor drove me today.", "The bus was late this morning, that is why I almost missed you."],
    },
    "radiation": {
        "q": ["Does the pain spread anywhere, like your arm or jaw?", "Does it travel to your neck or shoulder?", "Do you feel it in your left arm or in your jaw?", "Does it move into your arms or up toward your neck?"],
        "a": ["No, it stays right where it is.", "Yes, it goes down my left arm a little.", "I feel it in my jaw sometimes.", "No, nowhere else."],
        "wrong": ["My jaw? I eat just fine, I had oatmeal this morning.", "My arm? I carried the groceries up the steps all by myself."],
    },
    "exertional": {
        "q": ["Does walking or climbing stairs bring it on?", "Does it come on when you are active?", "Do you notice it when you exercise or exert yourself?", "Does doing chores around the house set it off?"],
        "a": ["Yes, walking up the hill makes it come on.", "No, it comes even when I am sitting.", "Yes, when I carry the laundry.", "Only when I hurry."],
        "wrong": ["The weather has been so cold this week, I keep my coat on all day.", "I used to like the hill behind the old school, lovely flowers there."],
    },
    "relieving": {
        "q": ["Does anything make it better?", "What have you done to get relief?", "Have you taken anything for it?", "Does anything ease the pain when it is there?"],
        "a": ["Sitting quietly makes it better.", "I have not taken anything for it.", "Nothing really helps.", "I took an antacid and it did not do anything."],
        "wrong": ["My television is too loud, the neighbors complain about it.", "Better? The soup was nicer last week, today it is too salty."],
    },
    "dyspnea": {
        "q": ["Are you short of breath when this happens?", "Do you have trouble breathing with it?", "Do you feel winded along with the pain?", "Is your breathing affected?"],
        "a": ["Yes, I feel winded.", "No, my breathing is fine.", "A little bit, yes.", "No trouble breathing at all."],
        "wrong": ["Breath? I need to buy some mints, my mouth is always dry.", "My neighbor bakes bread on Sundays, the whole house smells wonderful."],
    },
    "diaphoresis": {
        "q": ["Do you break out in a sweat with it?", "Do you get sweaty or clammy when it happens?", "Have you been sweating with the pain?", "Are you drenched or clammy during the episodes?"],
        "a": ["No, I do not sweat.", "Yes, I get clammy.", "A little sweaty, yes.", "No, nothing like that."],
        "wrong": ["Sweat? I only knit sweaters in the winter, I am making one now.", "The heater in my apartment breaks down every other week."],
    },
    "syncope": {
        "q": ["Have you fainted or felt like you might pass out?", "Any dizziness or lightheadedness?", "Have you blacked out at all?", "Have you felt faint or dizzy?"],
        "a": ["No, I have not fainted.", "I felt dizzy once earlier this week.", "No, nothing like that.", "Yes, I almost passed out in the kitchen."],
        "wrong": ["Faint? Oh, the print on the paper is faint, I need new glasses.", "My cousin lives in Dayton now, she calls on Fridays."],
    },
    "risk_factors": {
        "q": ["Do you smoke, or have high blood pressure, diabetes or high cholesterol?", "Tell me about your health conditions, like smoking, blood pressure, sugar and cholesterol.", "Do you have any history of diabetes, blood pressure problems or cholesterol problems, or do you smoke?", "Let me ask about risk factors: tobacco, blood pressure, diabetes, cholesterol."],
        "wrong": ["My blood? The nurse took some earlier, she was very kind.", "I stopped driving a few years ago, my daughter takes me places."],
    },
    "family_history": {
        "q": ["Has anyone in your family had heart trouble at a young age?", "Does heart disease run in your family?", "Has a parent or sibling had a heart attack?", "Any heart problems in your close relatives?"],
        "a": ["No, not that I know of.", "My father had a heart attack in his fifties.", "No, nobody that I remember.", "My brother had bypass surgery."],
        "wrong": ["Family? We all get together at the holidays, it is a big noisy crowd.", "My house is quiet now, everyone has moved away."],
    },
}

# Risk-factor answers are built from the chart (truthful) and one contradiction pool.
RISK_DENIAL = ["No, none of those. I am healthy otherwise.", "No, I do not have any of those problems.", "None of those, I take good care of myself.", "No, nothing like that for me."]
SMOKING = {"former": "I quit smoking years ago.", "never": "I have never smoked."}
COND_PHRASE = {"htn": "I have high blood pressure", "dm": "I have diabetes", "hld": "I have high cholesterol", "afib": "I have an irregular heartbeat"}

PASTHX_Q = ["Have you ever had a heart procedure, like a stent or bypass surgery?", "Any past heart operations or procedures?", "Have you had any procedure on your heart before?", "Do you have a history of heart surgery or stents?"]
PASTHX_TRUE = {
    "stent": ["Yes, I had a stent put in a few years back.", "I had a stent placed in one of my heart arteries.", "Yes, a stent, a long time ago.", "They put a small tube in my heart artery some years back."],
    "cabg": ["Yes, I had bypass surgery years ago.", "I had open heart surgery, a bypass.", "Bypass surgery, a long time ago.", "Yes, they did a heart bypass on me some years back."],
    "none": ["No, never.", "No, I have not had any heart procedures.", "Nothing like that.", "No, I have never had any."],
}
PASTHX_DENY = ["No, I have never had any heart procedure.", "No, nothing has ever been done on my heart.", "No, I have not had a stent or any surgery.", "Never, my heart has always been fine."]

MEDS_Q = ["What medicines do you take every day?", "Can you tell me your daily medicines?", "Which pills do you take regularly?", "What are you taking at home for your health?"]
MEDS_DENY = ["I do not take any medicines.", "None, I do not take any pills.", "I am not on any medicines at all.", "No medicines, I stay away from them."]

OPEN_Q = ["Tell me what brought you in today.", "What can I help you with today?", "What brings you to the clinic today?", "How can I help you today?"]
OPEN_A = ["I have not felt right lately, my chest is bothering me.", "My chest has been troubling me.", "I came because of my chest.", "Something is wrong with my chest, I think."]
HOH_OPEN = [("Can you hear me okay?", "Clearer if you face me and talk slowly."), ("Is this volume all right for you?", "Yes, as long as you do not turn away."), ("Are you comfortable with how I am speaking?", "Please talk a bit slower, my hearing is poor."), ("Let me know if I am too quiet.", "You are fine, thank you for asking.")]
CAREGIVER_OPEN = ["I brought her in today. She has been uneasy about her chest.", "I came along to help her today.", "I am here with her, she asked me to come.", "I drove her over, I will listen along."]
CAREGIVER_CLOSE = ["I will make sure she follows the plan.", "I will go over it again with her at home.", "I will write it down for her.", "I will remind her."]

# (patient concern, clinician response)
CONCERNS = [
    ("I am scared this could be a heart attack. Is that what this is?", "I understand the worry. That is why we are looking at it carefully today, and we will talk about what we find."),
    ("I worry about paying for the tests. I do not have much money.", "Thank you for telling me. Our office can check what your insurance covers and help with costs."),
    ("I get confused with my pills. I am afraid I will take them wrong.", "That is a fair concern. We will go over them one at a time and I will write them down for you."),
    ("My daughter lives far away. I am afraid to be alone if this happens again.", "That matters. We will talk about who you can call and when to call for help."),
    ("I did not catch most of what the nurse told me earlier.", "Thank you for saying so. I will speak slowly and write down the main points."),
    ("Will I have to stay in the hospital?", "Not necessarily. We will decide after we see your test results."),
]

CLOSE = ["Take care, and we will see you soon.", "Thank you for coming in. Take care.", "Okay, that is everything for today. Take care.", "All right, we are done. Take care of yourself."]
ANY_Q = ["Do you have any other questions?", "Is there anything else you want to ask me?", "Anything else on your mind?", "Any other questions before you go?"]
NO_Q = ["No, that is all, thank you.", "No, I think I understand.", "Nothing else, thank you.", "No, thank you."]
WRAP = ["Before we finish, let me go over the plan.", "Before you go, let me go over the plan.", "Let us wrap up with the plan.", "To finish, here is the plan."]
TEACHBACK_Q = ["Just so I know I explained it clearly, can you tell me in your own words what you will do?", "Can you tell me back what the plan is, so I know I was clear?", "To be sure I was clear, what will you do next?", "Can you repeat the plan in your own words for me?"]
BARE_OK = ["Okay.", "Yes, okay.", "Okay, yes.", "Mm-hm, okay."]
REPEAT_REQ = [["Sorry, what did you say?", "Pardon? I did not hear you."], ["Could you say that again? The ringing in my ears is loud today.", "I missed that, can you repeat it?"]]
REPEAT_FIX = ["Of course, let me say that again, louder.", "Sorry about that. Let me ask it another way.", "No problem, I will repeat it more slowly.", "Let me say that again, facing you."]

# (clinician instruction, plan item id, plan item text, patient restatement)
PLAN = [
    ("get a heart tracing and a blood test today", "ecg-bloods", "Get a heart tracing and a blood test today.", "get the heart tracing and the blood test today"),
    ("see the heart specialist within two weeks", "cardiology", "See the heart specialist within two weeks.", "see the heart specialist in two weeks"),
    ("take one baby aspirin every morning", "aspirin", "Take one baby aspirin every morning.", "take one baby aspirin each morning"),
    ("come back to this clinic in one week", "return", "Come back to the clinic in one week.", "come back here in a week"),
    ("call 911 if the pain gets worse or does not stop", "call-911", "Call 911 if the pain gets worse or does not stop.", "call 911 if the pain gets worse or will not stop"),
    ("bring your medicine bottles to your next visit", "bring-meds", "Bring your medicine bottles to the next visit.", "bring my medicine bottles next time"),
]

# Lint: item-specific words must occur only in that item's own segment.
LINT = {
    "nature": r"feels? like|describe|what kind of|sensation|squeez|burning|dull|heavy",
    "onset": r"when did|start|begin|began|how long|yesterday|this morning|days? ago|last night",
    "radiation": r"\b(spread|spreads|travel|travels|radiat\w*|arm|arms|jaw|neck|shoulder|shoulders)\b",
    "exertional": r"walk|stairs|exert|active|climb|exercise|chores|hurry|hill",
    "relieving": r"\bbetter\b|relie\w+|antacid|nitro|\brest(ing)?\b|taken anything|ease the",
    "dyspnea": r"breath|breathing|winded",
    "diaphoresis": r"sweat|clammy|drenched",
    "syncope": r"faint|pass(ed)? out|lightheaded|dizzy|black(ed)? out",
    "risk_factors": r"smok|cigarette|tobacco|blood pressure|diabet|sugar|cholesterol|hypertension",
    "family_history": r"family|relative|mother|father|parent|sibling|brother|sister|runs in",
}
LINT_RE = {k: re.compile(v, re.I) for k, v in LINT.items()}


def half(pool: list, split: str) -> list:
    n = len(pool)
    assert n % 2 == 0 and n >= 2, "pools must have even length"
    return pool[: n // 2] if split == "dev" else pool[n // 2 :]
