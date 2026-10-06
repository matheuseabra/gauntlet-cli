# Language and coverage support

This matrix describes the revisions in `requirements-tools.txt`, not whatever
version happens to be on PATH. **Verified** means the pinned docs and source were
inspected for discovery, analysis, and coverage handling. It does not certify every
project/toolchain. **Unsupported** means the pinned discovery/dispatch has no support.
Other versions and languages not listed here are **unverified**.

| Language | Crapper / coverage | Mutator / coverage | Dryer / coverage | Status |
| --- | --- | --- | --- | --- |
| Python | Verified / coverage.py LCOV | Verified / LCOV covered lines | Verified / none needed | Source verified; real pipeline exercised |
| TypeScript / TSX | Verified / LCOV (branches when available) | Verified / LCOV covered lines | Verified / none needed | Source verified; runtime toolchain unverified |
| Go | Verified / Go coverprofile | Verified / Go coverprofile covered lines | Verified / none needed | Source verified; runtime toolchain unverified |
| Swift | Unsupported / none | Unsupported / none | Unsupported / none | Unsupported; no Swift coverage reader or adapter |
| Java | Verified / JaCoCo XML instruction counters | Verified / JaCoCo XML covered lines | Verified / none needed | Source verified; runtime toolchain unverified |
| Rust | Verified / LCOV | Verified / LCOV covered lines | Verified / none needed | Source verified; runtime toolchain unverified |
| Clojure | Verified / Cloverage HTML form counts or LCOV | Verified / Cloverage HTML or LCOV covered lines | Verified / none needed | Source verified; runtime toolchain unverified |
| JavaScript / JSX | Verified / LCOV | Verified / LCOV covered lines | Unsupported / none | Default enabled Dryer makes preflight fail; explicitly disabling Dryer permits the other two |
| ClojureDart (.cljd) | Unsupported / none | Unsupported / none | Verified / none needed | Not supported by the Gauntlet pipeline |

Coverage-free `scan` needs no reports. A full check requires a nonempty report of
the applicable format; presence does not establish that the report is current.
The shared setup prefetches grammars, but project runtimes, test runners, coverage
generation, and locked dependencies still need separate provisioning.

## Evidence

- [Crapper 9f1bead discovery](https://github.com/unclebob/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/discover.py), [language implementations](https://github.com/unclebob/crapper/tree/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/languages), and [coverage reader](https://github.com/unclebob/crapper/blob/9f1bead298b5a9d576bdd6319289fcf426e5b18a/src/crapper/coverage.py).
- [Mutator c57f038 Crapper dependency](https://github.com/unclebob/mutator/blob/c57f03879a08d2afe8c7e044e86c80bb164afd30/src/mutator/crapper_link.py), [mutation sites](https://github.com/unclebob/mutator/blob/c57f03879a08d2afe8c7e044e86c80bb164afd30/src/mutator/sites.py), and [coverage reader](https://github.com/unclebob/mutator/blob/c57f03879a08d2afe8c7e044e86c80bb164afd30/src/mutator/coverage.py).
- [Dryer 66ff6d2 discovery](https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/src/dryer/discover.py) and [README](https://github.com/unclebob/dryer/blob/66ff6d21a42c04afcad89c78a80066176d1294b0/README.md).

`doctor` checks changed files before resolving executables. `check`/`scan` check
the chosen working-tree, full, or committed scope before native commands run.
Recognized unsupported code extensions fail with exit 4, including mixed-language
changes; they do not become an empty pass. Include/exclude and explicit path scope
remain intentional limits. Non-code assets are ignored. Unknown extensions are
not claimed as supported; see `support.py` for the recognized code-extension list.
