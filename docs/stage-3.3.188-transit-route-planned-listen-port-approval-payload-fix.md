# Stage 3.3.188 Transit Route Planned Listen Port Approval Payload Fix

## Background

Creating a HAProxy TCP transit route failed at the Worker safety gate with:

```text
transit_route_create haproxy_tcp planned_listen_port is not approved
```

The read-only payload inspection showed `planned_listen_port` was present, but the corresponding approval fields were missing:

```text
planned_listen_port = 25963
approved_planned_listen_port = empty
approved_firewall_confirmation = empty
dry_run = true
```

The frontend checkbox confirms that the operator reviewed cloud security group, cloud firewall, and server firewall exposure, but that UI confirmation must still be persisted into the Worker command payload. The Worker must not infer approval from the planned port alone.

## Fix

The backend now includes explicit approval fields in HAProxy TCP `transit_route_create` payloads:

```text
planned_listen_port = <planned TCP port>
approved_planned_listen_port = <same planned TCP port>
approved_firewall_confirmation = true
approved_landing_target_host = <current landing host>
approved_landing_target_port = <current landing port>
```

For real execution payloads the backend also keeps:

```text
dry_run = false
approved_real_execution = true
execution_mode = real_create
```

Final approval and real execution checks now require the dry-run command payload to contain the approved planned listen port and firewall confirmation before continuing.

## Worker Boundary

The HAProxy TCP Worker path now accepts dynamic planned listen ports only when the explicit approval fields match the requested plan:

```text
approved_planned_listen_port == planned_listen_port
approved_firewall_confirmation == true
approved_landing_target_host == landing_target_host
approved_landing_target_port == landing_target_port
```

The socat path remains on the previous fixed protected-port behavior.

Worker version:

```text
0.1.36-stage-3.3.188-transit-port-approval
```

Bundled Linux amd64 Worker binary sha256:

```text
377a6b9a53ddc3971e2e32e8b0fa48bdc594f53c634d34a6a8bd45597f21ae8e
```

## Validation Notes

This stage adds tests for:

- HAProxy dry-run payload includes `approved_planned_listen_port` and `approved_firewall_confirmation`.
- Final approval blocks dry-run payloads missing or mismatching the approved planned listen port.
- Real execution blocks dry-run payloads missing or mismatching the approved planned listen port.
- Worker HAProxy dry-run accepts a dynamic port only when the planned and approved ports match.
- Worker HAProxy real execution accepts a dynamic port only when the planned and approved ports match.

## Safety Boundary

This stage did not:

- create a real transit route
- add a real listener
- modify HAProxy runtime configuration on a remote VPS
- start, stop, or restart HAProxy
- execute SSH or remote commands
- perform cutover
- write `transit_routes.share_link`
- output a full client link
- modify cloud security groups, cloud firewall, or server firewall
- modify `docker-compose.yml`
- submit `.bak` files
