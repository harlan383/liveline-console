# Stage 3.6.5 Single Route Create Flow Stability Archive

## Current Stage Conclusion

Stage 3.6.5 archives the stable baseline for the single-route create flow. This
stage is documentation-only and is not a new route creation stage, not a remote
execution stage, and not a cutover stage.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- No rollback is triggered by this stage.

This stage does not modify code, frontend functionality, backend logic, scripts,
database schema, `node.share_link`, listening ports, firewall rules, route
state, or current transit links. It does not execute SSH or remote commands,
trigger backend tasks, perform cutover, let `socat` take over 8443, or stop,
downgrade, or replace `gost` 8443.

## Stage 3.6 Completed Capabilities

| Stage | Capability | Archive Status |
| --- | --- | --- |
| Stage 3.6.1 | Single-route create flow review | Reviewed |
| Stage 3.6.2 | Single-route create safety gates | Added |
| Stage 3.6.3 | Single-route diagnosis display polish | Added |
| Stage 3.6.4 | Browser manual acceptance record | Recorded |

The Stage 3.6 baseline now covers flow review, port safety, route creation
boundaries, diagnosis display clarity, redacted task/result display, and browser
acceptance notes.

## Current Single Route Flow Stable Baseline

The current system has the following stable local-console capabilities:

- Transit resource records are available.
- Active node selection is available.
- Topology preview is available.
- Single-route UI/API boundaries are available.
- Port safety gates are available.
- `8443` is forbidden or clearly protected because it is retained for the
  `gost` fallback route.
- `18443` is forbidden or clearly protected because it is the current formal
  `socat` route and must not be reused or overwritten by a new route.
- Route creation is clearly separated from formal cutover.
- Route creation does not modify `node.share_link`.
- Any new or changed listening port requires cloud security group, cloud
  firewall, and server firewall checks for the corresponding TCP port before
  real creation and diagnosis.
- Diagnosis display is clearer and separates checks such as listen state,
  process state, target connectivity, service status, task status, failure
  summary, and next action.
- Diagnosis and task result display use redaction and must not display complete
  node links, SSH keys, passwords, tokens, or session secrets.
- Browser manual acceptance for the Stage 3.6.2 and Stage 3.6.3 UI changes has
  been recorded.

## Standard Single Route Flow

### A. Preparation

- Back up the local database before risky changes.
- Confirm the current formal link remains `socat` 18443.
- Confirm the current fallback link remains `gost` 8443.
- Confirm `node.share_link` will not be modified during route creation.
- Confirm the intended transit server and landing node before any real remote
  work.

### B. Port Planning

- Choose a new listening port intentionally.
- Do not use `8443`, because `8443` is retained for the `gost` fallback route.
- Do not overwrite `18443`, because `18443` is the current formal `socat`
  route.
- Before any new or changed listening port is used, check that the cloud
  security group, cloud firewall, and server firewall allow the corresponding
  TCP port.

### C. Creation

- Enter a real creation stage only after explicit user authorization.
- Real SSH and remote forwarding creation require Workbuddy or a separately
  authorized remote-execution stage.
- Creation must not directly modify `node.share_link`.
- Creation must not perform cutover.

### D. Diagnosis

- Check listening port state.
- Check the `socat` process state when the route uses `socat`.
- Check transit-to-landing connectivity.
- Check task records and task result summaries.
- Diagnosis results must not show complete node links, SSH keys, passwords,
  tokens, session secrets, or complete sensitive command output.

### E. Acceptance

- Test candidate links manually in the client.
- Record candidate-link acceptance separately.
- Do not write complete links into documentation, terminal commands, logs, task
  results, reports, or Git.

### F. Formal Cutover

- Enter a separate formal cutover approval stage before changing
  `node.share_link`.
- Changing `node.share_link` requires separate approval and a rollback plan.
- Keep `gost` 8443 as the fallback link unless a later approved stage changes
  that boundary.
- Do not let `socat` take over 8443 as part of the single-route creation flow.

## Workbuddy Boundary

Workbuddy is not needed for this Stage 3.6.5 documentation archive.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login to a VPS or transit server.
- Real `socat` or `gost` installation checks.
- Real remote forwarding creation.
- Real remote listening-port checks.
- Real remote diagnosis.
- Real `node.share_link` cutover or rollback execution, which also requires
  separate approval.

## Current Link Stable Baseline

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.6 does not modify `node.share_link`.
- Stage 3.6 does not add real listening ports.
- Stage 3.6 does not close, downgrade, or replace `gost` 8443.
- Stage 3.6 does not let `socat` take over 8443.
- Stage 3.6 does not perform cutover.

## Security Boundary

This stage maintains the following boundaries:

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH keys.
- Do not write passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not commit real database backup files.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not trigger backend tasks.
- Do not modify firewall rules.
- Do not let `socat` take over 8443.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Future Recommendations

- If a new single-route forwarding path is needed, enter a remote-execution
  preparation stage first.
- Reconfirm port planning before creating any new route.
- Confirm cloud security group, cloud firewall, and server firewall rules before
  using any new or changed TCP listening port.
- Use Workbuddy when real SSH, remote route creation, or remote diagnosis is
  required.
- Record candidate-link acceptance separately after client testing.
- Use a separate formal cutover approval stage before modifying
  `node.share_link`.

## Impact Summary

| Item | Result |
| --- | --- |
| Code modified | No |
| Frontend functionality modified | No |
| Backend logic modified | No |
| Scripts added or modified | No |
| Real backup files generated | No |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` read or modified | No |
| SSH or remote command executed | No |
| Backend task triggered | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
