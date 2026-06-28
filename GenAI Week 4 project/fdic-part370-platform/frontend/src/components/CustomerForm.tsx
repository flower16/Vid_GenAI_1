import { Grid, TextField, MenuItem, Typography, Paper } from "@mui/material";
import type { Customer } from "../types";

const CUSTOMER_TYPES = ["INDIVIDUAL", "JOINT", "TRUST", "BUSINESS", "GOVERNMENT", "PLAN", "FIDUCIARY", "ESTATE"];

interface Props {
  customer: Customer;
  onChange: (c: Customer) => void;
}

export default function CustomerForm({ customer, onChange }: Props) {
  const set = (k: keyof Customer) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...customer, [k]: e.target.value });

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <Typography variant="h6" gutterBottom>Customer Demographics</Typography>
      <Grid container spacing={2}>
        <Grid item xs={6} md={3}><TextField fullWidth label="Customer ID" value={customer.customer_id} onChange={set("customer_id")} /></Grid>
        <Grid item xs={6} md={3}><TextField fullWidth label="First Name" value={customer.first_name} onChange={set("first_name")} /></Grid>
        <Grid item xs={6} md={3}><TextField fullWidth label="Last Name" value={customer.last_name} onChange={set("last_name")} /></Grid>
        <Grid item xs={6} md={3}><TextField fullWidth label="SSN/TIN" value={customer.ssn_tin} onChange={set("ssn_tin")} /></Grid>
        <Grid item xs={6} md={3}>
          <TextField select fullWidth label="Customer Type" value={customer.customer_type ?? ""} onChange={set("customer_type")}>
            {CUSTOMER_TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </TextField>
        </Grid>
        <Grid item xs={6} md={5}><TextField fullWidth label="Address" value={customer.address} onChange={set("address")} /></Grid>
        <Grid item xs={6} md={2}><TextField fullWidth label="Email" value={customer.email} onChange={set("email")} /></Grid>
        <Grid item xs={6} md={2}><TextField fullWidth label="Phone" value={customer.phone} onChange={set("phone")} /></Grid>
      </Grid>
    </Paper>
  );
}
