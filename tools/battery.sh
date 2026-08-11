#!/usr/bin/env bash
# The repo battery (spec section 11). Zero hits expected on every grep.
#
# Patterns are CONSTRUCTED, never spelled: every tracked file - this script and the plan section
# that embeds it included - has to pass the battery it defines. A gate whose own pattern appears
# literally in a file it scans can only be made green by exempting something, and an exemption is
# how a gate stops measuring.
#
#   bash tools/battery.sh
#   PYTHON=/path/to/python bash tools/battery.sh   # when `python` on PATH is not the venv's
set -u

# `git ls-files` answers RELATIVE to the current directory and lists only what sits beneath it, so
# a run from tools/ would scan a subset of the tree and print exactly the same "ok" as a full run.
root=$(git rev-parse --show-toplevel 2>/dev/null) || {
  printf 'battery: not inside a git work tree, so there is nothing to scan\n' >&2
  exit 1
}
cd "$root" || exit 1

PY="${PYTHON:-python}"
fail=0
say() { printf '%-40s %s\n' "$1" "$2"; }

# -z with mapfile rather than word splitting: a tracked path containing a space would otherwise
# split into two names that do not exist, grep would error on both, and that file would go
# unscanned while every gate still reported "ok".
mapfile -d '' -t ALL < <(git ls-files -z ':!*.whl')

# One pattern over the tracked list. Prints a count, or ERR<status> when grep ITSELF failed.
#
# grep -c over a SINGLE file prints a bare count with no "filename:" prefix, so summing the last
# colon-separated field would read a real count as a filename and add zero, and a hit would vanish
# into an "ok". /dev/null is a second file, which forces the prefix on unconditionally.
#
# grep exits 0 with matches, 1 with none, and >1 on an ERROR: a bad pattern, a tracked file that
# is not on disk, a build that dies. Folding an error into "0 hits" is how a gate reports ok for a
# scan that never happened, and this script has already been caught doing it - see the token pass.
hits() {
  local out rc
  out=$(grep -c "$1" -e "$2" -- "${ALL[@]}" /dev/null)
  rc=$?
  if [ "$rc" -gt 1 ]; then printf 'ERR%s\n' "$rc"
  else printf '%s\n' "$out" | awk -F: '{s+=$NF} END{print s+0}'
  fi
}

gate() {  # gate <label> <output of hits>
  case "$2" in
    0)    say "$1" "ok" ;;
    ERR*) say "$1" "grep FAILED ($2), which is not zero hits"; fail=1 ;;
    *)    say "$1" "$2 FAIL"; fail=1 ;;
  esac
}

# Two anti-vacuity guards, because every gate below reports zero hits over a tree it never read,
# and zero is exactly what "ok" means here.
#   1. An empty file list - wrong directory, a pathspec that excluded everything, a repository
#      with nothing tracked yet. The battery would exit 0 having read nothing at all.
[ "${#ALL[@]}" -gt 0 ] || { printf 'battery: no tracked files to scan\n' >&2; exit 1; }
#   2. The counting machinery itself - a mis-summed awk field, a grep that will not run, a list of
#      names that are not on disk. A pattern that MUST hit is the only thing that tells a clean
#      tree apart from a battery that has quietly stopped reading one.
control=$(hits -I "retinue")
case "$control" in
  ''|0|ERR*)
    printf 'battery: the positive control returned %s, so the greps are not reading the tree\n' \
      "${control:-nothing}" >&2
    exit 1 ;;
esac
say "scanning" "${#ALL[@]} tracked files (control: $control hits)"

EMD=$(printf '\342\200\224')   # octal, so the byte sequence itself appears in no tracked file
gate "em dashes" "$(hits -I "$EMD")"

# Word-bounded, because a substring check is WRONG here: "provenance" contains one of the two
# adjectives, and vendor/PROVENANCE.md records where the vendored wheel came from. Correct English
# is never renamed to satisfy a check that should not have fired.
for t in prov{able,en}; do gate "adjective $t" "$(hits -Iwi "$t")"; done

gate "removed 2.x result kwarg" "$(hits -I "result""_type=")"
gate "stale model ids"          "$(hits -IE "claude-[23]|gpt-""4")"

# Client and organisation tokens. The list lives OUTSIDE this repository (untracked, ignored by
# name in .gitignore): a tracked list would ship into the reviewer's clone the very tokens it
# exists to keep out. So the pass is optional by design, it SAYS when it did not run rather than
# reporting an "ok" it never earned, and a hit prints [redacted] rather than the token itself.
TOKENS=tools/banned_tokens.txt
if [ -f "$TOKENS" ]; then
  entries=0
  # `|| [ -n "$tok" ]`: read returns non-zero on a final line with no trailing newline, and the
  # plain form drops that entry in silence - one token never checked, reported as a clean pass.
  while read -r tok || [ -n "$tok" ]; do
    case "$tok" in ''|'#'*) continue;; esac
    entries=$((entries + 1))
    # -i, and deliberately NOT -F. The entries are literal tokens, so -F reads as the right flag,
    # and it is how this pass first shipped: the msys GNU grep 3.0 on the authoring machine ABORTS
    # when -i and -F are combined, the abort printed nothing, the sum read zero, and the gate
    # reported ok for a token occurring 113 times in the tree. Entries are therefore basic regular
    # expressions - write a metacharacter escaped - and the status check in `hits` above is what
    # makes the next crash of that family a red gate instead of a clean pass.
    gate "token [redacted]" "$(hits -Ii "$tok")"
  done < "$TOKENS"
  say "token list" "$entries entries checked"
else
  say "token list" "absent by design (untracked) - this pass did NOT run"
fi

# Spec section 11 names one grep family this script does not implement: marketing figures. That is
# a decision rather than an oversight, and it belongs here and not only in a report. A marketing
# figure has no reliable textual signature - every byte budget, threshold, version and count in
# this repository is a number sitting in prose - so a pattern loose enough to catch one reddens on
# correct text, and a gate that cries wolf gets exempted until it measures nothing. The governing
# plan serves that intent differently, at Tasks 10 and 24: every invented figure hand-diffed
# against the published ranges of the firms on the untracked list. Named absent beats missing.

"$PY" tools/fleet_audit.py || fail=1
# No second -q: pyproject's addopts already carries one, and -qq deletes the "N passed" line, so
# the battery would be reporting a suite result it never printed.
"$PY" -m pytest || fail=1
exit $fail
