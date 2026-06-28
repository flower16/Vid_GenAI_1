import {
  Paper, Typography, Box, Divider, Chip, Stack,
  Table, TableBody, TableCell, TableHead, TableRow,
} from "@mui/material";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeQuartz } from "ag-grid-community";
import type { Account, CoverageResult, Customer, DeterminationResponse } from "../types";

// AG Grid v33 requires explicit module registration; without it the grid
// renders no rows. Theming also moved to the JS Theming API (themeQuartz),
// which replaces the legacy `ag-theme-quartz` CSS import + className.
ModuleRegistry.registerModules([AllCommunityModule]);

const SMDIA = 250000;
const money = (v: string | number) => `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

// Coverage results that carry a per-owner aggregation (SGL / JNT / CRA).
type OwnerShares = Record<string, string>;
type OwnerNames = Record<string, string>;
const ownerShares = (r: CoverageResult): OwnerShares | undefined =>
  (r.evidence as { owner_shares?: OwnerShares })?.owner_shares;
const ownerNames = (r: CoverageResult): OwnerNames =>
  (r.evidence as { owner_names?: OwnerNames })?.owner_names ?? {};

// Trust (TST) evidence: grantors (owners) + beneficiaries, with display names.
interface GrantorCoverage {
  grantor: string; trust_interest: string; coverage_limit: string;
  insured: string; uninsured: string;
}
interface PairCoverage {
  grantor: string; beneficiary: string; allocated: string;
  insured: string; uninsured: string; counted?: boolean;
}
interface TrustEvidence {
  owners: string[];
  beneficiaries: string[];
  owner_names?: OwnerNames;
  beneficiary_names?: OwnerNames;
  grantors_count?: number;
  eligible_beneficiaries?: number;
  grantor_coverage?: GrantorCoverage[];
  pair_coverage?: PairCoverage[];
}
const trustEvidence = (r: CoverageResult): TrustEvidence | undefined => {
  const e = r.evidence as unknown as TrustEvidence;
  return e && Array.isArray(e.beneficiaries) ? e : undefined;
};
const named = (ids: string[], names: OwnerNames = {}) =>
  ids.map((id) => names[id] || id);

// Pass-through (EBP / ANC / DIT / PBA): plan owner + per-participant coverage.
interface ParticipantCoverage {
  participant: string; allocated: string; insured: string; uninsured: string;
}
interface ParticipantEvidence {
  participant_coverage?: ParticipantCoverage[];
  plan_owner?: string;
  equal_split?: boolean;
}
const participantEvidence = (r: CoverageResult): ParticipantEvidence | undefined => {
  const e = r.evidence as unknown as ParticipantEvidence;
  return e && Array.isArray(e.participant_coverage) && e.participant_coverage.length
    ? e : undefined;
};
// Owner role per ORC (shown as "<label> (owner)").
const OWNER_LABEL: Record<string, string> = {
  EBP: "Plan / Employer", ANC: "Insurance Company", DIT: "Trustee (IDI)",
  PBA: "Bond Issuer", MSA: "Mortgagee (Servicer)", BIA: "Custodian / Agent",
};
// Pass-through party role per ORC (the participant-table column header).
const PARTY_LABEL: Record<string, string> = {
  EBP: "Plan Participant", ANC: "Annuitant", DIT: "Trust Beneficiary",
  PBA: "Bondholder", MSA: "Mortgagor", BIA: "Native American",
};

interface Props {
  result: DeterminationResponse;
  accounts?: Account[];
  customer?: Customer;
}

export default function EvidencePanel({ result, accounts = [], customer }: Props) {
  const cov = result.coverage_results;

  // Owners for an account: explicit owners (JNT/TST), else the customer (single
  // ownership — the account holder is the owner).
  const customerName =
    [customer?.first_name, customer?.last_name].filter(Boolean).join(" ") ||
    customer?.customer_id ||
    "—";
  const ownersOf = (a: Account): string =>
    a.owners && a.owners.length
      ? a.owners.map((o) => o.name).join(", ")
      : customerName;
  const listNames = (xs?: { name: string }[]) =>
    xs && xs.length ? xs.map((x) => x.name).join(", ") : "—";

  return (
    <Paper sx={{ p: 2, mt: 2 }}>
      <Typography variant="h5" gutterBottom>Calculation Evidence</Typography>

      {/* Accounts & Parties — every submitted account and its parties */}
      {accounts.length > 0 && (
        <Section title="Accounts & Parties">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Account #</TableCell>
                <TableCell>ORC</TableCell>
                <TableCell>Product</TableCell>
                <TableCell align="right">Balance</TableCell>
                <TableCell>Owner(s)</TableCell>
                <TableCell>Beneficiaries</TableCell>
                <TableCell>Participants</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {accounts.map((a, i) => (
                <TableRow key={i}>
                  <TableCell>{a.account_number}</TableCell>
                  <TableCell><Chip size="small" label={a.orc} /></TableCell>
                  <TableCell>{a.product_type}</TableCell>
                  <TableCell align="right">{money(a.balance)}</TableCell>
                  <TableCell>{ownersOf(a)}</TableCell>
                  <TableCell>{listNames(a.beneficiaries)}</TableCell>
                  <TableCell>{listNames(a.participants)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}

      {/* Rules Applied */}
      <Section title="Rules Applied">
        {Object.entries(result.applicable_rules).map(([orc, r]: [string, any]) => (
          <Box key={orc} mb={1}>
            <Chip label={`${orc} — ${r.name}`} color="primary" size="small" />{" "}
            <Typography variant="caption">SMDIA: {r.smdia} · {r.citation}</Typography>
          </Box>
        ))}
      </Section>

      {/* Aggregation + Coverage grid */}
      <Section title="Aggregation & Coverage">
        <div style={{ width: "100%", height: 220 }}>
          <AgGridReact
            theme={themeQuartz}
            rowData={cov}
            columnDefs={[
              { headerName: "ORC", field: "orc", width: 90 },
              { headerName: "Accounts", valueGetter: (p) => p.data?.accounts_included.length ?? 0, width: 110 },
              { headerName: "Aggregated PI", field: "aggregated_pi", valueFormatter: (p) => money(p.value) },
              { headerName: "Coverage Limit", field: "coverage_limit", valueFormatter: (p) => money(p.value) },
              { headerName: "Insured", field: "insured_amount", valueFormatter: (p) => money(p.value) },
              { headerName: "Uninsured", field: "uninsured_amount", valueFormatter: (p) => money(p.value) },
            ]}
          />
        </div>
      </Section>

      {/* Per-owner allocation (SGL / JNT / CRA) — how much each owner is insured */}
      {cov.some((r) => ownerShares(r)) && (
        <Section title="Per-Owner Allocation (Insured vs Uninsured)">
          {cov.map((r, i) => {
            const shares = ownerShares(r);
            if (!shares) return null;
            const names = ownerNames(r);
            return (
              <Box key={i} mb={1.5}>
                <Typography variant="subtitle2" gutterBottom>
                  {r.orc} — each owner insured up to SMDIA ({money(SMDIA)})
                </Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Owner</TableCell>
                      <TableCell align="right">Aggregated Share</TableCell>
                      <TableCell align="right">Insured</TableCell>
                      <TableCell align="right">Uninsured</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {Object.entries(shares).map(([owner, shareStr]) => {
                      const share = Number(shareStr);
                      const insured = Math.min(share, SMDIA);
                      const uninsured = share - insured;
                      return (
                        <TableRow key={owner}>
                          <TableCell>{names[owner] || owner}</TableCell>
                          <TableCell align="right">{money(share)}</TableCell>
                          <TableCell align="right" sx={{ color: "success.main", fontWeight: 600 }}>
                            {money(insured)}
                          </TableCell>
                          <TableCell align="right" sx={{ color: uninsured > 0 ? "error.main" : "text.secondary" }}>
                            {money(uninsured)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Box>
            );
          })}
        </Section>
      )}

      {/* Trust (TST) — grantors (owners) and beneficiaries */}
      {cov.some((r) => trustEvidence(r)) && (
        <Section title="Trust — Grantors & Beneficiaries">
          {cov.map((r, i) => {
            const t = trustEvidence(r);
            if (!t) return null;
            const grantors = named(t.owners, t.owner_names);
            const benes = named(t.beneficiaries, t.beneficiary_names);
            return (
              <Box key={i} mb={1.5}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Owners / Grantors ({grantors.length})</TableCell>
                      <TableCell>
                        Beneficiaries ({benes.length}; {t.eligible_beneficiaries ?? Math.min(benes.length, 5)} counted, max 5)
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      {/* one cell: the full list of owners */}
                      <TableCell sx={{ verticalAlign: "top" }}>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          {grantors.map((n, k) => (
                            <Chip key={k} size="small" color="primary" variant="outlined" label={n} />
                          ))}
                        </Stack>
                      </TableCell>
                      {/* one cell: the full list of beneficiaries */}
                      <TableCell sx={{ verticalAlign: "top" }}>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          {benes.map((n, k) => (
                            <Chip key={k} size="small" color="secondary" variant="outlined" label={n} />
                          ))}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
                <Typography variant="body2" fontFamily="monospace" mt={1} mb={1}>
                  Coverage = {t.grantors_count ?? grantors.length} grantor(s) ×{" "}
                  {t.eligible_beneficiaries ?? Math.min(benes.length, 5)} beneficiary(ies)
                  (≤5) × {money(SMDIA)} = {money(r.coverage_limit)} limit · Insured{" "}
                  {money(r.insured_amount)} · Uninsured {money(r.uninsured_amount)}
                </Typography>

                {/* Coverage for each grantor */}
                {t.grantor_coverage && t.grantor_coverage.length > 0 && (
                  <Box mb={1}>
                    <Typography variant="subtitle2" gutterBottom>Coverage per Grantor</Typography>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Grantor</TableCell>
                          <TableCell align="right">Trust Interest</TableCell>
                          <TableCell align="right">Limit (≤5×SMDIA)</TableCell>
                          <TableCell align="right">Insured</TableCell>
                          <TableCell align="right">Uninsured</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {t.grantor_coverage.map((g, k) => (
                          <TableRow key={k}>
                            <TableCell>{g.grantor}</TableCell>
                            <TableCell align="right">{money(g.trust_interest)}</TableCell>
                            <TableCell align="right">{money(g.coverage_limit)}</TableCell>
                            <TableCell align="right" sx={{ color: "success.main", fontWeight: 600 }}>{money(g.insured)}</TableCell>
                            <TableCell align="right" sx={{ color: Number(g.uninsured) > 0 ? "error.main" : "text.secondary" }}>{money(g.uninsured)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                )}

                {/* Coverage for each grantor × beneficiary pair (each up to SMDIA) */}
                {t.pair_coverage && t.pair_coverage.length > 0 && (
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      Coverage per Grantor–Beneficiary (each up to {money(SMDIA)}; max 5 per grantor)
                    </Typography>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Grantor</TableCell>
                          <TableCell>Beneficiary</TableCell>
                          <TableCell align="right">Allocated</TableCell>
                          <TableCell align="right">Insured</TableCell>
                          <TableCell align="right">Uninsured</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {t.pair_coverage.map((p, k) => {
                          const excluded = p.counted === false;
                          return (
                            <TableRow key={k} sx={excluded ? { opacity: 0.6, bgcolor: "action.hover" } : undefined}>
                              <TableCell>{p.grantor}</TableCell>
                              <TableCell>
                                {p.beneficiary}
                                {excluded && (
                                  <Chip size="small" color="warning" variant="outlined" sx={{ ml: 1 }}
                                    label="not counted (>5)" />
                                )}
                              </TableCell>
                              <TableCell align="right">{money(p.allocated)}</TableCell>
                              <TableCell align="right" sx={{ color: excluded ? "text.disabled" : "success.main", fontWeight: 600 }}>{money(p.insured)}</TableCell>
                              <TableCell align="right" sx={{ color: Number(p.uninsured) > 0 ? "error.main" : "text.secondary" }}>{money(p.uninsured)}</TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </Box>
                )}
              </Box>
            );
          })}
        </Section>
      )}

      {/* Plan / pass-through participants (EBP, ANC, DIT, PBA) */}
      {cov.some((r) => participantEvidence(r)) && (
        <Section title="Plan / Pass-Through Participants">
          {cov.map((r, i) => {
            const p = participantEvidence(r);
            if (!p) return null;
            const ownerLabel = OWNER_LABEL[r.orc] ?? "Account Holder";
            return (
              <Box key={i} mb={1.5}>
                <Typography variant="subtitle2" gutterBottom>
                  {r.orc} — {ownerLabel} (owner): <b>{customerName}</b>
                  {p.equal_split && " · interests split equally (amounts not provided)"}
                </Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{PARTY_LABEL[r.orc] ?? "Participant"}</TableCell>
                      <TableCell align="right">Allocated Interest</TableCell>
                      <TableCell align="right">Insured (≤ SMDIA)</TableCell>
                      <TableCell align="right">Uninsured</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {p.participant_coverage!.map((pc, k) => (
                      <TableRow key={k}>
                        <TableCell>{pc.participant}</TableCell>
                        <TableCell align="right">{money(pc.allocated)}</TableCell>
                        <TableCell align="right" sx={{ color: "success.main", fontWeight: 600 }}>{money(pc.insured)}</TableCell>
                        <TableCell align="right" sx={{ color: Number(pc.uninsured) > 0 ? "error.main" : "text.secondary" }}>{money(pc.uninsured)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Typography variant="body2" fontFamily="monospace" mt={1}>
                  Pass-through: each participant insured up to {money(SMDIA)} · Total insured{" "}
                  {money(r.insured_amount)} · Uninsured {money(r.uninsured_amount)}
                </Typography>
              </Box>
            );
          })}
        </Section>
      )}

      {/* Calculation Formula + AI Reasoning */}
      <Section title="Calculation Formula & AI Reasoning">
        {cov.map((r, i) => (
          <Box key={i} mb={1.5}>
            <Typography variant="subtitle2">{r.orc}</Typography>
            <Typography variant="body2" fontFamily="monospace">
              Total PI = {money(r.aggregated_pi)} · Limit = {money(r.coverage_limit)} ·
              Insured = {money(r.insured_amount)} · Uninsured = {money(r.uninsured_amount)}
            </Typography>
            <Typography variant="body2" color="text.secondary">{r.rationale}</Typography>
          </Box>
        ))}
      </Section>

      {/* Pending */}
      {result.pending_decisions.some((d) => d.is_pending) && (
        <Section title="Pending File">
          <Stack direction="row" spacing={1} flexWrap="wrap">
            {result.pending_decisions.filter((d) => d.is_pending).map((d, i) => (
              <Chip key={i} color="warning" label={`${d.reason}: ${d.account_number ?? "customer"} — ${d.detail}`} />
            ))}
          </Stack>
        </Section>
      )}

      {/* Evals */}
      <Section title="Evals">
        <Stack direction="row" spacing={1} flexWrap="wrap">
          {result.eval_results.map((e, i) => (
            <Chip key={i} label={`${e.name}: ${e.status}`}
              color={e.status === "PASS" ? "success" : e.status === "FAIL" ? "error" : "warning"} />
          ))}
        </Stack>
      </Section>
    </Paper>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box mb={2}>
      <Typography variant="h6" sx={{ mt: 1 }}>{title}</Typography>
      <Divider sx={{ mb: 1 }} />
      {children}
    </Box>
  );
}
