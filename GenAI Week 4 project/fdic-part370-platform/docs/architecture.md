# FDIC Part 370 Platform — Architecture

> Diagrams use Mermaid. View on GitHub or any Mermaid-aware Markdown renderer.

## 1. End-to-End Architecture

```mermaid
flowchart TB
  subgraph Client["Browser (React + MUI + AG Grid)"]
    UI[ORC Form / Evidence Panel]
  end

  subgraph Edge["Azure App Gateway / Ingress (TLS)"]
    AGW[WAF + Routing]
  end

  subgraph AKS["Azure Kubernetes Service"]
    FE[Frontend Pods - nginx]
    API[FastAPI Pods]
    MCP[MCP Server]
  end

  subgraph AI["AI Layer"]
    LG[LangGraph Workflow - 9 Agents]
    LC[LangChain RAG]
    LS[(LangSmith Tracing/Evals)]
  end

  subgraph Data["Data & Knowledge"]
    SF[(Snowflake)]
    PC[(Pinecone Vector Store)]
  end

  subgraph Identity
    AAD[Azure AD SSO + RBAC]
  end

  UI -->|OIDC| AAD
  UI -->|Bearer JWT| AGW --> FE
  AGW --> API
  API -->|validate JWT| AAD
  API --> LG
  LG --> LC --> PC
  LG --> LS
  API --> SF
  MCP --> LG
  API -. OTel .-> LS
```

## 2. LangGraph Multi-Agent Workflow

```mermaid
flowchart LR
  START((START)) --> R[1. FDIC Rules Agent]
  START --> CV[2. Customer Validation]
  START --> AV[3. Account Validation]
  R --> CL[4. ORC Classification]
  CV --> CL
  AV --> CL
  CL --> IC[5. Insurance Calculation]
  IC --> PD[6. Pending Determination]
  PD --> OF[7. Output File Agent]
  OF --> SR[8. Summary Report Agent]
  SR --> EV[9. Evals Agent]
  EV --> END((END))
```

The three entry agents run **in parallel**; LangGraph's reducer-annotated state
merges their outputs before classification. The remainder is a linear pipeline.

## 3. Sequence — Determination Request

```mermaid
sequenceDiagram
  participant U as User (React)
  participant A as Azure AD
  participant F as FastAPI
  participant G as LangGraph
  participant P as Pinecone
  participant S as Snowflake

  U->>A: OIDC login
  A-->>U: id_token + access_token
  U->>F: POST /api/v1/determinations (Bearer)
  F->>A: Validate JWT + roles (RBAC)
  F->>G: run_determination(request)
  par Parallel agents
    G->>P: retrieve Part 370 rules (RAG)
    P-->>G: rule snippets
  and
    G->>G: validate customer + accounts
  end
  G->>G: classify ORC, calculate, pending, files, summary, evals
  G-->>F: final state (coverage + evidence)
  F->>S: persist INSURANCE_RESULT + CALCULATION_AUDIT + EVALS
  F-->>U: determination response (evidence chain)
```

## 4. Sequence — Iterative Recalculation (Alternative Recordkeeping)

```mermaid
sequenceDiagram
  participant Svc as Recordkeeping Source
  participant F as FastAPI
  participant G as LangGraph
  participant S as Snowflake

  Note over F: Initial run left accounts in Pending (AR* reason codes)
  Svc->>F: POST /determinations/{id}/recalculate (updated accounts)
  F->>G: run_determination(alt_recordkeeping_received=true)
  G->>G: Pending Agent clears AR* reasons; engine recomputes
  G-->>F: revised coverage + cleared pending
  F->>S: persist recalc (IS_RECALC=true)
```

## 5. Security Architecture

```mermaid
flowchart TB
  subgraph Identity
    AAD[Azure AD] --> RBAC[Role mapping: Analyst/Reviewer/Admin]
  end
  subgraph Secrets
    KV[Azure Key Vault] --> CSI[CSI Secret Store]
  end
  CSI --> Pods
  RBAC --> API[FastAPI: require - capability]
  API --> Enc[(TLS in transit)]
  SF[(Snowflake: column-level enc + masking on SSN_TIN)]
  API --> SF
  PII[PII tokenization before persistence]
```

**Controls**
- Azure AD SSO (OIDC); JWT signature + issuer + audience verified per request.
- RBAC capability matrix in `core/auth.py` (`run_determination`, `view_audit`, `seed_rag`).
- Secrets via Azure Key Vault + CSI driver (never in images/env files in prod).
- SSN/TIN tokenized/encrypted; Snowflake dynamic data masking on `SSN_TIN`.
- TLS everywhere; WAF at App Gateway; non-root containers; network policies.
- Full immutable audit trail in `CALCULATION_AUDIT` (VARIANT evidence payload).

## 6. Audit & Compliance Architecture

```mermaid
flowchart LR
  G[LangGraph agents emit trace + evidence] --> AUD[(CALCULATION_AUDIT)]
  G --> RES[(INSURANCE_RESULT)]
  EV[Evals Agent] --> EVT[(LANGSMITH_EVAL_RESULTS)]
  EVT -->|sync_evals_to_langsmith.py| LS[(LangSmith runs + feedback)]
  LS -->|LANGSMITH_RUN_ID| EVT
  AUD --> REP[FDIC Summary Report Tables 1-3]
  RES --> REP
  REP --> EXPORT[Pipe-delimited FDIC files: Customer/Account/Participant/Pending]
```

Every determination produces: (a) a reproducible evidence chain per ORC,
(b) reconciliation evals (insured + uninsured = PI), and (c) the four FDIC
output files plus the 3-table Summary Report — all persisted and queryable.

**Eval flow.** The in-workflow Evals Agent writes one row per check to
`LANGSMITH_EVAL_RESULTS` on every determination. `sync_evals_to_langsmith.py`
then pushes those rows to LangSmith as **runs + feedback** (PASS=1 / WARNING=0.5 /
FAIL=0) and writes the `LANGSMITH_RUN_ID` back, linking each Snowflake eval row to
its LangSmith run. The separate **offline experiment**
(`seed_langsmith_dataset.py --run`) scores the labeled per-ORC dataset with the 6
named evaluators and lives only in the LangSmith UI.
```
