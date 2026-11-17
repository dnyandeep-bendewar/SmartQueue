import { api } from "./api";
import type { ServiceType, TokenStatus } from "./visitor";

export interface AnalyticsOverview {
  waiting_tokens: number;
  serving_tokens: number;
  currently_served_tokens: number;
  historically_served_visitors: number;
  active_counters: number;
  total_counters: number;
}

export interface DailyTrend {
  served_date: string;
  visitor_count: number;
}

export interface DailyTrendsResponse {
  trends: DailyTrend[];
}

export interface ServiceBreakdownItem {
  service_type: ServiceType;
  status: TokenStatus;
  token_count: number;
}

export interface ServiceBreakdownResponse {
  breakdown: ServiceBreakdownItem[];
}

export interface WaitingTimeObservation {
  recorded_at: string;
  actual_waiting_time: number;
  predicted_waiting_time: number;
}

export interface WaitingTimesResponse {
  observations: WaitingTimeObservation[];
  valid_observation_count: number;
  sufficient_observations: boolean;
  excluded_observation_count: number;
}

export interface CounterEstimate {
  counter_id: number;
  counter_name: string;
  service_type: ServiceType;
  predicted_wait_minutes: number | null;
  available: boolean;
  error_code?: "prediction_unavailable" | null;
}

export interface CounterEstimatesResponse {
  counters: CounterEstimate[];
  recommended_counter_id: number | null;
}

export async function fetchAnalyticsOverview(): Promise<AnalyticsOverview> {
  const response = await api.get<AnalyticsOverview>(
    "/api/admin/analytics/overview",
  );
  return response.data;
}

export async function fetchDailyTrends(): Promise<DailyTrendsResponse> {
  const response = await api.get<DailyTrendsResponse>(
    "/api/admin/analytics/daily-trends",
  );
  return response.data;
}

export async function fetchServiceBreakdown(): Promise<ServiceBreakdownResponse> {
  const response = await api.get<ServiceBreakdownResponse>(
    "/api/admin/analytics/service-breakdown",
  );
  return response.data;
}

export async function fetchWaitingTimes(): Promise<WaitingTimesResponse> {
  const response = await api.get<WaitingTimesResponse>(
    "/api/admin/analytics/waiting-times",
  );
  return response.data;
}

export async function fetchAnalyticsCounterEstimates(): Promise<CounterEstimatesResponse> {
  const response = await api.get<CounterEstimatesResponse>(
    "/api/admin/analytics/counter-estimates",
  );
  return response.data;
}
