# Stage 3.3.96 Resource Safe Delete Public Smoke Record

## Purpose

Stage 3.3.96 records the public-console UI smoke test after Stage 3.3.95 was deployed to the public master console.

This stage does not add features. It only records the operator-confirmed UI result for the safe-delete buttons and confirmation dialogs.

## Scope

This record covers the following public UI checks:

- landing server row delete button
- direct node row delete button
- transit server row delete button
- transit route row delete button
- delete confirmation modal behavior

This stage does not perform an actual delete operation.

## Public UI Smoke Result

The operator confirmed the following results on the public console:

| Area | Expected result | Observed result |
| --- | --- | --- |
| Landing server page | Landing server row has `删除` button | Passed |
| Landing server page | Direct node row has `删除节点` button | Passed |
| Transit server page | Transit server row has `删除` button | Passed |
| Transit route page | Transit route row has `删除` button | Passed |
| Delete action | Clicking delete opens a confirmation modal | Passed |

No production resource was deleted during this smoke test.

## Safety Boundary

This stage did not:

- execute cutover
- delete any system record
- modify `nodes.share_link`
- write `transit_routes.share_link`
- read or export complete `nodes.share_link`
- generate or record complete node links
- create Worker commands
- create VPS records
- create nodes
- create transit routes
- add listening ports
- restart, stop, or delete `socat`
- modify Xray
- modify firewalls, cloud firewalls, or cloud security groups
- execute SSH or remote commands
- add database migrations
- deploy the public console
- change backend APIs
- change frontend runtime code
- change Worker code or binaries

## Important Operator Note

The Stage 3.3.95 delete buttons are intentionally safe-delete controls.

They delete or soft-delete LiveLine Console system records only. They do not stop remote Xray, stop remote socat, remove systemd services, close ports, clean VPS files, or change cloud firewall rules.

The current live resources should not be deleted casually:

- landing VPS record
- direct Reality node `liveline-reality-27939`
- Hong Kong transit server record
- transit route `hk-socat-live-23843`

Deleting these system records would remove them from the console daily list and make later management less convenient, even though the remote service may continue to run.

## Result

Stage 3.3.96 confirms that the public console displays all Stage 3.3.95 safe-delete UI entry points and opens confirmation dialogs correctly.

The stage is accepted as a UI smoke-test record.

## Follow-Up Reminder

The GitHub repository was temporarily made public to make public VPS clone/deployment easier.

After public deployment, clone, and smoke testing are stable, change the GitHub repository back to private.