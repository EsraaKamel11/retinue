#!/usr/bin/env bash
# The repo battery (spec section 11). Zero hits expected on every grep.
#
# Patterns are CONSTRUCTED, never spelled: every tracked file - this script and the plan section
# that embeds it included - has to pass the battery it defines. A gate whose own pattern appears
# literally in a file it scans can only be made green by exempting something, and an exemption is
# how a gate stops measuring. The plan's embedded copy is held byte-identical to this file by
# tests/test_plan_sync.py, so the document and the artifact cannot drift apart quietly.
#
# Every gate here asserts a MAGNITUDE, not merely a non-zero. "Nothing found" and "nothing looked"
# print the same word, so each gate proves it can still find a violation of EVERY BRANCH it relies
# on before its zero is believed, the scan proves its scope, and the suite proves its pass count.
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

# Floors, not counts, and both sit deliberately below what the tree holds today: ordinary growth
# and the odd deletion stay quiet, while a COLLAPSE reddens. A pathspec that stops matching, or a
# suite that stops collecting, is the failure these two numbers exist for.
#
# RE-BASELINED to the finished tree. They were set against the Phase 1 tree, 40 against 50 files
# and 72 against 75 passed, and four phases later that leaves a 42-file and a 165-test gap: numbers
# that catch a collapse while sitting green through the deletion of every test Phases 2 to 4 added.
# A floor trailing the tree by two thirds has stopped measuring erosion. Still floors and never
# equalities, for the reason the old comment gave and which has not changed: a floor raised to
# equality reddens on the first added test and gets exempted, which is how a gate stops measuring.
FILE_FLOOR=78   # tracked files scanned; 82 at the time of writing (was 40, against 50)
PASS_FLOOR=230  # tests that must PASS; the tree holds 237 passed and 9 skipped (was 72, against 75)

TMP=$(mktemp -d) || { printf 'battery: could not make a temp dir\n' >&2; exit 1; }
trap 'rm -rf "$TMP"' EXIT

# -z with mapfile rather than word splitting: a tracked path containing a space would otherwise
# split into two names that do not exist, grep would error on both, and that file would go
# unscanned while every gate still reported "ok".
mapfile -d '' -t ALL < <(git ls-files -z ':!*.whl')

# One pattern over one set of files. Prints a count, or ERR<status> when grep ITSELF failed.
#
# grep -c over a SINGLE file prints a bare count with no "filename:" prefix, so summing the last
# colon-separated field would read a real count as a filename and add zero, and a hit would vanish
# into an "ok". /dev/null is a second file, which forces the prefix on unconditionally.
#
# grep exits 0 with matches, 1 with none, and >1 on an ERROR: a bad pattern, a tracked file that is
# not on disk, a build that dies. Folding an error into "0 hits" is how a gate reports ok for a
# scan that never happened, and this script has already been caught doing it - see the token pass.
scan() {  # scan <grep flags> <pattern> <file>...
  local flags=$1 pat=$2 out rc
  shift 2
  out=$(grep -c "$flags" -e "$pat" -- "$@" /dev/null)
  rc=$?
  if [ "$rc" -gt 1 ]; then printf 'ERR%s\n' "$rc"
  else printf '%s\n' "$out" | awk -F: '{s+=$NF} END{print s+0}'
  fi
}

