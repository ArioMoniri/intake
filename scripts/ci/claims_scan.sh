#!/usr/bin/env bash
# INT-019 — accuracy-claims scan (invariant 20; ADR-022).
#
# Invariant 20, verbatim: "No sensitivity, specificity, AUROC, WER or accuracy
# figure appears in docs/regulatory/, docs/legal/, patient or clinician copy,
# marketing or a store listing." Measurements live in docs/evidence/ with a
# date and a named corpus — that tree is deliberately NOT scanned.
#
# TWO TIERS, because the same word means different things in the two places:
#
#   strict (default; --strict) — docs/regulatory, docs/legal, store listings.
#     These trees are small, curated, and are where claims actually get MADE.
#     An English performance term is a violation on sight, figure or not:
#     "high sensitivity" is a property claim about the product, which the
#     invariant's last sentence forbids just as firmly as a number does.
#
#   copy (--copy) — patient- and clinician-facing catalogues (i18n/locales).
#     Here the same vocabulary is legitimate CLINICAL vocabulary: the intake
#     flow has to be able to ask about photophobia, and its option label is
#     "Sensitivity to light" / "Işığa hassasiyet". Scanning those trees at
#     strict tier would fail on symptom names, so a claim here is a term
#     ADJACENT TO A FIGURE — the invariant's own noun. Terms that have no
#     innocent reading at all (AUROC, AUC, F1-score) still fail bare.
#
# The Turkish vocabulary is figure-adjacent in BOTH tiers: bare "doğruluk"
# ("bilgilerin doğruluğu") and bare "duyarlılık" ("kültürel duyarlılık",
# "veri duyarlılığı") are ordinary Turkish legal prose, not claims. Turkish is
# the product's first language, so duyarlılık/özgüllük/kesinlik/isabet are the
# words a Turkish regulatory file would really use — English-only patterns
# left invariant 20 unenforced for exactly the copy that matters most.
# Consonant softening (k -> ğ: duyarlılık -> duyarlılığı) is matched explicitly;
# multibyte characters are alternated, never put in a bracket expression, so
# the ERE behaves the same under BSD grep (macOS) and GNU grep (CI).
#
# No-args: scan every tree that exists today at its own tier (an absent tree is
# reported, never an error). With args: scan exactly those paths, strict tier
# unless --copy precedes them (used by the gate's own tests).
# Portable to macOS bash 3.2.
set -euo pipefail
cd "$(dirname "$0")/../.."

# Always a performance claim — no non-performance reading in any tree.
ALWAYS_PAT='auroc|(^|[^a-zA-Z])auc([^a-zA-Z]|$)|f1[ _-]?score'

# Performance vocabulary. Bare at strict tier; figure-adjacent at copy tier.
TERM_EN='sensitivit|specificit|accurac|(^|[^a-zA-Z])wer([^a-zA-Z]|$)'

# Turkish performance vocabulary — figure-adjacent in both tiers (see above).
TERM_TR='([Dd]oğrulu(k|ğ)|[Dd]uyarlıl(ı|i)(k|ğ)|(Ö|ö)zgüllü(k|ğ)|[Kk]esinli(k|ğ)|(İ|i)sabet)'

# A figure: a percentage (either order), "yüzde N", or a decimal.
FIG='(%[ ]*[0-9]|[0-9][ ]*%|yüzde[ ]*[0-9]|[0-9]+[.,][0-9]+)'

# Proximity window for term/figure adjacency, in the same line.
NEAR='.{0,40}'

TR_CLAIM="${TERM_TR}${NEAR}${FIG}|${FIG}${NEAR}${TERM_TR}"
EN_NEAR_CLAIM="(${TERM_EN})${NEAR}${FIG}|${FIG}${NEAR}(${TERM_EN})"

STRICT_TREES="docs/regulatory docs/legal"
STRICT_GLOBS="apps/*/store apps/*/store-listing apps/*/fastlane/metadata"
COPY_GLOBS="apps/*/src/locales apps/*/src/lib/i18n"

# scan_paths <tier> <path>...  — emits "file:line:content" for each violation.
scan_paths() {
  tier="$1"
  shift
  for f in "$@"; do
    [[ -f "$f" ]] || continue
    grep -inHE "$ALWAYS_PAT" -- "$f" 2>/dev/null || true
    if [[ "$tier" == "strict" ]]; then
      grep -inHE "$TERM_EN" -- "$f" 2>/dev/null || true
    else
      grep -inHE "$EN_NEAR_CLAIM" -- "$f" 2>/dev/null || true
    fi
    grep -nHE "$TR_CLAIM" -- "$f" 2>/dev/null || true
  done
}

# tracked_in <tree>... — git-tracked files under trees that exist.
tracked_in() {
  for tree in "$@"; do
    if [[ -d "$tree" ]]; then
      git ls-files -- "$tree"
    else
      echo "note: $tree absent — gate armed, nothing to scan yet" >&2
    fi
  done
}

tier="strict"
case "${1:-}" in
  --copy)
    tier="copy"
    shift
    ;;
  --strict)
    shift
    ;;
esac

if [[ $# -gt 0 ]]; then
  violations=$(scan_paths "$tier" "$@")
else
  # shellcheck disable=SC2086  # globs and tree lists are intentionally split
  strict_files=$(tracked_in $STRICT_TREES $STRICT_GLOBS)
  # shellcheck disable=SC2086
  copy_files=$(tracked_in $COPY_GLOBS)
  violations=""
  if [[ -n "$strict_files" ]]; then
    # shellcheck disable=SC2086
    violations="$(scan_paths strict $strict_files)"
  fi
  if [[ -n "$copy_files" ]]; then
    # shellcheck disable=SC2086
    copy_hits="$(scan_paths copy $copy_files)"
    if [[ -n "$copy_hits" ]]; then
      violations="${violations:+$violations
}$copy_hits"
    fi
  fi
fi

if [[ -n "$violations" ]]; then
  echo "FAIL: performance-claim language found (invariant 20 — no accuracy claims;"
  echo "measurements belong in docs/evidence/ with a date and a named corpus):"
  printf '%s\n' "$violations"
  exit 1
fi

echo "OK: no performance-claim patterns in scanned trees"
