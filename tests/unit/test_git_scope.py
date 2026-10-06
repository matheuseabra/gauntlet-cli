import subprocess
import tempfile
import unittest
from pathlib import Path

from gauntlet.config import Config
from gauntlet.discovery import source_file
from gauntlet.errors import GauntletError
from gauntlet.git import changed_files, changed_lines, compare, parse_changed, root
from gauntlet.scope import select


def git(directory: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=directory, check=True, capture_output=True)


class GitScopeTests(unittest.TestCase):
    def test_excludes_declarations_and_typescript_test_directories(self):
        self.assertFalse(source_file("src/types.d.ts"))
        self.assertFalse(source_file("src/__tests__/fixture.ts"))
        for directory in ("testdata", "out", ".clj-kondo", ".hg", ".svn", ".idea"):
            with self.subTest(directory=directory):
                self.assertFalse(source_file(f"{directory}/fixture.py"))

    def test_porcelain_parser_keeps_newlines_and_spaces(self):
        raw = " M src/a b.py\0?? weird\nname.ts\0 D removed.py\0"
        self.assertEqual(parse_changed(raw), ["src/a b.py", "weird\nname.ts"])

    def test_discovers_staged_unstaged_untracked_and_ignores_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "tests@example.invalid")
            git(repo, "config", "user.name", "Tests")
            (repo / "old.py").write_text("value = 1\n")
            git(repo, "add", "old.py")
            git(repo, "commit", "-m", "baseline", "-q")
            (repo / "old.py").write_text("value = 2\n")
            git(repo, "add", "old.py")
            (repo / "staged.py").write_text("value = 3\n")
            git(repo, "add", "staged.py")
            (repo / "untracked.py").write_text("value = 4\n")
            (repo / "removed.py").write_text("value = 5\n")
            git(repo, "add", "removed.py")
            git(repo, "commit", "--only", "removed.py", "-m", "add deleted fixture", "-q")
            (repo / "removed.py").unlink()
            names = changed_files(repo)
            self.assertEqual(names, ["old.py", "staged.py", "untracked.py"])
            self.assertEqual(changed_lines(repo, names)["untracked.py"], [(1, 2)])
            self.assertTrue(root(repo).samefile(repo))

    def test_scope_rejects_paths_outside_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory, "repo")
            root_path.mkdir()
            outside = Path(directory, "private.py")
            outside.write_text("pass\n")
            with self.assertRaises(GauntletError):
                select(root_path, [], Config(), [str(outside)])

    def test_scope_filters_source_and_globs(self):
        with tempfile.TemporaryDirectory() as directory:
            root_path = Path(directory)
            (root_path / "src/domain").mkdir(parents=True)
            (root_path / "src/domain/rules.py").write_text("pass\n")
            config = Config(include=("src/domain/**/*.py",))
            files = ["src/domain/rules.py", "src/domain/tests/test_rules.py", "src/ui/view.py"]
            self.assertEqual(select(root_path, files, config, []), ["src/domain/rules.py"])


class CommittedGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "tests@example.invalid")
        git(self.repo, "config", "user.name", "Tests")
        (self.repo / "old.py").write_text("def old():\n    return 1\n")
        self.base = self.commit()

    def commit(self):
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "fixture")
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, text=True
        ).strip()

    def test_committed_diff_preserves_names_and_excludes_deleted_and_untracked(self):
        names = ["a space.py", "a\nnewline.py", "-option.py"]
        for name in names:
            (self.repo / name).write_text("value = 2\n")
        (self.repo / "old.py").unlink()
        head = self.commit()
        (self.repo / "untracked.py").write_text("value = 3\n")
        comparison = compare(self.repo, self.base)
        self.assertCountEqual(comparison.files, names)
        self.assertEqual(comparison.head_sha, head)
        self.assertEqual(comparison.merge_base_sha, self.base)
        self.assertEqual(changed_lines(self.repo, names, self.base)["-option.py"], [(1, 1)])

    def test_renamed_file_is_analyzed_at_new_path(self):
        git(self.repo, "mv", "old.py", "new.py")
        self.commit()
        self.assertEqual(compare(self.repo, self.base).files, ["new.py"])

    def test_divergent_base_uses_common_ancestor(self):
        git(self.repo, "checkout", "-qb", "base-branch")
        (self.repo / "base-only.py").write_text("value = 1\n")
        base_tip = self.commit()
        git(self.repo, "checkout", "-qb", "feature", self.base)
        (self.repo / "feature.py").write_text("value = 2\n")
        self.commit()
        comparison = compare(self.repo, base_tip)
        self.assertEqual(comparison.files, ["feature.py"])
        self.assertEqual(comparison.base_sha, base_tip)
        self.assertEqual(comparison.merge_base_sha, self.base)

    def test_empty_comparison_and_invalid_ref(self):
        self.assertEqual(compare(self.repo, self.base).files, [])
        for ref in ("0" * 40, "--help"):
            with self.subTest(ref=ref), self.assertRaises(GauntletError) as error:
                compare(self.repo, ref)
            self.assertEqual(error.exception.code, 4)

    def test_staged_and_unstaged_changes_fail_closed(self):
        (self.repo / "old.py").write_text("def old():\n    return 2\n")
        for staged in (False, True):
            if staged:
                git(self.repo, "add", "old.py")
            with self.subTest(staged=staged), self.assertRaises(GauntletError) as error:
                compare(self.repo, self.base)
            self.assertEqual(error.exception.code, 4)


if __name__ == "__main__":
    unittest.main()
