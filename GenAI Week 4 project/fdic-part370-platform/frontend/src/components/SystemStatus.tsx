import { useEffect, useState } from "react";
import { Chip, Tooltip, Box, Typography } from "@mui/material";
import CloudDoneIcon from "@mui/icons-material/CloudDone";
import { getIntegrations, type IntegrationsHealth } from "../api/client";

const LABELS: Record<string, string> = {
  langsmith: "LangSmith", fireworks: "Fireworks", snowflake: "Snowflake",
  azure_ad: "Azure AD", pinecone: "Pinecone",
};

// Compact integrations indicator for the AppBar. Polls the cheap (non-live)
// health endpoint on mount; the tooltip lists each service's state.
export default function SystemStatus() {
  const [health, setHealth] = useState<IntegrationsHealth | null>(null);

  useEffect(() => {
    getIntegrations(false).then(setHealth).catch(() => setHealth(null));
  }, []);

  if (!health) return null;
  const total = health.integrations.length;

  return (
    <Tooltip
      title={
        <Box>
          <Typography variant="caption" fontWeight={700}>
            Integrations · env {health.environment}
          </Typography>
          {health.integrations.map((s) => (
            <Typography key={s.name} variant="caption" component="div">
              {s.configured ? "✓" : "·"} {LABELS[s.name] ?? s.name}
              {s.configured ? " — configured" : " — not configured"}
            </Typography>
          ))}
        </Box>
      }
    >
      <Chip
        icon={<CloudDoneIcon />}
        label={`Integrations ${health.configured_count}/${total}`}
        size="small"
        sx={{ mr: 2, bgcolor: "rgba(255,255,255,0.16)", color: "#fff",
              "& .MuiChip-icon": { color: "#fff" } }}
      />
    </Tooltip>
  );
}
