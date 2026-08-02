# Agent guide — lego brick pipeline

## Success criteria (always)

Hollow work is green only when **all** hold:

1. **1 clutch section** (Studio detached-sections graph)
2. **0 AABB collisions** (face-touch stacks OK)
3. **Hollow** (shell + connectors, not solid fill)

### Soft report (not a PASS gate)

`demo_sphere` / `demo_suite` also print:

- **clutch strength** — `mean_overlap`, `weak_edges` (Studio clutch-power *intent*, not bit-exact)
- **balance / tip** — CoM vs ground footprint; auto-adds an under-plate base when tipping if possible
- **overhang** — pieces unreachable from ground via clutch (`overhang.check_overhangs`)
- **build order** — bottom-up placement via vertical stud support only (`build_order.check_build_order`); mid-air / side-cling pieces are soft FAIL
- **part-count bloat** — adjacent pairs replaceable by one catalog part (`bloat.check_bloat`); audits the packer's output rather than trusting it
- **interlocking / shear planes** — aligned vs staggered vertical joins and fragile straight columns (`interlock.check_interlock`)
- **release score** — all validators folded into one 0–100 audit (`scorecard.score_release`) with a prioritized issue list; each issue names a `suggested_action` for the future Phase 6 loop

Do **not** fail demos on soft metrics. Improving them is a separate session type.

### Scorecard contract (Phase 6 reads this)

- Hard gates (1 section, 0 collisions, hollow) cap the score at 35, below the 40-point floor of any hard-passing model — soft polish can never buy a READY verdict.
- A score of 100 means release-ready. Any component that can raise an issue must lose points when it does, or a score-optimising loop stalls on a flagged model that already looks perfect.
- `report.next_action` is the highest-impact fix to attempt next.
- `report.unmeasured` is the blind-spot list — currently **micro_stress** only. Do not claim unmeasured standards are audited.

## Locked baseline

- Demo: `python -m phase5.demo_sphere`
- Default diameter: **20** (`BASELINE_DIAMETER_STUDS` in `phase5/demo_sphere.py`)
- Exit code **0** only on 1 section / 0 collisions; otherwise exit **1**
- Do **not** raise the default diameter until that size stays PASS
- Scale experiments: `python -m phase5.trial_sphere_scale 24`

## Studio suite (sphere + bunny + teapot)

- `python -m phase5.demo_suite` — full hollow models only (no half-cuts)
- Exports: `sphere_full.io`, `bunny_full.io`, `teapot_full.io`
- Teapot is the topology stress case (thin handle + spout)
- Shared pipeline: `phase5/hollow_build.py`

## How to use agents on this repo

**One writer at a time.** Do not run multiple coding agents editing `phase5/plate_bridge.py` (or the same reconnect path) in parallel.

| Do | Don’t |
|----|--------|
| One implementation agent per named gap | Two agents both fixing connectivity |
| Optional read-only explore / review agent | Parallel “cut staples” + “fix clutch” |
| New chat when context is muddy | “Make the sphere better” mega-prompts |

### Session types (keep separate)

**A. Gap-fill** — one metric: restore or keep 1/0. Named gaps that block larger spheres:

- Incomplete section maps (`vsec`: shell + 1×1 only; multi-stud floaters missed)
- Same-layer floaters (need under/span plates that actually clutch)
- Strip vs reconnect fighting (bridges deleted → section spike)
- Air-column / spine-nuke thrash at low section counts

**B. Visual polish** — only on an already-PASS export. No reconnect reordering in the same session.

**B2. Clutch strength** — only on an already-PASS export. Prefer multi-stud plates/bond merges / hollow thicken; report `weak_edges` / `mean_overlap`. Never solid-fill the cavity to chase the metric.

**C. Scale** — bump 16 → 18 → 20 only after the current size stays green. Keep experiments off the locked default until PASS.

### Prompt shape

Good:

- “Diameter 16 must stay 1/0. Fix X. Re-run `python -m phase5.demo_sphere`.”
- “One gap only: exhaust returns [] with 5 sections — complete brick footprints in vsec.”

Bad:

- “Make it look good and fix connectivity later.”
- Mixing prettier shell + scale to 32 + staple budget in one run.

### Verify every change

End with:

```text
python -m phase5.demo_sphere
```

Report: sections, collisions, part count, staples, weak_edges/mean_overlap. Paste reconnect log lines when FAIL (`exhaust`, `mst stuck`, `spine-nuke`).

## Phase 6 (deterministic agent)

- Single-shape: `python -m phase6.demo_agent` (sphere smoke test)
- Full suite: `python -m phase6.demo_suite_agent` — sphere + bunny + teapot
- Loop: `phase6/loop.improve_release` — score → try issue actions → keep if score↑ and hard gates hold
- Actions: `support_blocked_pieces`, `add_balance_base`, `merge_bloat`, `stagger_seams`, `strengthen_clutch`
- LLM layer still locked — expand/fix actions before orchestration
- Exports: `output/phase6/{sphere,bunny,teapot}_agent.io`
