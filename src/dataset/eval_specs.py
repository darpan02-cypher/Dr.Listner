"""Visit specs for the eval set. Per-split gap counts are printed in the manifest."""
from .eval_build import Spec

A, C = "hoh_lowlit_alone", "hoh_lowlit_caregiver"

DEV = [
    Spec("eval-dev-01", "dev", A, cardiac="stent", conds=("htn", "hld"), smoking="former"),
    Spec("eval-dev-02", "dev", C, cardiac="none", conds=("dm",), concern="addressed_mid", repaired=("nature",)),
    Spec("eval-dev-03", "dev", A, cardiac="cabg", conds=("htn",), missed=("syncope",)),
    Spec("eval-dev-04", "dev", C, cardiac="stent", conds=("htn", "dm"), missed=("relieving", "onset"), concern="unaddr_late"),
    Spec("eval-dev-05", "dev", A, cardiac="cabg", conds=("hld",), smoking="former", contradiction="cardiac", concern="unaddr_mid"),
    Spec("eval-dev-06", "dev", C, cardiac="none", conds=("htn", "dm"), contradiction="risk", missed=("dyspnea",)),
    Spec("eval-dev-07", "dev", A, cardiac="stent", conds=("afib",), mishear=("radiation", "wrong")),
    Spec("eval-dev-08", "dev", A, cardiac="none", conds=("htn",), mishear=("syncope", "repeat"), teachback_missing=True),
    Spec("eval-dev-09", "dev", C, cardiac="cabg", conds=("dm", "hld"), teachback_missing=True, contradiction="meds"),
]

TEST = [
    # clean controls, several with hard negatives (repaired repeat requests, addressed concerns)
    Spec("eval-test-01", "test", A, cardiac="stent", conds=("htn",), smoking="former", concern="addressed_mid", repaired=("radiation",)),
    Spec("eval-test-02", "test", A, cardiac="none", conds=("hld",)),
    Spec("eval-test-03", "test", C, cardiac="cabg", conds=("htn", "dm"), concern="addressed_late", repaired=("dyspnea",)),
    Spec("eval-test-04", "test", A, cardiac="stent", conds=("dm",), concern="addressed_mid"),
    Spec("eval-test-05", "test", C, cardiac="none", conds=("htn", "hld"), smoking="former", concern="addressed_late", repaired=("exertional",)),
    # gap visits
    Spec("eval-test-06", "test", A, cardiac="cabg", conds=("htn",), missed=("exertional",), concern="unaddr_mid", teachback_missing=True),
    Spec("eval-test-07", "test", C, cardiac="none", conds=("dm",), missed=("radiation", "syncope"), concern="unaddr_mid"),
    Spec("eval-test-08", "test", A, cardiac="none", conds=("htn", "hld"), missed=("family_history",), contradiction="risk"),
    Spec("eval-test-09", "test", A, cardiac="stent", conds=("htn",), missed=("relieving",), concern="unaddr_late"),
    Spec("eval-test-10", "test", A, cardiac="none", conds=("afib",), missed=("diaphoresis",), mishear=("nature", "wrong"), concern="unaddr_late"),
    Spec("eval-test-11", "test", A, cardiac="stent", conds=("hld",), smoking="former", contradiction="cardiac"),
    Spec("eval-test-12", "test", C, cardiac="cabg", conds=("htn", "dm"), contradiction="meds", concern="unaddr_mid"),
    Spec("eval-test-13", "test", A, cardiac="none", conds=("dm", "hld"), mishear=("onset", "wrong"), repaired=("dyspnea",), contradiction="meds"),
    Spec("eval-test-14", "test", C, cardiac="stent", conds=("htn",), mishear=("exertional", "repeat"), teachback_missing=True),
    Spec("eval-test-15", "test", A, cardiac="cabg", conds=("htn", "afib"), teachback_missing=True, contradiction="risk"),
]
ALL = DEV + TEST