# gate <label> <grep flags> <pattern> <specimen>...
#
# Each specimen is a string this gate MUST match. Before any zero from the tree is believed, the
# gate's own invocation - the same flags, the same pattern - runs against every specimen in turn,
# and a specimen that goes unmatched makes the gate INERT and reddens it by name.
#
# ONE PER BRANCH, because a single specimen only shows the pattern is not TOTALLY dead. Retarget
# the stale-id alternation's far branch at a version that occurs nowhere, leave the bracket branch
# intact, and a one-specimen self-test still reports ok with half the gate dead. That alternation
# therefore names three specimens, covering both ends of the bracket expression and the far side
# of the pipe. (Phrased without naming the branch, because naming it would spell a stale id in a
# file this gate scans. The battery caught precisely that in this comment's first draft: three
# hits across this file and the plan's copy of it, which is the rule firing on the comment that
# explains the rule.)
#
# A flag counts as a branch when the tree does not already police it. Dropping `-i` from the
# adjective gates would redden nothing, since no tracked file spells either word capitalised, so
# each adjective gate carries a capitalised specimen. Dropping `-w` needs no anti-specimen: the
# gate would then match "provenance", `vendor/PROVENANCE.md` exists, and the tree scan itself goes
# red - which is the difference between a flag that is unexercised and one that is unenforced.
gate() {
  local label=$1 flags=$2 pat=$3 probe n i=0 specimen
  shift 3
  # A gate called with no specimen would skip its own self-test and report ok, which is the exact
  # shape of vacuity this function exists to prevent.
  [ "$#" -gt 0 ] || {
    say "$label" "no specimen, so nothing shows this gate can still fire FAIL"
    fail=1
    return
  }
  for specimen in "$@"; do
    i=$((i + 1))
    printf '%s\n' "$specimen" > "$TMP/specimen"
    probe=$(scan "$flags" "$pat" "$TMP/specimen")
    case "$probe" in
      ''|0|ERR*)
        say "$label" "INERT: specimen $i of $# unmatched (${probe:-nothing}) FAIL"
        fail=1
        return ;;
    esac
  done
  n=$(scan "$flags" "$pat" "${ALL[@]}")
  case "$n" in
    0)    say "$label" "ok ($# specimens hit)" ;;
    ERR*) say "$label" "grep FAILED ($n), which is not zero hits"; fail=1 ;;
    *)    say "$label" "$n FAIL"; fail=1 ;;
  esac
}

# Scope. Not "more than zero files" but a floor, because a pathspec change that reduced the scan to
# a single file would otherwise still print ok for every gate below.
if [ "${#ALL[@]}" -lt "$FILE_FLOOR" ]; then
  printf 'battery: %s tracked files to scan, under the floor of %s - the scan has collapsed\n' \
    "${#ALL[@]}" "$FILE_FLOOR" >&2
  exit 1
fi
# The counting machinery itself - a mis-summed awk field, a grep that will not run, a list of names
# that are not on disk. A pattern that MUST hit is the only thing that tells a clean tree apart
# from a battery that has quietly stopped reading one.
control=$(scan -I "retinue" "${ALL[@]}")
case "$control" in
  ''|0|ERR*)
    printf 'battery: the positive control returned %s, so the greps are not reading the tree\n' \
      "${control:-nothing}" >&2
    exit 1 ;;
esac
say "scanning" "${#ALL[@]} tracked files, floor $FILE_FLOOR (control: $control hits)"

# What this run did NOT read, said out loud rather than left to be discovered. Every gate below
# scans `git ls-files`, so an UNTRACKED file is invisible to all of them while each still prints
# ok - measured during Task 12 by dropping an untracked file holding a stale model id into the tree
# and watching this script exit 0. Scanning what ships is the right scope and is not what changes
# here; the silence was the defect. It is the same shape as the token pass below, which says it did
# NOT run rather than skipping quietly.
#
# REPORTED, NEVER FAILED. A work in progress is not a violation, and a gate that reddens on
# ordinary work gets disabled, which costs more than this line is worth.
#
# `--others --exclude-standard` rather than a porcelain status: a status also lists MODIFIED tracked
# files, and those ARE scanned, so counting them would report as unread a file that was read.
# Ignored files stay out for the same reason they are ignored, `tools/banned_tokens.txt` among them.
# The exit status is checked rather than folded into a count, for the reason `scan` gives above: a
# git invocation that died would otherwise print the same "0 unscanned" as a clean tree.
if git ls-files --others --exclude-standard -z > "$TMP/untracked"; then
  # THE COUNTER'S OWN CONTROL, and it is here for the reason every gate above carries one. This
  # line reports rather than gates, so nothing else makes it prove itself, and that leaves it the
  # one output in this file whose zero would rest on nothing: a `tr` build that stopped matching
  # the NUL, or a `git ls-files -z` that stopped emitting it, prints "0 untracked files" forever
  # and reads exactly like a clean tree. Two delimiters go in and two must come out.
  printf 'a\0b\0' > "$TMP/untracked_probe"
  probe=$(tr -cd '\0' < "$TMP/untracked_probe" | wc -c | tr -d ' ')
  # NUL-delimited and counted by delimiter, so a filename holding a newline counts once rather than
  # twice. A command substitution would eat the NUL bytes, which is why this goes through a file.
  n_untracked=$(tr -cd '\0' < "$TMP/untracked" | wc -c | tr -d ' ')
  if [ "$probe" != 2 ]; then
    say "unscanned" "the delimiter counter returned ${probe:-nothing} where 2 went in FAIL"
    fail=1
  elif [ "$n_untracked" -eq 0 ]; then
    say "unscanned" "0 untracked files, so every non-ignored file in the tree was scanned"
  else
    say "unscanned" "$n_untracked untracked non-ignored file(s), read by no gate below:"
    tr '\0' '\n' < "$TMP/untracked" | sed 's/^/    /'
  fi
