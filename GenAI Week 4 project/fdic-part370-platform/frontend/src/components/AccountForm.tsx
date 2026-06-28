import {
  Grid, TextField, MenuItem, Typography, Paper, Box, Chip, IconButton, Stack,
  FormControlLabel, Checkbox,
} from "@mui/material";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import type { Account, ORCCode } from "../types";
import { ORC_OPTIONS } from "../types";

interface Props {
  account: Account;
  onChange: (a: Account) => void;
  index?: number;
  onRemove?: () => void;
}

// DP_Prod_Cat values per FDIC IT Functional Guide, Appendix A (Account File #4).
const PRODUCT_TYPES: { code: string; label: string }[] = [
  { code: "DDA", label: "DDA — Demand Deposit (checking)" },
  { code: "NOW", label: "NOW — Negotiable Order of Withdrawal" },
  { code: "SAV", label: "SAV — Savings" },
  { code: "MMA", label: "MMA — Money Market Deposit" },
  { code: "CDS", label: "CDS — Time Deposit / Certificate of Deposit" },
];

// Party inputs to show per ORC, with role-specific labels. The list that
// drives coverage is set on the backend (ORC_CONFIG.pass_through_source):
// owners for GOV/CRA, participants for EBP/MSA/PBA, beneficiaries for ANC/DIT/BIA.
type Role = "owners" | "beneficiaries" | "participants";
const ORC_PARTY_FIELDS: Record<ORCCode, Partial<Record<Role, string>>> = {
  SGL: {},
  JNT: { owners: "Co-Owners" },
  TST: { owners: "Grantors", beneficiaries: "Beneficiaries (≤5 → $1.25M cap)" },
  CRA: { owners: "Retirees / Account Holders" },
  EBP: { participants: "Plan Participants" },
  BUS: { owners: "Business Owners" },
  GOV1: { owners: "Official Custodians", beneficiaries: "Public Unit" },
  GOV2: { owners: "Official Custodians", beneficiaries: "Public Unit" },
  GOV3: { owners: "Official Custodians", beneficiaries: "Public Unit" },
  MSA: { owners: "Mortgagees (Servicer/Lender)", participants: "Mortgagors" },
  PBA: { participants: "Bondholders" },
  DIT: { owners: "Owners", beneficiaries: "Beneficiaries" },
  ANC: { owners: "Insurance Company / Owners", beneficiaries: "Annuitants / Beneficiaries" },
  BIA: { owners: "Owners", participants: "Bondholders", beneficiaries: "Native American Beneficiaries" },
  DOE: { owners: "IDI / Owners", beneficiaries: "Beneficiaries" },
};
const PARTY_ROLES: Role[] = ["owners", "beneficiaries", "participants"];

export default function AccountForm({ account, onChange, index, onRemove }: Props) {
  const set = (k: keyof Account) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = ["balance", "accrued_interest", "hold_amount"].includes(k as string)
      ? Number(e.target.value) : e.target.value;
    onChange({ ...account, [k]: v });
  };

  const csvToList = (csv: string, kind: "owners" | "beneficiaries" | "participants") => {
    const items = csv.split(",").map((s) => s.trim()).filter(Boolean).map((entry, i) => {
      const party_id = `${kind[0].toUpperCase()}${i + 1}`;
      if (kind === "participants") {
        // Accept "Name:Amount" (e.g. "Alice:200000"); amount optional.
        const [name, amt] = entry.split(":").map((s) => s.trim());
        return { party_id, name, vested_interest: Number(amt) || 0 };
      }
      if (kind === "beneficiaries") return { party_id, name: entry, interest_pct: 0 };
      return { party_id, name: entry, ownership_pct: 0 };
    });
    onChange({ ...account, [kind]: items } as Account);
  };

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
        <Typography variant="subtitle1" fontWeight={600}>
          Account {index !== undefined ? index + 1 : ""}{" "}
          <Chip size="small" label={account.product_type} sx={{ ml: 1 }} />
        </Typography>
        {onRemove && (
          <IconButton size="small" color="error" onClick={onRemove} aria-label="remove account">
            <DeleteOutlineIcon />
          </IconButton>
        )}
      </Stack>
      <Grid container spacing={2}>
        <Grid item xs={6} md={3}><TextField fullWidth label="Account Number" value={account.account_number} onChange={set("account_number")} /></Grid>
        <Grid item xs={6} md={3}>
          <TextField select fullWidth label="Product Type" value={account.product_type}
            onChange={(e) => onChange({ ...account, product_type: e.target.value })}>
            {PRODUCT_TYPES.map((p) => <MenuItem key={p.code} value={p.code}>{p.label}</MenuItem>)}
          </TextField>
        </Grid>
        <Grid item xs={6} md={2}><TextField fullWidth type="number" label="Balance" value={account.balance} onChange={set("balance")} /></Grid>
        <Grid item xs={6} md={2}><TextField fullWidth type="number" label="Accrued Interest" value={account.accrued_interest} onChange={set("accrued_interest")} /></Grid>
        <Grid item xs={6} md={2}><TextField fullWidth type="number" label="Hold Amount" value={account.hold_amount} onChange={set("hold_amount")} /></Grid>
        <Grid item xs={6} md={3}>
          <TextField select fullWidth label="ORC" value={account.orc}
            onChange={(e) => onChange({ ...account, orc: e.target.value as ORCCode })}>
            {ORC_OPTIONS.map((o) => <MenuItem key={o.code} value={o.code}>{o.label}</MenuItem>)}
          </TextField>
        </Grid>

        {/* Dynamic party fields based on ORC selection */}
        {PARTY_ROLES.map((role) => {
          const label = ORC_PARTY_FIELDS[account.orc][role];
          if (!label) return null;
          const helper = role === "participants"
            ? "Name:Amount, comma-separated — amount optional (omit → split equally)"
            : "comma-separated names";
          return (
            <Grid item xs={12} md={6} key={role}>
              <TextField fullWidth label={label} helperText={helper}
                onChange={(e) => csvToList(e.target.value, role)} />
            </Grid>
          );
        })}

        {/* BUS (12 CFR 330.11) eligibility — only relevant for business entities */}
        {account.orc === "BUS" && (
          <>
            <Grid item xs={12} md={6}>
              <TextField select fullWidth label="Independent Activity (§330.11)"
                helperText="Drives BUS coverage treatment"
                disabled={!!account.sole_proprietorship}
                value={account.independent_activity === true ? "YES"
                  : account.independent_activity === false ? "NO" : "ASSUMED"}
                onChange={(e) => {
                  const v = e.target.value;
                  onChange({
                    ...account,
                    independent_activity: v === "YES" ? true : v === "NO" ? false : null,
                  });
                }}>
                <MenuItem value="ASSUMED">Assumed engaged (unconfirmed) → one SMDIA</MenuItem>
                <MenuItem value="YES">Yes — independent activity → one SMDIA</MenuItem>
                <MenuItem value="NO">No — pass through to members (each ≤ SMDIA)</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControlLabel
                control={<Checkbox checked={!!account.sole_proprietorship}
                  onChange={(e) => onChange({ ...account, sole_proprietorship: e.target.checked })} />}
                label="Sole proprietorship → insured as owner's single ownership (SGL)"
              />
            </Grid>
          </>
        )}
      </Grid>
      <Box mt={1}>
        <Chip size="small" label={`PI = ${(Number(account.balance) + Number(account.accrued_interest)).toLocaleString()}`} />
      </Box>
    </Paper>
  );
}
