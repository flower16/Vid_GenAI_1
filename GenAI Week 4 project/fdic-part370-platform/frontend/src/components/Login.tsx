import { useState } from "react";
import {
  Box, Paper, Typography, Button, TextField, MenuItem, Divider, Stack, Alert,
  Chip, CircularProgress,
} from "@mui/material";
import AccountBalanceIcon from "@mui/icons-material/AccountBalance";
import LoginIcon from "@mui/icons-material/Login";
import { useAuth, type Role } from "../auth/AuthContext";

const ROLES: { value: Role; help: string }[] = [
  { value: "Analyst", help: "Run determinations" },
  { value: "Reviewer", help: "Run + view audit trail" },
  { value: "Admin", help: "Full access incl. RAG seeding" },
];

export default function Login() {
  const { loginSso, loginDemo, azureConfigured, error } = useAuth();
  const [name, setName] = useState("Jane Analyst");
  const [role, setRole] = useState<Role>("Analyst");
  const [busy, setBusy] = useState(false);

  const onSso = async () => {
    setBusy(true);
    try { await loginSso(); } finally { setBusy(false); }
  };

  return (
    <Box
      sx={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        background: "linear-gradient(135deg,#0b3d91 0%,#12326e 60%,#081b3a 100%)", p: 2,
      }}
    >
      <Paper elevation={8} sx={{ p: 4, width: "100%", maxWidth: 420, borderRadius: 3 }}>
        <Stack alignItems="center" spacing={1} mb={2}>
          <AccountBalanceIcon sx={{ fontSize: 44, color: "#0b3d91" }} />
          <Typography variant="h5" fontWeight={700} textAlign="center">
            FDIC Part 370 Platform
          </Typography>
          <Typography variant="body2" color="text.secondary" textAlign="center">
            Agentic AI Insurance Determination — sign in to continue
          </Typography>
        </Stack>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        <Button
          fullWidth variant="contained" size="large" startIcon={busy ? undefined : <LoginIcon />}
          onClick={onSso} disabled={!azureConfigured || busy} sx={{ mb: 1 }}
        >
          {busy ? <CircularProgress size={22} color="inherit" /> : "Sign in with Azure AD (SSO)"}
        </Button>
        {!azureConfigured && (
          <Typography variant="caption" color="text.secondary" component="div" textAlign="center">
            Azure AD not configured — set VITE_AZURE_CLIENT_ID to enable SSO.
          </Typography>
        )}

        <Divider sx={{ my: 2 }}>
          <Chip label="or demo access" size="small" />
        </Divider>

        <Stack spacing={2}>
          <TextField
            label="Display name" size="small" value={name}
            onChange={(e) => setName(e.target.value)} fullWidth
          />
          <TextField
            label="Role (RBAC)" size="small" select value={role}
            onChange={(e) => setRole(e.target.value as Role)} fullWidth
          >
            {ROLES.map((r) => (
              <MenuItem key={r.value} value={r.value}>
                {r.value} — {r.help}
              </MenuItem>
            ))}
          </TextField>
          <Button variant="outlined" size="large" onClick={() => loginDemo(name, role)}>
            Enter demo (local backend)
          </Button>
        </Stack>

        <Typography variant="caption" color="text.secondary" display="block" mt={2} textAlign="center">
          Demo mode maps to the backend's local Admin principal; RBAC roles are enforced
          on the API in production.
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" mt={1} textAlign="center" sx={{ opacity: 0.7 }}>
          build {__BUILD_SHA__} · {new Date(__BUILD_TIME__).toLocaleString()}
        </Typography>
      </Paper>
    </Box>
  );
}
