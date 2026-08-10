# Vendored wheel provenance

chaperone-0.1.0-py3-none-any.whl
Built from chaperone commit 08d3eb33746f940851613735e839657eed34f846 (committed HEAD via
`git archive` - never a working tree), `pip wheel . --no-deps`, 2026-08-10.

Why vendored: the PyPI name `chaperone` belongs to an unrelated package (a Docker init daemon,
last released 2016). A bare-name dependency would install the wrong software. The wheel ships
`src/chaperone` only; the source repository's `tools/` (purity audit) and `tests/` do not travel,
and this repository never implies they do.
