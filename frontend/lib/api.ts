export type ApiResponse<T> =
  | {
      success: true;
      data: T;
      message: string;
    }
  | {
      success: false;
      error_code: string;
      message: string;
    };

export type HealthData = {
  backend: ComponentHealth;
  database: ComponentHealth;
  redis: ComponentHealth;
  worker: ComponentHealth;
};

export type ComponentHealth = {
  status: string;
  detail: string | null;
};

export type TaskData = {
  id: string;
  vps_id: string | null;
  node_id: string | null;
  task_type: string;
  status: string;
  current_step: string | null;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  result_data: Record<string, unknown> | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type TaskLogData = {
  id: string;
  task_id: string;
  level: string;
  step: string | null;
  message: string;
  raw_output: string | null;
  created_at: string | null;
};

export type TaskListResult = {
  tasks: TaskData[];
};

export type ReadNodeResult = {
  task_id: string;
  vps_id: string;
};

export type NodeData = {
  id: string;
  vps_id: string;
  vps_ip: string | null;
  vps_status: string | null;
  node_name: string;
  protocol: string;
  transport: string | null;
  security: string;
  port: number | null;
  status: string;
  service_status: string | null;
  connectivity_status: string | null;
  uuid: string | null;
  uuid_present?: boolean;
  masked_uuid?: string | null;
  flow: string | null;
  reality_public_key: string | null;
  reality_public_key_present?: boolean;
  masked_reality_public_key?: string | null;
  reality_short_id: string | null;
  reality_short_id_present?: boolean;
  masked_reality_short_id?: string | null;
  reality_server_name: string | null;
  reality_dest: string | null;
  fingerprint: string | null;
  source: string;
  share_link?: string | null;
  has_share_link?: boolean;
  share_link_present?: boolean;
  share_link_length?: number | null;
  masked_share_link?: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_remote_check_at: string | null;
  last_sync_status: string | null;
};

export type NodeListResult = {
  nodes: NodeData[];
};

export type NodeShareLinkExportResult = {
  node_id: string;
  node_name: string;
  share_link: string;
  warning: string;
};

export type NodeActionResult = {
  task_id: string;
  node_id: string;
};

export type TransitResourceData = {
  id: string;
  name: string;
  resource_type: string;
  provider: string | null;
  entry_host: string | null;
  entry_port: number | null;
  entry_region: string | null;
  exit_region: string | null;
  bandwidth_mbps: number | null;
  traffic_limit_gb: number | null;
  traffic_used_gb: number | null;
  protocol_hint: string;
  has_ssh: boolean;
  ssh_host: string | null;
  ssh_port: number | null;
  ssh_username: string | null;
  status: string;
  connection_mode: string;
  worker_id: string | null;
  worker_status: string | null;
  worker_role: WorkerRole | null;
  worker_hostname: string | null;
  worker_interface_name: string | null;
  worker_version: string | null;
  worker_last_heartbeat_at: string | null;
  worker_online: boolean;
  display_status: string;
  expires_at: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
};

export type TransitResourceListResult = {
  resources: TransitResourceData[];
};

export type TransitResourcePayload = {
  name: string;
  resource_type: string;
  provider: string | null;
  entry_host: string | null;
  entry_port: number | null;
  entry_region: string | null;
  exit_region: string | null;
  bandwidth_mbps: number | null;
  traffic_limit_gb: number | null;
  traffic_used_gb: number | null;
  protocol_hint: string;
  has_ssh: boolean;
  ssh_host: string | null;
  ssh_port: number | null;
  ssh_username: string | null;
  status: string;
  expires_at: string | null;
  notes: string | null;
};

export type TransitServerReadResult = {
  task_id: string;
  transit_resource_id: string;
};

export type TransitGostInstallResult = {
  task_id: string;
  transit_resource_id: string;
};

export type TransitSocatInstallResult = {
  task_id: string;
  transit_resource_id: string;
};

export type TransitRouteData = {
  id: string;
  name: string;
  transit_resource_id: string;
  transit_resource_name: string | null;
  node_id: string;
  node_name: string | null;
  landing_vps_id: string | null;
  landing_vps_ip: string | null;
  listen_port: number;
  target_host: string;
  target_port: number;
  forwarding_method: string;
  service_name: string;
  service_path: string;
  status: string;
  share_link: string | null;
  created_at: string | null;
  updated_at: string | null;
  deleted_at: string | null;
};

export type TransitRouteListResult = {
  routes: TransitRouteData[];
};

export type TransitRouteCreateResult = {
  task_id: string;
  transit_resource_id: string;
  node_id: string;
};

export type TransitRouteDiagnoseResult = {
  task_id: string;
  transit_route_id: string;
};

export type TransitRouteRestartSocatResult = {
  task_id: string;
  transit_route_id: string;
};

export type ReadonlyPreflightPlanRequest = {
  transit_resource_id: string | null;
  transit_resource_name: string | null;
  transit_host_hint: string | null;
  landing_node_id: string | null;
  landing_node_name: string | null;
  landing_host_hint: string | null;
  landing_target_port: string;
  planned_listen_port: string;
  route_purpose: string | null;
  firewall_security_group_confirmed: boolean;
  cloud_firewall_confirmed: boolean;
  server_firewall_confirmed: boolean;
  local_backup_confirmed: boolean;
  user_approved_readonly_preflight: boolean;
  workbuddy_authorized: boolean;
  no_cutover_confirmed: boolean;
  no_node_share_link_change_confirmed: boolean;
};

export type ReadonlyPreflightCheckItem = {
  id: string;
  label: string;
  category: string;
  status: string;
  passed: boolean;
  message: string;
  evidence_summary: string;
  next_action: string;
  sensitive_output_redacted: boolean;
};

export type ReadonlyPreflightPlanResponse = {
  ready: boolean;
  blocked: boolean;
  status: string;
  summary: string;
  next_action: string;
  checks: ReadonlyPreflightCheckItem[];
  safety_boundary: string[];
  redacted_summary: string;
};

export type TransitReadonlyPreflightCommandRequest = {
  transit_resource_id: string;
  landing_node_id: string;
  planned_listen_port: number;
  landing_target_port: number;
  forwarding_method: "socat" | "gost";
  purpose: string | null;
  readonly: true;
};

export type TransitReadonlyPreflightCommandResponse = {
  command: WorkerCommandData;
  target_worker_id: string;
  target_worker_version: string | null;
  minimum_supported_worker_version: string;
  safety_boundary: string[];
};

export type LandingNodePlanRequest = {
  listen_port: number;
  protocol: string;
  security: string;
  flow: string;
  server_name: string;
  dest: string;
  remark?: string | null;
  allow_install_xray: boolean;
  allow_modify_firewall: boolean;
  allow_generate_share_link: boolean;
  allow_overwrite_existing_config: boolean;
  cloud_security_group_confirmed: boolean;
  cloud_firewall_confirmed: boolean;
  server_firewall_confirmed: boolean;
  require_manual_cloud_firewall_confirmation: boolean;
  require_preflight_success: boolean;
};

export type LandingNodePlanResponse = {
  plan_id: string;
  server_id: string;
  mode: string;
  ready: boolean;
  will_install_xray: boolean;
  will_create_config: boolean;
  will_open_local_firewall: boolean;
  will_modify_cloud_security_group: boolean;
  listen_port: number;
  protocol: string;
  security: string;
  flow: string;
  server_name: string;
  dest: string;
  key_generation_strategy: Record<string, string>;
  required_user_confirmations: string[];
  preflight_summary: Record<string, unknown>;
  warnings: string[];
  blocked_reasons: string[];
  next_stage_required: string;
  execution_guard: string[];
  safety_boundary: string[];
};

export type LandingNodeCreateRequest = {
  approved_port: number;
  confirm_firewall_open: boolean;
  confirm_generate_share_link: boolean;
  confirm_write_share_link_after_success: boolean;
  confirm_no_existing_xray: boolean;
  confirm_rollback_new_artifacts_only: boolean;
};

export type LandingNodeCreateResponse = {
  command_id: string;
  command: WorkerCommandData;
  target_worker_id: string;
  target_worker_version: string | null;
  server_id: string;
  approved_port: number;
  status: string;
  next_action: string;
  safety_boundary: string[];
};

export type VpsActionResult = {
  task_id: string;
  vps_id: string;
};

export type VpsServerNodeSummary = {
  id: string;
  name: string;
  address: string | null;
  ip: string | null;
  port: number | null;
  protocol: string;
  status: string;
  share_link_present: boolean;
  created_at: string | null;
};

export type VpsServerData = {
  id: string;
  name: string;
  ip: string;
  ssh_port: number;
  ssh_user: string;
  ssh_username: string;
  notes: string | null;
  status: string;
  last_ssh_status: string;
  last_ssh_check_at: string | null;
  last_ssh_error: string | null;
  connection_mode: string;
  worker_id: string | null;
  worker_status: string | null;
  worker_role: WorkerRole | null;
  worker_hostname: string | null;
  worker_interface_name: string | null;
  worker_version: string | null;
  worker_last_heartbeat_at: string | null;
  worker_online: boolean;
  display_status: string;
  created_at: string | null;
  updated_at: string | null;
  nodes: VpsServerNodeSummary[];
};

export type VpsServerListResult = {
  servers: VpsServerData[];
};

export type VpsServerTaskResult = {
  task_id: string;
  vps_id: string;
  server: VpsServerData;
};

export type VpsServerUpdateResult = {
  server: VpsServerData;
  ssh_status_reset: boolean;
};

export type VpsServerDeleteResult = {
  deleted_server_id: string;
  affected_nodes: number;
  system_record_only: boolean;
  remote_cleanup_performed: boolean;
  message: string;
};

export type WorkerRole = "landing" | "transit";

export type WorkerTokenCreateRequest = {
  role: WorkerRole;
  name?: string | null;
  server_id?: string | null;
  expires_in_minutes?: number;
};

export type WorkerTokenCreateResult = {
  token_id: string;
  role: WorkerRole;
  expires_at: string;
  install_command: string;
  masked_token: string;
  status: string;
  server_id: string | null;
};

export type VpsWorkerBootstrapRequest = {
  name: string;
  ip: string;
  expires_in_minutes?: number;
};

export type VpsWorkerBootstrapResult = {
  server: VpsServerData;
  token: WorkerTokenCreateResult;
  install_command: string;
  expires_at: string;
};

export type TransitWorkerBootstrapRequest = {
  name: string;
  ip: string;
  expires_in_minutes?: number;
};

export type TransitWorkerBootstrapResult = {
  resource: TransitResourceData;
  token: WorkerTokenCreateResult;
  install_command: string;
  expires_at: string;
};

export type TransitWorkerBootstrapRegenerateRequest = {
  expires_in_minutes?: number;
};

export type WorkerMetadataSummary = {
  received_at?: string | null;
  uptime_seconds?: number | null;
  os?: string | null;
  kernel?: string | null;
  cpu?: unknown;
  memory?: unknown;
  disk?: unknown;
  services?: Record<string, unknown> | null;
};

export type WorkerData = {
  id: string;
  server_id: string | null;
  role: WorkerRole;
  name: string | null;
  public_ip: string | null;
  hostname: string | null;
  interface_name: string | null;
  worker_version: string | null;
  status: "online" | "offline" | "unknown";
  last_heartbeat_at: string | null;
  registered_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  metadata_summary: WorkerMetadataSummary;
};

export type WorkerListResult = {
  workers: WorkerData[];
};

export type WorkerCommandType =
  | "ping"
  | "collect_status"
  | "service_status"
  | "landing_preflight"
  | "landing_node_create"
  | "transit_readonly_preflight";

export type WorkerCommandData = {
  id: string;
  worker_id: string;
  target_worker_id: string;
  target_worker_version: string | null;
  server_type: string | null;
  server_id: string | null;
  command_type: WorkerCommandType;
  status: string;
  lease_until: string | null;
  claimed_at: string | null;
  completed_at: string | null;
  result_json: Record<string, unknown>;
  result_summary: string | null;
  error_message: string | null;
  attempts: number;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkerCommandCreateResult = {
  command: WorkerCommandData;
  requested_worker_id: string | null;
  target_worker_id: string;
  target_worker_version: string | null;
  target_worker_changed: boolean;
  minimum_supported_worker_version: string;
};

export type WorkerCommandListResult = {
  commands: WorkerCommandData[];
};

export async function createWorkerToken(
  payload: WorkerTokenCreateRequest,
  csrfToken: string,
): Promise<ApiResponse<WorkerTokenCreateResult>> {
  return apiFetch<WorkerTokenCreateResult>("/api/worker-tokens", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export async function createWorkerCommand(
  workerId: string,
  payload: {
    command_type: WorkerCommandType;
    payload?: Record<string, unknown> | null;
    server_id?: string | null;
    server_type?: WorkerRole | null;
  },
  csrfToken: string,
): Promise<ApiResponse<WorkerCommandCreateResult>> {
  return apiFetch<WorkerCommandCreateResult>(`/api/workers/${workerId}/commands`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export async function listWorkerCommands(workerId: string): Promise<ApiResponse<WorkerCommandListResult>> {
  return apiFetch<WorkerCommandListResult>(`/api/workers/${workerId}/commands`);
}

export async function createVpsWorkerBootstrap(
  payload: VpsWorkerBootstrapRequest,
  csrfToken: string,
): Promise<ApiResponse<VpsWorkerBootstrapResult>> {
  return apiFetch<VpsWorkerBootstrapResult>("/api/vps/worker-bootstrap", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export async function createLandingNodePlan(
  serverId: string,
  payload: LandingNodePlanRequest,
  csrfToken: string,
): Promise<ApiResponse<LandingNodePlanResponse>> {
  return apiFetch<LandingNodePlanResponse>(`/api/vps/${serverId}/landing-node-plan`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export async function createLandingNodeExecution(
  serverId: string,
  payload: LandingNodeCreateRequest,
  csrfToken: string,
): Promise<ApiResponse<LandingNodeCreateResponse>> {
  return apiFetch<LandingNodeCreateResponse>(`/api/vps/${serverId}/landing-node-create`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export async function createTransitWorkerBootstrap(
  payload: TransitWorkerBootstrapRequest,
  csrfToken: string,
): Promise<ApiResponse<TransitWorkerBootstrapResult>> {
  return apiFetch<TransitWorkerBootstrapResult>("/api/transit-resources/worker-bootstrap", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export async function regenerateTransitWorkerBootstrap(
  resourceId: string,
  payload: TransitWorkerBootstrapRegenerateRequest,
  csrfToken: string,
): Promise<ApiResponse<TransitWorkerBootstrapResult>> {
  return apiFetch<TransitWorkerBootstrapResult>(`/api/transit-resources/${resourceId}/worker-bootstrap/regenerate`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export type CsrfResult = {
  csrf_token: string;
};

export type AuthUser = {
  admin_id: string;
  username: string;
};

export const AUTH_EXPIRED_EVENT = "livelines:auth-expired";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

function notifyAuthExpired(path: string, status: number) {
  if (
    typeof window !== "undefined" &&
    status === 401 &&
    !path.startsWith("/api/auth/")
  ) {
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<ApiResponse<T>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  notifyAuthExpired(path, response.status);
  return response.json() as Promise<ApiResponse<T>>;
}

export async function apiFormFetch<T>(
  path: string,
  formData: FormData,
  init: RequestInit = {},
): Promise<ApiResponse<T>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    method: init.method ?? "POST",
    body: formData,
    credentials: "include",
    headers: {
      ...(init.headers ?? {}),
    },
  });

  notifyAuthExpired(path, response.status);
  return response.json() as Promise<ApiResponse<T>>;
}

export async function requestReadonlyPreflightPlan(
  payload: ReadonlyPreflightPlanRequest,
): Promise<ApiResponse<ReadonlyPreflightPlanResponse>> {
  return apiFetch<ReadonlyPreflightPlanResponse>("/api/transit-routes/readonly-preflight-plan", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createTransitReadonlyPreflightCommand(
  payload: TransitReadonlyPreflightCommandRequest,
  csrfToken: string,
): Promise<ApiResponse<TransitReadonlyPreflightCommandResponse>> {
  return apiFetch<TransitReadonlyPreflightCommandResponse>("/api/transit-routes/readonly-preflight-command", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}

export async function exportNodeShareLink(
  nodeId: string,
  csrfToken: string,
  reason = "client_import",
): Promise<ApiResponse<NodeShareLinkExportResult>> {
  return apiFetch<NodeShareLinkExportResult>(`/api/nodes/${nodeId}/share-link/export`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ confirm_export: true, reason }),
  });
}
