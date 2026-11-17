import { api } from "./api";
import type { ServiceType, TokenStatus } from "./visitor";

export interface AdminCounter {
  counter_id: number;
  counter_name: string;
  service_type: ServiceType;
  is_active: boolean;
  people_waiting: number;
  active_counters: number;
  avg_service_time: number;
}

export interface CreateCounterRequest {
  counter_name: string;
  service_type: ServiceType;
  active_counters: number;
  avg_service_time: number;
}

export interface UpdateCounterRequest {
  people_waiting: number;
  active_counters: number;
  avg_service_time: number;
  is_active: boolean;
}

export interface AdminToken {
  token_id: number;
  token_number: string;
  service_type: ServiceType;
  counter_name: string;
  status: TokenStatus;
  created_at: string;
}

export interface AdminStatistics {
  waiting_count: number;
  serving_count: number;
  currently_served_count: number;
  historically_served_count: number;
  active_counter_count: number;
}

export interface CounterEstimate {
  counter_id: number;
  counter_name: string;
  service_type: ServiceType;
  predicted_wait_minutes: number | null;
  available: boolean;
  error_code?: "prediction_unavailable" | null;
}

export interface CounterEstimates {
  counters: CounterEstimate[];
  recommended_counter_id: number | null;
}

export async function fetchAdminCounters(): Promise<AdminCounter[]> {
  const response = await api.get<{ counters: AdminCounter[] }>(
    "/api/admin/counters",
  );
  return response.data.counters;
}

export async function createAdminCounter(
  payload: CreateCounterRequest,
  csrfToken: string,
): Promise<AdminCounter> {
  const response = await api.post<AdminCounter>(
    "/api/admin/counters",
    payload,
    { headers: { "X-CSRF-Token": csrfToken } },
  );
  return response.data;
}

export async function updateAdminCounter(
  counterId: number,
  payload: UpdateCounterRequest,
  csrfToken: string,
): Promise<AdminCounter> {
  const response = await api.put<AdminCounter>(
    `/api/admin/counters/${counterId}`,
    payload,
    { headers: { "X-CSRF-Token": csrfToken } },
  );
  return response.data;
}

export async function setAdminCounterStatus(
  counterId: number,
  isActive: boolean,
  csrfToken: string,
): Promise<AdminCounter> {
  const response = await api.patch<AdminCounter>(
    `/api/admin/counters/${counterId}/status`,
    { is_active: isActive },
    { headers: { "X-CSRF-Token": csrfToken } },
  );
  return response.data;
}

export async function fetchAdminTokens(): Promise<AdminToken[]> {
  const response = await api.get<{ tokens: AdminToken[] }>("/api/admin/tokens");
  return response.data.tokens;
}

export async function setAdminTokenStatus(
  tokenId: number,
  status: TokenStatus,
  csrfToken: string,
): Promise<void> {
  await api.patch(
    `/api/admin/tokens/${tokenId}/status`,
    { status },
    { headers: { "X-CSRF-Token": csrfToken } },
  );
}

export async function fetchAdminStatistics(): Promise<AdminStatistics> {
  const response = await api.get<AdminStatistics>("/api/admin/statistics");
  return response.data;
}

export async function fetchCounterEstimates(): Promise<CounterEstimates> {
  const response = await api.get<CounterEstimates>(
    "/api/admin/analytics/counter-estimates",
  );
  return response.data;
}
