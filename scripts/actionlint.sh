#!/usr/bin/env bash

set -euo pipefail

ACTIONLINT_VERSION="1.7.12"

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace_root="$(cd -- "$script_dir/.." && pwd)"

case "$(uname -s)-$(uname -m)" in
  Darwin-arm64)
    asset="darwin_arm64"
    expected_sha256="aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f"
    ;;
  Darwin-x86_64)
    asset="darwin_amd64"
    expected_sha256="5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644"
    ;;
  Linux-aarch64 | Linux-arm64)
    asset="linux_arm64"
    expected_sha256="325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6"
    ;;
  Linux-x86_64)
    asset="linux_amd64"
    expected_sha256="8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
    ;;
  *)
    echo "Unsupported platform: $(uname -s) $(uname -m)" >&2
    exit 1
    ;;
esac

actionlint_dir="$workspace_root/.cache/actionlint/$ACTIONLINT_VERSION/$asset"
actionlint_bin="$actionlint_dir/actionlint"

if [[ ! -x "$actionlint_bin" ]]; then
  mkdir -p "$actionlint_dir"
  archive="$actionlint_dir/actionlint.tar.gz"
  download_url="https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_${asset}.tar.gz"

  echo "Downloading actionlint $ACTIONLINT_VERSION for $asset..."
  curl --fail --location --silent --show-error "$download_url" --output "$archive"

  if command -v sha256sum >/dev/null 2>&1; then
    actual_sha256="$(sha256sum "$archive" | awk '{print $1}')"
  elif command -v shasum >/dev/null 2>&1; then
    actual_sha256="$(shasum -a 256 "$archive" | awk '{print $1}')"
  else
    echo "A SHA-256 checksum utility (sha256sum or shasum) is required." >&2
    exit 1
  fi

  if [[ "$actual_sha256" != "$expected_sha256" ]]; then
    echo "actionlint checksum verification failed." >&2
    exit 1
  fi

  tar -xzf "$archive" --directory "$actionlint_dir" actionlint
  rm "$archive"
fi

cd "$workspace_root"
exec "$actionlint_bin" -color "$@"
