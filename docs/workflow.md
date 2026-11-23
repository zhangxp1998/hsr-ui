# Semantic-first daily navigation

This is an integration guide, not a scheduler or a grant to spend resources.
Configure scheduling, account checks and resource budgets separately.

1. Verify the configured device/account and foreground game. Save brightness,
   use minimum manual brightness, and unlock through your own authorized setup.
2. Use native `hsr_ui`, or the same-service CLI if unavailable. Native/plugin
   owner scopes differ from CLI owners; do not reuse refs across owners.
3. Observe first on supported pages. Choose a contextual node and inspect its
   effect; perform one guarded action, then inspect its settling and observation.
4. Re-observe transitions or missing state before inspecting a fresh JPEG.
   Never infer battle success from missing controls or an animation frame.
5. For weekly materials, use semantic scroll nodes and fully visible dungeon
   names. Open the first-material candidate, require `page:item.material`, read
   `name/owned_count/stock_verified`, close and continue across all rows.
   Unknown stock is not zero. Early unlock is the distinct `early_unlock` effect.
6. Preparation state distinguishes ordinary/reserved power, selected count,
   visible maximum, displayed cost, refill state and weekly rewards remaining.
   The planner excludes reserve/fuel/premium currency. Reconcile with the user's
   actual budget and durable checkpoints; selected count is not completion count.
   Zero weekly allowance means no awarded weekly challenge.
7. Training claims, Honor task experience, Honor level rewards and purchases
   are separate effects. A candidate ref does not authorize any of them.
8. `battle.result` requires the success label plus exit control; inspect the
   observed last-round count and result state. Generic item rewards have their
   own verified dismiss action. A monthly reward card is dismiss, not a new claim.
9. Confirmed four-member visual HP state is sufficient for the supported HUD;
   missing bars remain unknown. A blue map marker is not a verified healing anchor.
10. The owning task releases video, locks and verifies lock state, restores its
    saved brightness, and preserves a game process that was already running.
    Do not interrupt another active device owner. Record actual results and gaps.

Unsupported dialogs, story variants and control-free cinematics may still need
fresh-JPEG fallback. This does not claim full-game or full-battle zero-fallback coverage.
