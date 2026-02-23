# Plan: Objective Funder Filtering via Works Count + Budget Data

## Context

Small/niche funders (e.g., NSF Sri Lanka — annual budget ~$2.5M, 15,789 global OpenAlex works) slip through the Weibull article-count threshold and appear on rankings alongside NIH ($48.6B), NSF ($9.1B), and Wellcome ($2.4B). The goal is to objectively filter to "major world funders" that peer institutions view as competitors. No budget data exists in OpenAlex or DuckDB, so we use `openalex_works_count` as a proxy filter and separately curate actual budget data for the final chart funders.

## Part 1: Dual-Threshold Filter (works_count + article count)

### Rationale

`openalex_works_count` (total publications across all of OpenAlex) is the best available proxy for funder scale. It's already in the `funders` table for all 27,465 funders.

**Key insight:** Parent funder groups (NIH, UKRI, European Commission) need **aggregated** works counts because the parent entity alone can have few works (UKRI: 26K individual → 1.04M aggregated across children).

**Threshold: 100,000 aggregated works** — this:
- Corresponds to P99.9 of all OpenAlex funders (top ~50 globally)
- Excludes NSF Sri Lanka (15,789 works)
- Keeps all legitimate major funders including NIHR (107K), CIHR (131K)

### Files to Modify

| File | Change |
|---|---|
| `scripts/utils/data_loader.py` | Add `query_funder_works_count()` |
| `scripts/table_funders.py` | Add `aggregated_works_count` column; add `--min-works-figure` / `--min-works-table` CLI args; apply dual filter |
| `Makefile` | Add `--min-works-figure 100000 --min-works-table 50000` to targets |

### Implementation Details

**`data_loader.py`** — new function:
```python
def query_funder_works_count(con, funder_ids: list[str]) -> dict[str, int]:
    """Return {funder_id: openalex_works_count} for given IDs."""
```

**`table_funders.py`** changes:
1. In `build_funder_summary()`: after each funder row is built, look up `openalex_works_count` for all member `funder_id`s (via the new query function) and store the sum as `aggregated_works_count`.
2. New CLI args: `--min-works-figure` (default 100000), `--min-works-table` (default 50000), `--no-works-filter`.
3. In `main()`: after Weibull threshold computation, apply dual filter — a funder must pass BOTH Weibull article count AND min works count to appear in figure/table. CSV/markdown remain unfiltered (all ≥100 articles).
4. Log the works-count filter effect: `"Works filter (>=100,000): 24 → 23 figure funders (removed: NSF Sri Lanka)"`.

**Makefile** — update `funder-table-2024`:
```makefile
python scripts/table_funders.py \
    ... \
    --min-works-figure 100000 --min-works-table 50000 \
    ...
```

## Part 2: Funder Budget Data Curation

### Data Source Strategy

No single database has budget data for all funders. Approach: manually curate from official sources (annual reports, budget pages, government appropriations), store in a seed CSV, and load into DuckDB.

### Budget Data (24 current figure funders)

Each row below will become one record in the seed CSV. Budget figures are the most recent publicly available annual values.

**1. NIH** (USA) — $48.6B USD, FY2024
- Source: NIH Office of Budget, "Appropriations History by Institute/Center"
- URL: https://officeofbudget.od.nih.gov/approp_hist.html
- Notes: Includes ARPA-H. Without ARPA-H: ~$47.3B

**2. UKRI** (UK) — £8.8B GBP (~$11.1B USD), 2024-25
- Source: UKRI, "Explainer: UKRI budget allocations"
- URL: https://www.ukri.org/publications/explainer-ukri-budget-allocations/budget-allocations-for-uk-research-and-innovation/
- Notes: Umbrella for 7 research councils + Innovate UK + Research England

**3. European Commission / Horizon Europe** (EU) — €12.8B EUR (~$13.9B USD), 2024
- Source: Science|Business, "Commission puts forward €13.6B research budget for 2024"
- URL: https://sciencebusiness.net/news/EU-budget/commission-puts-forward-eu136b-research-budget-2024-eu128b-horizon-europe
- Notes: €12.8B for Horizon Europe within €13.6B total research budget. Programme total 2021-2027: €93.5B

**4. NRF Korea** (Korea) — ~₩10.7T KRW (~$7.5B USD), 2024
- Source: MSIT (Ministry of Science and ICT), "2025 R&D Budget Plans"
- URL: https://www.msit.go.kr/eng/bbs/view.do?sCode=eng&nttSeqNo=1018&pageIndex=&bbsSeqNo=42&mId=4&mPid=2
- Notes: NRF manages ~36% of Korea's total govt R&D spend (₩29.7T in 2025)

