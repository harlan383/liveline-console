# Stage 3.4.25 Advanced Debug Resource Registration Plan

## Scope

This stage adds a read-only resource registration plan to the Advanced Debug HAProxy Runtime Readiness page.

It is shown below the Stage 3.4.24 resource rebuild plan and uses the selected HAProxy dry-run candidate plus the Stage 3.4.23 integrity checks as input.

## Goal

When an old HAProxy dry-run candidate is blocked because its referenced transit resource, landing node, or Transit Worker is missing, deleted, stale, or otherwise not usable, operators need a safe plan for what must be registered before a new dry-run can be generated.

The new plan explains the missing formal resource context without creating or modifying anything.

## Registration Drafts

The UI can derive these read-only sections:

- formal transit resource registration draft,
- formal landing node registration draft,
- Transit Worker preparation checklist.

Candidate values are treated only as historical hints. They must be manually verified before any future protected registration flow uses them.

## Manual Inputs

The plan highlights manual inputs that cannot be trusted from a historical candidate alone:

- transit server public host,
- transit server SSH port,
- transit server region and name,
- Transit Worker online and binding status,
- landing VPS IP,
- landing Xray / Reality port,
- active landing node status.

## Copy Output

Operators can copy a plain-text registration plan for follow-up work.

The copied text contains only redacted planning fields, candidate identifiers, status summaries, manual input names, and recommended next stage names. It does not include full client links, share links, tokens, private keys, passwords, install commands, or remote command output.

## Safety Boundary

This stage does not:

- change ordinary product pages,
- create transit resources,
- create landing nodes,
- create WorkerCommand records,
- create TransitRoute records,
- create HAProxy routes,
- bind listener ports,
- connect over SSH,
- execute remote commands,
- mutate firewall / cloud security group / cloud firewall settings,
- read or modify `nodes.share_link`,
- write `transit_routes.share_link`,
- export client links,
- perform cutover,
- modify Worker code,
- modify docker-compose,
- add migrations.

Stage 3.4.23 protection remains unchanged: readiness and protected real execution still require the selected dry-run candidate to be integrity-ready.

## Recommended Follow-up

If formal resources are missing, a future stage may design a protected registration UI. That future stage must preserve the same safety boundaries and remain separate from HAProxy route creation.

## Validation

- `git diff --check`
- `git diff --cached --check`
- frontend typecheck
- frontend production build
- staged sensitive scan
