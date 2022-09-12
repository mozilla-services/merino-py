#!/usr/bin/env bash
set -eu

# Remove any previous built docs
mdbook clean

# Build book-docs
mdbook build

# Add a redirect for the old location of the docs
# Merino crate's docs.
mkdir -p book/merino/merino
echo '<meta http-equiv="refresh" content="0; URL=../index.html" />' > book/merino/index.html
