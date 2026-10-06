import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { ApiErrorPayload, TokenPair } from "./types";

const ACCESS_KEY = "registry.access_token";
const REFRESH_KEY = "registry.refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function storeTokens(tokens: TokenPair): void {
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export const api = axios.create({ baseURL: "/api/v1" });

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Single-flight refresh: a burst of 401s must trigger one refresh, not N. */
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return null;
  try {
    // Deliberately uses the plain axios instance so the interceptor below does
    // not try to refresh with an already-dead access token.
    const { data } = await axios.post<TokenPair>("/api/v1/auth/refresh", { refresh_token });
    storeTokens(data);
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

api.interceptors.response.use(undefined, async (error: AxiosError) => {
  const config = error.config as RetriableConfig | undefined;
  const unauthorized = error.response?.status === 401;

  if (!config || !unauthorized || config._retried) {
    throw error;
  }
  // A refresh endpoint that itself 401s must not loop.
  if (config.url?.includes("/auth/login") || config.url?.includes("/auth/refresh")) {
    throw error;
  }

  config._retried = true;
  refreshInFlight ??= refreshAccessToken().finally(() => {
    refreshInFlight = null;
  });
  const token = await refreshInFlight;
  if (!token) {
    window.dispatchEvent(new Event("registry:signed-out"));
    throw error;
  }
  config.headers.Authorization = `Bearer ${token}`;
  return api.request(config);
});

/** Turn any thrown value into Arabic text a user can act on. */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as ApiErrorPayload | undefined;
    if (payload) {
      if (typeof payload.detail === "string") return payload.detail;
      if (Array.isArray(payload.detail)) {
        return payload.detail.map((item) => item.message).join("، ");
      }
      if (payload.errors?.length) return payload.errors.map((item) => item.message).join("، ");
    }
    if (!error.response) return "تعذّر الوصول إلى الخادم";
  }
  if (error instanceof Error && error.message) return error.message;
  return "حدث خطأ غير متوقع";
}
