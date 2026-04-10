import { api } from "@/lib/api";

export interface RegisterPayload {
  email: string;
  password: string;
  full_name?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  created_at: string;
}

export const authApi = {
  register: (data: RegisterPayload) =>
    api.post<UserResponse>("/auth/register", data).then((r) => r.data),

  login: (data: LoginPayload) =>
    api.post<LoginResponse>("/auth/login", data).then((r) => r.data),
};
