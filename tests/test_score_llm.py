import re
import sys
import unittest
from types import SimpleNamespace

from jobs_pipeline.llm import Budget, LLMAssist
from jobs_pipeline.pipeline import apply_llm, classify_rows
from jobs_pipeline.score import load_profile, score

PROFILE = load_profile("profile.toml")


class ScoreTests(unittest.TestCase):
    def test_reasons_sum_to_score(self):
        for title, fam, cat, remote in [("Forward Deployed AI Engineer", "A", "Data & AI", "Yes"),
                                        ("Senior Solutions Engineer", "C", "Sales & Customer Success", "No"),
                                        ("Forward Deployed Software Engineer", "A", "Engineering", "No"),
                                        ("Executive Assistant", "Other", "Operations", "No")]:
            s, reasons = score(title, fam, cat, remote, PROFILE)
            parts = [int(x) for x in re.findall(r"([+-]\d+)", reasons.split("; clamped")[0])]
            self.assertEqual(max(0, min(100, sum(parts))), s, reasons)

    def test_hand_coding_penalised(self):
        a, _ = score("Forward Deployed Engineer", "A", "Engineering", "No", PROFILE)
        b, why = score("Forward Deployed Software Engineer", "A", "Engineering", "No", PROFILE)
        self.assertLess(b, a)
        self.assertIn("hand_coding", why)

    def test_clamped_to_range(self):
        s, why = score("Senior Software Engineer", "Other", "Engineering", "No", PROFILE)
        self.assertEqual(s, 0)
        self.assertIn("clamped", why)

    def test_remote_weight_is_zero_by_default(self):
        self.assertEqual(score("GTM Engineer", "B", "x", "Yes", PROFILE)[0],
                         score("GTM Engineer", "B", "x", "No", PROFILE)[0])


class FakeMessages:
    def __init__(self, answer="A", stop_reason="end_turn", fail=False, tokens=(200, 20)):
        self.answer, self.stop_reason, self.fail, self.tokens = answer, stop_reason, fail, tokens
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise ConnectionError("boom")
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=self.tokens[0], output_tokens=self.tokens[1]),
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.answer)],
        )


def fake_client(**kw):
    m = FakeMessages(**kw)
    return SimpleNamespace(beta=SimpleNamespace(messages=m)), m


class LLMTests(unittest.TestCase):
    def test_parses_answer_and_tracks_cost(self):
        client, m = fake_client(answer="B")
        a = LLMAssist(client, Budget(1.0, 10), model="claude-opus-5-5")
        self.assertEqual(a.classify("AI Engineer", "Data & AI").family, "B")
        self.assertAlmostEqual(a.budget.spent_usd, (200 * 4 + 20 * 20) / 1e6)
        self.assertEqual(m.calls[0]["model"], "claude-opus-5-5")
        self.assertEqual(m.calls[0]["fallbacks"], "default")

    def test_call_cap(self):
        client, m = fake_client()
        a = LLMAssist(client, Budget(100.0, 3))
        results = [a.classify("x", "y") for _ in range(5)]
        self.assertEqual(len(m.calls), 3)
        self.assertTrue(results[-1].note.startswith("budget"))

    def test_usd_cap_is_checked_before_call(self):
        client, m = fake_client()
        # worst case per call on opus ~ 1024 out tokens * $20/M = ~$0.02; cap below that
        a = LLMAssist(client, Budget(0.01, 100))
        self.assertTrue(a.classify("x", "y").note.startswith("budget"))
        self.assertEqual(m.calls, [])

    def test_spend_never_exceeds_cap(self):
        client, _ = fake_client(tokens=(300, 1024))
        a = LLMAssist(client, Budget(0.1, 10_000))
        while not a.classify("Support person", "Operations").note.startswith("budget"):
            pass
        self.assertLessEqual(a.budget.spent_usd, 0.1)

    def test_refusal_and_errors_keep_rule_result(self):
        client, _ = fake_client(stop_reason="refusal")
        self.assertIsNone(LLMAssist(client, Budget(1, 5)).classify("x", "y").family)
        client, _ = fake_client(fail=True)
        self.assertEqual(LLMAssist(client, Budget(1, 5)).classify("x", "y").note, "error: ConnectionError")
        client, _ = fake_client(answer="no idea")
        self.assertEqual(LLMAssist(client, Budget(1, 5)).classify("x", "y").note, "unparseable")

    def test_unknown_model_requires_price(self):
        client, _ = fake_client()
        with self.assertRaises(ValueError):
            LLMAssist(client, Budget(1, 1), model="some-other-model")

    def test_apply_llm_only_touches_low_confidence_unskipped(self):
        rows = classify_rows([{"Role": "AI Engineer", "Category": "Data & AI"},
                              {"Role": "Head of Customer Success", "Category": "Sales & Customer Success"},
                              {"Role": "Solutions Engineer", "Category": "Sales & Customer Success"}])
        client, m = fake_client(answer="B")
        stats = apply_llm(rows, LLMAssist(client, Budget(1, 10)))
        self.assertEqual(len(m.calls), 1)
        self.assertEqual(stats["changed"], 1)
        self.assertEqual((rows[0]["family"], rows[0]["source"]), ("B", "llm"))
        self.assertEqual(rows[1]["skip_reason"], "senior_lead")

    def test_default_path_does_not_import_anthropic(self):
        self.assertNotIn("anthropic", sys.modules)


if __name__ == "__main__":
    unittest.main()
