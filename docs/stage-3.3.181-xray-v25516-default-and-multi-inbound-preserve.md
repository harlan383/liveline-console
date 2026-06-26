# Stage 3.3.181 Xray v25.5.16 Default and Multi-Inbound Preserve

## Production Finding

On 2026-06-26, a dynamic landing Reality node on `64.90.13.19:27940` was investigated after the client could reach the port but could not successfully use the node.

The investigation confirmed:

- The landing TCP port was reachable.
- The landing Xray service received client connections.
- Database metadata, server config, and the client runtime config matched for UUID, public key, short ID, SNI, dest, and flow.
- The local v2rayN proxy path was working.
- The landing server error log repeatedly reported `REALITY: processed invalid connection`.

The landing server was running Xray-core `25.1.1`, while the client used Xray `25.5.16`. A manual upgrade of the landing server Xray-core to `v25.5.16` restored the `27940` Reality node.

Manual repair record:

- Date: `2026-06-26`
- Landing VPS: `64.90.13.19`
- Backup directory: `/root/liveline-xray-backup-20260626-192914`
- Target version: `Xray-core v25.5.16`
- Linux amd64 archive sha256: `7679da6a3bb9dc2b3ce82d7f9f64ac1bb0e4bd6c3b9a0926613e5fc88abef25a`
- Result: the `27940` Reality node recovered normal client connectivity.

## Version Decision

Starting with this stage, LiveLine-managed Xray defaults to:

```text
Xray-core v25.5.16
```

The Worker does not use `latest` and does not move to 26.x by default. Version `v25.5.16` is pinned because it was verified in production to resolve the Reality/Vision invalid-connection issue and matches the current v2rayN Xray runtime used in testing.

The pinned Linux amd64 package is:

```text
https://github.com/XTLS/Xray-core/releases/download/v25.5.16/Xray-linux-64.zip
sha256: 7679da6a3bb9dc2b3ce82d7f9f64ac1bb0e4bd6c3b9a0926613e5fc88abef25a
```

## Worker Changes

- Worker version: `0.1.34-stage-3.3.181-xray-v25516-multi-inbound`.
- Bundled Linux amd64 Worker binary sha256: `8aaaa132980790a50613196860ef363c4f4dc150f50b35dabc51fbc09803343b`.
- If the LiveLine-managed Xray binary is missing, the Worker installs pinned `v25.5.16`.
- If the existing LiveLine-managed Xray binary is older than `v25.5.16`, the Worker backs it up and upgrades it.
- If the existing version is `v25.5.16` or newer, the Worker keeps it and does not downgrade.
- The downloaded archive is verified with sha256 before replacement.
- If config test or later startup validation fails after an upgrade, rollback restores the previous binary and config where applicable.

## Multi-Inbound Fix

Stage 3.3.180 introduced dynamic landing ports but the production repair showed that adding `27940` did not preserve the previous `27939` inbound. This stage hardens the Worker config path:

- Existing LiveLine-managed inbounds are preserved.
- New ports append a new inbound instead of replacing the config.
- Duplicate inbound ports are rejected.
- Existing config must be LiveLine-managed Reality TCP VLESS config.
- Invalid JSON or non-LiveLine config is rejected.
- The Worker writes a temporary config, runs `xray run -test`, and only then atomically replaces the managed config.
- After restart, all expected LiveLine-managed inbound ports must be listening.

This stage does not restore `27939`; any real recovery of that port must be handled by a separate approved stage.

## Client Link Compatibility

Direct and transient Reality client-link export now ensures the compatible TCP parameters include:

```text
encryption=none
flow=xtls-rprx-vision
security=reality
sni=<node.sni>
fp=<node.fingerprint>
pbk=<node.reality_public_key>
sid=<node.reality_short_id>
type=tcp
headerType=none
spx=%2F
```

Existing stored `nodes.share_link` values are not modified by this stage. Compatibility parameters are added only when a new node naturally generates a link or when an explicit export path returns a transient client link.

## Read-Only Diagnostics

Worker failure diagnostics may include safe operational fields:

- `xray_version`
- `xray_target_version`
- `xray_upgrade_required`
- `managed_config_detected`
- `inbound_ports`
- `inbound_tags`
- `service_active`
- `listening_ports`

Diagnostics must not return UUIDs, private keys, public keys, short IDs, or full client links.

## Safety Boundary

This stage does not:

- Create a real landing node.
- Add a real listener.
- Delete nodes or transit routes.
- SSH or execute remote commands.
- Perform a real remote Xray upgrade.
- Install or uninstall HAProxy, socat, or gost.
- Cut over traffic.
- Write `transit_routes.share_link`.
- Modify existing `nodes.share_link`.
- Output full client links.
- Modify cloud security groups, cloud firewalls, or server firewalls.
- Modify the public controller `docker-compose.yml`.
- Commit `.bak` files.
