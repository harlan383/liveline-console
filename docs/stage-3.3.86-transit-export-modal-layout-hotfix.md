# Stage 3.3.86 Transit Export Modal Layout Hotfix

## Purpose

Stage 3.3.86 fixes the `中转链路` page transient export modal layout after the Stage 3.3.85 modal polish. This is a frontend-only layout hotfix.

The goal is to keep the `临时导出测试配置` modal usable on the public console page without changing backend APIs, Worker behavior, database state, or production network state.

## Observed Issue

Public console retesting showed that the transient export modal could overflow horizontally:

- The modal showed a horizontal scrollbar.
- Checkbox inputs and confirmation text were too far apart.
- Confirmation text was squeezed to the far right and wrapped vertically.
- The modal content could become wider than the visible panel.

This made the export confirmation flow hard to read even though the underlying transient export behavior remained unchanged.

## Fix

The hotfix updates the modal layout and confirmation rows:

- The export modal now has a bounded responsive width and hides horizontal overflow.
- The modal uses vertical scrolling only when content is taller than the viewport.
- Route context content is constrained so long values wrap inside the modal.
- Confirmation items use a dedicated flex row layout:
  - checkbox stays close to its text
  - text wraps normally
  - text does not collapse into vertical characters
- The export result and manual-copy textarea are constrained to the modal width.
- The add-route modal shares the same overflow protection where applicable.

## Unchanged Behavior

The transient export flow remains the same:

1. Open the `临时导出` row action.
2. Confirm the safety items.
3. Generate a temporary test configuration.
4. Copy through Clipboard API when available.
5. Use the HTTP manual-copy textarea when automatic copy is unavailable.
6. Close the modal to clear transient export state.

The complete candidate link remains transient UI data only and must not be written to README, docs, logs, audit text, screenshots, or test fixtures.

## Safety Boundary

This stage does not:

- Execute cutover.
- Modify `nodes.share_link`.
- Write `transit_routes.share_link`.
- Read or export complete `nodes.share_link`.
- Generate or record complete node links.
- Create Worker commands.
- Create VPS resources, nodes, or transit routes.
- Add listening ports.
- Restart, stop, or delete `socat`.
- Modify Xray.
- Modify firewalls, cloud firewalls, or cloud security groups.
- Execute SSH or remote commands.
- Add database migrations.
- Deploy the public console.
- Run client tests.
- Modify backend APIs.
- Modify Worker binaries.

## Validation

Required validation for this stage:

- `git diff --check`
- `git diff --cached --check`
- `docker compose exec -T frontend npm run build`
- sensitive information scan

Backend tests and Go builds are not required because this stage does not modify backend or Worker code.

## Result

The transient export modal no longer creates page-level horizontal overflow. Checkbox inputs and confirmation text are aligned in readable rows, and the modal can show the export result plus manual-copy fallback without stretching beyond the viewport.
