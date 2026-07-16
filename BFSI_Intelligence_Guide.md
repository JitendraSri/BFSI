# 🏦 BFSI Intelligence Platform: The Complete Guide & Technical Architecture

Welcome to **BFSI Intelligence**, your all-in-one AI-powered financial security and intelligence platform. This comprehensive guide outlines the features, the underlying technology stack, and the complex machine learning algorithms that drive our enterprise-grade fraud detection system.

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
*   **Generative AI**: **Google Gemini Pro API**. Integrated via a custom `GenAIService` class for OCR, unstructured document parsing, and the interactive 'Cortex' AI financial advisor.

---

## 🧠 Core Algorithms & Intelligence Models

The BFSI Intelligence platform relies on three distinct algorithmic pipelines to ensure total financial security:

### 1. The Fraud Detection Algorithm (Random Forest)
At the heart of the platform is a supervised machine learning model built using the **RandomForestClassifier**.
*   **How it works**: It operates as an ensemble of numerous decision trees. Each tree makes a prediction on whether a transaction is fraudulent based on historical data. The forest then "votes" on the final outcome, drastically reducing overfitting compared to a single decision tree.
*   **Features Analyzed**: The algorithm analyzes continuous and categorical variables such as Transaction Amount, Payment Channel (UPI, Credit, NetBanking), Account Age, and KYC Status.
*   **Output**: It outputs a probabilistic risk score, classifying the transaction into 🔴 **High**, 🟡 **Medium**, or 🟢 **Low** risk.

### 2. Generative OCR & Parsing Pipeline (Gemini)
When users upload receipts (Images) or Bank Statements (PDFs), traditional OCR often fails at extracting relational data. 
*   **How it works**: We pass the raw document securely to the **Google Gemini multimodal LLM**. By using highly engineered prompt constraints, the LLM acts as an intelligent parser, extracting dates, merchants, and amounts, and structuring them strictly into machine-readable JSON format for our database.

### 3. Dynamic Trust Scoring Algorithm
Every user is assigned a Trust Score (0-100).
*   **How it works**: A deterministic weighted algorithm calculates this score dynamically. It rewards positive behaviors (e.g., fully verified KYC, consistent safe transactions) and penalizes risky behaviors (e.g., recent flagged anomalies, rapid sequential high-value transfers). 

---

## 🚀 Platform Features & User Guide

### 1. The Entry Point (Premium Hero Section)
*   **Visuals**: Features a CSS-only 3D mock dashboard, live particle nodes, glowing network connections, and responsive typography.
*   **Action**: Click **"Start Free Trial"** or **"Login"** to enter the secure zone.

### 2. 🔐 Authentication & Security
*   **Registration**: Sign up with email and password.
*   **OTP Verification**: Receive a 6-digit OTP via email to verify identity during sign-up or password resets.
*   **Session Management**: Secure, timeout-based sessions that require re-authentication for sensitive actions.

### 3. 📊 The Hub: Unified Dashboard
Your central cockpit for financial monitoring.
*   **Metrics**: Total Balance, dynamic Trust Score, and live threat counts.
*   **Visualizations**: CSS/JS-driven charts detailing Income vs. Expense, Transaction Volume history, and categorical spending breakdowns.
*   **Live Feed**: A real-time stream of the latest transactions and their AI-assigned safety status.

### 4. 📥 Data Ingestion
*   **CSV/Excel**: Bulk upload historical bank statements.
*   **AI Document Analysis**: Upload Image/PDF receipts and let the Gemini parsing algorithm automatically extract the data.

### 5. 🛡️ Alerts & Threat Management
*   **Anomalies**: View transactions flagged by the Random Forest model.
*   **Actionable Intelligence**: Approve or block flagged transactions directly from the UI to train the system.

### 6. 🔮 Predictive Simulator
*   **Transaction Simulator**: Manually input transaction parameters (Amount, Channel, etc.) to query the Random Forest model *before* execution. The AI will output the exact % probability of fraud.
*   **Model Insights**: View the backend ML metrics (Accuracy, Precision, Recall) directly in the UI.

### 7. 💰 Wealth & Portfolio Management
*   **Tracking**: Aggregate Stocks, Mutual Funds, Gold, Real Estate, and Crypto.
*   **Cortex Advisor**: Trigger the Gemini AI to analyze your current asset distribution and provide personalized diversification strategies.

### 8. 🧮 Financial Planning Tools
*   **Calculators**: Interactive Loan EMI calculators and Eligibility Checkers.
*   **Budgeting**: Set limits and track spending velocity.
*   **Credit Simulation**: Model how specific financial actions impact your credit worthiness over time.

---

## 🔌 Complete API Reference

### 🔐 Authentication & Identity
*   `POST /register`: Create a new user account.
*   `POST /login`: Authenticate and initialize session.
*   `POST /verify-registration`: Validate email via OTP.
*   `POST /forgot-password` & `POST /reset-password`: OTP-based credential recovery.

### 📥 Data & Transactions
*   `POST /upload`: Process CSV/Excel or trigger Gemini for Image/PDF parsing.
*   `GET /get-transactions`: Retrieve structured transaction history.
*   `POST /analyze-transaction`: Trigger Random Forest inference on a specific record.
*   `DELETE /delete-transaction/<id>`: Remove records.

### 🧠 AI & Analytics
*   `POST /predict-fraud`: Run the predictive simulator inference.
*   `POST /chat-advisor`: Communicate with the Gemini LLM financial advisor.
*   `GET /metrics`: Fetch current Random Forest evaluation metrics.
*   `GET /get-model-tips`: Generate AI recommendations to improve the ML pipeline.

### 💰 Financial Modules
*   `POST /transfer`: Execute simulated fund transfers.
*   `POST /handle-investments`: Mutate portfolio state.
*   `POST /analyze-portfolio`: Request LLM-based portfolio analysis.
*   `POST /apply-loan`: Submit loan applications.

### ⚙️ System Tools
*   `GET /test-atlas` & `GET /test_db`: Database health and connectivity checks.

---
*© 2026 BFSI Intelligence Platform - Built with purely Vanilla Web Technologies and cutting-edge AI.*
