#!/usr/bin/env python3
"""Unit tests for repo_eval.py — stdlib only, no network access.

Run:  python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import repo_eval


def full_signals(**over):
    s = {
        "pushed_days": 10,
        "license_spdx": "MIT",
        "has_license_file": True,
        "tests": True,
        "has_ci": True,
        "readme_len": 3000,
        "has_docker": True,
        "homepage": "https://example.com",
        "contributors": 12,
        "stars": 1000,
        "open_issues": 10,
    }
    s.update(over)
    return s


class TestParseRepoUrl(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(
            repo_eval.parse_repo_url("https://github.com/psf/requests"),
            ("psf", "requests"))

    def test_git_suffix(self):
        self.assertEqual(
            repo_eval.parse_repo_url("https://github.com/psf/requests.git"),
            ("psf", "requests"))

    def test_trailing_path_and_query(self):
        self.assertEqual(
            repo_eval.parse_repo_url("https://github.com/a/b/tree/main?x=1"),
            ("a", "b"))

    def test_not_github(self):
        with self.assertRaises(SystemExit):
            repo_eval.parse_repo_url("https://example.com/a/b")

    def test_empty(self):
        with self.assertRaises(SystemExit):
            repo_eval.parse_repo_url("")


class TestDaysSince(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(repo_eval.days_since(None))

    def test_garbage(self):
        self.assertIsNone(repo_eval.days_since("not-a-date"))

    def test_recent(self):
        from datetime import datetime, timezone, timedelta
        iso = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        self.assertEqual(repo_eval.days_since(iso), 3)


class TestHasTests(unittest.TestCase):
    def test_pytest_style(self):
        self.assertTrue(repo_eval.has_tests(["tests/test_eval.py"]))

    def test_unittest_style(self):
        self.assertTrue(repo_eval.has_tests(["pkg/eval_test.py"]))

    def test_js_spec(self):
        self.assertTrue(repo_eval.has_tests(["src/eval.spec.js"]))

    def test_tests_dir(self):
        self.assertTrue(repo_eval.has_tests(["tests/__init__.py"]))

    def test_negative(self):
        self.assertFalse(repo_eval.has_tests(["src/main.py", "README.md"]))

    def test_attest_is_not_a_test(self):
        # "latest" contains "test" but must not match
        self.assertFalse(repo_eval.has_tests(["docs/latest.md"]))


class TestDepParsers(unittest.TestCase):
    def test_json_deps(self):
        pkg = '{"dependencies": {"a": "1", "b": "2"}, "devDependencies": {"c": "3"}}'
        self.assertEqual(repo_eval._json_deps(pkg), 3)

    def test_req_lines(self):
        req = "# comment\nrequests\n\n-r other.txt\nphonenumbers>=1\n"
        self.assertEqual(repo_eval._req_lines(req), 2)

    def test_toml_deps(self):
        toml = "[project]\nname = 'x'\n[project.dependencies]\na = '1'\nb = '2'\n"
        self.assertEqual(repo_eval._toml_deps(toml), 2)

    def test_gomod_deps(self):
        mod = "module x\n\ngo 1.21\n\nrequire (\n\ta v1.2.3\n\tb v0.1.0\n)\n"
        self.assertEqual(repo_eval._gomod_deps(mod), 2)


class TestComputeScore(unittest.TestCase):
    def test_max_signals(self):
        score, breakdown = repo_eval.compute_score(full_signals())
        self.assertEqual(score, 90)
        labels = [b["label"] for b in breakdown]
        self.assertIn("Pushed in the last 30 days", labels)
        self.assertIn("Code license declared (MIT)", labels)

    def test_empty_signals(self):
        # stars=0 & issues=0 -> ratio 0 -> healthy-issue-ratio still awards 10
        score, breakdown = repo_eval.compute_score(full_signals(
            pushed_days=None, license_spdx=None, has_license_file=False,
            tests=False, has_ci=False, readme_len=0, has_docker=False,
            homepage=None, contributors=1, stars=0, open_issues=0))
        self.assertEqual(score, 10)
        self.assertEqual(len(breakdown), 1)

    def test_push_boundaries(self):
        for days, pts in [(30, 20), (31, 14), (90, 14), (91, 7), (365, 7), (366, 0)]:
            score, _ = repo_eval.compute_score(full_signals(pushed_days=days))
            self.assertEqual(score, 70 + pts, f"days={days}")

    def test_license_noassertion(self):
        score, breakdown = repo_eval.compute_score(
            full_signals(license_spdx="NOASSERTION"))
        self.assertEqual(score, 75)
        self.assertFalse(any("license declared" in b["label"].lower()
                             for b in breakdown))

    def test_readme_thin(self):
        score, _ = repo_eval.compute_score(full_signals(readme_len=499))
        self.assertEqual(score, 87)  # 90 - 5 + 2

    def test_readme_missing(self):
        score, _ = repo_eval.compute_score(full_signals(readme_len=0))
        self.assertEqual(score, 85)

    def test_issue_ratio_bands(self):
        cases = [((1000, 10), 10), ((1000, 50), 6), ((1000, 200), 3),
                 ((1000, 500), 0)]
        for (stars, issues), pts in cases:
            score, _ = repo_eval.compute_score(
                full_signals(stars=stars, open_issues=issues))
            self.assertEqual(score, 80 + pts,
                             f"stars={stars} issues={issues}")

    def test_contributors_band(self):
        score, _ = repo_eval.compute_score(full_signals(contributors=2))
        self.assertEqual(score, 85)

    def test_additive_traceability(self):
        score, breakdown = repo_eval.compute_score(full_signals())
        self.assertEqual(score, sum(b["points"] for b in breakdown))


if __name__ == "__main__":
    unittest.main()
