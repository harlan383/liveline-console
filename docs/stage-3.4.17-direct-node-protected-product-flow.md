# Stage 3.4.17 Direct Node Protected Product Flow

## Scope

Stage 3.4.17 connects the product-facing `新建直连节点` modal to the existing protected landing-node plan/create APIs.

This stage turns the direct-node product entry from demo-only into a guarded two-step flow:

- Generate a plan first.
- Create the real protected Worker command only after explicit confirmation.

It does not connect transit-route creation, provider transit entry, customer-line editing, settings persistence, BBR, deletion, or client-link export.

## Frontend Flow

The product modal now guides the administrator through:

1. Choose an online landing server.
2. Fill direct-node parameters.
3. Confirm the customer TCP port has been allowed in all required firewall layers.
4. Generate a protected creation plan.
5. Review warnings, blocked reasons, preflight summary, and safety boundary.
6. Type the exact confirmation text `CONFIRM_CREATE_DIRECT_NODE`.
7. Create the protected `landing_node_create` Worker command.

Only landing servers with an online Worker can be selected. Servers without an online Worker are not eligible for plan/create submission.

## Backend API Reuse

This stage reuses existing backend endpoints:

- `GET /api/auth/csrf`
- `POST /api/vps/{server_id}/landing-node-plan`
- `POST /api/vps/{server_id}/landing-node-create`

No backend API, database schema, migration, Worker binary, or deployment configuration was changed.

## Real Execution Boundary

The plan endpoint is a dry-run planning step:

- It does not create Worker commands.
- It does not SSH to a VPS.
- It does not execute remotely.

The create endpoint creates a protected Worker command:

- It can create a real `landing_node_create` Worker command.
- The Worker later polls and executes the command.
- Successful Worker execution can create a real Xray/VLESS Reality listener on the selected landing VPS.
- This can add a real customer TCP listener port.

The UI does not expose full Worker command payloads, `share_link`, `vless://` links, tokens, private keys, install commands, or Reality secrets.

## Port / Firewall Reminder

Before generating a plan or creating the command, the administrator must confirm the selected TCP port is allowed in:

1. Cloud server security group.
2. Cloud firewall.
3. Server operating-system firewall.

The system does not modify cloud security groups or cloud firewalls. Those checks remain an administrator responsibility.

## Still Demo-Only

These product areas remain demo-only or not connected in this stage:

- Real transit-route creation.
- Provider transit entry.
- Customer-line editing.
- Settings persistence.
- BBR operations.
- Delete / cleanup operations.
- Client-link export flow.

## Safety Boundary

This stage requires exact confirmation text before real create:

- `CONFIRM_CREATE_DIRECT_NODE`

This stage does not:

- Run frontend SSH or shell commands.
- Modify cloud security groups or cloud firewalls.
- Perform cutover.
- Create transit routes.
- Create HAProxy routes.
- Show or store `share_link`.
- Show or store `vless://` links.
- Show or store tokens, private keys, or install commands.
- Add database migrations.
- Modify Worker binaries.
- Modify `docker-compose.yml`.

Failed Worker execution must be limited to rolling back artifacts created by that command.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- frontend TypeScript check
- frontend Next build

Backend compile is not required when backend files are unchanged.
