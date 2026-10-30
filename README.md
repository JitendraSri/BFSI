# FinRAG AI: BFSI Intelligence Platform

An AI-powered financial intelligence platform for banking, financial services and insurance (BFSI). It integrates two engines in one dashboard:

- **Financial RAG engine (FinRAG):** answers questions about 10-K/10-Q filings and annual reports, with citations down to the page, section and table. It extends the metadata-driven RAG architecture of Dadopoulos et al., *Metadata-Driven Retrieval-Augmented Generation for Financial Question Answering* (arXiv:2510.24402, 2025), with table-aware chunking, multi-hop query decomposition, HyDE, live SEC EDGAR and annual-report ingestion, Indian-market handling and answer grounding checks.
- **Transaction Intelligence engine:** combines a supervised fraud model with unsupervised anomaly detection into an explainable 0–100 risk score with reason codes.

It is designed as a **decision-support system**. It flags, scores and explains; final actions stay with human reviewers.

**Stack:** Python 3.12 · Flask 3 · MongoDB Atlas · scikit-learn (Random Forest, Isolation Forest, TF-IDF) · Google Gemini (`google-genai`: generation and `gemini-embedding-001` embeddings) · NumPy vector index · vanilla JS + Chart.js

---

## Contents

1. [Features](#features) ([what's genuinely useful](#whats-genuinely-useful-here))
2. [Quick start](#quick-start)
3. [Configuration](#configuration)
4. [How it works](#how-it-works), including [the FinRAG engine](#finrag-engine) and [Transaction Intelligence](#transaction-intelligence-engine)
5. [Datasets and evaluation](#datasets-and-evaluation)
6. [How the project documents map to the code](#how-the-project-documents-map-to-the-code)
7. [API reference](#api-reference)
8. [Project structure](#project-structure)
9. [Testing](#testing)
10. [Security notes](#security-notes)
11. [Changelog](#changelog)

---

## Features

| Page | Route | What you can do |
|---|---|---|
| **Landing** | `/` | Product overview with an animated hero section |
| **Sign in / Register** | `/login`, `/register` | Register with email OTP verification, sign in, resend codes, reset your password by email |
| **Dashboard** | `/dashboard` | Balance, trust score, security status and fraud-risk cards; charts for transaction volume, income vs expense, spending by category, fraud trend and next-month forecast; subscription detector, spend insight, next-month forecast; recent fraud alerts; currency switcher for multi-currency imports; last sign-in timestamp |
| **Upload Data** | `/upload` | Import transactions from **CSV, Excel, PDF or images**; Indian bank statement column aliases (narration, withdrawal_amt, deposit_amt, chq_ref_no) supported; comma amounts and day-first dates handled; preview before saving, review rejected and duplicate rows, then confirm (or roll back the whole batch later) |
| **Transactions** | `/transactions` | Server-paginated, searchable, filterable ledger; filter by flagged/unflagged/disputed; statement CSV export; dispute flag per row |
| **Fraud Alerts** | `/fraudalerts` | Investigation queue of flagged transactions, each with a risk score (0–100), level and plain-language reasons; mark Legitimate / Fraud / Reopen with undo; labels feed the next model retrain |
| **Predictive Modeling** | `/predictive` | Risk simulator for a hypothetical transaction (fraud score, anomaly score, hybrid risk and reasons); real training-run history chart; admin-only retrain button (`ADMIN_EMAILS` env var) |
| **Insights** | `/insights` | Transaction-model metrics (ROC-AUC, PR-AUC, fraud-class precision/recall/F1, false-positive rate, detection latency, confusion matrix) for each detector; model drift chart across retrains; **measured FinRAG benchmark results** |
| **Investments** | `/investments` | Track holdings; return % per holding; allocation doughnut chart; PATCH revalue endpoint; AI rebalancing review |
| **Loans** | `/loans` | EMI calculator, affordability check (40% DTI), year-by-year amortization chart with prepayment modelling |
| **Credit Score** | `/credit-score` | What-if credit score simulator (300–850) starting from a real baseline derived from account history; factor breakdown card |
| **FinRAG Copilot** | `/rag` | **The main feature.** A streaming chat interface (SSE) with three panes: sources, conversation and evidence drawer. Add sources from one dialog: drag-and-drop upload (PDF/HTML/Markdown/text), a searchable list of 48 bundled 10-Ks, **the latest SEC EDGAR filing by ticker**, or **an annual report by URL** (e.g. BSE/NSE). Chat with one document, **all documents**, or Gemini alone. Answers stream token-by-token with live stage labels (Planning → Searching → Writing → Checking). Inline `[n]` citations open the evidence drawer at that passage (page, section, table, units, excerpt and reranker scores). Each answer shows confidence, a figures-verified count, multi-hop steps and timing, plus related questions. **Open in document** opens the original filing at the cited page/table in a sandboxed tab. Conversations are saved server-side and survive a page refresh. Stop button cancels mid-answer |
| **Profile** | `/profile` | Edit name, currency and budget limit; change password (12-char minimum); security status (Strong / Review); financial health score breakdown |

All monetary values are in Indian Rupees (₹). The dashboard handles mixed-currency imports: it asks you to pick a currency instead of adding up different currencies.

### What's genuinely useful here

An honest read on which parts of this project would hold up outside a classroom demo, and which wouldn't:

**Real-world useful, as-is or close to it:**
- **FinRAG Copilot** (`/rag`) — the strongest piece of this project. Asking a real SEC 10-K "what was the gross margin trend over 3 years, and why" and getting a cited, numerically-verified answer with the exact page and table is something a financial analyst would actually use for first-pass research. The live SEC EDGAR / annual-report-by-URL ingestion and the Indian-currency-aware parsing make it usable beyond a toy dataset.
- **Transaction Intelligence** (fraud model + anomaly detector) — a Random Forest plus an Isolation Forest giving a 0–100 risk score with plain-language reasons ("account is 3 days old", "channel rarely used by this customer") is a pattern real fraud-ops teams use. The code is correct and the metrics (ROC-AUC, PR-AUC, FPR) are measured, not guessed.
- **CSV/Excel/PDF/image transaction import** with column remapping, duplicate detection and rollback — this is a real problem (banks and fintechs spend real engineering time on exactly this), and the implementation (atomic imports, dedupe, rejected-row CSV export) is solid.
- **Credit score, loan EMI and affordability calculators** — standard, correct finance math (the actual EMI formula, a real affordability guideline), useful as a reference tool even if not hooked up to a real bureau.

**Fine as a demo, but wouldn't survive contact with a real deployment:**
- **The whole app runs on one server process with no real payment rail, no regulator, no audit trail beyond MongoDB, and OTP delivery depends on a single SMTP relay that (as you just saw) can silently start blocking you.** None of the "banking" in this app was ever going to be real money movement — that's normal for a project/demo, just worth being clear-eyed about.
- **Simulated banking/KYC** (now removed) was the clearest example of this: it looked like a bank, but PAN/Aadhaar validation and a payment risk score with no real core-banking system, regulator or settlement network behind them don't become "real" just by having a convincing UI. That effort is better spent making the two engines above (FinRAG, fraud detection) deeper and more reliable, which is what a real BFSI employer would actually evaluate.

If this project is for a college review/viva: lead with **FinRAG Copilot** and the **Transaction Intelligence** metrics — those are the parts with genuine technical depth (retrieval architecture, measured benchmarks, a real ML pipeline) rather than UI surface area.

---

## Quick start

**Prerequisites:** Python 3.12, a MongoDB Atlas cluster (or any MongoDB URI), and optionally a Gemini API key and a Brevo SMTP account.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
copy .env.example .env          # Windows  (cp on macOS / Linux)
#    then edit .env: MONGO_URI, DB_NAME and SECRET_KEY are required

# 4. (Optional) Create indexes and a demo user: sai@gmail.com / password
python app.py --seed

# 5. Run
python app.py
```

Open **http://127.0.0.1:5000**.

### Command-line options

| Command | What it does |
|---|---|
| `python app.py` | Start the server (same as `--server`) |
| `python app.py --seed` | Create MongoDB indexes and seed a demo user with 20 transactions |
| `python app.py --test-ai` | Send one test prompt to Gemini to confirm the key and model work |
| `python app.py --verify` | Register a test user and exercise the chat endpoint |
| `python app.py --setup` | Register, upload a sample CSV and train the model (needs `fraud_detection_dataset_LLM .csv` in the parent folder) |
| `python app.py download-datasets --financebench-pdfs 4` | Download FinanceBench questions + 4 of its 10-K PDFs, and the FinDER queries (see [Datasets](#datasets-and-evaluation)) |
| `python app.py evaluate-rag finder` | Measure retrieval on FinDER (Recall@k, MRR, nDCG@10) |
| `python app.py evaluate-rag financebench` | Measure end-to-end answers on FinanceBench (retrieval + RAGChecker-style claim metrics) |

---

## Configuration

All settings come from `.env` (see [.env.example](.env.example)).

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `MONGO_URI` | Yes | — | MongoDB connection string |
| `DB_NAME` | Yes | `BFSI` | Database name |
| `SECRET_KEY` | Yes | — | Signs JWTs and hashes OTPs. The app refuses to start without it |
| `GEMINI_API_KEY` | For AI features | — | Advisor chat, RAG answers, PDF/image import, AI risk explanations |
| `GEMINI_MODEL` | No | `gemini-flash-lite-latest` | Gemini model used everywhere |
| `SMTP_SERVER` / `SMTP_PORT` | For email | `smtp-relay.brevo.com` / `587` | Brevo relay. Other values are rejected |
| `SMTP_LOGIN` / `SMTP_PASSWORD` / `SENDER_EMAIL` | For email | — | Needed to send OTP emails |
| `HOST` / `PORT` | No | `127.0.0.1` / `5000` | Bind address |
| `FLASK_DEBUG` | No | `1` | Debugger and auto-reload. Turned off automatically if `HOST` is not localhost |
| `JWT_TTL_HOURS` | No | `24` | How long a sign-in stays valid |
| `FRONTEND_ORIGIN` | No | `http://localhost:5000` | Allowed CORS origin |
| `ENABLE_DIAGNOSTICS` | No | `0` | `1` exposes `/test_db` and `/test-atlas` |
| `GEMINI_EMBED_MODEL` | No | `gemini-embedding-001` | Embedding model for dense retrieval (768-dimensional vectors) |
| `GEMINI_EMBED_INTERVAL` | No | `4` | Seconds between embedding batches; keeps free-tier keys under their per-minute token cap |
| `FINRAG_MAX_METADATA_CHUNKS` | No | `800` | Maximum chunks per document sent to Gemini for chunk metadata (the rest use rule-based metadata) |
| `SEC_USER_AGENT` | For SEC import | — | SEC EDGAR rejects requests without a name and contact email, e.g. `FinRAG AI your-name you@example.com` |

**Without a Gemini key** the app still runs: the advisor switches to built-in offline answers, model tips come from rule-based heuristics, and FinRAG falls back to sparse (BM25 + TF-IDF) retrieval with rule-based metadata. Only PDF/image transaction import and generated RAG answers are unavailable.
**Without SMTP** new users can't receive verification codes. Seeded users are pre-verified.

---

## How it works

### Architecture

```
Browser (Jinja templates + vanilla JS + Chart.js)
   │  JWT in localStorage → "Authorization: Bearer <token>"
   ▼
Flask (app.py — single file: routes, ML, and the FinRAG engine all live here)
   ├── auth_required decorator        ─ verifies JWT (HS256, 24h expiry)
   ├── Flask-Limiter                  ─ per-IP rate limits (e.g. login 10/min, transfer 5/min)
   ├── Flask-Caching                  ─ in-memory cache, versioned per user
   ├── Flask-Compress                 ─ gzip/brotli responses
   ├── Transaction Intelligence       ─ Random Forest + Isolation Forest, risk scores and reason codes
   ├── Gemini client helpers          ─ shared google-genai wrapper: text, JSON, embeddings, retry/backoff
   ├── RAG service                    ─ FinRAG library + query engine (storage, background enrichment, retrieve, answer)
   └── FinRAG engine                  ─ parsing · chunking · metadata · retrieval · query · generation · ingest · evaluation
   ▼
MongoDB: users · transactions · file_uploads · loans · insurance_policies · investments
Disk:    assets/models/*.pkl · assets/rag_documents/<sha256(user)>/<doc>.json + <doc>.npy (vectors)
```

Every API query is scoped to the `user_id` in the token, so users can only ever read or change their own records.

### Authentication and OTP

1. **Register:** the name, email (stored lowercase) and password (8–72 bytes) are validated, the password is hashed with bcrypt, and a 6-digit OTP is emailed. Only an **HMAC-SHA256 digest** of the OTP is stored, never the code itself.
2. **Verify:** the code is compared in constant time and is valid for 10 minutes. Resends have a 60-second cooldown and a limit of 5 per hour.
3. **Login:** returns a JWT (`user_id`, `email`, `iat`, `exp`) plus a trimmed user object. Unverified accounts can't sign in.
4. **Password reset:** uses a *separate* OTP so a registration code can't reset a password. The response is the same whether or not the account exists, so it can't be used to discover registered emails.

### Transaction import pipeline

```
Upload (≤20 MB) ─▶ Parse ─▶ Normalize ─▶ Score ─▶ Dedupe ─▶ Preview (cached 15 min) ─▶ Confirm ─▶ MongoDB
                                                                  │                          │
                                                       optional column remap           Rollback by batch
```

1. **Parse:** CSV and Excel are read with pandas. PDFs and images go to Gemini, which returns structured JSON (a summary, a risk percentage and CSV rows). If the AI risk is above 70%, the extracted rows are flagged as fraud.
2. **Normalize** (`normalize_uploaded_transactions`): about 40 header aliases are mapped to canonical fields (`amount` → `transaction_amount`, `dr_cr` → `direction`, and so on). Separate debit and credit columns are merged. ₹, `$` and commas are stripped from amounts, and rows with an invalid amount are set aside as rejected. Dates are parsed, and missing IDs, channels, KYC flags and account ages are filled from your profile.
3. **Score:** every row gets a fraud probability, an anomaly score, a 0–100 risk score and reason codes (see [Transaction Intelligence](#transaction-intelligence-engine)). Rows without an explicit fraud label are flagged when the probability passes the learned threshold.
4. **Dedupe:** if a transaction ID repeats, the last row wins, and the preview lists which source rows collided.
5. **Preview:** the first 20 rows are shown with counts of valid, rejected and duplicate rows. Rejected rows can be downloaded as CSV. If the headers weren't recognized, `/upload/map` re-runs the pipeline on the **original** rows with your column mapping.
6. **Confirm:** rows are upserted on `(transaction_id, user_id)`, so re-importing the same file updates records instead of duplicating them. Each import gets an `import_batch_id`, and `/upload/rollback` deletes exactly that batch.

### Transaction Intelligence engine

The Transaction Intelligence Engine (in [app.py](app.py)) combines two detectors.

| Detector | What it learns | Why |
|---|---|---|
| **Random Forest** (supervised) | Patterns of labelled fraud: amount, channel, account age, KYC. 200 trees, depth 10, `balanced_subsample` class weights | Strong on fraud types seen in the labels |
| **Isolation Forest** (unsupervised) | What *legitimate* transactions look like; trained only on non-fraud rows | Flags unusual behaviour even when no fraud label exists |

**Risk score (0–100)** = 75% Random Forest probability + 25% anomaly score. It's labelled High (≥ 70), Medium (≥ 40) or Low. Each flag comes with **reason codes**, for example:

- "Amount is 85.0x this customer's typical transaction"
- "Channel "ATM" is rarely used by this customer"
- "Account is less than 30 days old"
- "KYC not verified"
- "Made between midnight and 5 a.m."
- "Fraud model score 93% is above the 60% alert threshold"

**Training** (`/api/retrain`, or the Training Lab on the Predictive page):

1. All labelled transactions are split 80/20, stratified so both sets contain fraud.
2. The alert threshold is the value that maximises fraud-class F1 on 5-fold out-of-fold predictions **of the training split only**, so the test set never influences it.
3. Every detector is evaluated on the held-out 20%. Fraud is only about 2% of transactions, so accuracy alone is misleading; the metrics below focus on the fraud class.

**Measured on 10,061 labelled transactions** (2.0% fraud; test split of 2,013), 2026-10-25:

| Detector | ROC-AUC | PR-AUC | Fraud precision | Fraud recall | Fraud F1 | False-positive rate |
|---|---|---|---|---|---|---|
| Random Forest (threshold 0.60) | 0.998 | 0.897 | 76.2% | 80.0% | 78.0% | 0.51% |
| Isolation Forest (no labels used) | 0.986 | 0.487 | 49.2% | 72.5% | 58.6% | 1.52% |
| Hybrid risk score | 0.997 | 0.898 | 76.2% | 80.0% | 78.0% | 0.51% |

Detection latency is 0.02 ms per transaction when scoring a batch, and about 20 ms for a single API request (mostly scikit-learn call overhead). Transaction amount carries 90% of the Random Forest's feature importance. These numbers come from `assets/models/metrics.json` and appear live on the Insights page; they change whenever you retrain.

The system never blocks a transaction automatically. It scores, ranks and explains, and a person decides.

### Dashboard intelligence

Computed on every load (`_compute_user_intelligence`) and cached for 60 seconds:

| Metric | How it's computed |
|---|---|
| **Trust score (0–100)** | KYC status (30) + fraud history (25) + activity in the last 90 days (20) + account age (15) + balance tier (10) |
| **Security status** | *Strong* = email and KYC verified with no fraud; *Moderate* = one of the two verified; *Weak* = neither |
| **Fraud risk level** | 95th percentile of fraud probability over the last 90 days: ≥ 0.7 High, ≥ 0.3 Medium, otherwise Low |
| **Per-transaction risk** | Hybrid risk score and reason codes stored on each imported transaction (see above) |
| **Expense forecast** | Average of the last three months of debits, plotted as the next month's prediction |

Any change to your data (import, rollback, transfer, delete) bumps a per-user cache version, so the dashboard updates immediately.

### FinRAG engine

```
INDEXING (once per document)
  PDF / HTML / MD / TXT ─▶ structure-preserving parse ─▶ section- and table-aware chunks
      ─▶ rule-based entities (instant; searchable immediately)
      ─▶ [background] Gemini document metadata ─▶ Gemini chunk metadata ─▶ contextual-chunk embeddings

ANSWERING (per question)
  question ─▶ file filter (all-documents mode) ─▶ query plan: rewrite + HyDE + multi-hop sub-questions
      ─▶ BM25 + TF-IDF + dense, for every query variant ─▶ reciprocal-rank fusion (25 candidates)
      ─▶ metadata reranker ─▶ top 7 ─▶ cited answer ─▶ numeric grounding + confidence + related questions
```

**1. Parsing** (the FinRAG parsing section of [app.py](app.py)) keeps structure instead of flattening it to text:

- **HTML filings (SEC inline XBRL):** hidden XBRL headers are skipped. Real `<table>`s become row/column tables, with split `$` and `)` cells merged back (`$ | 7,367` → `$7,367`). Page numbers come from page-break styles.
- **PDFs:** read in layout mode so columns stay aligned. Data rows are detected (mostly numeric cells), justified prose is kept out of tables, and header lines above a table are attached to it.
- **Section headings:** "Item 7. Management's Discussion…", "Item 1A—Risk Factors", "Consolidated Statements of Cash Flows", and Indian-report headings such as "Directors' Report", "Standalone Balance Sheet" and "Notes to the Financial Statements".
- **Units:** "(Dollars in millions)", "(₹ in crore)" and "Rs. in lakhs" are recognised and attached to the table they describe.

**2. Chunking** (the FinRAG chunking section of [app.py](app.py)): text chunks are about 1,800 characters with 200 characters of overlap, cut at sentence boundaries, and a new section always starts a new chunk. **Each table is its own chunk** (Table N, with caption and units). Large tables are split by rows with the header repeated, so no part loses its column labels. Every chunk records page, section, table number and units; that is what makes citations like *"COSTCO.html, p. 40, Consolidated Statements of Cash Flows, Table 21"* possible.

**3. Metadata** (the FinRAG metadata section of [app.py](app.py)), following the base paper §3.3:

- **Document level (one Gemini call):** one-liner, 120–200-word summary, 5–20 thematic *clusters*, company, fiscal year, document type, market (US/India), currency.
- **Chunk level (Gemini, batches of 12):** `parent_clusters`, `chunk_entities`, `answered_questions` (3–5 questions the chunk can answer) and `retrieval_nuggets`.
- **Rule-based extraction (always runs, even offline):** organisations, periods, amounts and 50 financial metrics, with Indian conventions: `₹1,23,456 crore`, lakh/crore multipliers, `FY 2023-24` → fiscal year 2024. A document is tagged *India* when it uses ₹, crore/lakh, BSE/NSE, SEBI or Ind AS.

**4. Contextual chunks and embeddings:** as the paper recommends, each chunk is embedded with its metadata prepended (document one-liner, section, topics, entities, answerable questions). Vectors come from `gemini-embedding-001` (768 dimensions, normalised), stored as `<doc>.npy` next to the document and searched by exact cosine similarity. This is an embedded vector index rather than a separate vector database server; at a library's scale (thousands of chunks) exact search takes milliseconds, and a server such as Qdrant could replace it without other changes.

**5. Background enrichment:** a document is searchable with BM25 the moment it's uploaded. Metadata and embeddings are added in a background thread, and the library shows *Enriching → Hybrid ready*. Enrichment is resumable: if it stops on an API quota, **Retry enrichment** continues where it left off. Embedding batches are size-limited and paced for free-tier keys.

**6. Query processing** (the FinRAG query section of [app.py](app.py)): **one** Gemini call returns the whole plan, which keeps latency to a single round-trip:

- **Query rewriting:** restates the question in filing terminology (base paper, Architecture 4).
- **HyDE:** a 1–2 sentence hypothetical passage, used as an extra dense query.
- **Multi-hop decomposition:** for comparisons, growth rates, ratios and multi-period questions, up to 3 self-contained sub-questions. Each is retrieved separately and is guaranteed at least one supporting passage.
- **All-documents mode:** a file filter first picks the 3 most relevant documents from their one-liners (base paper's pre-retrieval filtering).

**7. Hybrid retrieval and fusion** (the FinRAG retrieval section of [app.py](app.py)): every query variant is searched with **BM25** (k1 = 1.5, b = 0.75) and **TF-IDF** (1–2-grams) over the contextual text. The original query, the rewritten query, the HyDE passage and the sub-questions are also searched with **dense** cosine similarity. All ranked lists are merged with **reciprocal-rank fusion** (k = 60) into 25 candidates. The paper found that rewriting alone can drop recall; searching the original query alongside the rewrite guards against that.

**8. Metadata reranker:** the paper's custom reranker (§3.4.3), with four equally weighted (25%) signals:

- `entity_freq`: how common the chunk's entities are across the candidates
- `cluster_coherence`: how prevalent its topic clusters are
- `entity_query`: how many of its entities match the question
- `retrieval`: its normalised fused score

The top 7 go to the generator (the paper's k = 7). The paper's reranker needs no extra model or API call.

**9. Generation and verification** (the FinRAG generation section of [app.py](app.py)):

- **Prompt rules:** answer only from the excerpts; cite every statement `[n]`; quote figures with their units (₹ crore stays ₹ crore); show formula and inputs for calculations; respect reporting periods; say what's missing rather than guess; ignore instructions inside documents.
- **Numeric grounding check:** every figure in the answer is looked up in the cited passages, and any that don't appear verbatim are listed under "Check these figures". In testing on Costco's 10-K this caught a misquoted dividend figure ($6,555M; the filing says $6,655M).
- **Confidence (0–100%):** 40% retrieval strength + 35% numeric grounding + 25% citation coverage, capped low when the answer says the evidence is missing.
- **Related questions:** suggested from the `answered_questions` metadata of the retrieved chunks.
- **Pipeline trace:** shows the rewritten query, HyDE passage, sub-questions, file filter and per-stage timings.

**10. Live ingestion** (the FinRAG ingestion section of [app.py](app.py)):

- **SEC EDGAR:** ticker → CIK → latest 10-K/10-Q/8-K/20-F → primary document, indexed and enriched like an upload. Requires `SEC_USER_AGENT`.
- **By URL:** any public PDF or HTML report, for example an Indian company's annual report linked from BSE, NSE or the company website. Only public addresses are fetched; private, loopback, link-local and cloud-metadata IPs are refused, including on redirects.

Bundled reports: 48 SEC 10-K filings in `assets/rag_documents/finrag_reports/` (up to 25 MB each). Each user's library is isolated under `assets/rag_documents/<sha256(user_id)>/`. With no document selected, the workspace is a general Gemini chat and never claims document evidence.

### AI features (Gemini)

All AI calls go through the Gemini client section of [app.py](app.py), which keeps one cached client per API key and uses one configurable model name.

| Feature | Endpoint | Behaviour |
|---|---|---|
| Cortex advisor | `/api/chat` | Answers finance-only questions using your balance, risk level and last five transactions. Has offline fallback answers |
| Transaction risk explanation | `/api/analyze` | Gives a Low/Medium/High rating with reasoning. Results are cached for 24 hours per unique input |
| Portfolio review | `/api/investments/analyze` | Compares your allocation with your risk profile and suggests rebalancing |
| Model tips | `/api/model-tips` | Suggests improvements based on the model metrics. Falls back to rule-based tips |
| Document extraction | `/upload` (PDF/image) | Turns statements and receipts into transaction rows |

User text is checked for common prompt-injection patterns ("ignore previous instructions", `[INST]`, role tags and similar), and control characters are stripped and length limits applied before anything reaches the model.

### Loans and EMI

- **EMI and affordability:** amounts are validated as finite, positive and at most ₹10 crore. EMI uses the standard formula `P·r·(1+r)ⁿ / ((1+r)ⁿ − 1)`. Results are labelled as estimates, not lending decisions. A `/api/loan/amortization` endpoint returns the full year-by-year schedule including the effect of an extra monthly payment.

---

## Datasets and evaluation

| Dataset | What it is | How it's used | Get it |
|---|---|---|---|
| **FinanceBench** (open-source subset) | 150 analyst questions over 10-K/10-Q filings, with answers and annotated evidence pages | End-to-end evaluation: retrieval metrics plus RAGChecker-style claim metrics, the base paper's protocol (k = 7) | `python app.py download-datasets --financebench-pdfs N` (questions + the N most-used 10-K PDFs; `all` for every PDF) |
| **FinDER** | 5,703 expert-annotated query / evidence / answer triplets from 10-Ks; short, jargon-heavy queries ("Delta in CBOE Data & Access Solutions rev from 2021-23") | Retrieval evaluation: does the exact annotated evidence passage come back? | downloaded by default (13 MB); `--finder-corpus` adds the 140 MB 10-K corpus |
| **SEC EDGAR** | Live 10-K/10-Q/8-K filings | Real-time ingestion in the app; 48 filings are already bundled | in-app import (needs `SEC_USER_AGENT`) |
| **BSE / NSE annual reports** | Indian company filings (₹ crore, FY2023-24, Ind AS) | In-app import by URL; parsing, units and entities handle Indian conventions | in-app import by URL |
| **Transaction data** | 10,061 labelled transactions in MongoDB | Training and evaluating the fraud model and anomaly detector | already in your database |

Downloaded data lives in `datasets/` (git-ignored).

### Metrics

- **Retrieval:** Recall@k (share of questions whose annotated evidence is in the top k), MRR, nDCG@10. For FinanceBench, a retrieved chunk counts as evidence when it mostly overlaps an annotated evidence passage (token overlap ≥ 55% either way).
- **Generation (RAGChecker-style, as in the base paper):** a Gemini judge splits the ground truth and the answer into atomic claims and checks entailment. **Precision** = answer claims that are correct; **recall** = ground-truth claims that are covered; **F1**; **claim recall** = ground-truth claims present in the retrieved context (retriever quality); **context precision** = retrieved chunks containing a ground-truth claim; **faithfulness** = answer claims supported by the context; **hallucination** = answer claims neither supported nor correct.
- **Transaction model:** ROC-AUC, PR-AUC, fraud-class precision/recall/F1, false-positive rate, detection latency (see [above](#transaction-intelligence-engine)).

Runs are resumable (per-question results go to `evaluation/results/<dataset>_runs.jsonl`) and write `<dataset>_latest.json` and `.md`. The Insights page displays the latest results.

### Measured results

**FinDER retrieval:** 25 random queries (seed 7), searched against 630 expert-annotated 10-K evidence passages, measured 2026-10-25. A hit means the exact annotated passage was retrieved.

| Pipeline | Recall@1 | Recall@3 | Recall@10 | Recall@50 | MRR | nDCG@10 | p95 latency |
|---|---|---|---|---|---|---|---|
| Sparse (BM25 + TF-IDF) | 36% | 52% | 64% | 92% | 0.462 | 0.497 | 15 ms |
| Dense (`gemini-embedding-001`) | **72%** | **84%** | **88%** | **100%** | **0.778** | **0.783** | 0.7 s |
| Hybrid (sparse + dense, RRF) | 60% | 68% | 72% | 96% | 0.663 | 0.665 | 0.9 s |
| Full (+ query rewrite + HyDE) | 64% | 76% | **88%** | 96% | 0.713 | 0.748 | 5.3 s |

What this shows:
- **Dense retrieval is far stronger than keyword search on FinDER's short, jargon-heavy queries:** MRR 0.778 vs 0.462.
- **Plain hybrid fusion without a reranker scored *below* dense alone,** because the weak keyword lists dilute the dense ranking. This is the same effect the base paper reports (§4.1: "advanced retrieval strategies like hybrid search can introduce noise … if not paired with a robust reranking mechanism").
- **Query rewriting + HyDE recovers Recall@10 to 88%,** at the cost of one extra Gemini call (about 3 s more).
- **Next step:** tuning the fusion weights needs a separate validation set, so they were not tuned on these 25 queries.

**Limits of these numbers:**
- **Sample size:** with n = 25, each query is 4 percentage points, so treat them as indicative. To extend, rerun `python app.py evaluate-rag finder --limit 200`; cached queries are reused. On a free-tier Gemini key, this takes several hours because of rate limits.
- **No FinanceBench run yet:** the end-to-end benchmark (`python app.py evaluate-rag financebench`) is ready. It needs about 200–400 Gemini calls for its 4 PDFs and 26 questions, more than the free-tier quota allowed during development.
- **Not comparable to the proposal targets:** the 92% Recall@10 target is a project goal, not a measured result, and is defined over a different corpus.

---

## How the project documents map to the code

Status of every item in the abstract, the basic-data sheet and the Review-1 notes. **Implemented** means running and tested; **substituted** means the goal is met with a different tool, and the reason is given.

| Proposal item | Status | Where / notes |
|---|---|---|
| Document parsing (Docling / PyPDF2 / BeautifulSoup) | Implemented (substituted) | FinRAG parsing section of `app.py`: pypdf layout mode + a purpose-built HTML table parser; no heavy Docling/PyTorch install |
| Table-aware chunking | Implemented | FinRAG chunking section of `app.py`: tables are atomic chunks with header-repeating splits, captions and units |
| LLM-generated document + chunk metadata | Implemented | FinRAG metadata section of `app.py`: the paper's exact fields, generated by Gemini |
| Contextual (metadata-enriched) embeddings | Implemented | `contextual_text()` in the RAG service section of `app.py`, `gemini-embedding-001` |
| Dense + BM25 hybrid retrieval | Implemented | FinRAG retrieval section of `app.py` (+ TF-IDF), fused with RRF |
| Metadata filtering / pre-retrieval file filtering | Implemented | `select_documents()` in the FinRAG query section of `app.py` (all-documents mode); entity/period matching inside the reranker |
| Query rewriting | Implemented | single-call query plan; the original query is always searched too |
| HyDE | Implemented | hypothetical passage used as an extra dense query |
| Multi-hop query decomposition | Implemented | up to 3 sub-questions, each guaranteed evidence; the generator shows sub-answers and the combination |
| Reranking | Implemented (substituted) | The base paper's own metadata reranker. A cross-encoder (ms-marco / BGE) would need PyTorch (~2 GB) and adds latency; the paper reports its metadata reranker at F1 43.2 vs 44.4 for Cohere's commercial reranker, faster and at zero cost (Table 1) |
| NER (FinBERT) | Substituted | rule-based financial entities (organisations, periods, amounts, metrics; Indian formats) + Gemini chunk entities; no PyTorch dependency |
| Precise citations (page, section, table) | Implemented | every chunk carries page, section, table number and units |
| Hallucination check | Implemented | numeric grounding check on every answer; claim-level faithfulness/hallucination in evaluation |
| Confidence score, related questions | Implemented | FinRAG generation section of `app.py` |
| Real-time ingestion (SEC EDGAR) | Implemented | `/api/rag/ingest/sec`; needs `SEC_USER_AGENT` |
| Indian market (BSE/NSE) | Implemented: import by URL + Indian-format parsing | Automated BSE/NSE scraping is not included: their sites block scripted access and their terms restrict it. Import any annual report by URL instead |
| Vector database (Qdrant / Chroma / FAISS) | Substituted | exact-cosine NumPy index per document; fast at library scale, no extra server. Qdrant is the drop-in upgrade for large corpora |
| Caching (Redis) | Partially | in-process caches for query plans, sparse indexes, dashboards and AI analyses. Redis is the multi-worker upgrade (see Security notes) |
| LLM (Llama 2 / Mistral / Gemini) | Gemini | `gemini-flash-lite-latest` (generation), `gemini-embedding-001` (embeddings); configurable |
| Transaction anomaly detection, risk scores, alerts | Implemented | Transaction Intelligence Engine section of `app.py`: Isolation Forest + Random Forest, hybrid risk 0–100, reason codes |
| ROC-AUC, PR-AUC, FPR, detection latency | Implemented and measured | Insights page and `assets/models/metrics.json` |
| RAG metrics: Recall@k, MRR, nDCG, claim recall, context precision, F1, faithfulness, hallucination | Implemented and measured | FinRAG evaluation section of `app.py`, run via `python app.py evaluate-rag` |
| Unified dashboard: transaction risk + document evidence | Implemented | Fraud Alerts → "Investigate with report evidence" opens FinRAG with the transaction context |
| React + TypeScript frontend | Added (optional) | A **Next.js 16 + React 19 + TypeScript** client lives in [`frontend/`](frontend/), talking to the same Flask API over JWT + SSE. It is an alternative to the Jinja UI, not a replacement — the server-rendered app remains the default. See [frontend/README.md](frontend/README.md) |
| FastAPI backend | Not adopted | The working Flask backend was kept; a rewrite would have put every working feature at risk for no functional gain |
| Docker, CI/CD, cloud deployment, Prometheus/Grafana | Not done | Docker isn't installed on the development machine, so a container couldn't be tested here |

---

## API reference

All `/api/*` and `/upload*` routes need `Authorization: Bearer <JWT>`.

<details>
<summary><strong>Authentication</strong></summary>

| Method | Path | Purpose |
|---|---|---|
| POST | `/register` | Create an account and email an OTP |
| POST | `/verify-registration` | Verify the email OTP |
| POST | `/resend-registration-otp` | Request a new OTP (60 s cooldown, 5 per hour) |
| POST | `/login` | Get a JWT |
| POST | `/forgot-password` | Email a reset code |
| POST | `/reset-password` | Set a new password (12–72 bytes) |

</details>

<details>
<summary><strong>Transactions and import</strong></summary>

| Method | Path | Purpose |
|---|---|---|
| POST | `/upload` | Upload a file and get a preview |
| POST | `/upload/map` | Re-map columns: `{preview_id, column_map: {source: target}}` |
| GET | `/upload/invalid-csv?preview_id=` | Download rejected rows |
| POST | `/upload/confirm` | Save a previewed import |
| POST | `/upload/rollback` | Delete an import: `{import_batch_id}` |
| GET | `/api/transactions?limit=&start_date=&end_date=` | List transactions (limit 1–1000) |
| DELETE | `/api/transactions/<id>` | Delete one transaction |
| GET | `/api/alerts` | Fraud-flagged transactions |
| GET | `/api/dashboard?currency=` | All dashboard data |
| POST | `/api/transfer` | `{recipient_id, amount}` |

</details>

<details>
<summary><strong>ML and AI</strong></summary>

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/predict` | `{amount, channel, account_age, kyc_verified, timestamp?}` → probability, anomaly score, risk score/level, reasons, threshold |
| POST | `/api/retrain` | Retrain the fraud model and anomaly detector (2 per hour) |
| GET | `/api/metrics` | Model metrics (per-detector ROC-AUC, PR-AUC, FPR, latency, …) |
| GET | `/api/model-tips` | AI improvement tips |
| POST | `/api/analyze` | AI risk explanation for a transaction |
| POST | `/api/chat` | Cortex advisor: `{query}` |
| GET | `/api/rag/documents` | Your library, with status, enrichment progress and metadata |
| GET | `/api/rag/documents/<id>` | One document's details |
| POST | `/api/rag/documents/<id>/enrich` | Start or resume metadata + embedding generation |
| DELETE | `/api/rag/documents/<id>` | Remove a document and its vectors |
| GET | `/api/rag/catalog` | Bundled 10-K reports |
| POST | `/api/rag/index` | Index an uploaded `file` or a catalog `source_id` (enrichment starts automatically) |
| GET | `/api/rag/sec/filings?ticker=&form=` | List recent SEC filings for a ticker |
| POST | `/api/rag/ingest/sec` | `{ticker, form?, accession?}`: download and index an SEC filing |
| POST | `/api/rag/ingest/url` | `{url}`: download and index a public PDF/HTML report |
| POST | `/api/rag/ask` | `{query, document_id?: id \| "all" \| "", history?, options?: preset or flags}`. Presets: `full`, `hybrid_rerank`, `hybrid`, `dense`, `sparse`; flags: `rewrite`, `hyde`, `decompose`, `dense`, `rerank` |
| GET | `/api/rag/evaluation` | Latest measured benchmark results |

</details>

<details>
<summary><strong>Profile, finance tools</strong></summary>

| Method | Path | Purpose |
|---|---|---|
| GET / PUT | `/api/profile` | Read or update name, email (re-verification required) and savings |
| POST | `/api/profile/image` | Profile photo (re-encoded to JPEG, up to 1024 px) |
| POST | `/api/profile/kyc` | Submit an ID photo |
| POST | `/api/profile/kyc/confirm` | Confirm with the emailed OTP |
| POST | `/api/profile/kyc/resend-otp` | Resend the KYC OTP |
| GET / POST | `/api/investments` | List or add holdings |
| POST | `/api/investments/delete` | Remove a holding |
| POST | `/api/investments/analyze` | AI portfolio review |
| POST | `/api/loan/emi` | EMI calculation |
| POST | `/api/check-loan-eligibility` | Affordability check |
| POST | `/api/loan/apply` | Loan application |
| POST | `/api/insurance/apply` | Insurance quote request |
| GET / POST | `/api/credit-score` | Credit score simulation |
| GET | `/api/budget-data` | This month's spending by category |
| POST | `/api/update-budget` | Set a budget limit |

</details>

---

## Project structure

```
BFSI_Project/
├── app.py                 # The entire backend in one file, in dependency order:
│                           #   - Gemini client (shared google-genai wrapper: text, JSON, embeddings, retry/backoff)
│                           #   - FinRAG: parsing, chunking, metadata, retrieval, query planning, generation,
│                           #     SEC EDGAR/URL ingestion, evaluation metrics
│                           #   - RAG service (document library + question-answering engine)
│                           #   - Transaction Intelligence Engine (fraud model + anomaly detector)
│                           #   - dataset download / RAG evaluation CLIs (`download-datasets`, `evaluate-rag`)
│                           #   - Flask routes, auth, upload pipeline, dashboard logic, server CLI
├── evaluation/results/    # Measured benchmark reports (JSON + Markdown)
├── datasets/              # Downloaded benchmark data (git-ignored)
├── requirements.txt
├── .env.example           # Configuration template
├── templates/             # Jinja pages (one per feature) + components/
│   └── rag.html           # FinRAG Copilot (chat UI)
├── static/
│   ├── css/               # styles.css (global), rag.css, hero.css, transactions.css
│   ├── js/                # rag.js, dashboard.js, navbar.js, transactions.js, fraud-alerts.js, hero.js, curved-bg.js
│   └── images/
├── assets/
│   ├── models/            # fraud_model.pkl, encoder.pkl, anomaly_model.pkl, metrics.json
│   ├── rag_documents/     # per-user indexed documents + finrag_reports/ (git-ignored)
│   ├── private_kyc_documents/   # KYC photos (git-ignored, never served)
│   └── logs/app.log
├── uploads/profiles/      # Profile photos (served at /uploads/…)
├── frontend/              # Optional Next.js + React + TypeScript client (talks to the Flask API)
└── tests/                 # pytest suite
```

### Two frontends, one backend

The backend serves both UIs from the same JWT-authenticated API:

- **Jinja app (default):** server-rendered pages in `templates/` + vanilla JS in `static/js/`, served by Flask at `http://127.0.0.1:5000`. No build step.
- **Next.js app (optional):** [`frontend/`](frontend/) — a React 19 / TypeScript single-page client (Tailwind v4, Radix UI, Recharts) that calls the Flask API via `NEXT_PUBLIC_API_URL` and renders the FinRAG Copilot with the same token-by-token SSE streaming. Run it alongside the backend with `npm run dev` (port 3000); see [frontend/README.md](frontend/README.md).

Both store the JWT in `localStorage` the same way, so they are interchangeable against one running backend.

---

## Testing

```bash
python -m pytest -q
```

**91 tests** run in about 10 seconds with MongoDB and Gemini mocked, so no network access or credentials are needed.

| File | Covers |
|---|---|
| `test_otp_flow.py` | Registration, OTP hashing, expiry and resend limits, password reset isolation |
| `test_financial_integrity.py` | Dashboard maths, currency separation, KYC flow, profile, investments, loans, page assets |
| `test_upload_pipeline.py` | Header aliasing, debit/credit handling, KYC normalization, ML scoring on import |
| `test_upload_import_features.py` | Column mapping, invalid-row export, duplicate review, rollback |
| `test_rag_retrieval.py` | Hybrid ranking, citations, conversation fallbacks |
| `test_rag_security.py` | Per-user document isolation |
| `test_hardening.py` | Regression tests for the fixes listed in the changelog |
| `test_finrag_pipeline.py` | Table/section/page/units parsing, header-repeating table splits, Indian amounts and fiscal years, the paper's reranker, RRF, numeric grounding, the full pipeline with plan + dense vectors, all-documents mode |
| `test_transaction_intel.py` | Detector metrics, threshold selection, reason codes, unseen channels, `/api/predict`, SSRF protection on URL import, SEC User-Agent requirement, new RAG routes |

---

## Security notes

- Passwords are hashed with bcrypt. OTPs are stored only as HMAC-SHA256 digests and compared in constant time.
- JWTs expire after 24 hours by default. Every query is scoped to the token's `user_id`.
- Login, OTP, transfer, upload and AI endpoints are rate-limited.
- Uploaded images are decoded and re-encoded before they're stored. KYC images are kept outside any served folder.
- `X-Content-Type-Options: nosniff` is set on every response.
- The dev server binds to `127.0.0.1`. The Werkzeug debugger allows running code from the browser, so it switches off automatically if the server is bound to a network address.
- **For production:** run behind a WSGI server (`waitress-serve app:app` on Windows, `gunicorn app:app` on Linux), set `FLASK_DEBUG=0`, use a strong `SECRET_KEY`, and swap the in-memory cache and rate-limit storage for Redis if you run more than one worker.

---

## Changelog

### 2026-10-27: FinRAG Copilot streaming, saved conversations, open-in-document; UI audit; KYC/banking removal

**FinRAG Copilot — streaming and persistence**
- **Streamed answers via SSE:** `POST /api/rag/ask/stream` returns a `text/event-stream`. Events: `stage` (plan / retrieve / dense / rerank / select / generate / verify), `token` (one text chunk), `done` (full result + `conversation_id`), `error`. The client renders tokens as they arrive and shows real stage labels instead of a fake timer.
- **Stop button:** an AbortController cancels the fetch; the server's cancel flag (`threading.Event`) is checked in every `on_stage`/`on_token` callback and raises `_AnswerCancelled`. Partial text is kept; a "Stopped. This answer is incomplete" note is added.
- **Saved conversations:** each exchange is appended to MongoDB `rag_conversations` (last 100 messages per document, owner-scoped). A "Recent chats" sidebar lists them; clicking one replays the full exchange. Conversations survive page refresh and re-login. `GET|DELETE /api/rag/conversations`, `GET /api/rag/conversations/<id>`.
- **Open in document:** `POST /api/rag/documents/<id>/open` returns a short-lived signed URL (JWT, 300 s, separate key so it can't double as a sign-in token). `GET /rag/original/<id>?t=<jwt>` serves the original file with `Content-Security-Policy: sandbox; default-src 'none'`, nosniff, no-referrer, no-store. PDFs open to the cited page (`#page=N`); HTML uses a scroll-to-text fragment (`#:~:text=`). For HTML, the charset is auto-detected (UTF-8 vs Windows-1252) so SEC filings don't show `â€™`.
- Conversation `conversation_id` persists across the session and is saved in `sessionStorage`.

**All pages audited and fixed**
- **Dashboard:** currency defaulting (untagged rows treated as account currency; dominant currency auto-selected); charts for income/expense, spending categories, transaction volume and forecast now all have real data paths; subscription card; spend insight; currency switcher; last sign-in; disputed card; security line; chatbot replaced by a link to `/rag`.
- **Transactions:** server-side paging (`/api/transactions`); status filter (all/flagged/unflagged/disputed); statement export CSV (formula-neutralised with `_csv_cell`); dispute flag per row (`/api/transactions/<id>/dispute`).
- **Fraud alerts:** Legitimate / Fraud / Reopen verdict buttons with undo (`/api/alerts/<id>/review`); labels stored with `label_source: 'user_review'` and fed back at retrain.
- **Upload:** Indian bank header aliases (narration/particulars → description, withdrawal_amt/deposit_amt, chq_ref_no → transaction_id); comma amounts (`to_amount`); day-first date parsing (`dayfirst=True, format='mixed'`); debit/credit column direction (`split_direction`); sample CSV; recent imports with Undo rollback.
- **Investments:** return % per holding; allocation doughnut chart; `PATCH /api/investments/<id>` revalue endpoint.
- **Predictive:** real training-run history chart; admin-only retrain (`ADMIN_EMAILS` env var; `is_admin`; `can_retrain` flag in metrics response); structuring advice removed.
- **Credit score:** factor breakdown card from `_financial_health_breakdown`.
- **Loans:** full amortization schedule and prepayment chart (`/api/loan/amortization`).
- **Profile:** security status (Strong / Review); budget limit and currency settings; `POST /api/profile/password` (12-char minimum); KYC section removed.
- **Auth:** new left panel; Font Awesome icons.
- **Navbar:** notification bell positioned correctly; `.sidebar-header-actions` stack correctly when sidebar is collapsed.
- **Sidebar:** collapsed state no longer hides the ☰ toggle (uses `column-reverse` stacking and `overflow:hidden`).

**KYC and banking simulation removed**
- Removed: KYC upload endpoints (`/api/profile/kyc*`), `KYC_UPLOAD_FOLDER`, KYC fields from registration/login payload/dashboard/scoring, transfer endpoint (`/api/transfer`), `/api/loan/apply`, `/api/insurance/apply`, the AI advisor chat, and `gemini_client.py` / `rag_service.py` (already merged into `app.py`).
- `assets/private_kyc_documents/` (two git-ignored ID photos) must be deleted manually from the filesystem. Old `kyc_*` / `trust_score` / `security_status` / `fraud_risk_level` fields still sitting in MongoDB user documents are harmless (nothing reads them) but can be removed with a one-time `db.users.update_many({}, {$unset: {kyc_status: '', kyc_image: '', kyc_verified: '', trust_score: '', security_status: '', fraud_risk_level: ''}})`.

**Infrastructure**
- MongoDB client timeouts: 10 s connect, 10 s server select, 30 s socket, `retryReads=True`.
- `ADMIN_EMAILS` env var: comma-separated list; when unset every signed-in user may retrain.
- `/favicon.ico` endpoint.
- 111 tests pass (up from 91).

### 2026-10-25: Spend analytics, subscription detection, statement export, disputes, a notification centre

Patterns from real consumer banking apps, built from data already in the system (no new fake simulation):

- **"Where did my money go" insight:** the Dashboard's Spending Categories card now shows which category rose the most since last month and by how much, computed from a month-over-month category aggregation.
- **Subscription/recurring-payment detector:** a new heuristic (`_detect_subscriptions`) scans debit history for a roughly constant amount repeating at a weekly/monthly/quarterly interval and surfaces it as a detected subscription with an estimated monthly total — a new "Subscriptions" card on the Dashboard.
- **Statement export:** the Transactions page's CSV export now has an "Export statement" button that exports everything matching the current search/filters (not just a manual row selection).
- **Dispute flag:** each transaction row has a flag action (`/api/transactions/<id>/dispute`) to mark it disputed, with a matching "Disputed" filter chip — the same self-serve marker every banking app offers, without pretending to run an actual chargeback.
- **Notification centre:** a bell icon in the sidebar header (every page) opens a cross-page activity feed combining high-risk transactions, budget overage, and subscriptions due soon (`/api/notifications`), instead of alerts being scattered per page.
- Removed a dead, unreachable "Account Statement" modal on the Dashboard that had a non-functional "Download PDF" button — the same category of fake-looking, unbacked feature as the banking/KYC module cut earlier.

### 2026-10-25: Fraud alerting, velocity checks, a real credit-score baseline, model drift tracking, loan amortization

- **Fraud alert emails:** a transaction import that contains a High-risk transaction now emails the account owner a summary (transaction, channel, amount, reasons) instead of leaving it to sit unread on the Fraud Alerts page. Reuses the existing SMTP setup (`send_fraud_alert_email`, built on a new shared `_send_email` helper).
- **Velocity / rapid-activity detection:** `score_transactions` now flags "N other transactions within 10 minutes of this one" as a reason code, checked against both the current import batch and the customer's recent history (`customer_history` now also returns `recent_timestamps`). This is an explanatory signal alongside the model score, not a new model feature, so it needs no retraining.
- **Credit Score Simulator now starts from a real baseline:** instead of a flat 650 for every user, `/api/credit-score` computes a 300-850 baseline from the account's own data (KYC status, account age, fraud history, budget adherence, balance buffer) via `_compute_financial_health_score`. The what-if scenario toggles are unchanged (still clearly labelled illustrative adjustments), but now apply on top of a number that actually means something.
- **Model drift tracking:** every retrain appends a metrics snapshot to `assets/models/metrics_history.json` (last 50 runs); a new "Model drift across retrains" chart on Insights plots Fraud-F1, ROC-AUC and hybrid-risk F1 over time, so a slow decline is visible instead of only ever seeing the latest run.
- **Loan amortization + prepayment calculator:** a new `/api/loan/amortization` endpoint and a chart on the Loans page show the year-by-year principal/interest split, and how much an extra monthly payment shortens the term and cuts total interest.
- **Background:** the site-wide curved-line canvas background was recolored from red to the existing brand indigo/purple (matching `--primary`/`--secondary` in `styles.css`).

### 2026-10-25: Consolidated the entire backend into app.py

- Merged `gemini_client.py`, `transaction_intel.py`, `rag_service.py`, the whole `finrag/` package (`parsing.py`, `chunking.py`, `metadata.py`, `retrieval.py`, `query.py`, `generation.py`, `ingest.py`, `evaluation.py`) and `scripts/download_datasets.py` + `scripts/evaluate_rag.py` into `app.py`. The project is now a single Python file end to end — routes, ML, and the whole FinRAG engine.
- The two CLI scripts are still runnable, now as `app.py` subcommands: `python app.py download-datasets ...` and `python app.py evaluate-rag ...`.
- Removed the now-empty `finrag/` and `scripts/` directories and the standalone module files. No behavior change: all 91 tests pass unmodified except for import paths (the 4 test files that imported the merged modules directly now import `app` instead).

### 2026-10-25: FinRAG Copilot redesign and conversational fixes

- **FinRAG Copilot:**
  - redesigned as a three-pane chat app (sources, conversation, evidence drawer)
  - greetings get a friendly reply without retrieval
  - general finance questions are answered from general knowledge (labelled) alongside any cited document facts
  - figure checks recognise correct calculations
- **Fix:** timestamps are now sent as ISO local time. They were labelled GMT, so the browser showed them 5½ hours off.
- **Measured:** FinDER retrieval results (see [Datasets and evaluation](#datasets-and-evaluation)).
- **Built, then removed same day:** a simulated banking module (accounts, payments, cards, deposits, bills, budgets/goals, an AI payment-risk check, a "chat with your own transactions" copilot) and an 8-step KYC onboarding wizard. Both worked end-to-end and were fully tested, but were cut because they duplicated what a demo bank app can show without adding real value here — see [What's genuinely useful](#whats-genuinely-useful-here) for what's worth keeping instead. Tests: 88 → 109 → 91 (net, after the removal).

### 2026-10-25: FinRAG engine and Transaction Intelligence aligned with the project proposal

**FinRAG (document intelligence)**
- New `finrag/` package implementing the base paper's metadata-driven architecture: LLM document and chunk metadata, contextual-chunk embeddings, hybrid dense + BM25 retrieval with RRF, and the paper's metadata reranker.
- Proposal novelties: table-aware chunking; page/section/table citations with units; query rewriting + HyDE + multi-hop decomposition in one planning call; all-documents mode with pre-retrieval file filtering; numeric grounding (hallucination) check; confidence score; related questions.
- Real-time ingestion: SEC EDGAR by ticker and annual reports by URL (BSE/NSE or company sites), with SSRF protection.
- Indian-market handling: ₹ crore/lakh amounts and units, FY2023-24 periods, Indian report sections, market detection.
- Background, resumable enrichment with free-tier-friendly embedding batching. The workspace shows enrichment status, document summaries, a pipeline selector and a pipeline trace.

**Transaction Intelligence**
- Isolation Forest anomaly detector alongside the Random Forest; hybrid 0–100 risk score with reason codes, stored on every imported transaction and shown on Fraud Alerts and the Predictive page.
- Alert threshold learned from cross-validated training data (0.60) instead of a fixed 0.5.
- New metrics: ROC-AUC, PR-AUC, fraud-class precision/recall/F1, false-positive rate, confusion matrix and detection latency for each detector, shown on Insights.

**Datasets and evaluation**
- `scripts/download_datasets.py` (FinanceBench, FinDER) and `scripts/evaluate_rag.py`: Recall@k, MRR, nDCG@10 and RAGChecker-style claim metrics, mirroring the base paper's protocol. Results appear on Insights.
- Added `pyarrow` (pinned below 20 for NumPy 1.x compatibility) for FinDER's Parquet data. Tests: 63 → 88.

### 2026-10-25: Bug fixes and upgrade

**Upgrades**
- Moved from the discontinued `google-generativeai` SDK to **`google-genai`**, with all calls going through a new shared `gemini_client.py`. The model is configurable with `GEMINI_MODEL`. This removed the deprecation warning and cut test time from 32 s to 10 s.
- `flask-cors` 3.0.10 → 6.x, which fixes published security vulnerabilities.
- Pinned Chart.js to 4.4.1, so a new CDN release can't silently break the charts.
- Requirements now have sensible version ranges, and `.env.example` was added.

**Bug fixes**
- **Column remapping crashed** against a real MongoDB connection (`if db` raises on a pymongo `Database`). It also re-processed already-mapped rows instead of the original file, so custom mappings didn't apply and rejected rows were lost.
- **Duplicate-row review was always empty** because it was calculated after duplicates had already been removed.
- **Transfers could corrupt balances:** an amount of `"NaN"` passed every check and wrote NaN into the balance. The balance check and debit weren't atomic, so concurrent requests could overdraw. Transfers also weren't recorded as debits, so they were missing from cash-flow charts.
- Loans and insurance accepted negative or non-numeric amounts. `/api/predict` returned a 500 on bad input.
- **Registration** returned a 503 when fields were missing, silently truncated passwords longer than 72 bytes, and stored emails with their original capitalization. That meant anyone who registered as `Name@Gmail.com` could never reset their password. Emails are now stored lowercase, and older mixed-case accounts are still found when signing in.
- The dashboard stayed stale for up to 60 seconds after an import, because the code cleared an old cache key (`dashboard_v3`) that was no longer used. Per-user cache versioning fixes this.
- Unknown `*.html` URLs returned a 500 error instead of a 404.
- `/api/analyze` was defined twice. Only the first, uncached version ever ran, so the 24-hour AI result cache never worked.
- The ML model was given unnamed features, which caused scikit-learn warnings. Model tips received the metrics in an unreadable format and always fell back to generic advice.
- `/api/transactions?limit=0` returned every row (MongoDB treats 0 as "no limit"). Invalid dates returned a 500.

**Security**
- The server bound to `0.0.0.0` with the debugger on, which let anyone on the same network run code on the machine. It now binds to localhost by default.
- `/test-atlas` exposed the database cluster hostname and connection errors without authentication. Diagnostics are now off unless `ENABLE_DIAGNOSTICS=1`.
- JWTs never expired. They now last 24 hours, and expired sessions get a clear "please sign in again" response.
- Profile photos were accepted based on file extension alone. They're now decoded and re-encoded, with size limits.
- Removed duplicate imports, debug `print` statements that logged on every request, and a duplicated service initialization.
