import tempfile
import unittest
from datetime import date
from pathlib import Path

from coverage import CoverageData

from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.models import Finding, Location, RunContext
from gauntlet.pipeline.acceptance import Acceptance, accepted, apply_acceptances
from gauntlet.pipeline.triage import covering_tests, signals
from tests.integration.test_cli import call, git


class AcceptanceTriageTests(unittest.TestCase):
    def test_expired_acceptance_keeps_survivor_blocking_and_orphan_is_review(self):
        survivor = Finding(
            "mutator:known",
            "mutator",
            "surviving-mutant",
            "error",
            Location("code.py", line=2),
            "survivor",
            blocking=True,
        )
        findings = [survivor]
        entries = {
            "mutator:known": Acceptance("Domain constraint.", date(2026, 1, 1)),
            "mutator:missing": Acceptance("Old exception."),
        }
        apply_acceptances(findings, entries, date(2026, 1, 2))
        self.assertTrue(survivor.blocking)
        self.assertFalse(survivor.accepted)
        self.assertEqual(
            {f.rule for f in findings},
            {"surviving-mutant", "expired-acceptance", "orphaned-acceptance"},
        )
        self.assertTrue(all(not f.blocking for f in findings[1:]))
        self.assertFalse(findings[-1].metadata["observed_in_scope"])

    def test_expiry_validation_and_inclusive_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gauntlet").mkdir()
            path = root / ".gauntlet/accept.toml"
            for expiry in ['"not-a-date"', "2026-01-01T12:00:00Z", "42"]:
                path.write_text(f'[[finding]]\nid="mutator:x"\nreason="why"\nexpires={expiry}\n')
                with self.assertRaises(GauntletError):
                    accepted(root)
            path.write_text('[[finding]]\nid="mutator:x"\nreason="why"\nexpires=2026-01-01\n')
            findings = [
                Finding(
                    "mutator:x",
                    "mutator",
                    "surviving-mutant",
                    "error",
                    Location("code.py"),
                    "survivor",
                    blocking=True,
                )
            ]
            apply_acceptances(findings, accepted(root), date(2026, 1, 1))
            self.assertTrue(findings[0].accepted)
            self.assertFalse(findings[0].blocking)

    def test_context_evidence_is_real_line_attribution_not_guessed_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "code.py"
            source.write_text("def f():\n    return True\n")
            self.assertEqual(covering_tests(root, "code.py", 2)[0], [])
            data = CoverageData(basename=str(root / ".coverage"))
            data.set_context("tests.test_rules.test_boundary")
            data.add_lines({str(source): {2}})
            data.write()
            self.assertEqual(
                covering_tests(root, "code.py", 2)[0], ["tests.test_rules.test_boundary"]
            )
            self.assertEqual(covering_tests(root, "code.py", 1)[0], [])

    def test_advisory_signals_require_new_test_and_correlated_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            (root / "code.py").write_text("def f():\n    return True\n")
            (root / "test_rules.py").write_text("def test_existing():\n    pass\n")
            git(root, "add", ".")
            git(
                root,
                "-c",
                "user.name=Test",
                "-c",
                "user.email=t@example.invalid",
                "commit",
                "-qm",
                "baseline",
            )
            (root / "test_rules.py").write_text(
                "def test_existing():\n    pass\n\n"
                "def test_no_oracle():\n    f()\n\n"
                "def test_with_oracle():\n    assert f()\n"
            )
            context = RunContext(
                root, "changed", ["code.py", "test_rules.py"], ["code.py"], Config()
            )
            survivor = Finding(
                "mutator:x",
                "mutator",
                "surviving-mutant",
                "error",
                Location("code.py", line=2),
                "survivor",
            )
            result = signals(
                context, [survivor], {"mutator:x": Acceptance("why")}, {"code.py": [(2, 2)]}
            )
            self.assertEqual(
                {f.rule for f in result},
                {
                    "survivor-production-cochange",
                    "test-without-assertion",
                    "acceptance-code-cochange",
                },
            )
            self.assertTrue(all(f.severity == "review" and not f.blocking for f in result))
            self.assertEqual(
                next(f.metadata["test"] for f in result if f.rule == "test-without-assertion"),
                "test_no_oracle",
            )
            no_site_change = signals(context, [survivor], {}, {"code.py": [(4, 4)]})
            self.assertFalse(any(f.rule == "survivor-production-cochange" for f in no_site_change))

    def test_test_only_diff_and_empty_selection_still_report_hygiene(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            (root / "test_new.py").write_text("def test_empty():\n    pass\n")
            (root / ".gauntlet").mkdir()
            (root / ".gauntlet/accept.toml").write_text(
                '[[finding]]\nid="mutator:absent"\nreason="Old"\nexpires=2000-01-01\n'
            )
            import json

            result = call(root, "check", "--json")
            self.assertEqual(result.returncode, 0, result.stdout)
            data = json.loads(result.stdout)
            self.assertEqual(
                {f["rule"] for f in data["findings"]},
                {"test-without-assertion", "expired-acceptance"},
            )

    def test_explain_survivor_has_classification_and_preservation_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git(root, "init", "-q")
            (root / ".gauntlet").mkdir()
            import json

            (root / ".gauntlet/results.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "findings": [
                            {
                                "id": "mutator:x",
                                "rule": "surviving-mutant",
                                "location": {"file": "code.py", "line": 2},
                                "message": "survivor",
                                "metadata": {},
                            }
                        ],
                    }
                )
            )
            result = call(root, "explain", "mutator:x")
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("Triage guidance", result.stdout)
            self.assertIn("equivalent", result.stdout)
            self.assertIn("Do not change production behavior solely", result.stdout)
