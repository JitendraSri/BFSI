# FinRAG AI: Project Guide & Technical Architecture

Welcome to **FinRAG AI — Integrated Financial Intelligence Platform**. The project brings transaction-risk review and financial-document question answering into one workspace, while retaining the existing financial-planning modules.

## Current Build Baseline

The shipped implementation preserves the existing Vanilla HTML/CSS/JavaScript frontend, Flask API, MongoDB storage, Scikit-learn fraud model, and Google Gemini integrations. Its bundled data includes 5,000 labeled transaction records (4,568 non-fraud and 432 fraud) and 48 financial-report documents.

The current document-answering path extracts searchable text, chunks it with source/page metadata, ranks passages using TF-IDF and BM25 reciprocal-rank fusion, and asks Gemini to answer from those passages with source citations. PDF citations include page numbers where available; HTML report citations identify the source document. The RAG workspace also supports normal Gemini conversation when no document is selected or no relevant passage matches, with recent chat context for follow-up questions; these responses are identified as general AI answers rather than document-grounded evidence.

Dense embeddings, metadata-aware filtering, table-preserving extraction, cross-encoder reranking, and multi-hop evidence chaining are research extensions in the supplied project materials, not capabilities claimed by this build. Model flags and imported fraud labels are investigation signals, not confirmed fraud findings. Model scores are not calibrated probabilities.

---

## 🛠️ Complete Technology Stack

The platform is built on a highly optimized, modern technology stack designed for performance, security, and scalability.

### Frontend Architecture (Client-Side)
*   **Core Structure**: Semantic **HTML5**.
*   **Styling**: **Modern Vanilla CSS3**. We intentionally avoided frameworks like React, Tailwind, or Bootstrap to ensure zero bloat and maximum rendering performance.
*   **Design System**: Premium Enterprise SaaS UI featuring Glassmorphism, 3D CSS parallax effects, animated mesh gradients (`#050816` deep navy theme), and hardware-accelerated 60 FPS CSS animations.
*   **Interactivity**: **Vanilla JavaScript (ES6+)**. Utilizes modern browser APIs like `IntersectionObserver` for scroll animations, custom event listeners for interactive 3D mock dashboards, and the `Fetch API` for asynchronous backend communication.

### Backend Architecture (Server-Side)
*   **Language**: **Python 3.x**.
*   **Framework**: **Flask** (Micro-framework chosen for lightweight, fast API routing).
*   **Database**: **MongoDB (Atlas Cloud)**. A NoSQL database used for storing unstructured user data, transaction logs, and dynamic risk scores.
*   **Security & Auth**: Custom session/JWT management. Email-based **OTP (One-Time Password) Verification** powered by SMTP.

### AI & Machine Learning Stack
*   **Machine Learning**: **Scikit-Learn** (Algorithms, Metrics), **Pandas** (Data manipulation), **NumPy** (Numerical operations), **Joblib** (Model serialization).
*   **Generative AI**: **Google Gemini API**. Integrated through the existing service for document parsing, transaction explanations, portfolio analysis, and document-grounded question answering.

---

## 🧠 Core Algorithms & Intelligence Models

The FinRAG AI platform combines transaction-risk scoring, document parsing and retrieval, and account-level financial heuristics:

### 1. The Fraud Detection Algorithm (Random Forest)
At the heart of the platform is a supervised machine learning model built using the **RandomForestClassifier**.
*   **How it works**: It operates as an ensemble of numerous decision trees. Each tree makes a prediction on whether a transaction is fraudulent based on historical data. The forest then "votes" on the final outcome, drastically reducing overfitting compared to a single decision tree.
*   **Features Analyzed**: Transaction amount, payment channel, account age, and KYC status. The bundled labeled dataset uses Mobile, POS, ATM, and Web channel values.
*   **Output**: It returns an uncalibrated model score used as a review signal. Displayed risk bands are not verified fraud findings.
*   **Evaluation**: The bundled dataset is imbalanced, so class-level precision, recall, and F1 should be reviewed alongside overall accuracy.

### 2. Generative OCR & Parsing Pipeline (Gemini)
When users upload receipts (Images) or Bank Statements (PDFs), traditional OCR often fails at extracting relational data. 
*   **How it works**: We pass the raw document securely to the **Google Gemini multimodal LLM**. By using highly engineered prompt constraints, the LLM acts as an intelligent parser, extracting dates, merchants, and amounts, and structuring them strictly into machine-readable JSON format for our database.

### 3. Financial Document Retrieval-Augmented Generation
The private FinRAG workspace indexes PDFs, HTML, Markdown, and text documents, as well as the bundled financial-report catalog.
*   **Retrieval**: Document chunks are ranked with TF-IDF and BM25, then combined using reciprocal-rank fusion. This is lexical retrieval; the current build does not use dense embeddings or a vector database.
*   **Grounded answers**: Gemini receives the top matching excerpts and is instructed to answer only from those excerpts, cite the provided source numbers, and say when the evidence does not contain the answer.
*   **Traceability**: Retrieved passages retain their source name and PDF page number when available. Each user's indexed documents are stored in an isolated directory.
*   **Conversational mode**: Users can chat without selecting a document, ask everyday questions, and ask follow-ups. Responses are labeled as general AI answers when no evidence was retrieved.

