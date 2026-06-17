# Stage 3.3.67 — Transit Readonly Preflight Simple Button

## Purpose

Stage 3.3.67 simplifies the transit readonly preflight UI.

The previous remote readonly preflight flow exposed planning, approval, Worker command creation, and refresh details separately. That was hard to use from the console.

This stage adds a simple one-button panel under the `中转链路` tab.

## Changes

- Add `TransitReadonlyPreflightSimplePanel`.
- Route the `中转链路` tab to the simplified panel.
- Keep the older complex component in the codebase for rollback.
- Default the planned listen port to `24731`.
- Show only user-facing fields:
  - transit server,
  - landing node,
  - planned listen port,
  - landing target port,
  - purpose,
  - one readonly confirmation checkbox,
  - one `远程只读预检` button.
- Automatically polls the resulting Worker command until a terminal status is returned.
- Hides command id and target Worker under an advanced details section.

## Safety boundary

This stage changes frontend UI only.

The simple button still calls the existing approved readonly endpoint and does not create a real transit route by itself.

No backend route creation logic is changed.

No remote command is run by this commit or PR.

The UI explicitly states that it does not install, start, stop, or restart `socat` or `gost`, bind port `24731`, change firewall rules, modify Xray, change `nodes.share_link`, export full client links, or perform cutover.

## Result

The transit readonly preflight path is now easier to operate from the `中转链路` tab.

Recommended next stage after deployment:

`Stage 3.3.68-simple-button-deploy-and-ui-check`
