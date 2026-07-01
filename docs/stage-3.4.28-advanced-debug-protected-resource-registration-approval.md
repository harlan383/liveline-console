# Stage 3.4.28 Advanced Debug Protected Resource Registration Approval

## Goal

Stage 3.4.28 adds an approval dry-run after the Stage 3.4.27 protected resource registration dry-run.

The goal is to verify that an operator has reviewed a successful registration dry-run result, copied the exact expected approval text, and confirmed the safety boundary before any later command-creation stage is considered.

## Endpoint

```text
POST /api/transit-routes/protected-resource-registration-approval-dry-run
```

The endpoint requires an admin session and CSRF token. It only validates the submitted approval payload in memory.

## Why Approval Dry-run Only

The previous stage proves that the proposed resource registration payload is structurally valid and ready for review. This stage does not make the registration real. It only records that the next step should require an exact approval text and explicit safety confirmations.

This keeps the workflow auditable and prevents a successful dry-run from silently becoming a resource write or command creation.

## Safety Boundary

This stage does not:

- create transit resources
- create landing node records
- create `WorkerCommand`
- create `TransitRoute`
- create HAProxy routes
- bind listener ports
- run SSH or remote commands
- change firewall, cloud firewall, or cloud security groups
- perform cutover
- read, output, or modify complete client configuration values
- modify ordinary product UI
- modify Worker, docker-compose, or migrations

The approval dry-run response intentionally avoids echoing the pasted normalized preview body. It returns only a small sanitized approval summary.

## Frontend

The frontend entry is limited to the advanced debug HAProxy panel. It lets an operator:

- reuse the current Stage 3.4.27 dry-run result
- paste a copied Stage 3.4.27 dry-run result
- view the `expected_approval_text`
- type the exact approval text
- see a local exact-match indicator
- check the approval safety confirmations
- preview and copy the approval payload
- run the approval dry-run endpoint
- clear the approval draft

No ordinary product page is changed.

## Stage 3.4.27 Process Note

Stage 3.4.27 exists on `main` as a direct commit rather than a standard PR review and merge loop. Stage 3.4.28 restores the standard branch, commit, PR, review, and merge workflow.

## Next Stage

If this approval dry-run passes, the recommended next stage is:

```text
Stage 3.4.29-protected-resource-registration-command-create
```

That later stage must still be separately reviewed before any command creation or database mutation is implemented.
