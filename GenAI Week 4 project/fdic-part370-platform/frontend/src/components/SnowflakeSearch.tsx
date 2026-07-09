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
// Fetch a generous page so the initial (empty-query) dropdown isn't truncated
// alphabetically — otherwise later ORCs (SGL, JNT, TST, MSA, PBA) get cut off.
const SEARCH_LIMIT = 100;

export default function SnowflakeSearch({ onLoad }: Props) {
  const [custOptions, setCustOptions] = useState<CustomerSearchResult[]>([]);
  const [acctOptions, setAcctOptions] = useState<AccountSearchResult[]>([]);
  const [custValue, setCustValue] = useState<CustomerSearchResult | null>(null);
  const [acctValue, setAcctValue] = useState<AccountSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Prime both lists on mount so the dropdowns aren't empty before typing.
  useEffect(() => {
    searchCustomers("", SEARCH_LIMIT).then(setCustOptions).catch(() => {});
    searchAccounts("", SEARCH_LIMIT).then(setAcctOptions).catch(() => {});
  }, []);

  const debounce = (fn: () => void) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(fn, 250);
  };

  // Restrict the account dropdown to a single customer (or all when cleared).
  const refreshAccounts = (customerId?: string) =>
    searchAccounts("", SEARCH_LIMIT, customerId).then(setAcctOptions).catch(() => {});

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

  const onCustomerChange = (value: CustomerSearchResult | null) => {
    setCustValue(value);
    setAcctValue(null); // clear any account picked for the previous customer
    // Scope the account dropdown to this customer (or reset to all when cleared).
    refreshAccounts(value?.customer_id);
    if (value) load(value.customer_id, `${value.first_name} ${value.last_name}`);
  };

  const onAccountChange = (value: AccountSearchResult | null) => {
    setAcctValue(value);
    if (!value) return;
    // Keep the customer selection in sync so the scope reflects the pick.
    const cust = custOptions.find((c) => c.customer_id === value.customer_id) ?? null;
    if (cust && cust.customer_id !== custValue?.customer_id) {
      setCustValue(cust);
      refreshAccounts(cust.customer_id);
    }
    load(value.customer_id, value.account_number);
  };

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 2, bgcolor: "grey.50" }}>
      <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
        <StorageIcon fontSize="small" color="primary" />
        <Typography variant="subtitle2">Load from Snowflake</Typography>
        {loading && <CircularProgress size={16} />}
        {custValue && (
          <Chip size="small" variant="outlined"
            label={`accounts scoped to ${custValue.customer_id}`} />
        )}
      </Stack>

      <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
        <Autocomplete
          sx={{ flex: 1 }}
          options={custOptions}
          value={custValue}
          getOptionLabel={(o) =>
            `${o.customer_id} — ${o.first_name} ${o.last_name} (${o.customer_type ?? "?"}) · ${o.account_count} acct`
          }
          isOptionEqualToValue={(a, b) => a.customer_id === b.customer_id}
          filterOptions={(x) => x}
          onInputChange={(_, value, reason) => {
            if (reason === "input") debounce(() => searchCustomers(value, SEARCH_LIMIT).then(setCustOptions).catch(() => {}));
          }}
          onChange={(_, value) => onCustomerChange(value)}
          renderInput={(params) => (
            <TextField {...params} label="Search customer (id / name / SSN-TIN)" size="small" />
          )}
        />

        <Autocomplete
          sx={{ flex: 1 }}
          options={acctOptions}
          value={acctValue}
          getOptionLabel={(o) =>
            `${o.account_number} — ${o.orc} · ${o.product_type} · $${o.balance.toLocaleString()} (${o.customer_id})`
          }
          isOptionEqualToValue={(a, b) => a.account_number === b.account_number}
          filterOptions={(x) => x}
          noOptionsText={custValue ? `No accounts for ${custValue.customer_id}` : "No accounts"}
          onInputChange={(_, value, reason) => {
            if (reason === "input")
              debounce(() =>
                searchAccounts(value, SEARCH_LIMIT, custValue?.customer_id)
                  .then(setAcctOptions).catch(() => {})
              );
          }}
          onChange={(_, value) => onAccountChange(value)}
          renderInput={(params) => (
            <TextField
              {...params}
              label={custValue ? `Account for ${custValue.customer_id}` : "Search account (number / ORC)"}
              size="small"
            />
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
