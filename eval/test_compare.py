"""Grader tests: oracle (identical decisions -> no divergence), null (flipped decision -> HARD),
noise attribution (a field the same condition disagrees with itself on is NOISE, not DIVERGE).
Run: python3 -m pytest eval/test_compare.py -q   or   python3 eval/test_compare.py
"""
import copy
import unittest

from compare import HARD, SOFT, attribute, diff, positions


def base_decision():
    return {
        "listing_id": "x", "property": "P", "currency": "CAD", "data_status": "complete",
        "gate": {"status": "pass", "invisible_nights": 0, "markup_median": 1.0,
                 "markup_spread_warning": False, "long_term_rental": False,
                 "min_stay_mismatches": 0, "drift_dates": 0},
        "facts": {}, "flags": ["OCC_BELOW_MARKET"],
        "changes": [
            {"field": "base_price", "action": "lower", "old": 300, "new": 270, "pct_move": -10.0,
             "date_from": None, "date_to": None, "confidence": "high", "framework_rule": "r", "reason": ""},
            {"field": "date_override", "action": "raise", "old": None, "new": None, "pct_move": 15.0,
             "date_from": "2026-12-20", "date_to": "2027-01-03", "confidence": "medium", "framework_rule": "r", "reason": ""},
        ],
        "overall_direction": "lower", "confidence": "high", "summary": "",
    }


class Oracle(unittest.TestCase):
    def test_identical_is_clean(self):
        a = base_decision(); b = copy.deepcopy(a)
        self.assertEqual(diff(positions(a), positions(b)), [])

    def test_absent_field_equals_hold(self):
        a = base_decision(); b = copy.deepcopy(a)
        b["changes"].append({"field": "max_price", "action": "hold", "old": 1000, "new": 1000, "pct_move": 0.0,
                             "date_from": None, "date_to": None, "confidence": "low", "framework_rule": "", "reason": ""})
        self.assertEqual(diff(positions(a), positions(b)), [])


class Null(unittest.TestCase):
    def test_sign_flip_is_hard(self):
        a = base_decision(); b = copy.deepcopy(a)
        b["changes"][0]["action"] = "raise"; b["changes"][0]["pct_move"] = 10.0
        b["overall_direction"] = "raise"
        d = diff(positions(a), positions(b))
        keys = {(x.key, x.severity) for x in d}
        self.assertIn(("global:base_price", HARD), keys)
        self.assertIn(("direction", HARD), keys)

    def test_gate_blocked_vs_pass_is_hard(self):
        a = base_decision(); b = copy.deepcopy(a); b["gate"]["status"] = "blocked"
        self.assertIn(("gate", HARD), {(x.key, x.severity) for x in diff(positions(a), positions(b))})

    def test_hard_flag_missing_is_hard(self):
        a = base_decision(); b = copy.deepcopy(a); b["flags"] = ["LONG_TERM_RENTAL", "OCC_BELOW_MARKET"]
        d = diff(positions(a), positions(b))
        self.assertIn(("flag:LONG_TERM_RENTAL", HARD), {(x.key, x.severity) for x in d})

    def test_soft_flag_is_soft(self):
        a = base_decision(); b = copy.deepcopy(a); b["flags"] = []
        d = diff(positions(a), positions(b))
        self.assertEqual({(x.key, x.severity) for x in d}, {("flag:OCC_BELOW_MARKET", SOFT)})

    def test_small_move_vs_hold_is_soft_large_is_hard(self):
        a = base_decision(); b = copy.deepcopy(a); b["changes"] = []; b["overall_direction"] = "hold"
        a["changes"][0]["pct_move"] = -3.0
        d = {(x.key, x.severity) for x in diff(positions(a), positions(b))}
        self.assertIn(("global:base_price", SOFT), d)
        a["changes"][0]["pct_move"] = -12.0
        d = {(x.key, x.severity) for x in diff(positions(a), positions(b))}
        self.assertIn(("global:base_price", HARD), d)

    def test_dated_opposite_direction_same_month_is_hard(self):
        a = base_decision(); b = copy.deepcopy(a)
        b["changes"][1]["action"] = "lower"; b["changes"][1]["pct_move"] = -15.0
        d = {(x.key, x.severity) for x in diff(positions(a), positions(b))}
        self.assertIn(("dated:2026-12:date_override", HARD), d)
        self.assertIn(("dated:2027-01:date_override", HARD), d)


class Attribution(unittest.TestCase):
    def test_stable_cross_divergence_is_attributed(self):
        r = base_decision(); f = copy.deepcopy(r)
        f["changes"][0]["action"] = "raise"; f["changes"][0]["pct_move"] = 10.0; f["overall_direction"] = "raise"
        out = attribute(reduced=[r, copy.deepcopy(r)], full=[f, copy.deepcopy(f)])
        self.assertEqual(out["global:base_price"]["status"], "DIVERGE")
        self.assertEqual(out["global:base_price"]["severity"], HARD)

    def test_within_condition_instability_is_noise(self):
        r1 = base_decision(); r2 = copy.deepcopy(r1)
        r2["changes"][0]["action"] = "raise"; r2["changes"][0]["pct_move"] = 10.0; r2["overall_direction"] = "raise"
        f = copy.deepcopy(r2)
        out = attribute(reduced=[r1, r2], full=[f, copy.deepcopy(f)])
        self.assertEqual(out["global:base_price"]["status"], "NOISE")

    def test_agreement_everywhere(self):
        r = base_decision()
        out = attribute(reduced=[r, copy.deepcopy(r)], full=[copy.deepcopy(r)])
        self.assertTrue(all(v["status"] == "AGREE" for v in out.values()))
        self.assertIn("global:base_price", out)


if __name__ == "__main__":
    unittest.main(verbosity=1)
