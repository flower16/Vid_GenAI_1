import { PublicClientApplication, type Configuration } from "@azure/msal-browser";

// Azure AD SSO configuration. Populate from environment at build time.
export const msalConfig: Configuration = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID ?? "",
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID ?? "common"}`,
    redirectUri: import.meta.env.VITE_REDIRECT_URI ?? "http://localhost:5173",
  },
  cache: { cacheLocation: "sessionStorage" },
};

export const loginRequest = {
  scopes: [import.meta.env.VITE_API_SCOPE ?? "api://fdic-part370/.default"],
};

export const msalInstance = new PublicClientApplication(msalConfig);
