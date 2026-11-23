# Semantic-first daily navigation and iteration

The goal is a complete daily routine that no longer **needs** screenshot fallback
because semantic coverage is sufficient. It is not a ban on agent screenshots,
a restricted tool list, or permission to spend additional resources. Keep account,
checkpoint, spending and device-lifecycle rules separately configured.

## Prefer semantics; keep diagnostic capability

Use `hsr_ui` observe/click/scroll first on covered pages. The same JSON-service CLI
is an alternative transport if the native plugin is unavailable, not an image
fallback. Keep one owner and use its latest live observationId/ref. Saved-image
analyze is for development; replay refs can never authorize live input.

When a transition or missing state persists after bounded re-observation, the
agent may inspect a fresh JPEG, use auxiliary OCR and perform verified current-
frame mapped input to complete already-authorized work. Keep image/GUI tools
available. Use the capture/mapping helpers with the selected device and current
screenshot metadata; validate identity, freshness, orientation and geometry.
Do not reuse historical coordinates, replay uncertain inputs or weaken semantic
click guards. A rejected stale reference needs a fresh observation, not a blind
manual replay. A reference image may help interpretation but is not live evidence.

All persisted screenshots remain JPEG. Internal capture, OCR, original-Sprite
matching and fresh-pixel validation continue unchanged. **Screenshot-crop templates
remain prohibited**: private JPEGs may be observations and regression fixtures,
not reusable recognition assets. New templates come from the game-resource recipe.

## Iteration loop

1. Record each gap: phase, page/observationId, missing node/state, private current
   JPEG, fallback reason/action and verified outcome. Prefer existing complete
   semantics; distinguish necessary fallback from redundant image reading.
2. Add or repair the missing reader/node using original Sprites, layout and OCR.
   Add positive and meaningful negative cases (occlusion, ambiguous or wrong
   state), then run affected regressions. Do not fabricate enabled/count fields,
   remove negative cases or lower guards to make tests pass.
3. When feasible within the current run, finish that repair/test cycle, reload
   only the owned worker and re-observe to verify the live semantic route. Otherwise
   complete what is authorized and verifiable, retain an explicit repair item and
   continue iteration afterward. A repeated fallback is not the final solution.
4. After any mapped fallback, obtain a new semantic observation before using
   refs again. Keep diagnostic/replay tests distinct from actual task actions.
   Never rerun completed battles or spend extra power merely to prove coverage.

## Current evidence and task boundaries

- Confirm the configured device, save brightness and use the authorized unlock
  procedure. Restore brightness, release the owned stream and verify locking
  afterward; preserve a pre-existing game and do not interrupt another owner.
- Prefer `login.entry`/`login.title` and their observed server. Verify the full
  current `state.uid` on a live field or recognized `supply.monthly` before claims
  or spending. The monthly overlay retains its visible UID. If the reader misses
  identity, a fresh JPEG may supply evidence; prior-run identity never substitutes.
  Wrong or still-unverifiable identity stops the affected work. Server/UID changes
  before a semantic input reject its reference.
- Select unique contextual nodes and inspect effects, selected/enabled/checked
  state and authorization. One input, then inspect settling. For normal transitions,
  re-observe up to three times (roughly 2/5/10 seconds); loading may take up to
  180 seconds. Persistent coverage gaps may use the fallback/iteration loop.
- During a confirmed battle, observe about every 20 seconds up to a 20-minute
  batch deadline. `battle.active`, waves and animations are not completion.
  Auto ON needs no click. The current profile verifies only ON; OFF/white/gray/
  disabled remains null with no semantic toggle. A fresh JPEG may distinguish
  an available OFF state for verified fallback and a new regression case; null
  or absent gold alone never proves OFF.
- Traverse weekly rows including locked entries; verify full names, material
  stock and allowance using tooltips and semantic scrolls first. Unknown stock
  is not zero. Missing coverage, including authorized early-unlock/story flows,
  may use current-image fallback, not guessed or historical values.
- Read current/reserved power, selected count, displayed cost, refill state and
  weekly allowance from current evidence. The planner uses ordinary power only;
  apply the actual authorized budget and checkpoints. Selected count is not
  completed count, and zero weekly allowance is not a rewarded challenge.
  Inspect missing fields if needed, then stop spending if evidence is still
  uncertain. Fuel/premium currency/purchases need separate authorization.
- Prefer `battle.result` success and exit evidence. Missing result fields may be
  verified from a fresh image; weekly before/after allowance differences can
  establish count. Never infer completion, blindly repeat a batch or reset an
  unresolved checkpoint. Exit rather than replaying a challenge.
- Preserve commission choices, distinguish training claims from claimed milestones,
  and Honor task XP from level rewards/purchases. Re-observe card reordering.
  A confirmed monthly reward card is dismiss, not a second claim.
- Blue map markers are candidates, not proof of healing anchors. Verify the
  selected anchor and four visible full HP bars using structured state first,
  fresh-image evidence if missing. Do not duplicate complete semantic evidence.

## Acceptance

Audit actual executed leaf calls, not just configured intentions. Count native/CLI
semantic actions, necessary screenshot/mapped fallbacks, redundant image reads,
diagnostics and repaired/outstanding gaps separately. Internal service capture/OCR
and authorized device lifecycle are not agent fallback. Necessary fallback is
permitted iteration evidence, not automatically a policy violation.

A full occurrence that completes all required work without needing fallback is
the coverage goal. Disabling image tools or stopping early cannot establish it.
Report task completion, coverage and delivery separately; missing/truncated history
makes whole-run coverage unverified. Retain unknown states in the tool and improve
coverage through tests rather than pretending every page is already supported.
