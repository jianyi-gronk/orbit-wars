# Engine provenance

The production ruleset `orbit-wars-2p-v1` is derived from the Orbit Wars
environment in Kaggle Environments and is intentionally pinned. Production
code imports only `orbit_engine`; it does not import `kaggle_environments`
or follow its `master` branch.

## Upstream identity

- Repository: `https://github.com/Kaggle/kaggle-environments.git`
- Requested revision at installation: `master`
- Resolved commit: `462efa26dd3d11018cde2b9e9ce9245b91cef471`
- Distribution metadata version: `1.30.1`
- License: Apache License 2.0; copied verbatim to `LICENSE`
- Upstream wheel contained no separate `NOTICE` file

## Audited source inputs

| Installed source                     | SHA-256                                                            |
| ------------------------------------ | ------------------------------------------------------------------ |
| `envs/orbit_wars/orbit_wars.py`      | `3f78c1a9064644a7789d9aa464aa83770071d42023716213d223887b8ca267f4` |
| `envs/orbit_wars/orbit_wars.json`    | `8d8a2b6c0b092f40ea5f4c381328788a402dfcbd7a1bd8ed5f1c3e1eb5f079d1` |
| `envs/orbit_wars/test_orbit_wars.py` | `f2a11c1ba87231009832f801d4d5bd5e8f199d1869a0378b1f24b7d1541ae8ca` |

## Extraction boundary

`orbit_engine/_pinned_kernel.py` retains the upstream constants, geometry,
map/comet generation, launch, production, movement, collision, combat,
termination, scoring, and helper logic. The following Kaggle-facing pieces
were removed:

- JSON specification loading
- text/HTML renderers
- bundled random and starter agents
- imports used only by those removed pieces

`orbit_engine/engine.py` supplies a small in-process runtime compatible with
the retained interpreter semantics. It fixes the player count at two, records
the resolved seed only on the trusted engine object, and exposes a seed
commitment plus canonical SHA-256 state hash in snapshots.

Any future behavior change must use a new `ruleset_id`; this ruleset is not
silently updated in place.
