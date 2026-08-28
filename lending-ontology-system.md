# Master Credit Box → RAG Knowledge System

## System Architecture

```mermaid
flowchart TB
    subgraph INPUTS["Input Sources"]
        XLSX["Master Credit Box (xlsx)\n~78 lenders, 16 products\n~23K cells"]
        PDF["Lender Rate Sheets (pdf)\nNew/changed programs\nStructured tables"]
        DOCX["Lender Program Guides (docx)\nUnderwriting details\nNarrative text"]
        MANUAL["Manual Updates\nBroker notes, addendums\nCS sheets"]
    end

    subgraph INGEST["Ingestion Pipeline"]
        P1["Parser Layer\nopenpyxl (xlsx)\npypdf2/docling (pdf)\npython-docx (docx)"]
        P2["Normalizer\nWide→EAV triples\nAttr name mapping\nType coercion\nLender dedup (alias merge)"]
        P3["Entity Builder\nLender, Product,\nContact, Attribute,\nScenarioRule objects"]
    end

    subgraph STORE["Knowledge Store"]
        K1["Obsidian Vault\n{k}/Lenders/Kiavi.md\n{k}/Products/SFR-DSCR.md\n{k}/Scenarios/Baltimore-MD.md\n{k}/Underwriting/Credit-Grids.md"]
        K2["Vector Index\nChroma / LanceDB\nEmbeddings for RAG\nSemantic search"]
        K3["Structured JSON\n{k}/corpus.json\nNormalized EAV\nTyped attributes"]
    end

    subgraph QUERY["Query Layer"]
        Q1["Natural Language\n\"Borrower in Baltimore\n640 FICO, $90k, 1 flip\""]
        Q2["Structured\n\"LTV > 80%\nFICO >= 680\nState = IL\""]
        Q3["Comparison\n\"Compare Kiavi vs CV3\non 0-exp FNF terms\""]
    end

    subgraph OUTPUT["Output"]
        O1["LLM Response\nRanked lenders\nWith reasoning"]
        O2["Graph View\nObsidian local graph\nOf connected entities"]
        O3["Decision Tree\nInteractive\nLender selector"]
    end

    subgraph UPDATE["Update Workflow"]
        U1["Diff Engine\nCompare old vs new\nDetect changed values"]
        U2["Version Track\nPer-lender changelog\nIn vault metadata"]
        U3["Validation\nSchema checks\nMissing values\nCross-field consistency"]
    end

    XLSX --> P1
    PDF --> P1
    DOCX --> P1
    MANUAL --> P1
    P1 --> P2 --> P3
    P3 --> K1
    P3 --> K2
    P3 --> K3
    K1 --> U1
    K2 --> U1
    K3 --> U1
    U1 --> U2 --> U3 --> P3
    K1 --> Q1
    K2 --> Q1
    K3 --> Q1
    K1 --> Q2
    K2 --> Q2
    K3 --> Q2
    K1 --> Q3
    K2 --> Q3
    K3 --> Q3
    Q1 --> O1
    Q2 --> O1
    Q3 --> O1
    O1 --> O2
    O1 --> O3
```

## Data Flow

```mermaid
flowchart LR
    subgraph RAW["Raw (per source)"]
        direction LR
        S1["Lender A Rate Sheet
        (PDF: table of rates/LTV)"]
        S2["Lender B Program Guide
        (DOCX: narrative UW rules)"]
        S3["Master Credit Box update
        (XLSX: new row added)"]
    end

    subgraph NORM["Normalized (EAV triples)"]
        T1["[
        lender: Kiavi,
        product: fnf,
        attr: fico_min,
        value: 700,
        source: credit-box-v3
        ]"]
    end

    subgraph ENT["Entity Graph"]
        E1["Lender:Kiavi
        ──┬── Product:FNF
          ├── Contact:Derek
          ├── Attr:FICO=700
          └── Scenario:NoExp"]
    end

    subgraph PUB["Published"]
        P1["obsidian/Kiavi.md
        ---
        yaml frontmatter
        + body with context"]
        P2["corpus.json
        {lender,product,attr,value}"]
        P3["vector index
        embeddings"]
    end

    RAW -->|"parse + normalize"| NORM
    NORM -->|"entity resolution"| ENT
    ENT -->|"render"| PUB
```

## Update Workflow (Robust)

