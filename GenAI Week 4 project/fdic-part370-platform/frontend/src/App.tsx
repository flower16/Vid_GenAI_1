import { useState } from "react";
import {
  Container, AppBar, Toolbar, Typography, Button, Box, CircularProgress, Alert, Stack,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CustomerForm from "./components/CustomerForm";
import AccountForm from "./components/AccountForm";
import EvidencePanel from "./components/EvidencePanel";
import { runDetermination } from "./api/client";
import type { Account, Customer, DeterminationResponse } from "./types";

const emptyCustomer: Customer = {
  customer_id: "C1001", first_name: "Jane", last_name: "Doe", ssn_tin: "123-45-6789",
  customer_type: "INDIVIDUAL", address: "1 Main St", email: "jane@example.com", phone: "555-0100",
};

// Seeded with one depositor holding multiple single accounts of different
// product types — they aggregate within the SGL ORC for the coverage calc.
const seedAccounts = (): Account[] => [
  acct("ACCT-1", "DDA", 100000),
  acct("ACCT-2", "SAV", 80000),
  acct("ACCT-3", "CDS", 120000),
  acct("ACCT-4", "MMA", 50000),
];

function acct(account_number: string, product_type: string, balance: number): Account {
  return {
    account_number, customer_id: "C1001", product_type, balance,
    accrued_interest: 0, hold_amount: 0, orc: "SGL",
    owners: [], beneficiaries: [], participants: [],
  };
}

export default function App() {
  const [customer, setCustomer] = useState<Customer>(emptyCustomer);
  const [accounts, setAccounts] = useState<Account[]>(seedAccounts());
  const [result, setResult] = useState<DeterminationResponse | null>(null);
  // Snapshot of exactly what was submitted, so the evidence reflects the run
  // (not later edits to the form).
  const [submitted, setSubmitted] = useState<{ accounts: Account[]; customer: Customer } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateAccount = (i: number, a: Account) =>
    setAccounts((prev) => prev.map((x, k) => (k === i ? a : x)));
  const removeAccount = (i: number) =>
    setAccounts((prev) => prev.filter((_, k) => k !== i));
  const addAccount = () =>
    setAccounts((prev) => [...prev, acct(`ACCT-${prev.length + 1}`, "DDA", 0)]);

  const totalPI = accounts.reduce(
    (s, a) => s + Number(a.balance) + Number(a.accrued_interest), 0
  );

  const onCalculate = async () => {
    setLoading(true); setError(null);
    try {
      const withCust = accounts.map((a) => ({ ...a, customer_id: customer.customer_id }));
      setResult(await runDetermination(customer, withCust));
      setSubmitted({ accounts: withCust, customer });
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            FDIC Part 370 — Insurance Determination Platform
          </Typography>
          <Typography variant="caption">Agentic AI · LangGraph</Typography>
        </Toolbar>
      </AppBar>
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <CustomerForm customer={customer} onChange={setCustomer} />

        <Stack direction="row" alignItems="center" justifyContent="space-between" mb={1}>
          <Typography variant="h6">Accounts ({accounts.length})</Typography>
          <Box>
            <Typography variant="caption" sx={{ mr: 2 }}>
              Total P&amp;I: ${totalPI.toLocaleString()}
            </Typography>
            <Button startIcon={<AddIcon />} variant="outlined" size="small" onClick={addAccount}>
              Add Account
            </Button>
          </Box>
        </Stack>

        {accounts.map((a, i) => (
          <AccountForm
            key={i}
            index={i}
            account={a}
            onChange={(next) => updateAccount(i, next)}
            onRemove={accounts.length > 1 ? () => removeAccount(i) : undefined}
          />
        ))}

        <Box display="flex" alignItems="center" gap={2} mt={1}>
          <Button variant="contained" size="large" onClick={onCalculate} disabled={loading}>
            {loading ? <CircularProgress size={22} /> : "Calculate Coverage"}
          </Button>
          {result && <Typography variant="caption">Determination {result.determination_id}</Typography>}
        </Box>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        {result && (
          <EvidencePanel
            result={result}
            accounts={submitted?.accounts ?? []}
            customer={submitted?.customer ?? customer}
          />
        )}
      </Container>
    </>
  );
}