### 4. Dynamic Trust Scoring Heuristic
Every user is assigned a Trust Score (0-100).
*   **How it works**: A deterministic weighted heuristic uses KYC state, flagged-record ratio, recent activity, account age, and balance tiers. It is a profile indicator—not a credit score or validated measure of trust.

---

## 🚀 Platform Features & User Guide

### 1. The Entry Point
*   **Visuals**: Features a CSS-only 3D mock dashboard, live particle nodes, glowing network connections, and responsive typography.
*   **Action**: Create an account or sign in to open the authenticated workspace.

### 2. 🔐 Authentication & Security
*   **Registration**: Sign up with email and password.
*   **OTP Verification**: Receive a 6-digit OTP via email to verify identity during sign-up or password resets.
*   **Session Management**: Secure, timeout-based sessions that require re-authentication for sensitive actions.

### 3. 📊 The Hub: Unified Dashboard
Your central cockpit for financial monitoring.
*   **Metrics**: Account profile indicators, transaction counts, and flagged-record counts.
*   **Visualizations**: Transaction volume, income vs. expense, categories, flagged-record trends, and available forecasts.
*   **Live Feed**: Recent activity for the signed-in user. Model flags and uploaded labels remain review signals.

### 4. 📥 Data Ingestion
*   **CSV/Excel**: Bulk upload historical bank statements.
*   **AI Document Analysis**: Upload supported statement/image documents through the existing Gemini parsing pipeline and review the transaction preview before confirming an import.

### 5. 🛡️ Alerts & Investigation
*   **Review queue**: Inspect records carrying a fraud label or model flag without presenting either as a confirmed finding.
*   **AI explanation**: Request an explanation through the existing Gemini integration.
*   **Evidence handoff**: Carry transaction context into the FinRAG workspace, select a report, and compare the answer with its retrieved source passages.

### 6. 🔮 Predictive Simulator
*   **Transaction Simulator**: Manually input transaction parameters (amount, channel, account age, KYC state) to query the Random Forest model. Its output is an uncalibrated score, not an exact probability or confirmed fraud decision.
*   **Model Insights**: View the backend ML metrics (Accuracy, Precision, Recall) directly in the UI.

### 7. 💰 Wealth & Portfolio Management
*   **Tracking**: Aggregate Stocks, Mutual Funds, Gold, Real Estate, and Crypto.
*   **Cortex Advisor**: Trigger the Gemini AI to analyze your current asset distribution and provide personalized diversification strategies.

### 8. 🧮 Financial Planning Tools
*   **Calculators**: Interactive Loan EMI calculators and Eligibility Checkers.
*   **Credit Simulation**: Model how specific financial actions impact your credit worthiness over time.
*   The budget page has been removed from the website navigation and routes; its existing API endpoints are retained.

### 9. 📚 FinRAG Workspace
*   **Sources**: Index private PDFs, HTML, Markdown, and text documents, or choose a bundled financial report.
*   **Retrieval**: Combine TF-IDF and BM25 rankings with reciprocal-rank fusion, then send the strongest passages to Gemini.
*   **Evidence**: Review the returned source citations and page numbers where available. A flagged transaction can be carried into this workspace as analyst context.

---

## 🔌 API Reference

### 🔐 Authentication & Identity
*   `POST /register`: Create a new user account.
*   `POST /login`: Authenticate and initialize session.
*   `POST /resend-registration-otp`: Request another registration OTP.
*   `POST /verify-registration`: Validate email via OTP.
*   `POST /forgot-password` & `POST /reset-password`: OTP-based credential recovery.
*   `GET /api/profile` & `PUT /api/profile`: Retrieve or update the signed-in user's profile.

### 📥 Data & Transactions
*   `POST /upload`: Preview CSV/Excel imports or supported Gemini-parsed documents.
*   `POST /upload/map`, `/upload/confirm`, `/upload/rollback`: Map fields, commit an import, or roll it back.
*   `GET /api/transactions` & `DELETE /api/transactions/<id>`: List or delete the signed-in user's records.
*   `GET /api/alerts`: Retrieve records carrying a fraud label or model flag.

### 🧠 AI & Analytics
*   `POST /api/predict` & `POST /api/retrain`: Run inference or retrain the existing model.
*   `GET /api/metrics` & `GET /api/model-tips`: Retrieve model metrics and improvement guidance.
*   `POST /api/analyze` & `POST /api/chat`: Request a transaction explanation or advisor response.
*   `GET /api/rag/documents`, `GET /api/rag/catalog`, `POST /api/rag/index`, and `POST /api/rag/ask`: Manage sources and ask document-grounded questions.

### 💰 Financial Modules
*   `GET/POST /api/investments` and `POST /api/investments/analyze`: Manage and review the user-entered portfolio.
*   `POST /api/loan/emi`, `/api/check-loan-eligibility`, and `/api/loan/apply`: Run loan planning actions.
*   `GET/POST /api/credit-score`: Use the existing credit simulation module.
*   `GET /api/budget-data` and `POST /api/update-budget`: Existing endpoints retained for compatibility; the budget page is not available in the website.

### ⚙️ System Tools
*   `GET /test-atlas` & `GET /test_db`: Database health and connectivity checks.

---
*© 2026 BFSI Intelligence Platform - Built with purely Vanilla Web Technologies and cutting-edge AI.*
