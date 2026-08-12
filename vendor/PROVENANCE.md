# Vendored wheel provenance

Source repository: `https://github.com/EsraaKamel11/chaperone`

Added 2026-08-12, when that repository was published. Until then this file named a commit and no
repository, which left the boundary library unreadable from here - and this repository's whole
argument is that its safety comes from that library being IMPORTED rather than reimplemented. An
argument resting on an artifact the reader cannot open is one they have to take on trust, which is
the thing this repository refuses to ask for anywhere else.

chaperone-0.1.0-py3-none-any.whl
Built from chaperone commit 8044a4c9cc1e796484ed5b28d83397513c40ebfa (committed HEAD via
`git archive` - never a working tree), `pip wheel . --no-deps`, 2026-08-10. An earlier revision
of this file named the same tree by a pre-publication commit id: the source repository rewrote
its commit messages before it was first published, which renamed every commit while changing no
tree. Verified 2026-08-12: a rebuild from the commit named above reproduced every packaged file
byte for byte, differing only in the build tool's own version stamps.

Why vendored: the PyPI name `chaperone` belongs to an unrelated package (a Docker init daemon,
last released 2016). A bare-name dependency would install the wrong software. The wheel ships
`src/chaperone` only; the source repository's `tools/` (purity audit) and `tests/` do not travel,
and this repository never implies they do.
