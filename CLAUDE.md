# retinue

An orchestrated fleet around an imported deterministic boundary. All data is synthetic.

## Non-negotiable

- **This repository adds no policy code.** The boundary is imported from the vendored wheel, never
  reimplemented; `tools/fleet_audit.py` holds that as AST rules. A predicate that seems missing is
  consumed from the library or becomes a Designed row, never rewritten here.
- **Built, designed and proposed: three words, always labelled.** The README table is the
  build-status authority; a claim and a row that disagree is its defect, and the row gets fixed.
- **Capture fixtures are frozen verbatim records, never edited silently.** A redaction is declared
  in the fixture's own `meta.redacted` or it does not happen; a re-run overwrites canon, deliberately.
- **Anything never executed is labelled never executed**, dated where publishing could make the
  label stale. Has-run and is-green are different claims; keep them apart.
- **Rates are measured and reported with their denominators, never asserted.** Invariants are
  asserted. A probabilistic quantity without its denominator is not stated.
- **No organisation name appears anywhere** (synthetic scenario). No em dashes in reader-facing
  prose; "judgment", never "judgement".
- Run `python -m pytest` AND `bash tools/battery.sh` before every commit, exit codes read unpiped
  (a piped exit code is the pipe's). Subjects under ~72 chars, body narrative, no trailers.

## When a guard fires

The guard is right; fix the work, never the guard. A guard that can be argued with is a
suggestion: if one is genuinely wrong, stop and raise it rather than editing it quietly.

- **A battery gate reddens** (em dash, banned adjective, stale id, a floor, an INERT specimen). Do
  not exempt the file or widen the pattern; fix the text or the tree.
- **`tests/test_plan_sync.py` reddens.** The battery and the plan's embedded copy drifted; change
  both together, byte-identically.
- **`tests/test_fixture_meta.py` reddens.** A fixture broke its provenance contract (one declared
  provenance, declared redactions, one session per family, tracked captures present). Fix the
  fixture's metadata or the checkout, never the rule.
