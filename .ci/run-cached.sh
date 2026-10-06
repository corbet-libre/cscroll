#!/usr/bin/env bash
# Execute the manifest's selected checks with content-keyed result reuse.
# cscroll has no Rust/cargo gates: the runner provides nix and python3 only.
# There is no advisories check (no cargo-deny surface).
set -euo pipefail
: "${CCID_BIN:?Missing verified ccid job runtime}"
: "${CI_COMMIT_SHA:?Missing verified source revision}"
: "${CI_REPOSITORY_URL:?Missing canonical repository identity}"
: "${CHECKS:?Missing declared check selection}"
if [ "$CHECKS" != "verify" ]; then
  echo "CHECKS must be exactly 'verify', got: $CHECKS" >&2
  exit 2
fi
cache_root=${CI_CACHE_ROOT:-${CARGO_HOME:-}}
[[ $cache_root = /* ]] || { echo 'An absolute persistent CI_CACHE_ROOT or CARGO_HOME is required' >&2; exit 2; }
namespace=$(printf '%s' "$CI_REPOSITORY_URL" | sha256sum | cut -c1-24)
state="$cache_root/ccid-cached/$namespace"
toolchains=${CI_TOOLCHAIN_ROOT:-$cache_root/ccid-cached/toolchains}
[[ $toolchains = /* ]] || { echo 'CI_TOOLCHAIN_ROOT must be absolute' >&2; exit 2; }
mkdir -p "$state" "$toolchains"
exec 9>"$state/lock"
flock -w "${CI_TIMEOUT:-2700}" 9
mkdir -p "$state/moon-cache/hashes" "$state/moon-cache/outputs" "$state/moon-home"
mkdir -p .moon/cache
ln -s "$state/moon-cache/hashes" .moon/cache/hashes
ln -s "$state/moon-cache/outputs" .moon/cache/outputs
# Tool installation is an explicit part of this job, in persistent CI storage.
# `ccid cached` requires moon on PATH: provision moon+proto from the same Nix
# pin and assert the actual versions. nix builds the pinned nixscroll
# runtime-lifetime check; python3 runs the downstream contract and manifest
# validation.
tool_source=github:NixOS/nixpkgs/b7c2ada94fe99c15b0dbcf4d11fd7850b957a436
tool_paths=$(nix build --no-link --print-out-paths "$tool_source#moon" "$tool_source#proto" "$tool_source#python3")
for path in $tool_paths; do PATH="$path/bin:$PATH"; done
export PROTO_HOME="$toolchains/proto"
export MOON_HOME="$state/moon-home"
export PROTO_AUTO_CLEAN=false PROTO_TELEMETRY=false PROTO_YES=true
export PATH="$(dirname "$CCID_BIN"):$PROTO_HOME/shims:$PROTO_HOME/bin:$PATH"
export CCID_SOURCE_REVISION="$CI_COMMIT_SHA"
"$CCID_BIN" render --repo "$PWD" --check
nix --version
python3 --version
moon --version
proto --version
"$CCID_BIN" cached --repo "$PWD" --check verify
test -s ".ccid/results/verify.jsonl"
