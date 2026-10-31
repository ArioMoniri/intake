#!/bin/sh
# INT-599: the admin-web runtime image carries Next's standalone output, and Next
# copies into that output every package file its trace of the server reached. The
# builder has the build tooling installed (typescript, eslint, vitest and the rest of
# the workspace root's devDependencies), so a trace could reach one. This guard runs
# in the builder right after `next build` and fails the image build unless every
# package file in the trace sits in a pnpm store entry that admin-web's production
# dependency closure names.
#
#   sh admin_web_trace_guard.sh <production-paths> <standalone-dir>
#
# <production-paths> is what
#   pnpm --filter "@intake/admin-web..." list --prod --parseable --depth Infinity
# prints: one path per line. A package's store entry is its directory under
# node_modules/.pnpm. <standalone-dir> is apps/admin-web/.next/standalone.
#
# pnpm keeps package files only in store entries and links everywhere else, so a
# regular file under any other node_modules directory is refused too. Only store
# entry names and paths are printed, never a file's contents.
# tests/infra/test_admin_web_runtime_image.py drives it over fixture trees.
set -eu
# no pathname expansion: entry names and paths are split on whitespace only
set -f

if [ "$#" -ne 2 ]; then
  echo "usage: admin_web_trace_guard.sh <production-paths> <standalone-dir>" >&2
  exit 2
fi
paths=$1
standalone=$2
store=node_modules/.pnpm

if [ ! -f "$paths" ]; then
  echo "trace guard: no production list at $paths" >&2
  exit 1
fi
allowed=$(sed -n 's#^.*/node_modules/\.pnpm/\([^/][^/]*\)/node_modules/.*$#\1#p' "$paths" | sort -u)
if [ -z "$allowed" ]; then
  echo "trace guard: the production list is empty; refusing an empty allow-list" >&2
  exit 1
fi

cd "$standalone"
if [ ! -d "$store" ]; then
  echo "trace guard: the trace holds no pnpm store at $standalone/$store" >&2
  exit 1
fi

# store entries the production closure does not name, by exact name
traced=$(find "$store" -mindepth 1 -maxdepth 1 ! -name node_modules | sed 's#^.*/##' | sort)
if [ -z "$traced" ]; then
  echo "trace guard: the trace's store holds no package" >&2
  exit 1
fi
unknown=$(printf '%s\n' "$traced" | grep -vxF -e "$allowed" || true)
# package files outside every store entry: a hoisted or nested copy, or a file in
# the store's own node_modules directory, where pnpm keeps only links
outside=$(find . -type f -path '*/node_modules/*' ! -path "./$store/*")
hoisted=$(find "$store" -type f -path "$store/node_modules/*")

if [ -n "$unknown$outside$hoisted" ]; then
  echo "trace guard: the standalone trace carries packages outside admin-web's production closure" >&2
  for line in $unknown; do
    echo "  store entry: $line" >&2
  done
  for line in $outside $hoisted; do
    echo "  package file outside a store entry: $line" >&2
  done
  exit 1
fi
count=$(printf '%s\n' "$traced" | wc -l | tr -d ' ')
echo "trace guard: $count store entries, all in admin-web's production closure"
