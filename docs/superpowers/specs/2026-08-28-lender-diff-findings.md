# Lender coverage diff: corpus.json vs corpus.db

**Date:** 2026-08-28
**Script:** `scripts/diff_lender_sources.py`
**Status:** BLOCKED — genuine data-integrity bug found in `migrate.py`

## Note on the "129 vs 91" framing

The task title references a 129-vs-91 lender count discrepancy. Running the
diagnostic against the actual checkout data, the real numbers are:

- `corpus.json` (parser.py): **65** unique `lender_canonical` values
- `corpus.db` (migrate.py): **91** canonical lenders + **31** aliases = 122 total known names

(129 may have referred to raw/pre-alias-collapse names counted elsewhere, or
to a different corpus snapshot than the one currently on disk. Regardless,
the diagnostic script runs against the real files as specified and the
diff below is what matters.)

## Diff output

```
corpus.json lenders: 65
corpus.db canonical: 91, aliases: 31

In corpus.json but NOT in corpus.db (canonical or alias): 2
  - Stormfield
  - Verus
```

## Categorization

### 1. `Verus` — alias-under-different-spelling (not a bug)

- `corpus.json` uses `lender_canonical: "Verus"` (shortened form), with the
  full `lender` field value `"Verus Capital"`.
- `corpus.db`'s `lenders` table has canonical name `"Verus Capital"`.
- `migrate.py` reads the raw header string `"Verus Capital"` directly from
  the source workbook's product-sheet header row and uses it verbatim as
  canonical (no shortening rule for "Verus" exists in `LENDER_NORMALIZE`,
  and none is needed — the raw header already says "Verus Capital").
- `parser.py`'s canonicalization independently shortens "Verus Capital" to
  "Verus" for its own `lender_canonical` field. This is a naming-convention
  difference between the two legacy scripts, not missing data. All of
  Verus's attribute data is present in `corpus.db` under the canonical name
  `"Verus Capital"` (confirmed: 103 records for Verus in `corpus.json`,
  matching lender rows present in `corpus.db`'s `lenders` table).
- **Verdict:** no data loss. `corpus.db` fully covers this lender under a
  slightly different canonical spelling.

### 2. `Stormfield` — genuinely-missing-real-lender (BUG)

- `corpus.json` has 29 attribute records for `lender_canonical: "Stormfield"`,
  all under `source_sheet: "Multi-Comm Bridge"`.
- `corpus.db` has **no** canonical lender and **no** alias matching
  "Stormfield" anywhere. `migration_log` has zero WARN/ERROR entries
  mentioning "Multi-Comm Bridge" or "Stormfield" — the sheet was processed
  silently and the column was dropped without any logged warning.
- Root cause, confirmed by opening the original source workbook
  (`/Users/jackrodenberg/Downloads/Copy of THE Master Credit Box-IPLE 2026 (1).xlsx`,
  same file referenced by both `corpus.json`'s `meta.source`/`file_mtime`
  and `corpus.db`'s `imports` table — both artifacts were built from the
  identical source file, ruling out a source-drift explanation):

  - Every other product sheet (e.g. `SFR DSCR`, `Fix & Flip`) has a
    `"VOTE COLUMN"` label in row 1, column A, and the first real lender
    name starts in row 1, column **C**.
  - `Multi-Comm Bridge` is laid out differently: column A row 1 is blank
    (no `"VOTE COLUMN"` label), so the lender names are shifted one column
    left — the first lender, `"Stormfield"`, sits in row 1, column **B**,
    with `"Lima One"` in column C, `"Conventus"` in column D, etc.
  - `migrate.py`'s `_insert_lenders()` (migrate.py:449-454) hardcodes the
    lender-name scan to start at column 3 (`for c in range(3, ws.max_column + 1)`)
    for **every** product sheet, assuming the uniform "VOTE COLUMN in A,
    blank/attr-label in B, lenders from C" layout. For `Multi-Comm Bridge`
    this assumption is wrong: column B holds a real lender name, and the
    scan starting at column 3 silently skips it. The same fixed offset is
    used in `_insert_product_sheet_data()` (migrate.py:592+), so
    Stormfield's entire data column (29 attribute values, matching the
    json record count) is dropped with no warning logged.
  - Confirmed by direct inspection of the source workbook: json's 19
    lenders for `Multi-Comm Bridge` match db's 18 lenders for that sheet
    exactly minus Stormfield — the leftmost/first lender column, exactly
    where the layout shift puts it.
- **Verdict:** this is a real, current lender with 29 real attribute values
  (AE contact info, differentiators, terms, etc.) that `migrate.py` drops
  due to a hardcoded column-offset assumption that doesn't hold for the
  `Multi-Comm Bridge` sheet. This is not a "VOTE COLUMN" artifact rejection
  or a misread numeric value — it is a legitimate lender name in a
  legitimate header cell that the fixed-offset scan never looks at.

## Conclusion

**1 of 2 diffed names is a genuinely missing real lender.** `migrate.py`
must be fixed to detect the `Multi-Comm Bridge` sheet's column-B-start
layout (or, more robustly, to detect the first lender column dynamically
per-sheet rather than hardcoding column 3) before `corpus.json` can be
safely deleted in Task 9. Per the task brief, this is a blocking
data-integrity decision beyond this diagnostic task's scope — reporting
BLOCKED rather than patching `migrate.py` myself.
