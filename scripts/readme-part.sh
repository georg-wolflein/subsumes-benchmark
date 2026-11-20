#!/usr/bin/env bash
# Puts a Markdown file into README.md as one of the parts that are written from data.
#
#   scripts/readme-part.sh <part> <file>
#   <command> | scripts/readme-part.sh <part>
#
# A part lies between the two lines `<!-- <part>:start -->` and `<!-- <part>:end -->`. What is
# between them is replaced by the file, or by the standard input where no file is named, with
# an empty line on either side. The rest of the README stays as it is. The script fails, and
# changes nothing, when there is nothing to put there or when the README does not have each of
# the two lines exactly once.
set -euo pipefail

part="$1"
file="${2:--}"
readme=README.md
start="<!-- $part:start -->"
end="<!-- $part:end -->"

block="$(mktemp)"
page="$(mktemp)"
trap 'rm -f "$block" "$page"' EXIT

cat -- "$file" > "$block"
if ! test -s "$block"; then
  echo "there is nothing to put into the part $part" >&2
  exit 1
fi
for marker in "$start" "$end"; do
  if test "$(grep -cxF -- "$marker" "$readme")" != 1; then
    echo "$readme does not have the line '$marker' exactly once" >&2
    exit 1
  fi
done

awk -v start="$start" -v end="$end" '
  FNR == NR { block = block $0 "\n"; next }
  $0 == start { print; printf "\n%s\n", block; inside = 1; next }
  $0 == end { inside = 0 }
  !inside
' "$block" "$readme" > "$page"
# Written into the file, so that it keeps its mode.
cat "$page" > "$readme"
