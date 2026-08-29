<!-- SPDX-License-Identifier: Apache-2.0 -->

# Licensing policy

`cscroll` is a close downstream of MIT-licensed `scroll` and `sway`. This
policy adds Apache-2.0 for original downstream work without erasing or
misrepresenting the license of inherited material.

## Inherited and pre-existing files

Code and documentation inherited from `scroll`, `sway`, wlroots, or another
third party retain their existing license, copyright notices, provenance, and
authorship. Existing files continue under the license identified by their SPDX
header or, when they have no header, by their recorded upstream provenance and
applicable license file. Never replace a third-party notice merely because the
file is modified downstream.

## Original downstream work

New standalone files independently authored for `cscroll` default to the
Apache License, Version 2.0 and should carry:

```text
SPDX-License-Identifier: Apache-2.0
```

The following current downstream files are Apache-2.0:

- `LICENSING.md`
- `UPSTREAM.md`
- `runtime-components.toml`
- `ipc-compat/meson.build`
- `ipc-compat/scroll-swayipc-compat`
- `ipc-compat/scroll-swayipc-compat.1.scd`
- `tests/test_swayipc_compat.py`

`scroll-swayipc-compat.1.scd` has no source-comment syntax; its entry in this
table is its license notice.

## Contributions to existing files

By intentionally submitting a contribution to this repository, the
contributor licenses any independently copyrightable original material in the
contribution under Apache-2.0. When the contribution modifies a file under MIT
or another compatible existing license, the contributor dual-licenses that
material as `Apache-2.0 OR` the file's existing license. This keeps the combined
file distributable under its existing license, so its SPDX header stays
unchanged.

This is a license grant, not a transfer of copyright. A submission explicitly
marked `Not a Contribution` is excluded.

## Distribution

The compositor sources remain MIT-derived. Apache-licensed downstream files
remain Apache-2.0. A source or binary distribution containing both must retain
the applicable notices and include both [LICENSE](LICENSE) and
[LICENSE-APACHE](LICENSE-APACHE). Existing MIT permissions remain valid.
