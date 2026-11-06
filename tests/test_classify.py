import unittest

from jobs_pipeline.classify import classify

# (title, category, expected family, expected skip_reason)
CASES = [
    ("Implementation Engineer", "Operations", "A", ""),
    ("Customer Success Manager", "Sales & Customer Success", "A", ""),
    ("Customer Solutions Engineer", "Sales & Customer Success", "A", ""),
    ("Forward Deployed Software Engineer", "Engineering", "A", ""),
    ("Deployment Strategist, CTI", "Operations", "A", ""),
    ("GTM Engineer", "Sales & Customer Success", "B", ""),
    ("Automation Engineer, Agentic Orchestration", "Engineering", "B", ""),
    ("AI Agent Engineer", "Data & AI", "B", ""),
    ("Solutions Engineer", "Sales & Customer Success", "C", ""),
    ("Partner Solutions Engineer", "Sales & Customer Success", "C", ""),
    ("Partnerships Solutions Engineer", "Sales & Customer Success", "Other", "sdr_sales"),
    ("PreSales Engineer - NYC", "Sales & Customer Success", "C", ""),
    ("Technical Support Engineer (L1)", "Engineering", "D", ""),
    ("Customer Support Specialist", "Operations", "D", ""),
    ("Support Engineer (DevTools & AI Reliability, remote)", "Data & AI", "D", ""),
    # skips
    ("Head of Customer Success", "Sales & Customer Success", "Other", "senior_lead"),
    ("Director, Forward Deployed Engineering", "Engineering", "Other", "senior_lead"),
    ("Manager, Sales Engineering", "Sales & Customer Success", "Other", "senior_lead"),
    ("Staff Forward Deployed Engineer", "Engineering", "Other", "senior_lead"),
    ("Sales Development Representative", "Sales & Customer Success", "Other", "sdr_sales"),
    ("Enterprise Account Executive", "Sales & Customer Success", "Other", "sdr_sales"),
    ("Content Marketing Manager", "Growth & Marketing", "Other", "marketing"),
    ("Event Operations Coordinator", "Growth & Marketing", "Other", "marketing"),
    ("Senior Technical Architect & Developer – Marketing Automation", "Growth & Marketing", "Other", "marketing"),
    # non-target
    ("Senior Backend Engineer, Onboarding and Provisioning", "Engineering", "Other", "not_target"),
    ("Integration Engineer, Avionics Test", "Engineering", "Other", "not_target"),
    ("QA Automation Engineer", "Engineering", "Other", "not_target"),
    ("Engineer I, Automation", "Engineering", "Other", "not_target"),
    ("Software Engineer, AI Automation", "Data & AI", "Other", "not_target"),
    ("Senior Entity Resolution Engineer", "Engineering", "Other", "not_target"),
    ("Ground Support Mechanical Design Engineer II", "Hardware & Manufacturing", "Other", "not_target"),
    ("Senior Product Manager, AI Audit Automation", "Data & AI", "Other", "not_target"),
    ("Executive Assistant", "Operations", "Other", "not_target"),
]


class ClassifyTests(unittest.TestCase):
    def test_cases(self):
        for title, cat, fam, skip in CASES:
            with self.subTest(title=title):
                c = classify(title, cat)
                self.assertEqual((c.family, c.skip_reason), (fam, skip), c.rule)

    def test_senior_skip_keeps_matched_family(self):
        c = classify("Head of Solutions Engineering", "Sales & Customer Success")
        self.assertEqual((c.family, c.matched_family), ("Other", "C"))

    def test_rule_is_recorded(self):
        self.assertIn("Solutions Engineer", classify("Solutions Engineer").rule)

    def test_ic_manager_with_comma_qualifier_not_senior(self):
        c = classify("Customer success manager, enterprise", "Sales & Customer Success")
        self.assertEqual(c.family, "A")

    def test_low_confidence_when_unmatched_in_ambiguous_category(self):
        self.assertEqual(classify("AI Engineer", "Data & AI").confidence, "low")
        self.assertEqual(classify("Driller", "Hardware & Manufacturing").confidence, "high")

    def test_whitespace_normalised(self):
        self.assertEqual(classify("  Solutions   Engineer ").family, "C")


    def test_customer_solutions_engineer_is_family_a(self):
        """P0 regression: Popl CSE must be A, not C via generic Solutions regex."""
        c = classify("Customer Solutions Engineer", "Sales & Customer Success")
        self.assertEqual(c.family, "A")
        self.assertEqual(c.skip_reason, "")
        self.assertIn("Customer Solutions", c.rule)
        # Plain / Partner Solutions Engineer must stay C
        self.assertEqual(classify("Solutions Engineer").family, "C")
        self.assertEqual(classify("Partner Solutions Engineer").family, "C")


if __name__ == "__main__":
    unittest.main()
