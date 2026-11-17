import { api } from "./api";

export interface AdminSession {
  authenticated: true;
  username: string;
  csrf_token: string;
  expires_in: number;
}

export interface AdminLoginRequest {
  username: string;
  password: string;
}

export async function fetchAdminSession(): Promise<AdminSession> {
  const response = await api.get<AdminSession>("/api/admin/auth/session");
  return response.data;
}

export async function loginAdmin(
  credentials: AdminLoginRequest,
): Promise<AdminSession> {
  const response = await api.post<AdminSession>(
    "/api/admin/auth/login",
    credentials,
  );
  return response.data;
}

export async function logoutAdmin(csrfToken: string): Promise<void> {
  await api.post(
    "/api/admin/auth/logout",
    {},
    { headers: { "X-CSRF-Token": csrfToken } },
  );
}
