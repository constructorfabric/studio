---
cf: true
type: requirement
name: Map Config-Assist Reference
version: 1.0
purpose: Reference data for cf-map config-assist — category candidate selection, name normalization, color palettes, and uncategorized-bucket semantics
---

# Map Config-Assist Reference

Reference data loaded by the `cf-map` skill's `MapConfigAssist` unit when generating or
refining `./md-map.toml`. This is reference content, not a runtime instruction sequence.

## Candidate Selection

From the JSON map payload (`./md-map.json`, or the `./md-map.html.js` sidecar with the
leading `window.MAP_DATA = ` and trailing `;` stripped):

1. Collect candidate nodes where `category_origin == "parent-dir"`.
2. Group candidates by their top-2 path segments (e.g. `src/studio`, `docs/architecture`).
   For each group capture: `prefix`, `node_count`, and 3 sample `rel_paths`.
3. Filter groups: keep only those with `node_count >= 5`.
4. Sort by `node_count` descending; take the top 10.
5. Propose one `[[categories]]` entry per surviving group:
   - `name` = derived name (see normalization below)
   - `paths` = `[<group_prefix> + "/**"]`
   - `style.color` / `style.background` = picked from the chosen palette, in order.

## Category-Name Normalization

Derive each category name deterministically from the group's path prefix:

- Lowercase the entire prefix.
- Replace `/`, `.`, and `_` with `-`.
- Strip leading `-` characters.
- Collapse consecutive `-` into a single `-`.
- Strip trailing `-`.

On collision (two prefixes normalize to the same name), suffix duplicates with `-2`, `-3`, …
in order of appearance.

| Prefix | Derived Name |
|---|---|
| `skills/studio` | `skills-studio` |
| `.bootstrap/config` | `bootstrap-config` |
| `.claude/agents` | `claude-agents` |
| `architecture/ADR` | `architecture-adr` |
| `examples/overwork_alert` | `examples-overwork-alert` |

## Color Palettes

Each palette lists 10 colors as `fill / background` pairs, applied to categories in order.

### `fixed-tailwind-500` (Tailwind-500 series; contrast-safe on light AND dark backgrounds)

```text
#ef4444 / #fee2e2   (red-500    / red-50)
#f97316 / #ffedd5   (orange-500 / orange-50)
#f59e0b / #fffbeb   (amber-500  / amber-50)
#eab308 / #fefce8   (yellow-500 / yellow-50)
#84cc16 / #f7fee7   (lime-500   / lime-50)
#22c55e / #f0fdf4   (green-500  / green-50)
#14b8a6 / #f0fdfa   (teal-500   / teal-50)
#06b6d4 / #ecfeff   (cyan-500   / cyan-50)
#3b82f6 / #eff6ff   (blue-500   / blue-50)
#6366f1 / #eef2ff   (indigo-500 / indigo-50)
```

### `theme-light` (Tailwind-300 series; muted mid-tone fills with -50 backgrounds)

```text
#fca5a5 / #fee2e2   (red-300    / red-50)
#fdba74 / #ffedd5   (orange-300 / orange-50)
#fcd34d / #fffbeb   (amber-300  / amber-50)
#fde047 / #fefce8   (yellow-300 / yellow-50)
#bef264 / #f7fee7   (lime-300   / lime-50)
#86efac / #f0fdf4   (green-300  / green-50)
#5eead4 / #f0fdfa   (teal-300   / teal-50)
#67e8f9 / #ecfeff   (cyan-300   / cyan-50)
#93c5fd / #eff6ff   (blue-300   / blue-50)
#a5b4fc / #eef2ff   (indigo-300 / indigo-50)
```

### `theme-dark` (Tailwind-700 series; deep fills with -950 backgrounds)

```text
#b91c1c / #450a0a   (red-700    / red-950)
#c2410c / #431407   (orange-700 / orange-950)
#b45309 / #451a03   (amber-700  / amber-950)
#a16207 / #422006   (yellow-700 / yellow-950)
#4d7c0f / #1a2e05   (lime-700   / lime-950)
#15803d / #052e16   (green-700  / green-950)
#0f766e / #042f2e   (teal-700   / teal-950)
#0e7490 / #083344   (cyan-700   / cyan-950)
#1d4ed8 / #172554   (blue-700   / blue-950)
#4338ca / #1e1b4b   (indigo-700 / indigo-950)
```

### `theme-pastel` (Tailwind-100 series; very soft fills with near-white backgrounds)

```text
#fee2e2 / #fff5f5   (red-100    / red-50 near-white)
#ffedd5 / #fff8f0   (orange-100 / orange-50 near-white)
#fef3c7 / #fffdf0   (amber-100  / amber-50 near-white)
#fef9c3 / #fffeeb   (yellow-100 / yellow-50 near-white)
#ecfccb / #f9ffe8   (lime-100   / lime-50 near-white)
#dcfce7 / #f0fdf4   (green-100  / green-50)
#ccfbf1 / #f0fdfa   (teal-100   / teal-50)
#cffafe / #ecfeff   (cyan-100   / cyan-50)
#dbeafe / #eff6ff   (blue-100   / blue-50)
#e0e7ff / #eef2ff   (indigo-100 / indigo-50)
```

### `theme-neon` (fluorescent/saturated fills on near-black backgrounds)

```text
#ff073a / #1a0005   (neon red    / near-black)
#ff6d00 / #1a0d00   (neon orange / near-black)
#ffe600 / #1a1800   (neon yellow / near-black)
#39ff14 / #021a00   (neon green  / near-black)
#00ffcc / #001a16   (neon teal   / near-black)
#00e5ff / #001a1f   (neon cyan   / near-black)
#1b9aff / #00101a   (neon blue   / near-black)
#b400ff / #0d001a   (neon purple / near-black)
#ff00c8 / #1a0016   (neon pink   / near-black)
#ffffff / #0d0d0d   (white       / near-black neutral anchor)
```

## Uncategorized Bucket

Top-level `show_uncategorized` controls nodes that match no `[[categories]]` path:

- `show_uncategorized = false` — hide unmatched nodes.
- `show_uncategorized = true` — show them as a single `_uncategorized` bucket.
