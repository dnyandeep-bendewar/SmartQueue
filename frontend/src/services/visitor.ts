import { api } from "./api";

export type ServiceType =
  | "Certificate"
  | "Fee Payment"
  | "General Enquiry"
  | "Admission";

export type TokenStatus = "Waiting" | "Serving" | "Served";

export interface PublicCounter {
  counter_id: number;
  counter_name: string;
  service_type: ServiceType;
  people_waiting: number;
  active_counters: number;
  avg_service_time: number;
  prediction: {
    counter_id: number;
    predicted_wait_minutes: number | null;
    available: boolean;
    error_code?: "prediction_unavailable" | null;
  };
}

export interface CounterList {
  counters: PublicCounter[];
  recommended_counter_id: number | null;
}

export interface TokenIssueRequest {
  counter_id: number;
  visitor_name?: string;
}

export interface TokenIssue {
  token_number: string;
  tracking_reference: string;
  status: "Waiting";
  queue_position: number | null;
  idempotent_replay?: boolean;
}

export interface TrackedToken {
  token_number: string;
  service_type: ServiceType;
  counter_name: string;
  status: TokenStatus;
  created_at: string;
  queue_position: number | null;
}

export async function fetchServices(): Promise<ServiceType[]> {
  const response = await api.get<{ services: ServiceType[] }>("/api/public/services");
  return response.data.services;
}

export async function fetchCounters(
  serviceType: ServiceType,
): Promise<CounterList> {
  const response = await api.get<CounterList>("/api/public/counters", {
    params: { service_type: serviceType },
  });
  return response.data;
}

export async function issueVisitorToken(
  body: TokenIssueRequest,
  idempotencyKey: string,
): Promise<TokenIssue> {
  const response = await api.post<TokenIssue>("/api/public/tokens", body, {
    headers: { "Idempotency-Key": idempotencyKey },
  });
  return response.data;
}

export async function trackVisitorToken(
  trackingReference: string,
): Promise<TrackedToken> {
  const response = await api.get<TrackedToken>(
    `/api/public/tokens/track/${encodeURIComponent(trackingReference)}`,
  );
  return response.data;
}