```mermaid
flowchart TD
    START["New source arrives\n(PDF/DOCX/XLSX/manual)"]
    CLASSIFY{"Source type?"}

    CLASSIFY -->|xlsx| P_XLSX["Parse with openpyxl\nSheet→[EAV tuples]"]
    CLASSIFY -->|pdf| P_PDF["Parse with docling\nTable extraction\nSection headers"]
    CLASSIFY -->|docx| P_DOCX["Parse with python-docx\nTable + paragraph\nStructured fields"]
    CLASSIFY -->|manual| P_MANUAL["CLI prompt template\nStructured entry"]

    P_XLSX --> NORM
    P_PDF --> NORM
    P_DOCX --> NORM
    P_MANUAL --> NORM

    NORM["Normalize attr names\nMap to canonical schema\nType coercion"]
    NORM --> DIFF

    DIFF["Diff against current corpus\nPer {lender,product,attr} key\nCheck changed / added / removed"]
    DIFF --> CHANGES{"Changes found?"}

    CHANGES -->|no| EXIT["Skip. Log unchanged."]
    CHANGES -->|yes| VALIDATE["Validation pass:
    - Required attrs present?
    - Values in expected range?
    - Cross-field consistency?
    (e.g., min ≤ max)"]

    VALIDATE -->|fail| ALERT["Alert + human review\nAuto-reject update"]
    VALIDATE -->|pass| VERSION["Bump version\nPer-lender changelog entry\nTimestamp + source"]
    VERSION --> UPDATE

    UPDATE["Rebuild outputs:
    1. Obsidian .md files (updated)
    2. corpus.json (regenerated)
    3. Vector index (re-embed changed docs)
    4. Decision rules (re-indexed)"]

    UPDATE --> NOTIFY["Notify team: changes deployed"]
```

## Schema (Entity–Attribute–Value)

```yaml
# Canonical entity types and their attributes

entities:
  lender:
    canonical_name: string        # Kiavi
    aliases: list<string>         # [Kiavi Lending]
    contacts: list<Contact>
    dropbox_link: url
    pricer_type: enum[online, pdf, excel, contact_poc]
    portal_url: url
    login_credentials: {username, password}
    lbz_ae: string                # internal account exec
    last_updated: date

  product:
    lender_id: ref(Lender)
    product_type: enum[
      sfr_dscr, fnf, new_construction, multifamily_lt,
      sfr_bridge, sfr_blanket, multifamily_rehab,
      multi_comm_bridge, sb_commercial_lt
    ]
    status: enum[active, paused, removed]

  attribute:
    lender_id: ref(Lender)
    product_id: ref(Product)
    attr_name: string             # canonical: fico_min
    attr_value: any               # 680 or "680+" or "680-720"
    raw_text: string              # original cell value
    source_sheet: string
    source_row: int
    confidence: enum[typed, extracted_text, manual]

  contact:
    name: string
    email: string
    phone: string
    lender_id: ref(Lender)
    role: string                  # Account Executive / Processor

  scenario_rule:
    scenario_id: string           # "baltimore-md", "poor-credit-600"
    product_type: string
    condition: string             # "Borrower has property in Baltimore"
    recommendation: string         # "Send to Constructive, CV3, or Conventus"
    detail: text                  # LTV haircuts, rate adders, notes
    source_sheet: string

  decision_matrix:
    matrix_type: enum[
      credit_by_fico,             # CS-CREDIT: LTV per FICO bucket
      experience_by_tier,         # CS-EXPERIENCE: LTV per experience level
      reserves_policy,            # CS-RESERVESASSETS
      lease_occupancy             # CS-LEASEOCCUPANCY
    ]
    lender: ref(Lender)
    rows: list<MatrixRow>         # depends on type
    source_sheet: string
```

## Ingestion Skill Workflow

```yaml
skill: ingest-lender-data
trigger: "New lender doc received" or /ingest

steps:
  - step: classify_source
    input: file path
    output: source type + confidence

  - step: parse
    uses: appropriate parser (xlsx/pdf/docx/manual)
    output: list of [lender, product, attr, value] tuples

  - step: normalize
    uses: attr_name mapping table
    dedup: alias resolution against existing lenders
    output: canonical EAV triples

  - step: diff
    query: current corpus for matching keys
    output: {added: [...], changed: [...], removed: [...], unchanged: [...]}

  - step: validate
    rules:
      - required attrs not null (per product type)
      - numeric ranges sensible (min_loan ≤ max_loan)
      - no duplicate {lender, product, attr}
      - state coverage parseable
    on_fail: human review flag

  - step: update
    actions:
      - write/update Obsidian .md files
      - regenerate corpus.json
      - re-embed changed vectors
      - log to changelog

  - step: notify
    output: summary of changes deployed
```

## Robustness Considerations

| Risk | Mitigation |
|---|---|
| Attribute name drift ("FICO Min" vs "min FICO") | Mapping table + fuzzy match fallback |
| New product type not in schema | Open schema — attr stored as key-value even if unmodeled |
| Partial source (only rates, no UW rules) | Per-attribute confidence score; nulls OK with source annotation |
| Lender changes name / DBA | SSCS alias table; canonical name persists; all aliases searchable |
| Stale data persists after removal | Versioned corpus; rollback capability; tombstone markers |
| PDF table extraction errors | Human verification flag on low-confidence extractions |
| Manual entry typos | Validation regex + range checks on all numeric fields |

## Query Examples (Post-Normalization)

```python
# Hypothetical query API
corpus.query("""
  lender WITH product=fix-and-flip
  AND fico_min <= 680
  AND state_coverage CONTAINS "MD"
  AND loan_min <= 100000
  AND max_experience_required >= 1
  ORDER BY rate_floor ASC
""")
# Returns: [RCN, ROC Capital, CV3, ...]

corpus.query("""
  scenario = "heavy-rehab"
  AND product = "fix-and-flip"
  AND lender NOT IN ("Kiavi", "Groundfloor")
""")
# Returns lenders with heavy-rehab + drawn-funds interest
```
