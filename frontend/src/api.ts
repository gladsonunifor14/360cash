// Cliente HTTP "burro": toda regra de negócio, validação e cálculo acontecem na API.
// O access token fica só em memória; o refresh token em sessionStorage (some ao fechar a aba).

const BASE = (import.meta.env.VITE_API_URL ?? "") + "/v1";
const REFRESH_KEY = "c360.rt";

let accessToken: string | null = null;
let onLogout: () => void = () => {};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function setSession(tokens: { access_token: string; refresh_token: string }) {
  accessToken = tokens.access_token;
  try {
    sessionStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  } catch {
    /* modo privado */
  }
}

export function clearSession() {
  accessToken = null;
  try {
    sessionStorage.removeItem(REFRESH_KEY);
  } catch {
    /* ignore */
  }
}

export function onSessionEnd(fn: () => void) {
  onLogout = fn;
}

function storedRefresh(): string | null {
  try {
    return sessionStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export async function tryRestoreSession(): Promise<boolean> {
  const rt = storedRefresh();
  if (!rt) return false;
  const r = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
  });
  if (!r.ok) {
    clearSession();
    return false;
  }
  setSession(await r.json());
  return true;
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return `Erro ${status}`;
}

export async function api<T = unknown>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const r = await fetch(`${BASE}${path}`, { ...init, headers });
  if (r.status === 401 && retry && storedRefresh()) {
    if (await tryRestoreSession()) return api<T>(path, init, false);
    onLogout();
  }
  const isJson = r.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await r.json() : await r.blob();
  if (!r.ok) throw new ApiError(r.status, errorMessage(body, r.status));
  return body as T;
}

export const post = <T = unknown>(path: string, data?: unknown) =>
  api<T>(path, { method: "POST", body: data instanceof FormData ? data : JSON.stringify(data ?? {}) });

export async function logout() {
  const rt = storedRefresh();
  if (rt) await post("/auth/logout", { refresh_token: rt }).catch(() => undefined);
  clearSession();
}

// ------------------------------------------------------------------ formatação (apenas exibição)

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
export const money = (v: number | string | null | undefined) => brl.format(Number(v ?? 0));
export const pct = (v: number | string | null | undefined) =>
  v === null || v === undefined ? "—" : `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
export const dateBR = (v: string | null | undefined) =>
  v ? new Date(v.length === 10 ? `${v}T00:00:00` : v).toLocaleDateString("pt-BR") : "—";
export const cnpjMask = (v: string) =>
  v.replace(/\D/g, "").replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2}).*/, "$1.$2.$3/$4-$5");

// ------------------------------------------------------------------ tipos de resposta

export type User = { id: string; name: string; email: string; role: "admin" | "contador" | "cliente"; client_id: string | null };
export type Client = {
  id: string; cnpj: string; razao_social: string; nome_fantasia: string | null; regime_tributario: string | null;
  situacao_cadastral: string | null; cnae_principal: string | null; endereco: Record<string, string> | null;
  email: string | null; telefone: string | null;
};
export type ChartAccount = { id: string; code: string; name: string; nature: string; dre_group: string | null };
export type Header = {
  titulo: string; periodo: { inicio: string; fim: string }; gerado_em: string;
  empresa: { razao_social: string; cnpj: string };
  elaborado_por: { razao_social: string; cnpj: string; crc: string | null; responsavel_tecnico: string | null };
};
