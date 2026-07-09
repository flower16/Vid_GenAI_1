import { useEffect, useRef, useState } from "react";
import {
  Autocomplete, TextField, Paper, Stack, Typography, Chip, Alert, CircularProgress, Box,
} from "@mui/material";
import StorageIcon from "@mui/icons-material/Storage";
import {
  searchCustomers, searchAccounts, getCustomerDetail,
  type CustomerSearchResult, type AccountSearchResult,
} from "../api/client";
import type { Account, Customer } from "../types";

interface Props {
  onLoad: (customer: Customer, accounts: Account[]) => void;
}

// Search customers & accounts that already exist in Snowflake and auto-populate
// the determination forms from the selected record.
export default function SnowflakeSearch({ onLoad }: Props) {
  const [custOptions, setCustOptions] = useState<CustomerSearchResult[]>([]);
  const [acctOptions, setAcctOptions] = useState<AccountSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Prime both lists on mount so the dropdowns aren't empty before typing.
  useEffect(() => {
    searchCustomers("").then(setCustOptions).catch(() => {});
    searchAccounts("").then(setAcctOptions).catch(() => {});
  }, []);

  const debounce = (fn: () => void) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(fn, 250);
  };

  const load = async (customerId: string, label: string) => {
    setLoading(true);
    setError(null);
    try {
      const detail = await getCustomerDetail(customerId);
      onLoad(detail.customer, detail.accounts);
      setLoaded(`${label} · ${detail.accounts.length} account(s) loaded from Snowflake`);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: "grey.50" }}>
      <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
        <StorageIcon fontSize="small" color="primary" />
        <Typography variant="subtitle2">Load from Snowflake</Typography>
        {loading && <CircularProgress size={16} />}
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Autocomplete
          sx={{ flex: 1 }}
          options={custOptions}
          getOptionLabel={(o) =>
            `${o.customer_id} — ${o.first_name} ${o.last_name} (${o.customer_type ?? "?"}) · ${o.account_count} acct`
          }
          isOptionEqualToValue={(a, b) => a.customer_id === b.customer_id}
          filterOptions={(x) => x}
          onInputChange={(_, value, reason) => {
            if (reason === "input") debounce(() => searchCustomers(value).then(setCustOptions).catch(() => {}));
          }}
          onChange={(_, value) => {
            if (value) load(value.customer_id, `${value.first_name} ${value.last_name}`);
          }}
          renderInput={(params) => (
            <TextField {...params} label="Search customer (id / name / SSN-TIN)" size="small" />
          )}
        />

        <Autocomplete
          sx={{ flex: 1 }}
          options={acctOptions}
          getOptionLabel={(o) =>
            `${o.account_number} — ${o.orc} · ${o.product_type} · $${o.balance.toLocaleString()} (${o.customer_id})`
          }
          isOptionEqualToValue={(a, b) => a.account_number === b.account_number}
          filterOptions={(x) => x}
          onInputChange={(_, value, reason) => {
            if (reason === "input") debounce(() => searchAccounts(value).then(setAcctOptions).catch(() => {}));
          }}
          onChange={(_, value) => {
            if (value) load(value.customer_id, value.account_number);
          }}
          renderInput={(params) => (
            <TextField {...params} label="Search account (number / ORC)" size="small" />
          )}
        />
      </Stack>

      {loaded && (
        <Box mt={1.5}>
          <Chip color="success" size="small" label={loaded} />
        </Box>
      )}
      {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
    </Paper>
  );
}
