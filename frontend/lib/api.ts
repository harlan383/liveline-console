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
  flow: string | null;
  reality_public_key: string | null;
  reality_short_id: string | null;
  reality_server_name: string | null;
  reality_dest: string | null;
  fingerprint: string | null;
  source: string;
  share_link?: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_remote_check_at: string | null;
  last_sync_status: string | null;
};

export type NodeListResult = {
  nodes: NodeData[];
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

export type VpsActionResult = {
  task_id: string;
  vps_id: string;
};

export type CsrfResult = {
  csrf_token: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

  return response.json() as Promise<ApiResponse<T>>;
}