**5. National Key R&D Program** (China) — ~¥50B CNY (~$7B USD), 2024
- Source: Ministry of Science and Technology annual work report
- URL: https://www.most.gov.cn/
- Notes: Estimate based on total MOST R&D expenditure allocation; not separately disclosed

**6. NSFC** (China) — ¥36.3B CNY (~$5.1B USD), 2024
- Source: Nature News, "China's basic-science agency gets biggest funding boost in years"
- URL: https://www.nature.com/articles/d41586-024-03120-y
- Notes: 10% increase over 2023

**7. BMBF** (Germany) — ~€21B EUR total (~€10B R&D portion, ~$10.8B USD), 2024
- Source: BMBF, "Bundeshaushalt 2024"
- URL: https://www.bmbf.de/bmbf/de/ueber-uns/aufgaben-und-aufbau/der-bundeshaushalt/der-bundeshaushalt_node.html
- Notes: Total ministry budget; R&D portion is ~half

**8. DFG** (Germany) — €3.9B EUR (~$4.2B USD), 2024
- Source: DFG, "Facts and Figures"
- URL: https://www.dfg.de/en/news/facts-figures/
- Notes: Distributed across 30,940+ projects

**9. NSF** (USA) — $9.06B USD, FY2024
- Source: NSF, "FY 2024 Appropriations"
- URL: https://www.nsf.gov/about/budget/fy2024/appropriations
- Notes: 5% decrease from FY2023

**10. Wellcome Trust** (UK) — £1.92B GBP (~$2.4B USD), 2024-25
- Source: Wellcome, "Annual Report and Financial Statements 2024/25"
- URL: https://wellcome.org/insights/articles/wellcome-annual-report-and-financial-statements-202425
- Notes: Charitable expenditure. Investment portfolio: £39.9B

**11. JSPS** (Japan) — ¥318.8B JPY (~$2.1B USD), FY2025
- Source: JSPS, "Budget" page
- URL: https://www.jsps.go.jp/english/e-organization/budget/
- Notes: Includes ¥76.9B Grants-in-Aid (KAKENHI), 99.4% from govt subsidies

**12. NIHR** (UK) — ~£1.5B GBP (~$1.9B USD), 2024-25
- Source: NIHR Annual Report 2023-24
- URL: https://www.nihr.ac.uk/about-us/our-key-data-and-publications/annual-reports/
- Notes: UK's largest public funder of health and care research

**13. SNSF** (Switzerland) — CHF 1.32B (~$1.5B USD), 2024
- Source: SNSF Annual Report 2024
- URL: https://www.snf.ch/en/PPHjxRR5rDBOB5F2/page/annual-report
- Notes: CHF 960M invested in new projects

**14. NSERC** (Canada) — ~$1.5B CAD (~$1.1B USD), 2024-25
- Source: NSERC Departmental Plan 2024-25
- URL: https://www.nserc-crsng.gc.ca/NSERC-CRSNG/Reports-Rapports/DP/2024-2025/index_eng.asp
- Notes: Natural sciences and engineering grants

**15. ANR** (France) — €1.24B EUR (~$1.35B USD), 2024
- Source: ANR, "Budget" page
- URL: https://anr.fr/fr/lanr/nous-connaitre/budget/
- Notes: Intervention budget; +3.9% over 2023

**16. CIHR** (Canada) — ~$1.34B CAD (~$0.97B USD), 2024-25
- Source: CIHR, "Grants and Awards Expenditures"
- URL: https://cihr-irsc.gc.ca/e/51250.html
- Notes: Grants and awards only

**17. Swedish Research Council** (Sweden) — ~SEK 8B (~$750M USD), 2024
- Source: Vetenskapsrådet Annual Report
- URL: https://www.vr.se/english/about-us/annual-reports.html
- Notes: Sweden's largest government research funder

**18. CAPES** (Brazil) — ~BRL 4.8B (~$900M USD), 2024
- Source: CAPES Orçamento (Budget)
- URL: https://www.gov.br/capes/pt-br/acesso-a-informacao/institucional/orcamento
- Notes: Primarily graduate scholarships and postdoctoral fellowships

**19. CNPq** (Brazil) — ~BRL 2.4B (~$450M USD), 2024
- Source: CNPq Relatório de Gestão
- URL: https://www.gov.br/cnpq/pt-br/acesso-a-informacao/institucional/relatorio-de-gestao
- Notes: Brazil's main research grants agency

**20. European Regional Development Fund** (EU) — ~€200B EUR total for 2021-2027 (R&D fraction ~€30B)
- Source: European Commission, Cohesion Policy 2021-2027
- URL: https://ec.europa.eu/regional_policy/funding/erdf_en
- Notes: Not primarily a research funder; R&D is a small fraction. Budget type: structural_fund

