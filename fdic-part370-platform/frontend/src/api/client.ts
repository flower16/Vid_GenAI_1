import axios from "axios";
import type { Account, Customer, DeterminationResponse } from "../types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
});

// Attach Azure AD bearer token (injected by MSAL acquireTokenSilent).
export function setAuthToken(token: string) {
  api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
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
