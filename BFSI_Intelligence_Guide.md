# FinRAG AI: Project Guide & Technical Architecture

Welcome to **FinRAG AI — A Unified AI Framework for Financial Risk and Retrieval-Augmented Intelligence**. The platform brings transaction-risk review and financial-document question answering into one workspace, alongside financial-planning tools.

> This is a high-level guide. The authoritative, deep-dive reference is the main [README](README.md) — it carries the exact algorithms, configuration, measured benchmark numbers and API contract.

## Current Build Baseline

The platform runs on a **Flask** API with **MongoDB Atlas** storage, a **scikit-learn** Transaction Intelligence engine, and **Google Gemini** for generation and embeddings. The default UI is server-rendered (Jinja templates + vanilla JS + Chart.js); an **optional Next.js + React + TypeScript client** lives in [`frontend/`](frontend/) and talks to the same API. Bundled data includes ~10,000 labeled transaction records (≈2% fraud) and 48 financial-report documents.

The FinRAG document-answering path implements the metadata-driven RAG architecture of Dadopoulos et al., *Metadata-Driven Retrieval-Augmented Generation for Financial Question Answering* (arXiv:2510.24402, 2025), extended with table-aware chunking, LLM document/chunk metadata, contextual-chunk embeddings, **hybrid dense + BM25 + TF-IDF retrieval fused with reciprocal-rank fusion**, a metadata reranker, query rewriting + HyDE + multi-hop decomposition, page/section/table citations, and a numeric grounding (hallucination) check. When no Gemini key is configured, FinRAG degrades gracefully to sparse (BM25 + TF-IDF) retrieval with rule-based metadata.

Model flags and imported fraud labels are investigation signals, not confirmed fraud findings, and model scores are review signals rather than calibrated probabilities. The system scores, ranks and explains; a person decides.

---

## 🛠️ Technology Stack

### Frontend
*   **Default UI**: Server-rendered **Jinja** templates with **vanilla HTML5/CSS3/ES6+ JavaScript** and **Chart.js**. No build step; a glassmorphism enterprise theme with hardware-accelerated animations.
*   **Optional SPA**: **Next.js 16 + React 19 + TypeScript** client in [`frontend/`](frontend/) — Tailwind CSS v4, Radix UI primitives, Recharts, next-themes. It consumes the Flask API over JWT + Server-Sent Events. See [frontend/README.md](frontend/README.md).

### Backend
*   **Language**: **Python 3.12**.
*   **Framework**: **Flask 3** (routes, ML and the FinRAG engine all live in `app.py`).
*   **Database**: **MongoDB (Atlas Cloud)** — users, transactions, uploads, investments, loans, RAG conversations.
*   **Security & Auth**: **bcrypt** password hashing, **JWT** (HS256, 24h expiry), email **OTP** verification over SMTP (Brevo relay), per-IP rate limiting.

### AI & Machine Learning
*   **ML**: **scikit-learn** (Random Forest, Isolation Forest, TF-IDF), **Pandas**, **NumPy**, **Joblib**.
*   **Generative AI**: **Google Gemini** via the `google-genai` SDK — `gemini-flash-lite-latest` for generation and `gemini-embedding-001` (768-dim) for dense retrieval. One shared, cached client with retry/backoff.
*   **Vector index**: an embedded exact-cosine NumPy index per document (no separate vector-DB server; Qdrant is the drop-in upgrade for large corpora).

---

## 🧠 Core Algorithms & Intelligence Models

### 1. Transaction Intelligence (Random Forest + Isolation Forest)
*   **Supervised Random Forest** (200 trees, depth 10, `balanced_subsample`) learns labeled fraud patterns over amount, channel, account age and KYC status.
*   **Unsupervised Isolation Forest**, trained only on non-fraud rows, flags unusual behaviour even where no label exists.
*   **Hybrid risk score (0–100)** = 75% Random Forest probability + 25% anomaly score, banded High / Medium / Low, each with plain-language **reason codes** ("Amount is 85× this customer's typical transaction", "Account is less than 30 days old", "KYC not verified").
*   **Learned threshold**: the alert threshold maximises fraud-class F1 on cross-validated training folds (≈0.60) rather than a fixed 0.5. Metrics (ROC-AUC, PR-AUC, fraud-class precision/recall/F1, false-positive rate, detection latency) are **measured on held-out data** and shown live on the Insights page.

