#!/bin/sh
# Copy the inference and load-test slides into the full deck (prefix i/p).
# The overview slides (o*) live only here; deck/ has its own separate copy.
set -e
cd "$(dirname "$0")"
for f in ../deck-inference/slides/[0-9]*.html; do cp "$f" "slides/i$(basename "$f")"; done
for f in ../deck-performance/slides/[0-9]*.html; do cp "$f" "slides/p$(basename "$f")"; done
cp ../deck-inference/slides/style/eweb.css ../deck-inference/slides/style/eweb.js slides/style/
echo "synced $(ls slides/i*.html | wc -l) inference and $(ls slides/p*.html | wc -l) load-test slides"
