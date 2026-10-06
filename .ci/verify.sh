#!/usr/bin/env bash
set -euo pipefail
export RUNNER_TEMP="${RUNNER_TEMP:-$(mktemp -d)}"

# Packaging stays in nixscroll. Override only the runtime source with
# this exact checkout so every cscroll change runs the real regressions.
nix build \
  github:julian-corbet/nixscroll-corbet-ch/6c1f986344d6034236e4b1674a41af0081711373#checks.x86_64-linux.runtime-lifetime \
  --override-input cscroll "git+file://$PWD" \
  --no-write-lock-file --no-link --print-build-logs

python3 -m unittest discover -s tests -p 'test_swayipc_compat.py' -v

python3 - <<'PY'
import pathlib
import tomllib

root = pathlib.Path.cwd()
manifest = tomllib.loads((root / "runtime-components.toml").read_text())
assert manifest["schema"] == 1
components = manifest["component"]
ids = [component["id"] for component in components]
assert len(ids) == len(set(ids))
assert set(ids) == {
    "wallpaper",
    "output-control",
    "capture-portal",
    "xwayland",
    "sway-ipc-compat",
}
assert all(component["required"] for component in components)
external = [c for c in components if c["kind"] != "bundled-command"]
assert all(c.get("arch-package") and c.get("nixpkgs-package") for c in external)
bundled = next(c for c in components if c["id"] == "sway-ipc-compat")
assert bundled["command"] == "scroll-swayipc-compat"
assert bundled["temporary"] is True
assert (root / "resources/scroll-portals.conf").is_file()
PY

test ! -e flake.nix
test ! -e flake.lock
! git ls-files | grep -E '(^|/)(nixscroll|home/richc)(/|$)'
test -x ipc-compat/scroll-swayipc-compat
test -f runtime-components.toml
