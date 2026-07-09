import axios from "axios";
import type { Account, Customer, DeterminationResponse } from "../types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
});

// Attach Azure AD bearer token (injected by MSAL acquireTokenSilent). Passing an
// empty token clears the header (used on logout).
export function setAuthToken(token: string) {
  if (token) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common["Authorization"];
  }
}

export interface IntegrationStatus {
  name: string;
  configured: boolean;
  reachable: boolean | null;
  detail: string;
}
export interface IntegrationsHealth {
  environment: string;
  live_checked: boolean;
  configured_count: number;
  integrations: IntegrationStatus[];
}

export async function getIntegrations(live = false): Promise<IntegrationsHealth> {
  const { data } = await api.get<IntegrationsHealth>("/api/v1/health/integrations", {
    params: { live },
  });
  return data;
}

export async function fetchOrcs() {
  const { data } = await api.get<{ code: string; name: string; smdia: string }[]>(
    "/api/v1/orcs"
  );
  return data;
}

export async function runDetermination(
  customer: Customer,
  accounts: Account[],
  altRecordkeepingReceived = true
): Promise<DeterminationResponse> {
  const { data } = await api.post<DeterminationResponse>("/api/v1/determinations", {
    customer,
    accounts,
    alt_recordkeeping_received: altRecordkeepingReceived,
  });
  return data;
}

export async function recalculate(
  determinationId: string,
  customer: Customer,
  accounts: Account[]
): Promise<DeterminationResponse> {
  const { data } = await api.post<DeterminationResponse>(
    `/api/v1/determinations/${determinationId}/recalculate`,
    { customer, accounts, alt_recordkeeping_received: true }
  );
  return data;
}
