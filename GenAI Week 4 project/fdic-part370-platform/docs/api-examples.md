# Sample API Requests & Responses

Base URL (local): `http://localhost:8000`

## 1. List ORCs (UI dropdown)

```http
GET /api/v1/orcs
```
```json
[
  { "code": "SGL", "name": "Single Ownership", "smdia": "$250,000 per owner." },
  { "code": "JNT", "name": "Joint Ownership", "smdia": "$250,000 per co-owner." }
]
```

## 2. Run a determination

```http
POST /api/v1/determinations
Authorization: Bearer <azure-ad-jwt>
Content-Type: application/json
```
```json
{
  "customer": {
    "customer_id": "C1001",
    "first_name": "Jane", "last_name": "Doe",
    "ssn_tin": "123-45-6789", "customer_type": "INDIVIDUAL",
    "address": "1 Main St", "email": "jane@example.com", "phone": "555-0100"
  },
  "accounts": [
    {
      "account_number": "ACCT-1", "customer_id": "C1001",
      "product_type": "DDA", "balance": 350000, "accrued_interest": 0,
      "hold_amount": 0, "orc": "SGL",
      "owners": [], "beneficiaries": [], "participants": []
    }
  ],
  "alt_recordkeeping_received": true
}
```

### Response (abridged)
```json
{
  "determination_id": "b1d2...",
  "customer_findings": [{ "code": "CUST_OK", "severity": "PASS", "message": "Customer demographics valid" }],
  "coverage_results": [
    {
      "orc": "SGL",
      "aggregated_pi": "350000.00",
      "coverage_limit": "250000.00",
      "insured_amount": "250000.00",
      "uninsured_amount": "100000.00",
      "rationale": "SGL: 1 unique owner(s) × SMDIA $250,000 = $250,000 aggregate limit...",
      "accounts_included": ["ACCT-1"],
      "evidence": { "owner_shares": { "C1001": "350000.00" }, "rule_citation": "12 CFR 330.6 / Part 370 App." }
    }
  ],
  "pending_decisions": [{ "is_pending": false, "detail": "No pending conditions" }],
  "output_files": {
    "customer_file": { "header": "CS_Unique_ID|CS_Govt_ID|CS_Govt_ID_Type|...", "rows": ["C1001|123-45-6789|SSN|INDIVIDUAL|Jane|Doe|..."], "record_count": 1 },
    "account_file": { "header": "CS_Unique_ID|DP_Acct_Identifier|DP_Right_Capacity|DP_Prod_Cat|DP_Allocated_Amt|...", "record_count": 1 },
    "participant_file": { "record_count": 0 },
    "pending_file": { "record_count": 0 }
  },
  "summary_report": {
    "table_1_coverage_by_orc": [{ "orc": "SGL", "dollars_insured": "0.00", "dollars_uninsured": "100000.00", "fully_insured_dollars": "0.00" }],
    "table_2_pending_by_code": { "I_records_maintained_by_bank": [{"reason_code":"A","count":0}], "II_alternative_recordkeeping": [], "total_pending_accounts": 0 },
    "reconciliation": { "total_insured": "250000.00", "total_uninsured": "100000.00", "reconciles": true }
  },
  "eval_results": [
    { "name": "input_completeness", "status": "PASS" },
    { "name": "deposit_balance_reconciliation", "status": "PASS" }
  ]
}
```

## 3. Iterative recalculation

```http
POST /api/v1/determinations/{determination_id}/recalculate
```
Same body with updated/late Alternative Recordkeeping data; `AR*` pending
reasons are cleared and coverage recomputed (`IS_RECALC=true` in Snowflake).

## 4. MCP tool call (stdio client)

```jsonc
// tool: calculate_insurance
{
  "customer": { "customer_id": "C1" },
  "accounts": [
    { "account_number": "J1", "customer_id": "C1", "orc": "JNT", "balance": 500000,
      "owners": [{ "party_id": "P1", "name": "A" }, { "party_id": "P2", "name": "B" }] }
  ]
}
// -> { "coverage_results": [{ "orc": "JNT", "insured_amount": "500000.00", ... }] }
```
