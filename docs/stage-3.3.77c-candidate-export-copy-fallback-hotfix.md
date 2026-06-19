# Stage 3.3.77c Candidate Export Copy Fallback Hotfix

## Stage Goal

Stage 3.3.77c fixes the transient candidate export copy experience on the
public console when it is accessed over HTTP.

The Stage 3.3.77b system test confirmed that the candidate summary and
transient export API work, but Chrome does not expose
`navigator.clipboard.writeText()` in an insecure HTTP context. The page
previously displayed a copied success message even when automatic copying
failed.

This stage adds an HTTP-safe manual copy fallback. It does not change backend
export behavior, route state, Worker behavior, or any production service.

## Observed Issue

Public console access currently uses:

- `http://my-con.golirong.xyz:3200`

Browser diagnostics showed:

- `isSecureContext=false`
- Clipboard API unavailable
- automatic copy failed before writing to the clipboard

The transient candidate export itself remained valid. The full candidate link
was available only in the API response and manual client import worked after
copying it from a controlled test path.

## Frontend Fix

The `中转链路` candidate panel now:

- checks whether `navigator.clipboard.writeText()` exists before using it;
- awaits the copy operation before showing a success message;
- shows success only after automatic copy succeeds;
- shows a clear fallback message when automatic copy is unavailable or fails;
- displays a read-only manual-copy textarea only after transient export
  succeeds and automatic copy fails;
- selects the textarea content on focus or click for easier manual copy.

The fallback message reminds the operator that the exported candidate link:

- is only for manual client import testing;
- must not be pasted into chats, PRs, logs, screenshots, or documentation;
- is not written to `nodes.share_link`;
- does not perform cutover.

## Safety Boundary

Stage 3.3.77c did not:

- perform cutover;
- mutate `nodes.share_link`;
- write `transit_routes.share_link`;
- create a Worker command;
- restart, stop, disable, or delete `socat`;
- modify Xray;
- modify firewall, cloud firewall, or cloud security group rules;
- execute SSH or remote commands;
- add a database migration;
- change backend API behavior.

## HTTPS Backlog

This hotfix only addresses the HTTP clipboard fallback. A separate future stage
should move the public console to HTTPS:

- `Stage 3.3.80-public-console-https-reverse-proxy`

That stage should review HTTPS reverse proxy setup, secure login cookie
settings, browser secure-context behavior, and public administration console
hardening. It is not executed in Stage 3.3.77c.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- `docker compose exec -T frontend npm run build`
- sensitive information scan

Backend tests and Go/Worker builds are not required for this stage because it
changes only frontend copy handling plus README/docs.