else
  say "unscanned" "git could not list untracked files, so the scope is unknown FAIL"
  fail=1
fi

# -I skips files grep judges binary. It is belt-and-braces here, since the only binary artifact in
# the tree is the vendored wheel and the pathspec above already excludes it. It is still a
# SILENCING flag, so it is named rather than left to be discovered: if a binary file is ever
# tracked, these gates skip it and say nothing.
EMD=$(printf '\342\200\224')   # octal, so the byte sequence itself appears in no tracked file
gate "em dashes" -I "$EMD" "an em dash $EMD here"
# Policy, settled now rather than under pressure: this gate covers the captured fixtures too, so a
# future capture whose model output carries an em dash would put a WRITING rule over CAPTURED
# EVIDENCE. Neither quiet answer is available then. The fixture is not edited, because a capture is
# evidence and editing one to satisfy a style rule is the thing fixtures/ exists to prevent; and
# the gate is not widened to all of fixtures/, which would retire it over exactly the files most
# likely to carry text nobody here wrote. The answer is a narrow exemption for that one path, named
# in the commit that adds it and citing the capture. Until such a capture exists, none exists.

# Word-bounded, because a substring check is WRONG here: "provenance" contains one of the two
# adjectives, and vendor/PROVENANCE.md records where the vendored wheel came from. Correct English
# is never renamed to satisfy a check that should not have fired. ${t^} builds the capitalised
# specimen from the same variable, so neither spelling is ever typed into this file.
for t in prov{able,en}; do gate "adjective $t" -Iwi "$t" "a $t claim" "${t^} again"; done

KW="result""_type="
gate "removed 2.x result kwarg" -I "$KW" "Agent(${KW}Brief)"

# Three specimens for three branches, each concatenated rather than spelled, so no stale id appears
# in this file even as an example.
STALE="claude-[23]|gpt-""4"
gate "stale model ids" -IE "$STALE" "model: claude-""2" "model: claude-""3" "model: gpt-""4"

# Client and organisation tokens. The list lives OUTSIDE this repository (untracked, ignored by
# name in .gitignore): a tracked list would ship into the reviewer's clone the very tokens it
# exists to keep out. So the pass is optional by design, it SAYS when it did not run rather than
# reporting an "ok" it never earned, and a hit prints [redacted] rather than the token itself.
# The cost of that design, stated where it is decided: an untracked list can never reach CI, so
# this is the one gate here with no standing enforcement outside the author's own machine.
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
    # expressions - write a metacharacter escaped - and the status check in `scan` above is what
    # makes the next crash of that family a red gate instead of a clean pass.
    #
    # One specimen, and it is the entry itself, so this gate's self-test is a grep-health check
    # rather than a branch check. That is the honest description and not an oversight: the pattern
    # IS the literal being hunted, so it has one branch and no separate trigger text to construct.
    gate "token [redacted]" -Ii "$tok" "$tok"
  done < "$TOKENS"
  # A list the author created and left holding nothing but comments is a mistake, not a policy.
  if [ "$entries" -eq 0 ]; then
    say "token list" "present but holds no entries FAIL"; fail=1
  else
    say "token list" "$entries entries checked"
  fi
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

# The suite gate, with a floor on what PASSED. Exit status alone is not enough: pytest exits 0 for
# a run in which every test skipped, so this gate would go green over a suite that asserted
# nothing - the vacuity this whole script exists to hunt, sitting in its own last gate. The floor
# is parsed from pytest's own summary line, which is also why no second -q is passed: pyproject's
# addopts already carries one, and -qq deletes the very line this reads.
"$PY" -m pytest 2>&1 | tee "$TMP/pytest.out"
[ "${PIPESTATUS[0]}" -eq 0 ] || fail=1
passed=$(grep -oE '[0-9]+ passed' "$TMP/pytest.out" | tail -1 | grep -oE '^[0-9]+')
if [ -z "$passed" ]; then
  say "suite floor" "no pass count in pytest's own summary FAIL"; fail=1
elif [ "$passed" -lt "$PASS_FLOOR" ]; then
  say "suite floor" "$passed passed, under the floor of $PASS_FLOOR FAIL"; fail=1
else
  say "suite floor" "$passed passed (floor $PASS_FLOOR)"
fi
exit $fail
