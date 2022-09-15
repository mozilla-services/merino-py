#!/usr/bin/env bash
set -eu

# Remove any previous built docs
mdbook clean

# Build book-docs
mdbook build
