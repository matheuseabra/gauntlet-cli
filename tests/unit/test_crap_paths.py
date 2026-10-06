import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from gauntlet.config import Config, CrapPath, load
from gauntlet.errors import GauntletError
from gauntlet.models import Finding, Location
from gauntlet.pipeline.crap import apply, lever


class CrapPathsTests(unittest.TestCase):
    def finding(self, file="src/ui/view.py"):
        return Finding(
            "crapper:x",
            "crapper",
            "crap-score",
            "info",
            Location(file, "view", 2, 10),
            "score",
            {"crap": 40, "cyclomatic_complexity": 8, "coverage_percent": 20},
        )

    def test_review_path_does_not_weaken_default_business_policy(self):
        config = Config()
        config = replace(
            config, policy=replace(config.policy, crap_paths=(CrapPath("src/ui/**", 35, "review"),))
        )
        ui, business = self.finding(), self.finding("src/domain/rule.py")
        for finding in (ui, business):
            apply(finding, config, [finding.location.file], None)
        self.assertFalse(ui.blocking)
        self.assertEqual(ui.severity, "review")
        self.assertEqual(ui.metadata["threshold"], 35)
        self.assertEqual(ui.metadata["policy_glob"], "src/ui/**")
        self.assertTrue(business.blocking)
        self.assertEqual(business.metadata["threshold"], 30)

    def test_first_matching_glob_and_threshold_keep_changed_line_policy(self):
        config = Config()
        config = replace(
            config,
            policy=replace(
                config.policy, crap_paths=(CrapPath("src/**", 50), CrapPath("src/ui/**", 10))
            ),
        )
        finding = self.finding()
        apply(finding, config, [finding.location.file], {finding.location.file: [(20, 22)]})
        self.assertEqual(finding.metadata["threshold"], 50)
        self.assertFalse(finding.blocking)
        self.assertFalse(finding.metadata["changed"])

    def test_formula_guidance_reports_leverage_not_unproven_cost(self):
        metrics = {"cyclomatic_complexity": 8, "coverage_percent": 20}
        result = lever(metrics, 30)
        self.assertEqual(result["recommended_lever"], "meaningful-tests")
        self.assertGreater(result["required_coverage_percent"], 20)
        self.assertEqual(
            lever({"cyclomatic_complexity": 35, "coverage_percent": 20}, 30)["recommended_lever"],
            "reduce-complexity",
        )
        self.assertEqual(lever({}, 30)["recommended_lever"], "unverified")

    def test_config_validates_rules_and_inherits_global_threshold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gauntlet.toml"
            prefix = "version=1\n[policy]\ncrap_threshold=40\n[[policy.crap_paths]]\n"
            path.write_text(prefix + 'glob="src/ui/**"\nmode="review"\n')
            self.assertEqual(load(root).policy.crap_paths, (CrapPath("src/ui/**", 40, "review"),))
            for invalid in [
                'glob=""',
                'glob="**"\nthreshold=-1',
                'glob="**"\nmode="skip"',
                'glob="**"\nunknown=1',
                'glob="**"\nthreshold=true',
            ]:
                path.write_text(prefix + invalid + "\n")
                with self.assertRaises(GauntletError):
                    load(root)