**21. NRF South Africa** (South Africa) — ~ZAR 5B (~$270M USD), 2024
- Source: NRF Annual Report 2023/24
- URL: https://www.nrf.ac.za/about-us/annual-reports/
- Notes: South Africa's primary research funder

**22. China Postdoctoral Science Foundation** (China) — ~¥1.5B CNY (~$200M USD), 2024
- Source: CPSF Annual Report
- URL: http://www.chinapostdoctor.org.cn/
- Notes: Postdoctoral fellowship funding only

**23. Fundamental Research Funds for Central Universities** (China) — no standalone budget
- Source: N/A — institutional funding mechanism administered by MOE
- URL: https://www.moe.gov.cn/
- Notes: Distributed directly to ~75 universities; no single public budget figure. Estimated ~¥10-15B CNY total across all universities.

**24. NSF Sri Lanka** (Sri Lanka) — ~LKR 370M (~$1.2M USD), 2024
- Source: National Science Foundation of Sri Lanka Annual Report
- URL: https://www.nsf.gov.lk/index.php/about-us/annual-report
- Notes: Very small national funder; 3+ orders of magnitude smaller than major funders

### DuckDB Schema: `funder_budgets` table

Add to `funder_extract.duckdb` (datalad-managed — requires `datalad unlock` before write, `datalad save` after):

```sql
CREATE TABLE funder_budgets (
    funder_name VARCHAR NOT NULL,        -- English display name (matches funders_summary CSV)
    funder_id VARCHAR,                   -- OpenAlex funder ID (nullable for aggregates)
    country_code VARCHAR,                -- ISO alpha-2
    budget_amount DOUBLE,                -- Annual budget in local currency
    budget_currency VARCHAR,             -- ISO 4217 currency code (USD, EUR, GBP, etc.)
    budget_usd DOUBLE,                   -- Approximate USD equivalent
    budget_year INTEGER,                 -- Fiscal/calendar year
    budget_type VARCHAR,                 -- 'total' | 'r_and_d' | 'grants_only' | 'charitable_spend'
    confidence VARCHAR,                  -- 'confirmed' | 'estimated' | 'unknown'
    source_url VARCHAR,                  -- URL of official source
    source_description VARCHAR,          -- Brief description (e.g. "NIH Office of Budget FY2024")
    notes VARCHAR,                       -- Caveats, methodology notes
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Files to Create/Modify

| File | Action | Description |
|---|---|---|
| `scripts/funder_budgets_seed.csv` | CREATE | Seed CSV with the budget data above |
| `scripts/load_funder_budgets.py` | CREATE | Script to load CSV into DuckDB table |
| `Makefile` | MODIFY | Add `load-budgets` target |

### `scripts/funder_budgets_seed.csv`

CSV with columns matching the schema above. One row per funder. Source URLs included for provenance.

### `scripts/load_funder_budgets.py`

- Reads seed CSV
- Connects to `funder_extract.duckdb` (user must `datalad unlock` first)
- Creates `funder_budgets` table (DROP IF EXISTS + CREATE)
- Inserts all rows
- Prints summary
- CLI: `--duckdb-path`, `--seed-csv`, `--verbose`

### Datalad Workflow

```bash
cd /data/adamt/osm/datalad-osm
datalad unlock duckdbs/funder_extract.duckdb
python ~/claude/osm/brnch_funderFig/scripts/load_funder_budgets.py --verbose
datalad save -m "Add funder_budgets table with annual budget data" duckdbs/funder_extract.duckdb
```

## Verification

```bash
source ~/claude/osm/venv/bin/activate

# Part 1: Regenerate with dual filter
python scripts/table_funders.py \
    --date-from 2024-01-01 --date-to 2025-06-30 --research-only \
    --table-survival 0.05 --figure-survival 0.03 \
    --min-works-figure 100000 --min-works-table 50000 \
    --output-suffix _2024_2025 --verbose

# Checks:
# - NSF Sri Lanka NOT in figure or table
# - UKRI present (aggregated works ~1.04M)
# - aggregated_works_count column in CSV
# - Figure has ~23 funders

# Part 2: Load budget data
python scripts/load_funder_budgets.py --verbose

# Check:
python3 -c "
import duckdb
con = duckdb.connect('/data/adamt/osm/datalad-osm/duckdbs/funder_extract.duckdb', read_only=True)
print(con.execute('SELECT funder_name, budget_usd, budget_year, source_description FROM funder_budgets ORDER BY budget_usd DESC').df().to_string())
"
```
