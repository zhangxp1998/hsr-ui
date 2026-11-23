---
name: hsr-ui
description: Recognize supported Star Rail pages from JPEGs and use observation-bound semantic clicks and scrolling on a configured Android tablet.
---

# Star Rail visual UI

Use the installed `hsr_ui` tool, or the `hsr-ui` launcher beside this file with one
JSON request on stdin. Read [README.md](README.md) for local asset/device setup.

- `status`: service health only. No capture, unlock, launch or device input.
- `analyze`: absolute saved JPEG; replay refs can never act on a device.
- `observe`: capture an already-unlocked foreground game on the configured device.
- `click` / `scroll`: latest live observationId/ref from the same owner. Check
  actions, effect, selected/enabled/checked and task authorization first. Scroll
  requires a node advertising that action; no raw coordinate input is accepted.
- `dryRun:true`: fresh-frame validation without input. Stale/unknown/changed
  targets require a new observation, never an unchecked retry.
- `release`: stop video and invalidate live refs when the owning task finishes.

Default `format:"agent"` returns page, refs, contextual node names, effects and
decision state. `format:"full"` adds the full coordinate tree and diagnostics;
`detail:"content"` adds read-only text independently of format. Web keeps full geometry.
This is a partial visual inference tree, not native accessibility.

Unknown state is null, not zero or false. Read current/reserved power, selected
count, cost, refill and weekly allowance from the same observation. Planning uses
ordinary power only and never grants refill/claim/challenge permission.
`challenge_without_weekly_rewards` is distinct from an awarded challenge.
Material names/counts come from the observed tooltip, not a dungeon lookup table.
Clipped row names require scrolling before selection. See [workflow](docs/workflow.md).

Inspect settling results before the next action. Unknown animation frames do not
prove success or failure. If necessary, inspect a fresh JPEG; only JPEG screenshots
may persist. Do not repeat an input whose delivery is uncertain.

Live tasks must preserve any already-running game, save/restore brightness, and
lock/verify the device after releasing their stream. Do not take over another
owner's brightness session. No PIN or credential is shipped with this skill.

## Original-only template contract

All current templates must be rebuilt from the game resource recipe; see
`docs/assets.md`. Never create, accept or restore a screenshot-crop template.
Missing original assets fail closed. Retain live screenshots for observation,
OCR and observation-bound pre-click checks; those are not template sources.
