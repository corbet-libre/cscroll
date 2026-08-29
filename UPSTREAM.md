<!-- SPDX-License-Identifier: Apache-2.0 -->

# Upstream relationship

`cscroll` preserves scroll's history and follows its `master` branch. The
configured `upstream` remote is:

```text
git@github.com:dawsers/scroll.git
```

The downstream started at scroll `1.12.21`, commit `f80c5820`. It was last
synchronized to upstream commit `66d0e9d0` (2026-08-28). The local downstream
branch is `main`; upstream keeps the name `master`.

## Downstream ledger

Keep this list short. A change belongs here only when it changes the compositor
runtime or packages a helper that is tightly coupled to its runtime protocol.

- `scroll-swayipc-compat`: temporary IPC proxy for strict Sway-schema clients.
  It changes only scroll's `horizontal` and `vertical` layout variants into the
  equivalent Sway schema names and recomputes IPC frame lengths. It can be
  deleted when every relevant client uses scroll's native schema.
- `runtime-components.toml`: canonical, platform-mapped manifest for the
  companions whose lifecycle is coupled to `scroll`.
- `scroll-portals.conf`: installed portal selection for the capture protocols
  implemented by the wlroots backend.

Nix modules, host values, desktop policy, bar or launcher code, and synthetic
workspace/favourites behaviour do not belong in this repository.

## Sync procedure

```sh
git fetch upstream --tags
git switch main
git merge --no-ff upstream/master
python3 -m unittest discover -s tests -p 'test_swayipc_compat.py' -v
```

Resolve conflicts in favour of the smallest downstream delta. Re-evaluate each
ledger entry after every merge and delete it once upstream or native clients
make it unnecessary. Full compositor builds and integration tests run on the
build host, never on the seated Elitebook.
