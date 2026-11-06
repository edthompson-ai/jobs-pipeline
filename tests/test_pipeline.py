import contextlib
import csv
import io
import json
import os
import shutil
import tempfile
import time
import unittest

from jobs_pipeline import sample
from jobs_pipeline.__main__ import main
from jobs_pipeline.loader import find_header_index, load_rows
from jobs_pipeline.pipeline import run

FIXTURE = "tests/fixtures/mini.csv"


class LoaderTests(unittest.TestCase):
    def test_skips_preamble(self):
        rows = load_rows(FIXTURE)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0]["Company"], "Acme")

    def test_header_detection(self):
        self.assertEqual(find_header_index(["x\n", "Company,Role,Category\n"]), 1)
        with self.assertRaises(ValueError):
            find_header_index(["nope\n"])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.out)

    def test_end_to_end_outputs(self):
        stats = run(FIXTURE, self.out, "profile.toml")
        self.assertEqual(stats["rows"], 12)
        for name in ("classified.csv", "dashboard.html", "label_sample.csv", "label_sample_key.csv", "run_stats.json"):
            self.assertTrue(os.path.exists(os.path.join(self.out, name)), name)
        with open(os.path.join(self.out, "classified.csv")) as f:
            rows = list(csv.DictReader(f))
        fams = {r["Role"]: r["family"] for r in rows}
        self.assertEqual(fams["Implementation Engineer"], "A")
        self.assertEqual(fams["GTM Engineer"], "B")
        self.assertEqual(fams["Solutions Engineer"], "C")
        self.assertEqual(fams["Technical Support Engineer"], "D")
        self.assertEqual(fams["Head of Customer Success"], "Other")
        self.assertTrue(all(r["fit_reasons"] for r in rows))

    def test_dashboard_escapes_and_has_sections(self):
        run(FIXTURE, self.out, "profile.toml")
        html = open(os.path.join(self.out, "dashboard.html")).read()
        self.assertNotIn("<script>", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("&lt;Evil &amp; Co&gt;", html)
        for s in ("Roles by family", "Top ", "Skips", "Built with Claude Code at my direction."):
            self.assertIn(s, html)
        self.assertNotIn("http", html.split("<body>")[0].replace("http-equiv", ""))  # no external assets

    def test_blind_sample_and_accuracy(self):
        run(FIXTURE, self.out, "profile.toml")
        blind = os.path.join(self.out, "label_sample.csv")
        key = os.path.join(self.out, "label_sample_key.csv")
        with open(blind) as f:
            header = f.readline()
        self.assertNotIn("family,", header.replace("human_family", ""))  # predictions hidden
        # Fake labeler: agrees with predictions except one row
        with open(key) as f:
            preds = {r["sample_id"]: r["family"] for r in csv.DictReader(f)}
        with open(blind) as f:
            rows = list(csv.DictReader(f))
        for i, r in enumerate(rows):
            r["human_family"] = preds[r["sample_id"]] if i else ("Other" if preds[r["sample_id"]] != "Other" else "A")
        with open(blind, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        res = sample.score_labels(blind, key)
        self.assertEqual(res["labeled"], 12)
        self.assertAlmostEqual(res["accuracy"], 11 / 12)
        self.assertEqual(len(res["errors"]), 1)
        report = os.path.join(self.out, "acc.md")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["accuracy", "--labels", blind, "--key", key, "--report", report]), 0)
        self.assertIn("91.7%", open(report).read())

    def test_accuracy_without_labels_returns_nonzero(self):
        run(FIXTURE, self.out, "profile.toml")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["accuracy", "--labels", os.path.join(self.out, "label_sample.csv"),
                       "--key", os.path.join(self.out, "label_sample_key.csv"),
                       "--report", os.path.join(self.out, "acc.md")])
        self.assertEqual(rc, 1)


class SampleTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for fam, n in (("A", 40), ("B", 5), ("C", 20), ("D", 18), ("Other", 900)):
            rows += [{"family": fam, "row_id": f"{fam}{i}", "Role": f"{fam} {i}"} for i in range(n)]
        return rows

    def test_size_strata_and_determinism(self):
        s1 = sample.draw_sample(self._rows())
        s2 = sample.draw_sample(self._rows())
        self.assertEqual(len(s1), 100)
        self.assertEqual([r["row_id"] for r in s1], [r["row_id"] for r in s2])
        counts = {f: sum(r["family"] == f for r in s1) for f in "ABCD"}
        self.assertEqual(counts, {"A": 15, "B": 5, "C": 15, "D": 15})

    def test_weighted_accuracy(self):
        # Other stratum all right, A stratum all wrong -> weighted accuracy dominated by Other
        d = tempfile.mkdtemp()
        try:
            s = sample.draw_sample(self._rows())
            blind, key = os.path.join(d, "b.csv"), os.path.join(d, "k.csv")
            sample.write_sample(s, blind, key)
            with open(blind) as f:
                rows = list(csv.DictReader(f))
            fam = {r["sample_id"]: r["family"] for r in s}
            for r in rows:
                r["human_family"] = "Other" if fam[r["sample_id"]] in ("Other", "A") else fam[r["sample_id"]]
            with open(blind, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows(rows)
            res = sample.score_labels(blind, key)
            self.assertAlmostEqual(res["accuracy"], 85 / 100)
            self.assertAlmostEqual(res["weighted_accuracy"], (983 - 40) / 983)
        finally:
            shutil.rmtree(d)


@unittest.skipUnless(os.path.exists("s.csv"), "s.csv not present")
class RealDataTests(unittest.TestCase):
    def test_full_file_under_60s(self):
        out = tempfile.mkdtemp()
        try:
            t = time.perf_counter()
            stats = run("s.csv", out, "profile.toml")
            elapsed = time.perf_counter() - t
            self.assertEqual(stats["rows"], 2123)
            self.assertLess(elapsed, 60)
            self.assertEqual(stats["sample_rows"], 100)
            self.assertEqual(sum(stats["families"].values()), 2123)
            json.dumps(stats)
        finally:
            shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