### 2. Generative Parsing Pipeline (Gemini)
Uploaded receipts (images) and bank statements (PDFs) are sent to the Gemini multimodal model under strict prompt constraints, which returns structured JSON (summary, risk percentage, transaction rows) for review before import.

### 3. Financial Document RAG (FinRAG)
*   **Indexing**: structure-preserving parse → section- and table-aware chunks (each table is its own chunk, with caption and units) → rule-based entities (instantly searchable) → background Gemini document/chunk metadata → contextual-chunk embeddings.
*   **Retrieval**: every query variant is searched with BM25, TF-IDF and dense cosine similarity; ranked lists are merged with **reciprocal-rank fusion**, then a **metadata reranker** (entity/cluster/query/retrieval signals) picks the top 7.
*   **Query understanding**: one Gemini call produces the whole plan — query rewriting, a HyDE passage, and up to 3 multi-hop sub-questions.
*   **Grounded answers**: Gemini answers only from the retrieved excerpts, cites every statement `[n]` with page/section/table and units, and a **numeric grounding check** lists any figure that doesn't appear verbatim in the cited passages. Each answer carries a confidence score and related questions.
*   **Live ingestion**: SEC EDGAR by ticker and any public annual report by URL (BSE/NSE or company site), with SSRF protection. Each user's library is isolated on disk.

### 4. Dynamic Trust-Scoring Heuristic
A deterministic 0–100 profile indicator from KYC state, flagged-record ratio, recent activity, account age and balance tier. It is a profile signal, not a credit score or validated measure of trust.

---

## 🚀 Platform Features & User Guide

### 1. Authentication & Security
*   Register with email + password; verify with a 6-digit email **OTP** (10-minute validity, 60-second resend cooldown, 5/hour). Password reset uses a separate OTP. Sessions are JWT-based and expire after 24 hours.

### 2. The Hub: Unified Dashboard
*   Profile and security indicators, transaction and flagged-record counts; charts for transaction volume, income vs expense, spending categories, fraud trend and next-month forecast; a subscription detector and a month-over-month spend insight; recent alerts; a multi-currency switcher. Everything is scoped to the signed-in user.

### 3. Data Ingestion
*   Import from **CSV, Excel, PDF or images**. Indian bank-statement column aliases, comma amounts and day-first dates are handled. Preview valid/rejected/duplicate rows (download rejected rows as CSV, remap columns if headers aren't recognised), then confirm — or roll back the whole batch later.

### 4. Alerts & Investigation
*   A review queue of flagged transactions, each with a 0–100 risk score, level and reasons. Mark **Legitimate / Fraud / Reopen** with undo; those labels feed the next retrain. Request a Gemini explanation, and carry transaction context into the FinRAG workspace to compare against report evidence.

### 5. Predictive Simulator & Insights
*   Score a hypothetical transaction (fraud score, anomaly score, hybrid risk, reasons). The Insights page shows measured model metrics, a model-drift chart across retrains, and FinRAG benchmark results. Retraining can be restricted to admins via `ADMIN_EMAILS`.

### 6. Wealth, Planning & Credit
*   Track holdings with per-holding returns and an allocation chart, plus an AI portfolio-rebalancing review. Loan EMI and affordability calculators (with a year-by-year amortization + prepayment chart) and a credit-score simulator that starts from a real baseline derived from account history.

### 7. FinRAG Copilot
*   The flagship feature. A streaming three-pane chat (sources, conversation, evidence drawer). Add sources by upload, from 48 bundled 10-Ks, by SEC ticker, or by annual-report URL. Chat with one document, all documents, or Gemini alone. Answers stream token-by-token with live stage labels; inline `[n]` citations open the exact passage; conversations are saved server-side.

---

## 🔌 API Reference

The full, current endpoint list — authentication, transactions/import, ML & AI, FinRAG, and finance tools — is maintained in the main [README API reference](README.md#api-reference). All `/api/*` and `/upload*` routes require `Authorization: Bearer <JWT>` and are scoped to the token's user.

---

## ✅ Testing

```bash
python -m pytest -q
```

The pytest suite runs with MongoDB and Gemini mocked, so it needs no network access or credentials. It covers the OTP flow, upload pipeline, FinRAG parsing/retrieval/security, and the Transaction Intelligence detectors. See the [README testing section](README.md#testing) for the per-file breakdown.

---
*© 2026 FinRAG AI — BFSI Intelligence Platform. Decision support, not automated decisions.*
