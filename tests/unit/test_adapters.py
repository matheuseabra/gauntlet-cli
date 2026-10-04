import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gauntlet.adapters.crapper import CrapperAdapter
from gauntlet.adapters.dryer import DryerAdapter
from gauntlet.adapters.edn import decode
from gauntlet.adapters.mutator import MutatorAdapter
from gauntlet.config import Config
from gauntlet.errors import GauntletError
from gauntlet.models import RunContext


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / "fixtures"

    def context(self, files):
        return RunContext(self.root, "changed", files, files, Config())

    def test_crapper_edn_records_metrics_and_stable_finding_id(self):
        data = decode(
            '{:entries [{:name "resolve" :namespace "billing.Plan" '
            ":complexity 14 :coverage 58.0 :crap 28.5}]}"
        )
        adapter = CrapperAdapter()
        findings = adapter.normalize(data, "src/billing.py")
        self.assertEqual(findings[0].metadata["coverage_percent"], 58.0)
        self.assertEqual(findings[0].location.file, "src/billing.py")
        self.assertEqual(findings[0].id, adapter.normalize(data, "src/billing.py")[0].id)

    def test_crapper_always_uses_the_selected_file_for_provenance(self):
        context = self.context(["src/retry.py"])
        context = context.__class__(
            context.root,
            context.mode,
            context.changed_files,
            context.selected_files,
            context.config,
            native_changed=True,
        )
        report = {"entries": []}
        with (
            patch("gauntlet.adapters.crapper.execute") as execute,
            patch("gauntlet.adapters.crapper.signature", return_value=None),
            patch("gauntlet.adapters.crapper.fresh"),
            patch("gauntlet.adapters.crapper.edn.read", return_value=report),
        ):
            CrapperAdapter().run(context)
        args = execute.call_args.args[1]
        self.assertNotIn("--changed", args)
        self.assertEqual(args[-1], str(context.root / "src/retry.py"))

    def test_dryer_reports_changed_pair_as_review_not_block(self):
        root = self.root
        context = RunContext(root, "changed", ["left.py"], ["left.py"], Config())
        data = decode(
            '{:candidates [{:score 0.91 :language "python" '
            ':left {:file "left.py" :start-line 1 :end-line 3} '
            ':right {:file "right.py" :start-line 1 :end-line 3}}]}'
        )
        finding = DryerAdapter().normalize(data, context)[0]
        self.assertEqual(finding.rule, "structural-duplication")
        self.assertEqual(finding.severity, "review")
        self.assertFalse(finding.blocking)

    def test_mutator_decodes_utf8_byte_offsets_and_survivor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = "src/retry.py"
            path = root / source_file
            path.parent.mkdir()
            path.write_text(
                "label = 'café'\ndef allowed(attempts, limit):\n    return attempts >= limit\n"
            )
            offset = path.read_bytes().index(b">=")
            identity = json.dumps(
                [source_file, "retry", "defn/allowed", offset, offset + 2, ">=", ">"]
            ).replace('"', '\\"')
            data = decode(
                '{:version 1 :namespace "retry" :source "src/retry.py" '
                ':outcomes {"' + identity + '" :survived} '
                ':forms [{:id "defn/allowed" :file "src/retry.py" '
                ":line 2 :end-line 3 :uncovered 0}]}"
            )
            context = RunContext(root, "changed", [source_file], [source_file], Config())
            finding = MutatorAdapter().normalize(data, context)[0]
            self.assertEqual(finding.location.line, 3)
            self.assertTrue(finding.id.startswith("mutator:"))

    def test_mutator_accepts_empty_deletion_replacements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_file = "src/retry.py"
            path = root / source_file
            path.parent.mkdir()
            path.write_text("def allowed(value):\n    return -value\n")
            start = path.read_bytes().index(b"-")
            identity = json.dumps(
                [source_file, "retry", "defn/allowed", start, start + 1, "-", ""]
            ).replace('"', '\\"')
            context = RunContext(root, "changed", [source_file], [source_file], Config())
            for state in ("killed", "survived"):
                data = decode(
                    '{:version 1 :namespace "retry" :source "src/retry.py" '
                    ':outcomes {"' + identity + '" :' + state + "} "
                    ':forms [{:id "defn/allowed" :file "src/retry.py" '
                    ":line 1 :end-line 2 :uncovered 0}]}"
                )
                findings = MutatorAdapter().normalize(data, context)
                if state == "killed":
                    self.assertEqual(findings, [])
                else:
                    self.assertEqual(findings[0].metadata["replacement"], "")
                    self.assertEqual(
                        findings[0].message,
                        "Tests do not distinguish deleting '-' from original behavior.",
                    )

    def test_mutator_scan_reads_upstream_deletion_site_format(self):
        context = self.context(["left.py"])
        findings = MutatorAdapter().scan("  left.py:12 delete !  [defn/check]\n", context)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].metadata["original"], "!")
        self.assertEqual(findings[0].metadata["replacement"], "")

    def test_stale_mutation_outcome_is_rejected(self):
        root = self.root
        files = ["typescript-mutant/src/retry.py"]
        source = (root / files[0]).read_bytes()
        offset = source.index(b">=")
        identity = json.dumps([files[0], "retry", "defn/allowed", offset, offset + 2, "<=", "<"])
        encoded = identity.replace('"', '\\"')
        data = decode(
            '{:version 1 :namespace "retry" :source "typescript-mutant/src/retry.py" '
            ':outcomes {"' + encoded + '" :survived} '
            ':forms [{:id "defn/allowed" :file "typescript-mutant/src/retry.py" '
            ":line 1 :end-line 2 :uncovered 0}]}"
        )
        with self.assertRaises(GauntletError):
            MutatorAdapter().normalize(data, self.context(files))

    def test_malformed_edn_and_invalid_dryer_path_fail_closed(self):
        with self.assertRaises(GauntletError):
            decode("{:entries [")
        data = decode(
            '{:candidates [{:score 0.9 :left {:file "../../escape" '
            ':start-line 1 :end-line 2} :right {:file "left.py" '
            ":start-line 1 :end-line 2}}]}"
        )
        context = self.context(["left.py"])
        with self.assertRaises(GauntletError):
            DryerAdapter().normalize(data, context)


if __name__ == "__main__":
    unittest.main()
