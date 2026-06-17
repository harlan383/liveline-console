# Stage 3.3.61 — Remote Readonly Preflight Implementation Plan

## Purpose

This stage defines the implementation plan for a Worker/API based remote readonly preflight.

This is a documentation-only planning stage. It does not implement the feature and does not run any remote checks.

## Background

Stage 3.3.60 was blocked because the system did not yet expose a safe Worker/API execution path for the approved remote readonly preflight.

Recorded plan inputs:

| Item | Value |
| --- | --- |
| Transit resource | `香港中转服务器` |
| Transit IP | `163.223.216.108` |
| Landing node | `liveline-reality-27939` |
| Planned listener port | `24731` |
| Landing target port | `27939` |
| Purpose | `直播线路` |

## Proposed capability

Add a first-party remote readonly preflight command path that uses the existing Worker command mechanism.

The new capability should allow the control plane to create a readonly command for an online transit Worker and receive a redacted result.

## Readonly checks to support

The first implementation should support only non-mutating checks:

- Worker is online and bound to the selected transit resource.
- Planned listener port status can be inspected.
- `socat` service or process status can be inspected.
- `gost` service or process status can be inspected.
- Transit-to-landing TCP reachability can be inspected.
- Local firewall status can be inspected as a read-only fact.
- Result summary is redacted before it is shown in the UI.

## Explicit No-Go scope

The implementation must not create a route, install packages, write config files, create or restart services, bind listener ports, modify firewall rules, modify Xray, modify `nodes.share_link`, export a full client link, or perform cutover.

## Suggested backend shape

Add a dedicated readonly preflight command type such as:

`transit_readonly_preflight`

The command payload should include only the minimum structured inputs:

- transit resource id,
- landing node id,
- planned listener port,
- landing target port,
- forwarding method,
- purpose label.

The API should validate that:

- the transit resource is a server resource,
- the resource is Worker-online,
- the Worker role is `transit`,
- the landing node is active,
- ports are numeric and valid,
- protected ports are rejected,
- the request is explicitly readonly.

## Suggested Worker behavior

The Worker should execute only a fixed allowlist of read-only probes for this command type.

The Worker must return structured results with:

- check id,
- status,
- passed boolean,
- short detail,
- redacted raw output if needed.

The Worker must not accept arbitrary shell from the API payload.

## Suggested frontend behavior

The Transit Links page should expose a clearly labeled readonly remote preflight action after local plan validation succeeds.

The UI should show:

- submitted command id,
- command status,
- per-check result,
- redacted summary,
- clear No-Go messaging for real creation.

The real creation button must remain disabled or clearly out of scope until a later explicit creation approval stage.

## Validation expectations for future code stage

A future implementation stage should include:

- backend validation tests,
- Worker command handling tests if available,
- frontend build validation,
- sensitive-output scan,
- confirmation that no route creation path is invoked.

## Recommended next stage

Recommended next stage:

`Stage 3.3.62-transit-worker-remote-readonly-preflight-api-design`

That stage may begin implementing the API and Worker command contract, still without enabling real route creation.

## Result

Stage 3.3.61 records the implementation plan for remote readonly preflight. Real execution remains No-Go.
