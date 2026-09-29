#!/usr/bin/env bash
# piv-next — which epic ticket is unblocked, and which loose tickets should fold into one.
# Read-only: gh + jq only, no writes. See SKILL.md.
set -euo pipefail

epics=$(gh issue list --state open --label epic --json number --jq '.[].number')
[ -z "$epics" ] && { echo "no open epic"; exit 0; }

# state of every issue referenced anywhere, fetched once
all=$(gh issue list --state all --limit 500 --json number,state,title,body,labels)

state_of() { jq -r --argjson n "$1" '.[] | select(.number==$n) | .state' <<<"$all"; }
title_of() { jq -r --argjson n "$1" '.[] | select(.number==$n) | .title[:80]' <<<"$all"; }

in_epic=" "
next=""
for e in $epics; do
  echo "== epic #$e — $(title_of "$e")"
  body=$(jq -r --argjson n "$e" '.[] | select(.number==$n) | .body' <<<"$all")
  # task-list rows: "- [ ] #303 — … (depends on #301, #299 · …)"
  while IFS= read -r row; do
    n=$(grep -oE '#[0-9]+' <<<"$row" | head -1 | tr -d '#')
    [ -z "$n" ] && continue
    in_epic="$in_epic$n "
    [ "$(state_of "$n")" = "OPEN" ] || continue
    deps=$(grep -oE 'depends on [^)·]*' <<<"$row" | grep -oE '#[0-9]+' | tr -d '#' || true)
    open_deps=""
    for d in $deps; do [ "$(state_of "$d")" = "OPEN" ] && open_deps="$open_deps #$d"; done
    if [ -z "$open_deps" ]; then echo "  UNBLOCKED  #$n  $(title_of "$n")"; next="${next:-#$n}"
    else echo "  blocked    #$n  waits on$open_deps"; fi
  done < <(grep -E '^\s*- \[ \] #[0-9]+' <<<"$body")
done

echo "== loose open tickets (no epic row) — fold target = the epic ticket their own body names"
jq -r '.[] | select(.state=="OPEN") | "\(.number)\t\(.title[:70])\t\([.body | scan("#([0-9]+)")] | flatten | unique | join(","))"' <<<"$all" \
| while IFS=$'\t' read -r n t refs; do
    case "$in_epic" in *" $n "*) continue;; esac
    jq -e --argjson n "$n" '.[] | select(.number==$n) | .labels // [] | any(.name=="epic")' <<<"$all" >/dev/null 2>&1 && continue
    fold=""
    for r in ${refs//,/ }; do case "$in_epic" in *" $r "*) [ "$(state_of "$r")" = "OPEN" ] && fold="$fold #$r";; esac; done
    echo "  #$n  $t  → fold into:${fold:- (none named)}"
  done

echo "== next: ${next:-nothing unblocked} (first UNBLOCKED row, oldest open epic first)"
