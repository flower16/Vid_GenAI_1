import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import { MsalProvider } from "@azure/msal-react";
import App from "./App";
import { msalInstance } from "./auth/msalConfig";
import { AuthProvider } from "./auth/AuthContext";

const theme = createTheme({ palette: { mode: "light", primary: { main: "#0b3d91" } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <MsalProvider instance={msalInstance}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MsalProvider>
    </ThemeProvider>
  </React.StrictMode>
);
