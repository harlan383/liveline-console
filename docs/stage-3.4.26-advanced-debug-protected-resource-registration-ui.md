# Stage 3.4.26 Advanced Debug Protected Resource Registration UI

## Scope

This stage adds a protected resource registration preparation UI only inside Advanced Debug.

It does not change ordinary product pages, customer-facing flows, backend APIs, database schema, Worker code, docker-compose, or deployment ports.

## Purpose

Stage 3.4.25 introduced a read-only formal resource registration plan for blocked HAProxy dry-run candidates.

Stage 3.4.26 turns that plan into a copy-only preparation form. Operators can assemble the fields that a later protected registration dry-run may need, but this stage does not submit, create, save, or mutate any records.

The prepared payload is explicitly marked:

- `stage = Stage 3.4.26-advanced-debug-protected-resource-registration-ui`
- `mode = preview_only`

## UI Sections

The Advanced Debug card contains:

- source candidate summary,
- transit resource registration draft fields,
- landing node registration draft fields,
- manual confirmations,
- payload preview and copy actions.

Candidate values are treated as historical hints. They must be manually verified before any future protected registration stage can use them.

## Validation

Local validation requires:

- transit resource name,
- transit entry host,
- transit entry port as a valid TCP port,
- transit entry region,
- transit exit region,
- landing node name,
- landing VPS IP,
- landing Xray / Reality port as a valid TCP port,
- all manual confirmations checked.

Passing local validation only marks the draft as ready for the next stage. It still does not create resources or call any backend registration endpoint.

## Safety Boundary

This stage does not:

- change ordinary product UI,
- add a backend endpoint,
- create transit resources,
- create landing nodes,
- create WorkerCommand records,
- create TransitRoute records,
- create HAProxy routes,
- bind listener ports,
- connect over SSH,
- execute remote commands,
- mutate firewall / cloud security group / cloud firewall settings,
- export full client links,
- export or mutate `share_link`,
- perform cutover,
- modify Worker code,
- modify docker-compose,
- add migrations.

Readiness and protected real execution remain blocked unless the selected dry-run candidate is integrity-ready.

## Next Stage

Recommended follow-up:

`Stage 3.4.27-advanced-debug-protected-resource-registration-dry-run`

That future stage should remain a protected dry-run first, not direct resource creation.

## Validation

- `git diff --check`
- `git diff --cached --check`
- frontend typecheck
- frontend production build
- staged sensitive scan
