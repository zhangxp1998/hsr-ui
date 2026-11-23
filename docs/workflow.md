# Semantic-only daily navigation

This is an integration policy, not a scheduler, device sandbox, or grant to spend
resources. Configure account checks, checkpoints and resource budgets separately.

## Execution boundary

All game UI observations and actions use `hsr_ui` observe/click/scroll. The same
JSON-service CLI is an allowed transport replacement for an unavailable native
plugin; it does not permit screenshot or coordinate fallback. Keep one owner and
use only that owner's latest live observationId/ref. Offline analyze is for
recognizer development, never for live input authorization.

The daily agent must not inspect current/reference images, invoke separate OCR,
use mapped taps/raw swipes, or switch to another GUI tool when semantics fail.
Remove unnecessary GUI/image tools from the scheduled task's allowlist. A shell
needed for device lifecycle is not a security sandbox: the execution policy still
forbids bypassing the semantic service through that shell. Audit actual calls,
not just the configured allowlist.

The service still captures JPEGs internally, performs local OCR/original-Sprite
matching and validates fresh pixels before input. Internal video-to-ADB capture
fallback is allowed and is not an agent image-reading fallback. Only JPEG capture
files persist. Device identity, authorized unlock, foreground/lock checks,
brightness save/restore, launch and owned-process cleanup remain separate device
lifecycle operations; these must not turn into game-coordinate input.

## Ordered evidence

1. Verify the configured device and save brightness before authorized unlock.
   Bring the game forward and observe it. `login.entry` exposes a corroborated
   `点击进入`; `login.title` exposes `开始游戏` plus an observed server. Match a
   visible server to the configured one before starting; neither page proves UID.
   Verify the configured full `state.uid` on a live field or recognized
   `supply.monthly` overlay before claims/spending. The initial monthly overlay
   retains a visible UID: verify it before claiming, not after dismissing it.
   A resumed field/overlay with that exact UID can bind the configured account without
   forcing logout. Unknown/mismatched identity stops the affected run; prior-run
   identity is not current evidence. UID changes/disappearance before input refuse.
2. Select a unique contextual node and inspect its effect and state. Send one
   guarded action, inspect settling and its returned observation. References do
   not authorize claims, purchases or challenges. Do not replay uncertain input.
3. For ordinary transitions, re-observe at most three times after approximately
   2, 5 and 10 seconds. Loading/teleport may wait up to 180 seconds with 10-second
   observations. Persistent missing state or validation failure stops that step;
   record phase, page, observationId, missing evidence and actual completed work.
4. After a confirmed challenge start, observe approximately every 20 seconds up
   to a 20-minute batch deadline. A control-free cinematic may remain unknown.
   Active-battle state and wave counters do not prove completion. Enable auto
   only from positively verified OFF and an observed enable action; null is not
   OFF. Already ON needs no click. The current battle profile verifies only ON;
   white/gray/OFF/disabled visuals remain null with no toggle. It cannot yet enable
   auto from an unverified OFF state. Never infer success/failure from an animation.
5. For weekly materials, traverse semantic scroll nodes and fully visible dungeon
   names. Open each first-material candidate, require `item.material`, read
   `name/owned_count/stock_verified`, close and continue across all rows including
   locked entries. Unknown stock is not zero. Early unlock has a distinct effect;
   authorization to skip story does not permit unsupported coordinate clicks.
6. Preparation state distinguishes ordinary/reserved power, selected count,
   visible maximum, displayed cost, refill state and weekly rewards remaining.
   The tool's planner uses ordinary power only. Apply the user's actual budget
   and durable checkpoints; selected count is not completion count. Missing
   balances/cost/refill/allowance stop spending. Zero weekly allowance means no
   awarded weekly challenge. Never infer fuel/premium-currency authorization.
7. `battle.result` requires success plus exit evidence. Verify the actual result
   count, or the authorized weekly before/after allowance difference; unknown is
   not a completed batch. Exit rather than blindly replaying a challenge. Retain
   an unresolved checkpoint on interruption, failure or ambiguous input/result.
8. Distinguish commission rewards from redispatch/change options, training cards
   from already-claimed milestones, and Honor task XP from level rewards and
   purchases. Observe after every claim because cards can reorder. A monthly
   reward card is dismiss, not another claim. Follow only reachable semantic
   routes to independent rewards after a blocked step.
9. A blue map marker is only a candidate. Require `space_anchor` after selection
   before healing teleport. Require four visible, full HP bars on a live field;
   missing bars remain unknown. Complete current structured evidence needs no
   duplicate image read.
10. Release the owning stream, preserve any pre-existing game process, lock and
    verify the device, and restore the saved brightness. Do not interrupt another
    owner. Report completed, pre-existing/skipped and blocked steps separately.

## Acceptance

Zero fallback and full daily completion are separate assertions. A safe stop can
satisfy the first while failing the second. A complete scheduled occurrence must
be audited using executed leaf calls, excluding mirrored wrappers and internal
service captures. Require zero agent image reads, external OCR bypasses, mapped
coordinate taps, raw game swipes and other GUI fallbacks. Count semantic scrolls
separately. Missing history prevents whole-run certification. Do not spend extra
resources or rerun a completed day merely to validate a policy change.

Unknown dialogs and story variants remain unsupported. This policy forbids a
fallback; it does not claim full-game recognition coverage or establish that a
future unattended daily has already succeeded.
