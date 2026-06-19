# Stage 3.3.81 Transit Page Advanced Sections Collapse

## Purpose

Stage 3.3.81 is a low-risk frontend usability polish stage. LiveLine Console is a lightweight self-use network build and troubleshooting helper, not a complex commercial node platform. This stage keeps the transit route page focused on the daily network-building flow and default-collapses advanced debug, approval, and Worker-oriented controls to reduce misoperation risk.

## Why This Change

The transit route page has grown to include candidate export, readonly preflight, Worker create-path dry-run, approval reminders, and route status data. The daily path is simple: review the active transit route, confirm the candidate summary, and transiently export a test configuration when needed. Advanced preflight and dry-run controls are useful for development and troubleshooting, but they should not compete with the main build flow or sit in the first-level page path.

## Default Visible Areas

- Transit route list.
- Route name.
- Entry IP and port.
- Landing target IP and port.
- Forwarding method.
- Service name.
- Route status.
- `share_link` unwritten state.
- Cutover not executed state.
- Candidate configuration summary.
- Transient export test configuration.
- HTTP manual-copy fallback.

## Default Collapsed Areas

The new `高级调试与审批操作` section is collapsed by default and contains:

- Local route planning controls.
- Worker allowlist confirmation.
- Remote readonly preflight controls.
- Worker create-path dry-run controls.
- Approval and safety confirmations related to debug or dry-run flows.

The section keeps the original controls available for development, approval, or troubleshooting work, but adds a warning that daily network setup usually does not need the section expanded.

## Safety Boundary

This stage does not:

- Execute cutover.
- Modify `nodes.share_link`.
- Write `transit_routes.share_link`.
- Read or export complete `nodes.share_link`.
- Generate or record complete node links.
- Create Worker commands automatically.
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
- Sensitive information scan

Backend tests and Go builds are not required because this stage does not modify backend or Worker code.

## Result

The transit route page now presents the candidate route and route table first, while advanced debug and approval controls remain available behind a clear collapsed section. The change improves self-use safety without changing backend behavior or production state.
