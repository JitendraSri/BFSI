# -*- coding: utf-8 -*-
import os
import io
import base64
import datetime
from datetime import timedelta
import time
from functools import wraps
import logging
import json
import math
import random
import re
import sys
import hashlib
import hmac
import secrets
import uuid
import argparse
from werkzeug.utils import secure_filename

# Third-party imports
from flask import Flask, request, jsonify, send_from_directory, render_template, Response
from flask_cors import CORS
from flask_caching import Cache
from flask_compress import Compress
from dotenv import load_dotenv
import pymongo
from bson.objectid import ObjectId
import certifi
import pandas as pd
import bcrypt
import jwt
import joblib
import google.generativeai as genai
from rag_service import ask_document, delete_document, index_document, index_finrag_report, list_available_reports, list_documents
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score, classification_report
from sklearn.metrics import accuracy_score, classification_report
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==========================================
# CONFIGURATION
# ==========================================
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'BFSI')
SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-secret')
MONGO_URI = os.getenv('MONGO_URI')

# SMTP Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp-relay.brevo.com")
try:
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
except ValueError:
    SMTP_PORT = 0
SMTP_LOGIN = os.getenv("SMTP_LOGIN")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
OTP_TTL_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_RESENDS_PER_HOUR = 5

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'assets', 'uploads')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'assets', 'logs', 'app.log')

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'models', 'fraud_model.pkl')
ENCODER_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'models', 'encoder.pkl')

# ==========================================
# UTILS
# ==========================================
def ensure_dirs():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'assets', 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'assets', 'uploads', 'profiles'), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(__file__), 'uploads', 'profiles'), exist_ok=True)
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

def get_logger(name='bfsi'):
    ensure_dirs()
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

# Configure global logger
logger = get_logger('bfsi.main') 

def safe_name(value):
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value).strip())
    return cleaned[:80] if cleaned else 'upload'


def validate_smtp_config(server=SMTP_SERVER, port=SMTP_PORT, login=SMTP_LOGIN,
                         password=SMTP_PASSWORD, sender=SENDER_EMAIL):
    errors = []
    if server != "smtp-relay.brevo.com":
        errors.append("SMTP_SERVER must be smtp-relay.brevo.com")
    if port != 587:
        errors.append("SMTP_PORT must be 587")
    for name, value in (("SMTP_LOGIN", login), ("SMTP_PASSWORD", password), ("SENDER_EMAIL", sender)):
        if not value:
            errors.append(f"{name} is required")
    return errors


def _otp_digest(email, otp):
    message = f"{email.strip().casefold()}:{otp}".encode("utf-8")
    return hmac.new(SECRET_KEY.encode("utf-8"), message, hashlib.sha256).hexdigest()


def send_otp_email(to_email, otp, subject="Your Verification Code"):
    configuration_errors = validate_smtp_config()
    if configuration_errors:
        logger.error("OTP email configuration invalid: %s", ", ".join(configuration_errors))
        return False

    stage = "connect"
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = to_email
        msg['Subject'] = subject

        body = f"""
        <html>
          <body>
            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 5px;">
              <h2 style="color: #333;">Verification Code</h2>
              <p>Your One-Time Password (OTP) is:</p>
              <h1 style="color: #4CAF50; letter-spacing: 5px;">{otp}</h1>
              <p>This code is valid for 10 minutes.</p>
              <p>If you did not request this, please ignore this email.</p>
            </div>
          </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            stage = "STARTTLS"
            server.starttls()
            server.ehlo()
            stage = "authentication"
            server.login(SMTP_LOGIN, SMTP_PASSWORD)
            stage = "message delivery"
            server.send_message(msg)
        logger.info("OTP email sent successfully")
        return True
    except Exception as e:
        logger.error("OTP email delivery failed during %s (%s)", stage, type(e).__name__)
        return False 

# ==========================================
# GENAI SERVICE
# ==========================================
class GenAIService:
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not found in environment")
            self.model = None
            return

        try:
            genai.configure(api_key=self.api_key)
            # Valid models from list: models/gemini-flash-latest, models/gemini-pro-latest, models/gemini-2.0-flash
            self.model = genai.GenerativeModel('models/gemini-flash-lite-latest')
        except Exception as e:
            logger.error(f"Failed to configure GenAI: {e}")
            self.model = None

    def analyze_transaction(self, transaction_data):
        """
        Analyzes a transaction and returns a risk explanation.
        """
        if not self.model:
            return "AI service unavailable: API key missing or invalid."

        prompt = f"""
        Analyze the following financial transaction for potential fraud risk.
        Provide a concise explanation of why it might be risky or safe.
        IMPORTANT: All monetary amounts must be expressed in Indian Rupees (₹).
        
        Transaction Details:
        - Amount: ₹{transaction_data.get('amount')}
        - Channel: {transaction_data.get('channel')}
        - Account Age (days): {transaction_data.get('account_age')}
        - KYC Verified: {transaction_data.get('kyc_verified')}
        - Time: {transaction_data.get('timestamp')}
        
        Response Format:
         Risk Level: [Low/Medium/High]
         Explanation: [Your explanation here, using ₹ for any amounts]
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"GenAI generation error: {e}")
            if "429" in str(e):
                return "⚠️ AI Service Busy: Quota Exceeded. Please try again later."
            return f"Error generating AI analysis: {str(e)[:50]}..."

    def analyze_document(self, file_path, mime_type):
        """
        Analyze document (PDF/Image) and extract transaction data using AI
        """
        # Check if API key is available
        if not self.api_key:
            # Try to get API key from environment
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                raise Exception("GEMINI_API_KEY not configured. Please set it in backend/.env file to analyze documents.")
        
        try:
            # Use the configured model or create a new one
            if self.model:
                model = self.model
            else:
                api_key_to_use = self.api_key or os.getenv('GEMINI_API_KEY')
                # available: models/gemini-flash-lite-latest
                model = genai.GenerativeModel('models/gemini-flash-lite-latest')
            
            with open(file_path, "rb") as f:
                file_data = f.read()

            prompt = """
            You are a financial fraud detection expert. Analyze this document/image.
            
            IMPORTANT: All monetary amounts must be expressed in Indian Rupees (₹).
            
            Return a JSON object with the following structure:
            {
                "explanation": "A concise HTML-formatted summary (using <p>, <ul>, <li>, <strong>) of the document. Focus on: Vendor, Items, Total Amount (in ₹), and any Risk Factors. Do NOT use markdown tables.",
                "risk_percentage": 0,  // Integer 0-100 indicating fraud risk
                "csv_data": "transaction_id,customer_id,kyc_verified,account_age_days,transaction_amount_in_rupees,channel,timestamp,is_fraud\\n..." 
            }

            For the 'csv_data' field:
            Extract ALL transactions in EXACT CSV format with this header:
            transaction_id,customer_id,kyc_verified,account_age_days,transaction_amount,channel,timestamp,is_fraud
            
            Rules for CSV:
            - transaction_amount: Numeric only (representing value in ₹)
            - transaction_id: Generate 'TXN_' + random digits
            - customer_id: Generate 'CUST_' + random digits
            - is_fraud: 0
            - If no transactions are visible, set csv_data to empty string.
            
            Return ONLY valid JSON.
            """

            parts = [
                {"mime_type": mime_type, "data": file_data},
                prompt
            ]

            response = model.generate_content(parts)
            text = response.text
            
            # Clean up markdown
            text = text.replace('```json', '').replace('```', '').strip()
            
            import json
            try:
                result = json.loads(text)
                return result
            except:
                # Fallback if AI fails to return JSON
                return {
                    "explanation": "Could not structure analysis.",
                    "risk_percentage": 0,
                    "csv_data": text if "transaction_id" in text else ""
                }

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Document analysis error: {error_msg}")
            raise Exception(f"Failed to analyze document: {error_msg}")

    def get_model_improvement_tips(self, metrics):
        """Generates tips to improve model based on current metrics"""
        # Try using the configured model first
        if self.model:
            try:
                prompt = f"""
                Act as an Expert Data Scientist. Analyze these Random Forest model metrics for Fraud Detection:
                {metrics}
                
                Provide 3-5 specific, technical actionable steps to improve these results.
                Focus on: Data balancing (SMOTE), Feature Engineering, or Hyperparameter tuning.
                Keep it concise and bulleted.
                """
                
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                logger.error(f"GenAI tips generation failed: {e}")
                # Fall through to fallback
        else:
            # Try creating a new model instance (might work if API key is in env)
            try:
                if self.api_key:
                    model = genai.GenerativeModel('models/gemini-flash-latest')
                    prompt = f"""
                    Act as an Expert Data Scientist. Analyze these Random Forest model metrics for Fraud Detection:
                    {metrics}
                    
                    Provide 3-5 specific, technical actionable steps to improve these results.
                    Focus on: Data balancing (SMOTE), Feature Engineering, or Hyperparameter tuning.
                    Keep it concise and bulleted.
                    """
                    response = model.generate_content(prompt)
                    return response.text
            except Exception as e:
                logger.error(f"GenAI tips generation failed: {e}")
        
        # Fallback: Provide basic tips based on metrics
        try:
            import json
            if isinstance(metrics, str):
                metrics_dict = json.loads(metrics)
            else:
                metrics_dict = metrics
            
            accuracy = metrics_dict.get('accuracy', 0)
            precision = metrics_dict.get('precision', 0)
            recall = metrics_dict.get('recall', 0)
            f1 = metrics_dict.get('f1_score', 0)
            
            tips = []
            tips.append("**General Model Improvement Recommendations:**")
            
            if accuracy < 0.8:
                tips.append("• **Improve Data Quality**: Clean and preprocess data to reduce noise and handle missing values effectively.")
                tips.append("• **Feature Engineering**: Create additional features that capture transaction patterns (time-based, frequency, velocity).")
            
            if precision < 0.7 or recall < 0.7:
                tips.append("• **Address Class Imbalance**: Use SMOTE (Synthetic Minority Oversampling) or adjust class weights to handle fraud class imbalance.")
                tips.append("• **Hyperparameter Tuning**: Optimize Random Forest parameters (n_estimators, max_depth, min_samples_split) using GridSearchCV.")
            
            if f1 < 0.7:
                tips.append("• **Threshold Tuning**: Adjust the classification threshold to balance precision and recall based on business requirements.")
                tips.append("• **Ensemble Methods**: Consider combining multiple models (bagging, boosting) for better performance.")
            
            tips.append("• **More Training Data**: Collect more labeled fraud cases to improve model generalization.")
            tips.append("• **Feature Selection**: Remove irrelevant features and focus on the most predictive ones using feature importance analysis.")
            
            return "\n".join(tips)
        except:
            return "**Model Improvement Tips:**\n• Balance your dataset using SMOTE or class weights\n• Perform feature engineering to capture more patterns\n• Tune hyperparameters (n_estimators, max_depth)\n• Collect more training data, especially fraud cases\n• Consider ensemble methods for better accuracy"

    def analyze_portfolio(self, portfolio_data, risk_profile, user_name="Investor"):
        """
        Analyzes investment portfolio and suggests rebalancing.
        """
        if not self.model:
            return "AI advisor unavailable."

        prompt = f"""
        Act as a Senior Wealth Manager. Analyze this investment portfolio for your client, {user_name} ({risk_profile} risk profile).
        
        IMPORTANT: All monetary amounts must be expressed in Indian Rupees (₹).
        
        Current Portfolio:
        {json.dumps(portfolio_data, indent=2)}
        
        Task:
        1. Start the response by addressing the user as "Dear {user_name},".
        2. Calculate current asset allocation (Stocks, Mutual Funds, Gold, etc.)
        3. Compare against ideal allocation for {risk_profile} profile.
        4. Suggest specific rebalancing actions (e.g., "Reduce Tech Stocks by ₹10,000, Buy Gold").
        5. highlight any concentration risks.
        
        Output format needs to be HTML (using <ul>, <li>, <b>, <p>) for direct display.
        All amounts in the HTML should be prefixed with ₹.
        Keep it professional, encouraging, and data-driven.
        """
        
        try:
            response = self.model.generate_content(prompt)
            # Clean up markdown if present
            cleaned_text = response.text.replace('```html', '').replace('```', '').strip()
            return cleaned_text
        except Exception as e:
            logger.error(f"Portfolio analysis failed: {e}")
            return "Could not analyze portfolio at this time."


    def chat_with_advisor(self, query, context):
        """
        Chat with AI Advisor. Returns plain text response.
        """
        # 1. Try Gemini (Online)
        if self.model:
            try:
                system_instruction = f"""
                You are "Cortex", a specialized BFSI Financial Advisor for the Indian market.
                User Context: {context}
                
                GOAL:
                Provide helpful, accurate, and data-backed financial advice.
                
                IMPORTANT: All monetary amounts MUST be expressed in Indian Rupees (₹). Never use dollars ($).
                
                SCOPE:
                - Answer questions about Loans, Banking, Investments, Insurance, Fraud, Tax, and the user's account (Balance, Risk).
                - If the user asks about non-financial topics (e.g., jokes, coding, movies), politely decline saying you only discuss finance.
                
                GUIDELINES:
                - Be concise, professional, and warm.
                - For "Loan" requests, explain the criteria or benefits.
                - For "Transfer" requests, guide them to the dashboard actions.
                - Use ₹ symbol for all currency values.
                """
                
                full_prompt = f"{system_instruction}\n\nUser: {query}\nAdvisor:"
                response = self.model.generate_content(full_prompt)
                return response.text
            except Exception as e:
                logger.error(f"Gemini API Failed: {e}")
                # Fall through to fallback
        
        # 2. Fallback Logic (Offline) - Enhanced with more financial queries
        query_lower = query.lower()
        
        if "risk" in query_lower:
            risk = context.get('risk_level', 'Unknown')
            return f"Based on your recent transaction patterns, your current Fraud Risk Level is {risk}. We monitor this 24/7 for you."
        
        elif "balance" in query_lower:
            bal = context.get('balance', 0)
            return f"Your current available balance is ₹{bal:,.2f}."
            
        elif "hello" in query_lower or "hi" in query_lower or "hey" in query_lower:
            return "Hello! I'm Cortex, your AI financial assistant. How can I help you manage your wealth today?"
        
        elif "loan" in query_lower:
            if "personal" in query_lower:
                return """To secure a Personal Loan, we primarily look at your eligibility based on:

1. **Credit Score:** A strong credit history demonstrates repayment reliability (typically 650+).
2. **Income Stability:** Verification of a stable and sufficient income stream.
3. **Debt-to-Income Ratio:** Assessment of your current financial obligations relative to your earnings (ideally below 40%).

You can initiate the application directly through the **'Loans'** section on your main dashboard. Our system will analyze your current financial standing and active transaction history for specific pre-approval options.

Would you like me to check your current eligibility status?"""
            else:
                return """We offer various loan products including Personal Loans, Home Loans, Auto Loans, and Business Loans.

Key criteria for loan approval generally include:
- Credit Score (typically 650+)
- Stable income verification
- Debt-to-Income Ratio (below 40% preferred)

You can apply through the **'Loans'** section on your dashboard. What type of loan are you interested in?"""
        
        elif "investment" in query_lower or "invest" in query_lower:
            return """We offer a range of investment products:

- **Fixed Deposits:** Safe, guaranteed returns
- **Mutual Funds:** Diversified portfolios managed by experts
- **Stocks & Equity:** Direct equity investments
- **Bonds:** Government and corporate bonds
- **Insurance-linked Investments:** ULIPs and pension plans

Your current balance and risk profile can help us recommend suitable options. Would you like personalized investment advice based on your profile?"""
        
        elif "insurance" in query_lower:
            return """We offer various insurance products:

- **Life Insurance:** Term and whole life policies
- **Health Insurance:** Comprehensive medical coverage
- **Vehicle Insurance:** Auto and bike coverage
- **Home Insurance:** Property protection

You can request quotes through the **'Insurance'** section on your dashboard. What type of coverage are you looking for?"""
        
        elif "transfer" in query_lower or "send money" in query_lower:
            bal = context.get('balance', 0)
            return f"""You can transfer funds through the **'Transfer'** section on your dashboard.

Your current available balance is ₹{bal:,.2f}. 

To initiate a transfer:
1. Go to the Transfer section
2. Enter recipient details and amount
3. Confirm the transaction

Is there anything specific about transfers you'd like to know?"""
        
        elif "fraud" in query_lower or "security" in query_lower:
            risk = context.get('risk_level', 'Unknown')
            return f"""We take security seriously. Your account is currently showing a **{risk}** fraud risk level.

Our system monitors:
- Unusual transaction patterns
- Location-based anomalies
- Velocity checks
- Device fingerprinting

All suspicious activities are flagged and reviewed. You can check your fraud alerts in the **'Fraud Alerts'** section. Is there a specific security concern you have?"""
            
        else:
            return """I'm currently running in offline mode. I can help you with:

• **Balance & Account Info** - Check your account balance
• **Loans** - Personal, Home, Auto, Business loans
• **Investments** - FDs, Mutual Funds, Stocks, Bonds
• **Insurance** - Life, Health, Vehicle, Home insurance
• **Transfers** - Send money instructions
• **Risk & Security** - Fraud risk assessment

For more detailed assistance, please ensure the Gemini API key is configured, or use the specific sections on your dashboard. What would you like to know?"""

# ==========================================
# ML TRAINING
# ==========================================
def train_model():
    """
    Fetches data from DB, trains a Random Forest model, and saves artifacts.
    """
    logger.info("Starting model training...")
    try:
        client = pymongo.MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True)
        db = client[DB_NAME]
        
        # Fetch required fields, exclude _id
        cursor = db.transactions.find({}, 
            {'transaction_amount': 1, 'channel': 1, 'account_age_days': 1, 'kyc_verified': 1, 'is_fraud': 1, '_id': 0}
        )
        df = pd.DataFrame(list(cursor))


        if df.empty:
            logger.warning("No data found in transactions table. Cannot train model.")
            return {"status": "error", "message": "No data available"}

        # Preprocessing
        # Fill missing values with median/mode instead of just 0
        df['transaction_amount'] = df['transaction_amount'].fillna(df['transaction_amount'].median())
        df['account_age_days'] = df['account_age_days'].fillna(df['account_age_days'].median())
        df['kyc_verified'] = df['kyc_verified'].fillna(0)
        df['channel'] = df['channel'].fillna('Unknown')

        # Encode Channel
        le = LabelEncoder()
        df['channel'] = le.fit_transform(df['channel'].astype(str))
        
        # Features & Target
        X = df[['transaction_amount', 'channel', 'account_age_days', 'kyc_verified']]
        y = df['is_fraud']

        # Train Test Split with Stratification
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

        # Model - Use balanced class weights and more estimators
        # Stratified split ensures fraud cases are in both sets
        clf = RandomForestClassifier(
            n_estimators=200, 
            class_weight='balanced_subsample', 
            random_state=42,
            max_depth=10,
            min_samples_split=5
        )
        clf.fit(X_train, y_train)

        # Evaluation
        y_pred = clf.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True)
        
        # Extract metrics safely - Use Weighted Average for better overall visibility
        precision = report.get('weighted avg', {}).get('precision', 0.0)
        recall = report.get('weighted avg', {}).get('recall', 0.0)
        f1 = report.get('weighted avg', {}).get('f1-score', 0.0)
        
        # Log class-specific metrics for debugging
        fraud_f1 = report.get('1', {}).get('f1-score', 0.0)
        logger.info(f"Model trained. Accuracy: {accuracy:.2f}, Weighted F1: {f1:.2f}, Fraud F1: {fraud_f1:.2f}")

        # Save Artifacts
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump(clf, MODEL_PATH)
        joblib.dump(le, ENCODER_PATH)
        
        metrics = {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'report': report
        }
        
        metrics_path = os.path.join(os.path.dirname(MODEL_PATH), 'metrics.json')
        with open(metrics_path, 'w') as f:
            json.dump(metrics, f)

        return {
            "status": "success",
            "metrics": metrics
        }

    except Exception as e:
        logger.error(f"Training failed with exception: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(e)}

# ==========================================
# MAIN APP
# ==========================================

# Global ML Model objects
ml_model = None
encoder = None

def load_ml_model():
    global ml_model, encoder
    try:
        if os.path.exists(MODEL_PATH) and os.path.exists(ENCODER_PATH):
            ml_model = joblib.load(MODEL_PATH)
            encoder = joblib.load(ENCODER_PATH)
            print("ML Model loaded successfully.")
    except Exception as e:
        print(f"Failed to load ML model: {e}")

load_ml_model()

# ==========================================
# INITIALIZE GENAI
# ==========================================
genai_service = GenAIService()

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app, resources={r"/*": {"origins": "*"}})

# --- PERFORMANCE CONFIG ---
# 1. COMPRESSION (Gzip/Brotli)
Compress(app)

# 2. CACHING (In-Memory SimpleCache)
# Switched to SimpleCache to avoid Redis timeouts on Windows without WSL
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

# --- LATENCY MONITORING ---
import time
@app.before_request
def start_timer():
    request.start_time = time.time()

@app.after_request
def log_request(response):
    if hasattr(request, 'start_time'):
        duration = (time.time() - request.start_time) * 1000
        # Add Timing Header
        response.headers['X-Process-Time'] = f"{duration:.2f}ms"
        print(f" >>> [PERF] {request.method} {request.path} completed in {duration:.2f}ms")
    return response
# --------------------------

# ==========================================
# PAGE ROUTES
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('auth.html') # Assuming auth.html handles login/register

@app.route('/register')
def register_page():
    # If using same auth.html, just render it. 
    # If distinct pages, use appropriate template.
    return render_template('auth.html') 

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/fraud-alerts')
def fraud_alerts():
    return render_template('fraudalerts.html')

@app.route('/rag')
def rag_page():
    return render_template('rag.html')

def rag_user_id():
    user_id = request.user.get('user_id') or request.user.get('id') or request.user.get('email')
    if not user_id:
        return None
    return str(user_id)

# Catch-all for simple pages if they exist directly
@app.route('/<path:filename>.html')
def serve_html(filename):
    return render_template(f'{filename}.html')

@app.route('/test_db', methods=['GET'])
def test_db():
    print("DEBUG: test_db called")
    try:
        db = get_db()
        count = db.users.count_documents({})
        return jsonify({'count': count})
    except Exception as e:
        print(f"DEBUG: test_db failed: {e}")
        return jsonify({'error': str(e)}), 500

# Global client
print(f"DEBUG: MongoDB URI configured: {bool(MONGO_URI)}")
try:
    print(f"DEBUG: Connecting to DB...")
    # Attempt connection but do not crash if it fails immediately
    # OPTIMIZATION: Connection Pooling
    client = pymongo.MongoClient(
        MONGO_URI, 
        tlsAllowInvalidCertificates=True, 
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=5000,
        maxPoolSize=10
    )
    # Check connection
    client.server_info()
    print("DEBUG: MongoDB Atlas connection verified.")
except Exception as e:
    print(f"\nCRITICAL ERROR: Failed to connect to MongoDB: {e}\n")
    client = None
    db = None


db = client[DB_NAME] if client else None

@app.route('/test-atlas', methods=['GET'])
def test_atlas():
    """Explicitly test connection to Atlas and return result"""
    try:
        # Force a fresh connection attempt
        test_client = pymongo.MongoClient(MONGO_URI, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=3000)
        info = test_client.server_info()
        return jsonify({
            "status": "success",
            "message": "Connected to MongoDB Atlas successfully!",
            "version": info.get("version"),
            "uri": MONGO_URI.split('@')[1] if '@' in MONGO_URI else "HIDDEN"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Failed to connect to MongoDB Atlas",
            "reason": str(e),
            "tip": "Check your firewall/VPN. Port 27017 must be open."
        }), 503

def get_db():
    return db

# Initialize AI Service
genai_service = GenAIService()

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', None)
        if not auth or not auth.startswith('Bearer '):
            return jsonify({'error': 'Authorization header missing'}), 401
        token = auth.split(' ', 1)[1]
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            request.user = data
        except Exception as e:
            return jsonify({'error': 'Invalid token', 'detail': str(e)}), 401
        return f(*args, **kwargs)

    return decorated


@app.route('/api/rag/documents', methods=['GET'])
@auth_required
def rag_documents():
    user_id = rag_user_id()
    if not user_id:
        return jsonify({'error': 'User identity is missing from the access token'}), 401
    return jsonify({'documents': list_documents(user_id)})

@app.route('/api/rag/documents/<string:document_id>', methods=['DELETE'])
@auth_required
def rag_delete_document(document_id):
    user_id = rag_user_id()
    if not user_id:
        return jsonify({'error': 'User identity is missing from the access token'}), 401
    if not delete_document(user_id, document_id):
        return jsonify({'error': 'Document not found'}), 404
    return jsonify({'status': 'deleted'})

@app.route('/api/rag/catalog', methods=['GET'])
@auth_required
def rag_catalog():
    return jsonify({'reports': list_available_reports()})

@app.route('/api/rag/index', methods=['POST'])
@auth_required
def rag_index():
    user_id = rag_user_id()
    if not user_id:
        return jsonify({'error': 'User identity is missing from the access token'}), 401

    source_id = request.form.get('source_id', '').strip()
    if source_id:
        try:
            report = index_finrag_report(user_id, source_id)
        except FileNotFoundError:
            return jsonify({'error': 'That FinRAG report is not available'}), 404
        except ValueError as error:
            return jsonify({'error': str(error)}), 400
        except Exception:
            return jsonify({'error': 'The document could not be indexed'}), 500
        return jsonify({'document': report}), 201

    uploaded_file = request.files.get('file')
    if not uploaded_file or not uploaded_file.filename:
        return jsonify({'error': 'Choose a PDF, HTML, Markdown, or text document'}), 400

    content = uploaded_file.stream.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        return jsonify({'error': 'Documents must be 10 MB or smaller'}), 413

    try:
        document = index_document(user_id, uploaded_file.filename, content)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception:
        return jsonify({'error': 'The document could not be indexed'}), 500

    return jsonify({'document': document}), 201

@app.route('/api/rag/ask', methods=['POST'])
@auth_required
def rag_ask():
    user_id = rag_user_id()
    if not user_id:
        return jsonify({'error': 'User identity is missing from the access token'}), 401

    data = request.get_json(silent=True) or {}
    query = str(data.get('query', '')).strip()
    document_id = str(data.get('document_id', '')).strip()
    if not query or len(query) > 1000:
        return jsonify({'error': 'Enter a question of 1,000 characters or fewer'}), 400
    if not document_id:
        return jsonify({'error': 'Select an indexed document'}), 400

    try:
        result = ask_document(user_id, document_id, query, os.getenv('GEMINI_API_KEY'))
    except FileNotFoundError:
        return jsonify({'error': 'That document is not available in your library'}), 404
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    except Exception:
        return jsonify({'error': 'The answer could not be generated. Check model availability and try again.'}), 503

    return jsonify(result)


@app.route('/register', methods=['POST'])
def register():
    print(f"DEBUG: Register request hit. Content-Type: {request.content_type}")
    print("DEBUG: Register payload received.")
    data = request.get_json(silent=True)
    if not data:
        print("DEBUG: Register failed - Invalid JSON or no data")
        return jsonify({'error': 'Invalid JSON or no data provided'}), 400
        
    try:
        db = get_db()
        if db is None:
            return jsonify({
                'error': 'Database Connection Failed',
                'detail': 'Could not reach MongoDB Atlas. Check the connection string and network access.'
            }), 503
        existing_user = db.users.find_one({'email': data['email']})
        if existing_user:
            if not existing_user.get('is_verified'):
                return jsonify({
                    'error': 'This account is awaiting email verification. Request a new code below.',
                    'verification_pending': True,
                    'email': data['email']
                }), 409
            return jsonify({'error': 'Email already exists'}), 400
            
        hashed_password = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
        
        initial_balance = 0.0
        if data.get('initial_balance'):
            try:
                initial_balance = float(data['initial_balance'])
            except ValueError:
                initial_balance = 0.0
        
        user_id = str(uuid.uuid4())
        otp = f"{secrets.randbelow(1_000_000):06d}"
        now = datetime.datetime.now()
        otp_expiry = now + timedelta(minutes=OTP_TTL_MINUTES)

        user = {
            'user_id': user_id,
            'name': data['name'],
            'email': data['email'],
            'password_hash': hashed_password.decode('utf-8'),
            'balance': initial_balance,
            'kyc_status': 'Pending',
            'trust_score': 20 if initial_balance > 0 else 0, # Bonus for depositing
            'security_status': 'Moderate',
            'fraud_risk_level': 'Low',
            'created_at': now,
            'is_verified': False,
            'otp_hash': _otp_digest(data['email'], otp),
            'otp_expiry': otp_expiry,
            'otp_last_sent': now,
            'otp_resend_window_started_at': now,
            'otp_resend_count': 0
        }
        
        db.users.insert_one(user)
        
        if not send_otp_email(data['email'], otp):
            return jsonify({
                'error': 'Your account was created, but the verification email could not be sent. Wait 60 seconds, then request a new code.',
                'verification_pending': True,
                'email': data['email']
            }), 503
        
        return jsonify({'message': 'Registration successful! OTP sent.', 'user_id': user_id}), 201
        
    except Exception as e:
        print(f"DB Error during register: {e}")
        return jsonify({'error': 'Registration Failed', 'detail': str(e)}), 503


@app.route('/resend-registration-otp', methods=['POST'])
def resend_registration_otp():
    data = request.get_json(silent=True) or {}
    email = str(data.get('email', '')).strip()
    if not email or len(email) > 254:
        return jsonify({'error': 'Enter the email address used during registration.'}), 400

    db = get_db()
    if db is None:
        return jsonify({'error': 'Email verification is temporarily unavailable. Please try again later.'}), 503

    user = db.users.find_one({'email': email})
    if not user or user.get('is_verified'):
        return jsonify({'message': 'If this account is awaiting verification, a new code will be sent.'}), 202

    now = datetime.datetime.now()
    last_sent = user.get('otp_last_sent')
    if isinstance(last_sent, datetime.datetime):
        seconds_since_last = (now - last_sent).total_seconds()
        if seconds_since_last < OTP_RESEND_COOLDOWN_SECONDS:
            retry_after = max(1, OTP_RESEND_COOLDOWN_SECONDS - int(seconds_since_last))
            return jsonify({'error': f'Please wait {retry_after} seconds before requesting another code.'}), 429

    window_started = user.get('otp_resend_window_started_at')
    window_is_current = (
        isinstance(window_started, datetime.datetime)
        and now - window_started < timedelta(hours=1)
    )
    resend_count = user.get('otp_resend_count', 0) if window_is_current else 0
    if resend_count >= OTP_MAX_RESENDS_PER_HOUR:
        return jsonify({'error': 'You have reached the verification code resend limit. Try again later.'}), 429

    otp = f"{secrets.randbelow(1_000_000):06d}"
    otp_expiry = now + timedelta(minutes=OTP_TTL_MINUTES)
    next_window_started = window_started if window_is_current else now
    query = {'_id': user['_id'], 'is_verified': {'$ne': True}}
    for field in ('otp_last_sent', 'otp_resend_window_started_at', 'otp_resend_count'):
        query[field] = user[field] if field in user else {'$exists': False}

    update = {
        '$set': {
            'otp_hash': _otp_digest(email, otp),
            'otp_expiry': otp_expiry,
            'otp_last_sent': now,
            'otp_resend_window_started_at': next_window_started,
            'otp_resend_count': resend_count + 1
        },
        '$unset': {'otp_code': ''}
    }
    try:
        result = db.users.update_one(query, update)
    except Exception as error:
        logger.error("OTP resend database update failed (%s)", type(error).__name__)
        return jsonify({'error': 'Email verification is temporarily unavailable. Please try again later.'}), 503

    if result.matched_count != 1:
        return jsonify({'error': 'A code was just requested. Wait before trying again.'}), 429
    if not send_otp_email(email, otp):
        return jsonify({'error': 'A new code was created, but email delivery failed. Please try again after the cooldown.'}), 503
    return jsonify({'message': 'A new verification code was sent. Any earlier code is no longer valid.'}), 200


@app.route('/login', methods=['POST'])
def login():
    print(f"DEBUG: Login request hit. Content-Type: {request.content_type}")
    print("DEBUG: Login payload received.")
    payload = request.get_json(silent=True) or {}
    email = payload.get('email')
    password = payload.get('password')
    if not (email and password):
        print(f"DEBUG: Login failed - email or password missing. Payload keys: {list(payload.keys())}")
        return jsonify({'error': 'email and password required'}), 400
    
    try:
        print(f"DEBUG: Attempting to find user {email} in DB...")
        db = get_db()
        if db is None: raise Exception("Database not initialized")
        start = time.time()
        user = db.users.find_one({'email': email})
        print(f"DEBUG: DB search took {(time.time()-start)*1000:.2f}ms. Found: {user is not None}")
    except Exception as e:
        print(f"DB Error during login: {e}")
        return jsonify({'error': 'Database Connection Failed', 'detail': 'Could not reach MongoDB Atlas. Check network firewall.'}), 503
            
    print(f"DEBUG: Find user result: {user is not None}")
    
    print(f"DEBUG: Find user result: {user is not None}")
    
    if not user:
        return jsonify({'error': 'invalid credentials'}), 401
    
    # Check if verified (optional constraint, but good practice)
    if user.get('is_verified', False) is False:
         return jsonify({'error': 'Account not verified. Please verify your email.'}), 403

    if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({'error': 'invalid credentials'}), 401
    
    payload = {'user_id': user['user_id'], 'email': user['email'], 'iat': int(time.time())}
    token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')
    
    # Create a pruned user object for the frontend to avoid QuotaExceededError (e.g., from large profile images)
    essential_fields = ['user_id', 'name', 'email', 'balance', 'kyc_status', 'trust_score', 'security_status', 'fraud_risk_level', 'is_verified', 'created_at']
    clean_user = {k: user[k] for k in essential_fields if k in user}
    if '_id' in user: clean_user['_id'] = str(user['_id'])
    
    print(f"DEBUG: Returning pruned user data to frontend. Size: {len(str(clean_user))} chars")
    return jsonify({'status': 'ok', 'token': token, 'user': clean_user}), 200




@app.route('/verify-registration', methods=['POST'])
def verify_registration():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    
    if not email or not otp:
        return jsonify({'error': 'Email and OTP required'}), 400
        
    db = get_db()
    user = db.users.find_one({'email': email})
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    if user.get('is_verified'):
        return jsonify({'message': 'User already verified'}), 200
        
    stored_hash = user.get('otp_hash')
    if stored_hash:
        otp_is_valid = hmac.compare_digest(str(stored_hash), _otp_digest(email, str(otp)))
    else:
        otp_is_valid = hmac.compare_digest(str(user.get('otp_code', '')), str(otp))

    if otp_is_valid:
        # Check expiry
        if user.get('otp_expiry') and user['otp_expiry'] > datetime.datetime.now():
            db.users.update_one(
                {'email': email},
                {
                    '$set': {'is_verified': True},
                    '$unset': {'otp_hash': '', 'otp_code': '', 'otp_expiry': '', 'otp_last_sent': ''}
                }
            )
            return jsonify({'message': 'Verification successful. You can now login.'}), 200
        else:
             return jsonify({'error': 'OTP expired'}), 400
    else:
        return jsonify({'error': 'Invalid OTP'}), 400

@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')
    
    if not email:
         return jsonify({'error': 'Email required'}), 400
         
    db = get_db()
    if db is None:
        return jsonify({'error': 'Password reset email is temporarily unavailable. Please try again later.'}), 503
    user = db.users.find_one({'email': email})
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    otp = str(random.randint(100000, 999999))
    otp_expiry = datetime.datetime.now() + timedelta(minutes=10)
    
    db.users.update_one(
        {'email': email},
        {'$set': {'otp_code': otp, 'otp_expiry': otp_expiry}}
    )
    
    if not send_otp_email(email, otp, subject="Password Reset OTP"):
        return jsonify({'error': 'The password reset email could not be sent. Please try again later.'}), 503
    
    return jsonify({'message': 'OTP sent to your email.'}), 200

@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    new_password = data.get('new_password')
    
    if not (email and otp and new_password):
        return jsonify({'error': 'Email, OTP, and new password required'}), 400
        
    db = get_db()
    user = db.users.find_one({'email': email})
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
        
    stored_otp = str(user.get('otp_code', '')).strip()
    received_otp = str(otp).strip()
    
    if stored_otp == received_otp:
        if user.get('otp_expiry') and user['otp_expiry'] > datetime.datetime.now():
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
            
            db.users.update_one(
                {'email': email},
                {'$set': {
                    'password_hash': hashed_password.decode('utf-8'),
                    'otp_code': None, 
                    'otp_expiry': None,
                    'is_verified': True # Verify if not already
                }}
            )
            return jsonify({'message': 'Password reset successful. Please login.'}), 200
        else:
            return jsonify({'error': 'OTP expired'}), 400
    else:
        return jsonify({'error': 'Invalid OTP'}), 400


def normalize_uploaded_transactions(df, user_id, user_profile=None, column_map=None, return_invalid=False):
    aliases = {
        'id': 'transaction_id',
        'transactionid': 'transaction_id',
        'txn_id': 'transaction_id',
        'txn': 'transaction_id',
        'reference': 'transaction_id',
        'reference_id': 'transaction_id',
        'amount': 'transaction_amount',
        'transactionamount': 'transaction_amount',
        'value': 'transaction_amount',
        'gross_amount': 'transaction_amount',
        'transaction_date': 'timestamp',
        'date': 'timestamp',
        'datetime': 'timestamp',
        'created_at': 'timestamp',
        'time': 'timestamp',
        'payment_method': 'channel',
        'payment_channel': 'channel',
        'mode': 'channel',
        'type': 'direction',
        'transaction_type': 'direction',
        'debit_credit': 'direction',
        'dr_cr': 'direction',
        'transaction_direction': 'direction',
        'merchant_name': 'description',
        'transaction_description': 'description',
        'memo': 'description',
        'expense_category': 'category',
        'customer': 'customer_id',
        'customerid': 'customer_id',
        'account_id': 'customer_id',
        'client_id': 'customer_id',
        'kyc': 'kyc_verified',
        'kyc_status': 'kyc_verified',
        'account_age': 'account_age_days',
        'fraud': 'is_fraud',
        'fraud_flag': 'is_fraud',
        'fraudulent': 'is_fraud',
        'transaction_status': 'status'
    }
    normalized = df.copy()
    if column_map:
        mapping = {str(k): str(v) for k, v in (column_map or {}).items() if str(k) in normalized.columns}
        if mapping:
            normalized = normalized.rename(columns=mapping)
    renamed = {}
    seen = set()
    for column in normalized.columns:
        key = re.sub(r'[^a-z0-9]+', '_', str(column).strip().lower()).strip('_')
        canonical = aliases.get(key, key)
        if canonical not in seen:
            renamed[column] = canonical
            seen.add(canonical)
    normalized = normalized.rename(columns=renamed)

    if 'transaction_amount' not in normalized.columns:
        debit = next((column for column in ('debit', 'debit_amount') if column in normalized.columns), None)
        credit = next((column for column in ('credit', 'credit_amount') if column in normalized.columns), None)
        if debit or credit:
            debit_values = pd.to_numeric(normalized[debit], errors='coerce').fillna(0) if debit else 0
            credit_values = pd.to_numeric(normalized[credit], errors='coerce').fillna(0) if credit else 0
            normalized['transaction_amount'] = debit_values.where(debit_values != 0, credit_values).abs()
    if 'transaction_amount' not in normalized.columns:
        raise ValueError('Could not identify an amount column. Include amount, transaction_amount, debit, or credit.')

    amount_values = normalized['transaction_amount'].astype(str).str.replace(r'[$₹,\s]', '', regex=True)
    normalized['transaction_amount'] = pd.to_numeric(amount_values, errors='coerce')
    invalid_mask = normalized['transaction_amount'].isna()
    invalid_rows = normalized.loc[invalid_mask].copy()
    if not invalid_rows.empty:
        invalid_rows['rejection_reason'] = 'Missing or invalid transaction amount'
        invalid_rows['_source_row'] = invalid_rows.index + 2
        if column_map:
            original_names = {
                str(target): str(source)
                for source, target in column_map.items()
                if str(target) in invalid_rows.columns and str(source) not in invalid_rows.columns
            }
            invalid_rows = invalid_rows.rename(columns=original_names)
    normalized = normalized[normalized['transaction_amount'].notna()].copy()
    if normalized.empty:
        if return_invalid:
            return normalized, invalid_rows
        raise ValueError('No rows contain a valid transaction amount.')

    signed_debit = normalized['transaction_amount'] < 0
    normalized['transaction_amount'] = normalized['transaction_amount'].abs()
    direction_aliases = {
        'debit': 'debit', 'dr': 'debit', 'withdrawal': 'debit', 'outgoing': 'debit',
        'expense': 'debit', 'payment': 'debit', 'purchase': 'debit',
        'credit': 'credit', 'cr': 'credit', 'deposit': 'credit', 'incoming': 'credit',
        'income': 'credit', 'refund': 'credit', 'reversal': 'credit'
    }
    if 'direction' in normalized.columns:
        normalized['direction'] = normalized['direction'].astype(str).str.strip().str.lower().map(direction_aliases)
    else:
        normalized['direction'] = None
    if 'action' in normalized.columns:
        action_directions = normalized['action'].astype(str).str.strip().str.lower().map(direction_aliases)
        normalized['direction'] = normalized['direction'].fillna(action_directions)
    normalized.loc[normalized['direction'].isna() & signed_debit, 'direction'] = 'debit'
    normalized['direction'] = normalized['direction'].fillna('unknown')

    now = datetime.datetime.now()
    if 'transaction_id' not in normalized.columns:
        normalized['transaction_id'] = None
    missing_ids = normalized['transaction_id'].isna() | normalized['transaction_id'].astype(str).str.strip().isin({'', 'nan', 'none'})
    for index in normalized.index[missing_ids]:
        normalized.at[index, 'transaction_id'] = f"UPL_{uuid.uuid4().hex}"
    normalized['transaction_id'] = normalized['transaction_id'].astype(str).str.strip()

    if 'timestamp' in normalized.columns:
        normalized['timestamp'] = pd.to_datetime(normalized['timestamp'], errors='coerce')
        normalized['timestamp'] = normalized['timestamp'].apply(
            lambda value: value.to_pydatetime() if not pd.isna(value) else None
        )
    else:
        normalized['timestamp'] = None

    if 'channel' not in normalized.columns:
        normalized['channel'] = 'Unknown'
    normalized['channel'] = normalized['channel'].fillna('Unknown').astype(str).str.strip()
    normalized.loc[normalized['channel'].isin({'', 'nan', 'None'}), 'channel'] = 'Unknown'

    if 'description' in normalized.columns:
        normalized['description'] = normalized['description'].where(normalized['description'].notna(), None)
    if 'category' in normalized.columns:
        normalized['category'] = normalized['category'].where(normalized['category'].notna(), 'Uncategorized')
    else:
        normalized['category'] = 'Uncategorized'
    if 'currency' not in normalized.columns:
        normalized['currency'] = None

    if 'customer_id' not in normalized.columns:
        normalized['customer_id'] = str(user_id)
    else:
        normalized['customer_id'] = normalized['customer_id'].fillna(str(user_id)).astype(str)

    user_profile = user_profile or {}
    if 'kyc_verified' not in normalized.columns:
        kyc_status = str(user_profile.get('kyc_status', '')).strip().lower()
        default_kyc = int(kyc_status in {'verified', 'yes', 'true', '1', 'approved', 'complete', 'completed'})
        normalized['kyc_verified'] = default_kyc
    else:
        normalized['kyc_verified'] = normalized['kyc_verified'].apply(
            lambda value: int(str(value).strip().lower() in {'yes', 'true', '1', '1.0', 'verified', 'approved', 'complete', 'completed'})
        )

    if 'account_age_days' not in normalized.columns:
        created_at = user_profile.get('created_at')
        try:
            if created_at is None:
                raise ValueError('account creation date is unavailable')
            created_at = pd.to_datetime(created_at).to_pydatetime()
            if created_at.tzinfo:
                created_at = created_at.replace(tzinfo=None)
            account_age = max(0, (now - created_at).days)
        except (TypeError, ValueError):
            account_age = 0
        normalized['account_age_days'] = account_age
    else:
        normalized['account_age_days'] = pd.to_numeric(normalized['account_age_days'], errors='coerce').fillna(0).clip(lower=0).astype(int)

    fraud_values = {'yes': 1, 'true': 1, '1': 1, '1.0': 1, 'fraud': 1, 'fraudulent': 1, 'suspicious': 1, 'flagged': 1,
                    'no': 0, 'false': 0, '0': 0, 'safe': 0, 'legitimate': 0, 'normal': 0}
    explicit_fraud = None
    if 'is_fraud' in normalized.columns:
        labels = normalized['is_fraud'].astype(str).str.strip().str.lower().map(fraud_values)
        numeric_labels = pd.to_numeric(normalized['is_fraud'], errors='coerce')
        explicit_fraud = labels.where(labels.notna(), numeric_labels.where(numeric_labels.isin([0, 1])))

    probabilities = pd.Series(None, index=normalized.index, dtype=object)
    predictions = pd.Series(None, index=normalized.index, dtype=object)
    needs_prediction = explicit_fraud is None or explicit_fraud.isna().any()
    if needs_prediction and ml_model is not None and encoder is not None:
        try:
            channel_values = []
            for channel in normalized['channel']:
                try:
                    channel_values.append(encoder.transform([channel])[0])
                except (ValueError, TypeError):
                    channel_values.append(0)
            features = [[amount, channel, age, kyc]
                        for amount, channel, age, kyc in zip(
                            normalized['transaction_amount'], channel_values,
                            normalized['account_age_days'], normalized['kyc_verified'])]
            probabilities = pd.Series(ml_model.predict_proba(features)[:, 1], index=normalized.index)
            predictions = (probabilities >= 0.5).astype(int).astype(object)
        except Exception as error:
            logger.warning("Upload fraud analysis unavailable (%s)", type(error).__name__)

    if explicit_fraud is not None:
        predictions = explicit_fraud.fillna(predictions).astype(int)
    normalized['is_fraud'] = predictions
    normalized['fraud_probability'] = probabilities
    normalized['_source_row'] = normalized.index + 2
    if return_invalid:
        return normalized.reset_index(drop=True), invalid_rows.reset_index(drop=True)
    return normalized.reset_index(drop=True)


def persist_transaction_import(df, user_id, file_name, import_batch_id,
                               rows_detected, rejected_rows, duplicate_rows,
                               explanation='', risk_percentage=0):
    db = get_db()
    if db is None:
        raise RuntimeError('Database is unavailable')

    bulk_ops = []
    for _, row in df.iterrows():
        timestamp = None if pd.isna(row['timestamp']) else (
            row['timestamp'].to_pydatetime() if hasattr(row['timestamp'], 'to_pydatetime') else row['timestamp']
        )
        created_at = datetime.datetime.now()
        document = {
            'transaction_id': str(row['transaction_id']),
            'user_id': user_id,
            'customer_id': str(row['customer_id']) if not pd.isna(row['customer_id']) else str(user_id),
            'kyc_verified': int(row['kyc_verified']) if not pd.isna(row['kyc_verified']) else 0,
            'account_age_days': int(row['account_age_days']) if not pd.isna(row['account_age_days']) else 0,
            'transaction_amount': float(row['transaction_amount']) if not pd.isna(row['transaction_amount']) else 0.0,
            'channel': str(row['channel']) if not pd.isna(row['channel']) else None,
            'timestamp': timestamp,
            'direction': str(row['direction']),
            'category': str(row['category']) if not pd.isna(row['category']) else 'Uncategorized',
            'currency': str(row['currency']) if not pd.isna(row['currency']) else None,
            'description': str(row['description']) if 'description' in row and not pd.isna(row['description']) else None,
            'is_fraud': int(row['is_fraud']) if not pd.isna(row['is_fraud']) else None,
            'fraud_probability': float(row['fraud_probability']) if not pd.isna(row['fraud_probability']) else None,
            'action': str(row['action']) if 'action' in row and not pd.isna(row['action']) else None,
            'status': str(row['status']) if 'status' in row and not pd.isna(row['status']) else None,
            'source_file': file_name,
            'import_batch_id': import_batch_id,
            'source_row': int(row['_source_row'])
        }
        bulk_ops.append(pymongo.UpdateOne(
            {'transaction_id': document['transaction_id'], 'user_id': user_id},
            {'$set': document, '$setOnInsert': {'created_at': created_at}},
            upsert=True
        ))

    result = db.transactions.bulk_write(bulk_ops) if bulk_ops else None
    imported = result.upserted_count + result.modified_count if result else 0
    unchanged = max(0, result.matched_count - result.modified_count) if result else 0
    db.file_uploads.insert_one({
        'user_id': user_id,
        'file_name': file_name,
        'import_batch_id': import_batch_id,
        'total_records': len(bulk_ops),
        'rows_detected': rows_detected,
        'rejected_rows': rejected_rows,
        'duplicate_rows': duplicate_rows,
        'processed': 1,
        'created_at': datetime.datetime.now()
    })
    cache.delete(f"dashboard_v2:{user_id}")
    return {
        'status': 'ok',
        'imported': imported,
        'processed': len(bulk_ops),
        'rows_detected': rows_detected,
        'rejected': rejected_rows,
        'duplicates_skipped': duplicate_rows,
        'unchanged': unchanged,
        'explanation': explanation,
        'risk_percentage': risk_percentage,
        'import_batch_id': import_batch_id
    }


def rollback_import_batch(user_id, import_batch_id):
    db = get_db()
    if db is None:
        raise RuntimeError('Database is unavailable')
    result = db.transactions.delete_many({
        'user_id': user_id,
        'import_batch_id': import_batch_id,
    })
    return int(result.deleted_count)


@app.route('/upload', methods=['POST'])
@auth_required
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'file part missing'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'no selected file'}), 400

    original_filename = secure_filename(file.filename)
    if not original_filename:
        return jsonify({'error': 'The uploaded filename is invalid.'}), 400
    file.stream.seek(0, os.SEEK_END)
    upload_size = file.stream.tell()
    file.stream.seek(0)
    if upload_size > 20 * 1024 * 1024:
        return jsonify({'error': 'Files must be 20 MB or smaller.'}), 413

    # Detect file type
    file_ext = os.path.splitext(original_filename)[1].lower()
    
    # Initialize analysis fields
    explanation = ""
    risk_percentage = 0
    
    if file_ext == '.csv':
        try:
            df = pd.read_csv(file)
        except Exception as e:
            return jsonify({'error': 'failed to parse CSV', 'detail': str(e)}), 400
            
    elif file_ext in ['.xlsx', '.xls']:
        try:
            # Reset file pointer to beginning
            file.seek(0)
            # Read Excel file - try first sheet
            df = pd.read_excel(file, engine='openpyxl' if file_ext == '.xlsx' else None)
            
            # If DataFrame is empty, try reading all sheets
            if df.empty:
                file.seek(0)
                excel_file = pd.ExcelFile(file, engine='openpyxl' if file_ext == '.xlsx' else None)
                if len(excel_file.sheet_names) > 0:
                    df = pd.read_excel(file, sheet_name=excel_file.sheet_names[0], engine='openpyxl' if file_ext == '.xlsx' else None)
                    
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Failed to parse Excel file', 'detail': str(e), 'hint': 'Ensure file is a valid Excel format (.xlsx or .xls)'}), 400
            
    elif file_ext in ['.pdf', '.jpg', '.jpeg', '.png']:
        # AI Processing for images and PDFs
        try:
            # Save temporarily
            temp_dir = os.path.join(os.path.dirname(__file__), "tmp")
            os.makedirs(temp_dir, exist_ok=True)
            temp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}{file_ext}")
            file.save(temp_path)
            
            # Determine mime type
            mime = 'application/pdf' if file_ext == '.pdf' else 'image/jpeg'
            if file_ext == '.png': 
                mime = 'image/png'
            elif file_ext in ['.jpg', '.jpeg']:
                mime = 'image/jpeg'
            
            try:
                analysis_result = genai_service.analyze_document(temp_path, mime)
                
                if isinstance(analysis_result, dict):
                    csv_data = analysis_result.get('csv_data', '')
                    explanation = analysis_result.get('explanation', '')
                    risk_percentage = analysis_result.get('risk_percentage', 0)
                else:
                    csv_data = analysis_result

            except Exception as ai_error:
                try:
                    os.remove(temp_path)
                except:
                    pass
                
                error_str = str(ai_error)
                if 'GEMINI_API_KEY' in error_str or 'API key' in error_str:
                    return jsonify({
                        'error': 'AI Analysis Unavailable', 
                        'detail': 'Gemini API key is not configured. Document analysis requires AI.',
                        'hint': 'To analyze images/PDFs, please configure GEMINI_API_KEY in backend/.env file. Alternatively, upload your data in CSV or Excel format.'
                    }), 400
                else:
                    return jsonify({
                        'error': 'AI document analysis failed', 
                        'detail': error_str,
                        'hint': 'The document might not contain readable transaction data, or the AI service is unavailable.'
                    }), 400
            
            # Cleanup temp file
            try:
                os.remove(temp_path)
            except:
                pass
            
            # Check if AI returned an error string
            if isinstance(csv_data, str) and csv_data.startswith('Error:'):
                return jsonify({
                    'error': 'AI analysis failed', 
                    'detail': csv_data,
                    'hint': 'Please ensure GEMINI_API_KEY is configured in backend/.env file'
                }), 400
            
            # Parse the CSV data returned by AI
            from io import StringIO
            try:
                df = pd.read_csv(StringIO(csv_data))
                
                # Check if we got any data
                if df.empty:
                    return jsonify({
                        'error': 'No transactions extracted',
                        'detail': 'The AI could not find any transaction data in the document.',
                        'hint': 'Ensure the document contains clear transaction information (amounts, dates, payment details).'
                    }), 400
                
                # --- SMART FILL & FRAUD TAGGING ---
                user_id = request.user.get('user_id')
                db = get_db()
                
                # 1. Fetch User History for Predictions
                pipeline = [
                    { '$match': { 'user_id': user_id } },
                    { '$group': {
                        '_id': None,
                        'avg_amt': { '$avg': '$transaction_amount' },
                        'top_channel': { '$first': '$channel' } # Simplified: just taking one
                    }}
                ]
                stats = list(db.transactions.aggregate(pipeline))
                predicted_amount = stats[0]['avg_amt'] if stats else 1000.0
                predicted_channel = stats[0]['top_channel'] if stats else 'UPI'
                
                # 2. Apply Fraud Tagging (if High Risk)
                if risk_percentage > 70:
                    df['is_fraud'] = 1
                
                # 3. Fill Missing Data & Apply User Overrides
                # Ensure columns exist
                if 'transaction_amount' not in df.columns: df['transaction_amount'] = 0.0
                if 'channel' not in df.columns: df['channel'] = 'Unknown'
                if 'transaction_id' not in df.columns: df['transaction_id'] = 'TXN_UNKNOWN' # Temp, will be prefixed
                
                # Prefix Transaction ID with IMG_
                # Remove 'TXN_' if exists, then prepend 'IMG_'
                df['transaction_id'] = df['transaction_id'].astype(str).str.replace('TXN_', '', regex=False)
                df['transaction_id'] = 'IMG_' + df['transaction_id']

                # Fill NaNs/Zeros
                df['transaction_amount'] = df['transaction_amount'].fillna(0)
                if 'channel' not in df.columns: df['channel'] = 'Unknown'
                
                # Fill NaNs/Zeros
                df['transaction_amount'] = df['transaction_amount'].fillna(0)
                df.loc[df['transaction_amount'] <= 0, 'transaction_amount'] = predicted_amount
                
                df['channel'] = df['channel'].fillna('Unknown')
                df.loc[df['channel'] == 'Unknown', 'channel'] = predicted_channel
                df.loc[df['channel'].str.lower() == 'nan', 'channel'] = predicted_channel
                
                # ----------------------------------

            except Exception as parse_error:
                # If CSV parsing fails, the AI might have returned invalid format
                return jsonify({
                    'error': 'Failed to parse AI-extracted data', 
                    'detail': f'AI returned data in unexpected format: {str(parse_error)}',
                    'hint': 'The document might not contain structured transaction data. Try uploading a clearer image or use CSV/Excel format.'
                }), 400
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'AI document analysis failed', 'detail': str(e)}), 400
    else:
        return jsonify({'error': 'Unsupported file type'}), 400

    # Check if DataFrame is empty
    if df.empty:
        return jsonify({
            'error': 'No data found in file', 
            'detail': 'The uploaded file appears to be empty or contains no readable transaction data.',
            'hint': 'For images/PDFs, ensure the document contains visible transaction information. For Excel/CSV, ensure data rows exist.'
        }), 400
    
    rows_detected = len(df)
    user_id = request.user.get('user_id')
    db = get_db()
    if db is None:
        return jsonify({'error': 'Database Connection Failed', 'detail': 'Could not update transactions because the database is unavailable.'}), 503
    user_profile = db.users.find_one({'user_id': user_id}, {'created_at': 1, 'kyc_status': 1}) or {}
    try:
        df, invalid_rows = normalize_uploaded_transactions(df, user_id, user_profile, return_invalid=True)
    except ValueError as error:
        return jsonify({
            'error': 'Unable to identify transaction data',
            'detail': str(error),
            'hint': 'Include a transaction amount column such as amount, transaction_amount, debit, or credit.'
        }), 400
    rejected_rows = len(invalid_rows)
    duplicate_rows = int(df.duplicated(subset=['transaction_id'], keep='last').sum())
    if duplicate_rows:
        df = df.drop_duplicates(subset=['transaction_id'], keep='last').copy()
    
    expected_cols = {'transaction_id', 'customer_id', 'kyc_verified', 'account_age_days',
                     'transaction_amount', 'channel', 'timestamp', 'is_fraud'}
    
    # Check for required columns (case-insensitive)
    actual_cols = set(df.columns)
    missing_cols = expected_cols - actual_cols
    
    if missing_cols:
        error_msg = f'Missing required columns: {", ".join(sorted(missing_cols))}'
        error_msg += f'\n\nFound columns: {", ".join(sorted(actual_cols))}'
        
        if file_ext in ['.pdf', '.jpg', '.jpeg', '.png']:
            error_msg += '\n\nHint: For images/PDFs, ensure GEMINI_API_KEY is configured and the document clearly shows transaction details.'
        elif file_ext in ['.xlsx', '.xls']:
            error_msg += '\n\nHint: Excel file must contain columns matching the expected format. Check that column names match exactly (case-insensitive).'
        else:
            error_msg += '\n\nHint: CSV file must contain the exact column headers as specified.'
        
        return jsonify({
            'error': 'Invalid file format', 
            'detail': error_msg,
            'required_columns': sorted(expected_cols),
            'found_columns': sorted(actual_cols)
        }), 400

    import_batch_id = uuid.uuid4().hex
    preview_id = uuid.uuid4().hex
    preview_key = f"upload_preview:{user_id}:{preview_id}"
    cache.set(preview_key, {
        'rows': df.to_json(orient='records', date_format='iso'),
        'file_name': original_filename,
        'import_batch_id': import_batch_id,
        'rows_detected': rows_detected,
        'rejected_rows': rejected_rows,
        'duplicate_rows': duplicate_rows,
        'explanation': explanation,
        'risk_percentage': risk_percentage
    }, timeout=900)

    preview_columns = [
        'transaction_id', 'timestamp', 'description', 'direction', 'transaction_amount',
        'currency', 'channel', 'category', 'status', 'is_fraud', 'fraud_probability'
    ]
    preview_rows = json.loads(df[[column for column in preview_columns if column in df.columns]]
                              .head(20).to_json(orient='records', date_format='iso'))
    duplicate_review = []
    duplicate_groups = df[df.duplicated(subset=['transaction_id'], keep=False)].groupby('transaction_id', dropna=False)
    for transaction_id, group in duplicate_groups:
        duplicate_review.append({
            'transaction_id': str(transaction_id),
            'rows': [int(row + 2) for row in group.index.tolist()]
        })
    available_columns = list(df.columns)
    invalid_rows_payload = invalid_rows.to_csv(index=False) if not invalid_rows.empty else ''
    cache.set(preview_key, {
        'rows': df.to_json(orient='records', date_format='iso'),
        'raw_columns': list(df.columns),
        'file_name': original_filename,
        'import_batch_id': import_batch_id,
        'rows_detected': rows_detected,
        'rejected_rows': rejected_rows,
        'duplicate_rows': duplicate_rows,
        'duplicate_review': duplicate_review,
        'invalid_rows_csv': invalid_rows_payload,
        'explanation': explanation,
        'risk_percentage': risk_percentage,
        'available_columns': available_columns,
    }, timeout=900)
    return jsonify({
        'status': 'preview',
        'preview_id': preview_id,
        'file_name': original_filename,
        'rows_detected': rows_detected,
        'valid_rows': len(df),
        'rejected': rejected_rows,
        'duplicates_skipped': duplicate_rows,
        'duplicate_review': duplicate_review,
        'preview': preview_rows,
        'preview_limit': 20,
        'available_columns': available_columns,
        'invalid_rows_url': f'/upload/invalid-csv?preview_id={preview_id}',
        'explanation': explanation,
        'risk_percentage': risk_percentage
    }), 200


@app.route('/upload/map', methods=['POST'])
@auth_required
def map_transaction_upload_columns():
    payload = request.get_json(silent=True) or {}
    preview_id = str(payload.get('preview_id', '')).strip()
    if not re.fullmatch(r'[0-9a-f]{32}', preview_id):
        return jsonify({'error': 'Upload preview expired. Please upload the file again.'}), 400
    user_id = request.user.get('user_id')
    preview_key = f"upload_preview:{user_id}:{preview_id}"
    staged = cache.get(preview_key)
    if not staged:
        return jsonify({'error': 'Upload preview expired or unavailable. Please upload the file again.'}), 410
    db = get_db()
    profile = db.users.find_one({'user_id': user_id}, {'created_at': 1, 'kyc_status': 1}) or {} if db else {}
    raw_df = pd.read_json(io.StringIO(staged['rows']), orient='records', convert_dates=['timestamp']) if staged.get('rows') else pd.DataFrame()
    if raw_df.empty:
        return jsonify({'error': 'No staged rows available to remap.'}), 400
    column_map = payload.get('column_map') or {}
    try:
        normalized, invalid_rows = normalize_uploaded_transactions(
            raw_df, user_id, profile, column_map, return_invalid=True
        )
    except ValueError as error:
        return jsonify({'error': 'Unable to map the selected columns', 'detail': str(error)}), 400
    staged['rows'] = normalized.to_json(orient='records', date_format='iso')
    staged['rejected_rows'] = len(invalid_rows)
    staged['invalid_rows_csv'] = invalid_rows.to_csv(index=False) if not invalid_rows.empty else ''
    staged['available_columns'] = list(normalized.columns)
    cache.set(preview_key, staged, timeout=900)
    preview_columns = ['transaction_id', 'timestamp', 'description', 'direction', 'transaction_amount', 'currency', 'channel', 'category', 'status', 'is_fraud', 'fraud_probability']
    preview_payload = normalized[[column for column in preview_columns if column in normalized.columns]].head(20)
    return jsonify({
        'status': 'mapped',
        'preview_id': preview_id,
        'preview': json.loads(preview_payload.to_json(orient='records', date_format='iso')),
        'available_columns': list(normalized.columns),
        'invalid_rows_url': f'/upload/invalid-csv?preview_id={preview_id}'
    })


@app.route('/upload/invalid-csv', methods=['GET'])
@auth_required
def download_invalid_rows_csv():
    preview_id = request.args.get('preview_id', '')
    if not re.fullmatch(r'[0-9a-f]{32}', preview_id):
        return jsonify({'error': 'Upload preview expired. Please upload the file again.'}), 400
    user_id = request.user.get('user_id')
    preview_key = f"upload_preview:{user_id}:{preview_id}"
    staged = cache.get(preview_key)
    if not staged:
        return jsonify({'error': 'Upload preview expired or unavailable. Please upload the file again.'}), 410
    csv_payload = staged.get('invalid_rows_csv', '')
    if not csv_payload:
        return jsonify({'error': 'There are no invalid rows to download.'}), 404
    return Response(csv_payload, mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={safe_name(user_id)}_invalid_rows.csv'})


@app.route('/upload/confirm', methods=['POST'])
@auth_required
def confirm_transaction_upload():
    data = request.get_json(silent=True) or {}
    preview_id = str(data.get('preview_id', '')).strip()
    if not re.fullmatch(r'[0-9a-f]{32}', preview_id):
        return jsonify({'error': 'Upload preview expired. Please upload the file again.'}), 400
    user_id = request.user.get('user_id')
    preview_key = f"upload_preview:{user_id}:{preview_id}"
    staged = cache.get(preview_key)
    if not staged:
        return jsonify({'error': 'Upload preview expired or unavailable. Please upload the file again.'}), 410

    try:
        df = pd.read_json(io.StringIO(staged['rows']), orient='records', convert_dates=['timestamp'])
        result = persist_transaction_import(
            df,
            user_id,
            staged['file_name'],
            staged['import_batch_id'],
            staged['rows_detected'],
            staged['rejected_rows'],
            staged['duplicate_rows'],
            staged['explanation'],
            staged['risk_percentage'],
        )
    except Exception as error:
        rollback_batch_id = staged.get('import_batch_id')
        if rollback_batch_id:
            try:
                rollback_import_batch(user_id, rollback_batch_id)
            except Exception:
                pass
        logger.error("Transaction import commit failed (%s)", type(error).__name__)
        return jsonify({'error': 'Transactions could not be saved. Your preview is still available to retry.'}), 503

    cache.delete(preview_key)
    return jsonify(result), 201


@app.route('/upload/rollback', methods=['POST'])
@auth_required
def rollback_transaction_upload():
    data = request.get_json(silent=True) or {}
    import_batch_id = str(data.get('import_batch_id', '')).strip()
    if not import_batch_id:
        return jsonify({'error': 'No import batch was supplied.'}), 400
    user_id = request.user.get('user_id')
    try:
        deleted_count = rollback_import_batch(user_id, import_batch_id)
    except Exception as error:
        logger.error("Batch rollback failed (%s)", type(error).__name__)
        return jsonify({'error': 'Rollback could not complete.'}), 500
    return jsonify({'status': 'rolled_back', 'deleted_count': deleted_count, 'import_batch_id': import_batch_id})


@app.route('/api/analyze', methods=['POST'])
@auth_required
def analyze_transaction():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        result = genai_service.analyze_transaction(data)
        return jsonify({'analysis': result})
    except Exception as e:
        return jsonify({'error': 'Analysis failed', 'detail': str(e)}), 500


@app.route('/api/alerts', methods=['GET'])
@auth_required
def get_alerts():
    try:
        user_id = request.user.get('user_id')
        db = get_db()
        
        alerts_cursor = db.transactions.find(
            {'user_id': user_id, 'is_fraud': 1}
        ).sort('timestamp', -1).limit(50)
        
        alerts = []
        for a in alerts_cursor:
            a['_id'] = str(a['_id']) # Mongo ObjectId to string
            alerts.append(a)
            
        return jsonify(alerts)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch alerts', 'detail': str(e)}), 500

@app.route('/api/transactions', methods=['GET'])
@auth_required
def get_transactions():
    try:
        user_id = request.user['user_id']
        limit = request.args.get('limit', 100, type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # CACHE CHECK
        cache_key = f"txns:{user_id}:{limit}:{start_date}:{end_date}"
        cached_res = cache.get(cache_key)
        if cached_res:
             return jsonify(cached_res)
        
        query = {'user_id': request.user['user_id']}
        
        if start_date or end_date:
            query['timestamp'] = {}
            if start_date:
                query['timestamp']['$gte'] = pd.to_datetime(start_date)
            if end_date:
                query['timestamp']['$lte'] = pd.to_datetime(end_date)
        
        db = get_db()
        txns_cursor = db.transactions.find(query).sort('timestamp', -1).limit(limit)
        
        txns = []
        for t in txns_cursor:
            t['_id'] = str(t['_id'])
            txns.append(t)
            
        # CACHE SET is tricky here because list might be filtered.
        # But we can cache the result list
        cache.set(cache_key, txns, timeout=30)
        return jsonify(txns)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch transactions', 'detail': str(e)}), 500

@app.route('/api/transactions/<string:txn_id>', methods=['DELETE'])
@auth_required
def delete_transaction(txn_id):
    try:
        db = get_db()
        owner_query = {'transaction_id': str(txn_id), 'user_id': request.user['user_id']}
        txn = db.transactions.find_one(owner_query)
        if not txn:
            return jsonify({'error': 'Transaction not found'}), 404

        db.transactions.delete_one(owner_query)
        return jsonify({'status': 'deleted'})
    except Exception as e:
        return jsonify({'error': 'Deletion failed', 'detail': str(e)}), 500

@app.route('/api/dashboard', methods=['GET'])
@auth_required
def get_dashboard_data():
    try:
        user_id = request.user['user_id']
        
        # 0. CACHE CHECK
        cache_key = f"dashboard_v2:{user_id}"
        cached_res = cache.get(cache_key)
        if cached_res:
            return jsonify(cached_res)
            
        db = get_db()
        
        # 1. User Stats
        user = db.users.find_one({'user_id': user_id}, {'password_hash': 0, '_id': 0})
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # 2. Counts
        total_txns = db.transactions.count_documents({'user_id': user_id})
        
        suspicious_activity = db.transactions.count_documents({'user_id': user_id, 'is_fraud': 1})
        pending_verifications = 1 if user.get('kyc_status', 'Pending') != 'Verified' else 0
        
        counts = {
            'total_transactions': total_txns,
            'suspicious_activity': suspicious_activity,
            'pending_verifications': pending_verifications
        }

        # 3. Chart Data (Last 365 days)
        thirty_days_ago = datetime.datetime.now() - timedelta(days=365)
        pipeline = [
            {
                '$match': {
                    'user_id': user_id,
                    'timestamp': {'$gte': thirty_days_ago}
                }
            },
            {
                '$group': {
                    '_id': { '$dateToString': { 'format': "%Y-%m-%d", 'date': "$timestamp" } },
                    'value': { '$sum': '$transaction_amount' }
                }
            },
            { '$sort': { '_id': 1 } }
        ]
        chart_data_raw = list(db.transactions.aggregate(pipeline))
        chart_data = [{'date': item['_id'], 'value': item['value']} for item in chart_data_raw]
        
        # Cash flow is only classified when the imported record has a known direction.
        flow_pipeline = [
            {'$match': {
                'user_id': user_id,
                'direction': {'$in': ['debit', 'credit']},
                'timestamp': {'$gte': thirty_days_ago}
            }},
            {'$group': {
                '_id': {
                    'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$timestamp'}},
                    'direction': '$direction'
                },
                'total': {'$sum': '$transaction_amount'}
            }},
            {'$sort': {'_id.date': 1}}
        ]
        flow_by_date = {}
        for item in db.transactions.aggregate(flow_pipeline):
            date_key = item['_id']['date']
            flow_by_date.setdefault(date_key, {'date': date_key, 'income': 0.0, 'expense': 0.0})
            flow_by_date[date_key]['income' if item['_id']['direction'] == 'credit' else 'expense'] = item['total']
        income_expense_data = list(flow_by_date.values())

        # Spending categories use transaction categories, not payment channels.
        pipeline_cat = [
            {'$match': {'user_id': user_id, 'direction': 'debit'}},
            {'$group': {
                '_id': {'$ifNull': ['$category', 'Uncategorized']},
                'total': {'$sum': '$transaction_amount'}
            }}
        ]
        cat_data_raw = list(db.transactions.aggregate(pipeline_cat))
        category_data = [{'category': item['_id'] or 'Other', 'amount': item['total']} for item in cat_data_raw]

        # C. Fraud Alerts Trend (Bar)
        pipeline_fraud = [
            {
                '$match': {
                    'user_id': user_id,
                    'is_fraud': 1,
                    'timestamp': {'$gte': thirty_days_ago}
                }
            },
            {
                '$group': {
                    '_id': { '$dateToString': { 'format': "%Y-%m-%d", 'date': "$timestamp" } },
                    'count': { '$sum': 1 }
                }
            },
            { '$sort': { '_id': 1 } }
        ]
        fraud_trend_raw = list(db.transactions.aggregate(pipeline_fraud))
        fraud_trend_data = [{'date': item['_id'], 'count': item['count']} for item in fraud_trend_raw]

        prediction_data = []

        # 4. Recent Alerts
        alerts_cursor = db.transactions.find(
            {'user_id': user_id, 'is_fraud': 1}
        ).sort('timestamp', -1).limit(5)
        
        recent_alerts = []
        for a in alerts_cursor:
             recent_alerts.append({
                 'transaction_id': a.get('transaction_id'),
                 'timestamp': a.get('timestamp'),
                 'transaction_amount': a.get('transaction_amount'),
                 'channel': a.get('channel')
             })

        # 5. DYNAMIC TRUST SCORE
        # No validated forecasting model exists for account spending.
        intelligence = {
            'expense_prediction': None,
            'fraud_risk_level': 'Not assessed'
        }

        response = {
            'user_stats': {
                'balance': None,
                'kyc_status': user.get('kyc_status', 'Pending'),
                'trust_score': None,
                'security_status': None,
                'fraud_risk_level': 'Not assessed'
            },
            'counts': counts,
            'chart_data': chart_data,
            'income_expense_data': income_expense_data,
            'category_data': category_data,
            'fraud_trend_data': fraud_trend_data,
            'prediction_data': prediction_data,
            'recent_alerts': recent_alerts,
            'intelligence': intelligence
        }
        
        cache.set(cache_key, response, timeout=60)
        return jsonify(response)

    except Exception as e:
        logger.error(f"Dashboard Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to load dashboard data'}), 500

@app.route('/api/transfer', methods=['POST'])
@auth_required
def transfer_funds():
    try:
        data = request.get_json()
        recipient_id = data.get('recipient_id')
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
             return jsonify({'error': 'Invalid amount'}), 400

        user_id = request.user['user_id']
        db = get_db()
        
        user = db.users.find_one({'user_id': user_id})
        if not user:
             return jsonify({'error': 'User not found'}), 404
             
        current_balance = float(user.get('balance', 0))
        if current_balance < amount:
             return jsonify({'error': 'Insufficient funds'}), 400
        
        # Deduct
        db.users.update_one({'user_id': user_id}, {'$inc': {'balance': -amount}})
        
        # Record Transaction
        import random
        txn_id = str(int(time.time() * 1000) + random.randint(1, 1000))
        
        db.transactions.insert_one({
            'transaction_id': txn_id,
            'user_id': user_id,
            'transaction_amount': amount,
            'channel': 'TRANSFER',
            'timestamp': datetime.datetime.now(),
            'is_fraud': 0,
            'created_at': datetime.datetime.now()
        })
        
        return jsonify({
            'status': 'success', 
            'message': 'Transfer successful', 
            'new_balance': current_balance - amount
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Transfer failed', 'detail': str(e)}), 500

@app.route('/api/loan/apply', methods=['POST'])
@auth_required
def apply_loan():
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        purpose = data.get('purpose', 'Personal')
        
        user_id = request.user['user_id']
        db = get_db()
        
        db.loans.insert_one({
            'user_id': user_id,
            'amount': amount,
            'purpose': purpose,
            'status': 'Pending',
            'created_at': datetime.datetime.now()
        })
        return jsonify({'status': 'success', 'message': 'Loan application submitted'})
    except Exception as e:
        return jsonify({'error': 'Loan application failed', 'detail': str(e)}), 500

@app.route('/api/insurance/apply', methods=['POST'])
@auth_required
def apply_insurance():
    try:
        data = request.get_json()
        policy_type = data.get('type')
        coverage = float(data.get('coverage', 0))
        premium = coverage * 0.01 
        
        user_id = request.user['user_id']
        db = get_db()
        
        db.insurance_policies.insert_one({
            'user_id': user_id,
            'type': policy_type,
            'coverage_amount': coverage,
            'premium': premium,
            'status': 'Pending',
            'created_at': datetime.datetime.now()
        })
        return jsonify({'status': 'success', 'message': 'Insurance quote requested'})
    except Exception as e:
         return jsonify({'error': 'Insurance request failed', 'detail': str(e)}), 500


@app.route('/api/metrics', methods=['GET'])
@auth_required
def get_metrics():
    """Returns the ML model performance metrics"""
    try:
        metrics_path = os.path.join(os.path.dirname(__file__), 'assets', 'models', 'metrics.json')
        
        if not os.path.exists(metrics_path):
            return jsonify({
                'error': 'Metrics not found',
                'message': 'Model has not been trained yet. Please train the model first.'
            }), 404
        
        import json
        with open(metrics_path, 'r') as f:
            metrics = json.load(f)
        
        return jsonify(metrics)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to load metrics', 'detail': str(e)}), 500

@app.route('/api/model-tips', methods=['GET'])
@auth_required
def get_model_tips():
    """Returns AI-generated tips for improving the model"""
    try:
        metrics_path = os.path.join(os.path.dirname(__file__), 'assets', 'models', 'metrics.json')
        
        if not os.path.exists(metrics_path):
            return jsonify({
                'tips': 'Please train the model first to get improvement tips.'
            })
        
        import json
        with open(metrics_path, 'r') as f:
            metrics = json.load(f)
        
        tips = genai_service.get_model_improvement_tips(str(metrics))
        
        return jsonify({'tips': tips})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to generate tips', 'detail': str(e)}), 500

@app.route('/api/profile', methods=['GET'])
@auth_required
def get_profile():
    try:
        user_id = request.user.get('user_id')
        db = get_db()
        user = db.users.find_one({'user_id': user_id})
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'id': user['user_id'],
            'name': user.get('name', ''),
            'email': user.get('email', ''),
            'balance': float(user.get('balance', 0)),
            'kyc_status': user.get('kyc_status', 'Pending'),
            'trust_score': int(user.get('trust_score', 0)),
            'security_status': user.get('security_status', 'Moderate'),
            'fraud_risk_level': user.get('fraud_risk_level', 'Low'),
            'profile_image': user.get('profile_image', '')
        })
    except Exception as e:
        return jsonify({'error': 'Failed to load profile', 'detail': str(e)}), 500

@app.route('/api/profile', methods=['PUT'])
@auth_required
def update_profile():
    try:
        user_id = request.user.get('user_id')
        data = request.get_json()
        db = get_db()
        
        update_data = {}
        if 'name' in data:
            update_data['name'] = data['name']
        if 'email' in data:
            existing = db.users.find_one({'email': data['email'], 'user_id': {'$ne': user_id}})
            if existing:
                return jsonify({'error': 'Email already in use'}), 409
            update_data['email'] = data['email']
        
        if not update_data:
            return jsonify({'error': 'No fields to update'}), 400
        
        result = db.users.update_one(
            {'user_id': user_id},
            {'$set': update_data}
        )
        
        if result.modified_count == 0:
            return jsonify({'error': 'No changes made'}), 400
        
        user = db.users.find_one({'user_id': user_id})
        return jsonify({
            'id': user['user_id'],
            'name': user.get('name', ''),
            'email': user.get('email', ''),
            'profile_image': user.get('profile_image', '')
        })
    except Exception as e:
        return jsonify({'error': 'Failed to update profile', 'detail': str(e)}), 500

@app.route('/api/profile/image', methods=['POST'])
@auth_required
def upload_profile_image():
    try:
        user_id = request.user.get('user_id')
        
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = os.path.splitext(file.filename)[1].lower().lstrip('.')
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP'}), 400
        
        # New: Store as File
        filename = f"{user_id}_{int(time.time())}.{file_ext}"
        upload_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'profiles')
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        # Relative URL for frontend access
        profile_image_url = f"/uploads/profiles/{filename}"
        
        db = get_db()
        db.users.update_one(
            {'user_id': user_id},
            {'$set': {'profile_image': profile_image_url}}
        )
        
        return jsonify({
            'profile_image': profile_image_url,
            'message': 'Profile image uploaded successfully (stored as file)'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Failed to upload image', 'detail': str(e)}), 500

@app.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    upload_folder = os.path.join(os.path.dirname(__file__), 'uploads')
    return send_from_directory(upload_folder, filename)

@app.route('/api/predict', methods=['POST'])
@auth_required
def predict_fraud():
    try:
        global ml_model, encoder
        
        if not ml_model or not encoder:
            return jsonify({
                'status': 'not_ready',
                'error': 'Model not loaded. Please train the model first.'
            }), 400
        
        data = request.get_json()
        amount = float(data.get('amount', 0))
        channel = data.get('channel', 'UPI')
        account_age = int(data.get('account_age', 0))
        
        kyc_val = data.get('kyc_verified', 'Yes')
        if isinstance(kyc_val, str):
            kyc_verified = 1 if kyc_val.lower() in ['yes', '1', 'true'] else 0
        else:
            kyc_verified = 1 if int(kyc_val) == 1 else 0
        
        try:
            channel_encoded = encoder.transform([channel])[0]
        except:
            channel_encoded = 0
        
        features = [[amount, channel_encoded, account_age, kyc_verified]]
        
        probability = ml_model.predict_proba(features)[0][1]
        
        return jsonify({
            'probability': float(probability),
            'prediction': 'fraud' if probability > 0.5 else 'safe'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Prediction failed', 'detail': str(e)}), 500

@app.route('/api/retrain', methods=['POST'])
@auth_required
def retrain_model():
    logger.info(f"Retrain requested by user: {request.user.get('email')}")
    try:
        result = train_model()
        
        if result.get('status') == 'error':
            logger.error(f"Retrain result error: {result.get('message')}")
            return jsonify({'error': result.get('message', 'Training failed')}), 500
        
        load_ml_model()
        
        logger.info(f"Retrain successful. Metrics: {result.get('metrics', {})}")
        return jsonify({
            'status': 'success',
            'message': 'Model training completed',
            'metrics': result.get('metrics', {})
        })
    except Exception as e:
        logger.error(f"Retrain API exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Training failed', 'detail': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
@auth_required
def chat_advisor():
    try:
        data = request.get_json()
        user_query = data.get('query')
        user_id = request.user['user_id']
        
        db = get_db()
        
        user = db.users.find_one({'user_id': user_id})
        balance = user.get('balance', 0)
        risk = user.get('fraud_risk_level', 'Low')
        
        txns = list(db.transactions.find({'user_id': user_id}).sort('timestamp', -1).limit(5))
        txn_summary = ""
        for t in txns:
            txn_summary += f"- {t.get('timestamp')}: {t.get('transaction_amount')} ({t.get('channel')})\n"
            
        context = {
            'balance': balance,
            'risk_level': risk,
            'recent_transactions': txn_summary if txn_summary else "No recent transactions."
        }
        
        response_text = genai_service.chat_with_advisor(user_query, context)
        return jsonify({'response': response_text})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Chat failed', 'detail': str(e)}), 500

# ==========================================
# CLI FUNCTIONS
# ==========================================

def seed_database():
    """Initializes the database with indexes and dummy data."""
    print("--- Seeding Database ---")
    try:
        db = get_db()
        print(f"Connected to MongoDB: {DB_NAME}")
        
        print("Creating indexes...")
        db.users.create_index("email", unique=True)
        db.transactions.create_index("user_id")
        db.transactions.create_index("transaction_id", unique=True)
        db.fraud_alerts.create_index("user_id")
        
        print("Indexes created.")
        
        # Seed User
        email = "sai@gmail.com"
        print(f"Seeding data for {email}...")
        
        user = db.users.find_one({'email': email})
        user_id = None
        
        if not user:
            print("User not found! Creating new user...")
            user_id = str(uuid.uuid4())
            pw_hash = bcrypt.hashpw("password".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user = {
                'user_id': user_id,
                'name': 'Sai User',
                'email': email,
                'password_hash': pw_hash,
                'balance': 75000.50,
                'kyc_status': 'Pending',
                'trust_score': 65,
                'security_status': 'Strong',
                'fraud_risk_level': 'Low',
                'created_at': datetime.datetime.now(),
                'is_verified': True 
            }
            db.users.insert_one(user)
        else:
            print("Updating existing user...")
            user_id = user['user_id']
            db.users.update_one({'email': email}, {'$set': {
                'balance': 150000.00,
                'security_status': 'Strong',
                'trust_score': 85,
                'is_verified': True
            }})
            
        # Seed Transactions
        print("Creating dummy transactions...")
        channels = ['Mobile App', 'Web', 'ATM', 'POS']
        types = ['Transfer', 'Payment', 'Withdrawal']
        
        # Clear old txns for this user
        db.transactions.delete_many({'user_id': user_id})
        
        transactions = []
        base_time = datetime.datetime.now()
        for i in range(20):
            txn_id = f"txn_{random.randint(10000,99999)}"
            days_ago = random.randint(0, 10)
            amount = random.uniform(500, 25000)
            is_fraud = 1 if i % 10 == 0 else 0 
            
            doc = {
                'transaction_id': txn_id,
                'user_id': user_id,
                'transaction_amount': round(amount, 2),
                'channel': random.choice(channels),
                'transaction_type': random.choice(types),
                'is_fraud': is_fraud,
                'kyc_verified': random.choice([0, 1]),
                'account_age_days': random.randint(10, 1000),
                'timestamp': base_time - timedelta(days=days_ago),
                'created_at': datetime.datetime.now()
            }
            transactions.append(doc)
            
        if transactions:
            db.transactions.insert_many(transactions)
            
        print("Seeding complete. User 'sai@gmail.com' (password) ready.")
        
    except Exception as e:
        print(f"Seeding failed: {e}")

def test_ai_connection():
    """Tests the connection to Gemini AI."""
    print("--- Testing AI Connection ---")
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found in environment.")
        return
    
    print("Gemini API key is configured.")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('models/gemini-flash-latest')
        response = model.generate_content("Hello, system check.")
        print(f"AI Response: {response.text}")
        print("SUCCESS: AI connection verified.")
    except Exception as e:
        print(f"AI Connection FAILED: {e}")

def verify_chat_function():
    """Verifies the chat endpoint using Flask's test client."""
    print("--- Verifying Chat Endpoint ---")
    
    # 1. Create a test user
    email = "verifier@test.com"
    password = "password123"
    
    with app.test_client() as client:
        # Register
        print("Registering test user...")
        client.post('/register', json={
            'name': 'Verifier', 'email': email, 'password': password
        })
        
        # Login
        print("Logging in...")
        resp = client.post('/login', json={'email': email, 'password': password})
        if resp.status_code != 200:
            print(f"Login failed: {resp.data}")
            return
            
        token = resp.get_json()['token']
        headers = {'Authorization': f"Bearer {token}"}
        
        # Chat
        print("Sending chat query...")
        chat_resp = client.post('/api/chat', json={'query': 'Hello'}, headers=headers)
        print(f"Chat Response Code: {chat_resp.status_code}")
        print(f"Chat Response Is: {chat_resp.get_json()}")

def setup_demo_data():
    """Sets up demo data: user, csv upload, training."""
    print("--- Setting up Demo Data ---")
    user_data = {'name': 'ML Admin', 'email': 'admin@ml.com', 'password': 'admin'}
    csv_filename = 'fraud_detection_dataset_LLM .csv'
    # Look for csv in parent dir
    csv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), csv_filename)
    
    if not os.path.exists(csv_path):
        print(f"CSV file not found at: {csv_path}")
        return

    with app.test_client() as client:
        # Register
        print("Registering...")
        client.post('/register', json=user_data)
        
        # Login
        print("Logging in...")
        resp = client.post('/login', json={'email': user_data['email'], 'password': user_data['password']})
        if resp.status_code != 200:
            print(f"Login failed: {resp.data}")
            return
        
        token = resp.get_json()['token']
        headers = {'Authorization': f"Bearer {token}"}
        
        # Upload
        print("Uploading CSV...")
        with open(csv_path, 'rb') as f:
            data = {'file': (f, csv_filename)}
            upload_resp = client.post('/upload', 
                                    data=data, 
                                    headers=headers,
                                    content_type='multipart/form-data')
            print(f"Upload Result: {upload_resp.status_code} - {upload_resp.get_json()}")
            
        # Train
        print("Triggering Training...")
        train_resp = client.post('/api/retrain', headers=headers)
        print(f"Training Result: {train_resp.status_code} - {train_resp.get_json()}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="BFSI Backend Application")
    parser.add_argument('--server', action='store_true', help='Run the Flask server (default)')
    parser.add_argument('--seed', action='store_true', help='Seed the database indexes')
    parser.add_argument('--test-ai', action='store_true', help='Test connection to Gemini AI')
    parser.add_argument('--verify', action='store_true', help='Run verification suite')
    parser.add_argument('--setup', action='store_true', help='Setup demo data (Register/Upload/Train)')
    
@app.route('/api/analyze', methods=['POST'])
@auth_required
def analyze_transaction_api():
    """
    Analyzes a specific transaction using GenAI to provide risk assessment and safety tips.
    Expects JSON payload with: amount, channel, account_age, kyc_verified, timestamp
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Prepare transaction dictionary for service
        txn_data = {
            'amount': data.get('amount'),
            'channel': data.get('channel'),
            'account_age': data.get('account_age', 'Unknown'),
            'kyc_verified': data.get('kyc_verified', 'Unknown'),
            'timestamp': data.get('timestamp')
        }
        
        # Re-use existing GenAIService logic if possible or call it directly
        
        # CACHE CHECK (AI is expensive)
        import hashlib
        # Create a stable hash of the input data
        data_str = json.dumps(txn_data, sort_keys=True)
        data_hash = hashlib.md5(data_str.encode()).hexdigest()
        cache_key = f"ai_analysis:{data_hash}"
        
        cached_analysis = cache.get(cache_key)
        if cached_analysis:
            return jsonify({'analysis': cached_analysis, 'cached': True})
            
        analysis = genai_service.analyze_transaction(txn_data)
        
        # CACHE SET (Long TTL - 24 hours)
        cache.set(cache_key, analysis, timeout=86400)
        
        return jsonify({'analysis': analysis})

    except Exception as e:
        logger.error(f"Analysis API Error: {e}")
        return jsonify({'error': 'Failed to analyze transaction'}), 500


# ==========================================
# INVESTMENT MODULE
# ==========================================
@app.route('/investments')
def investments_page():
    return render_template('investments.html')

@app.route('/api/investments', methods=['GET', 'POST'])
@auth_required
def handle_investments():
    db = get_db()
    if request.method == 'GET':
        investments = list(db.investments.find({'user_id': request.user['user_id']}))
        for investment in investments:
            investment['_id'] = str(investment['_id'])
        return jsonify(investments)
    
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        asset_type = str(data.get('type', '')).strip()
        name = str(data.get('name', '')).strip()
        if not asset_type or asset_type not in {'Stocks', 'Mutual Fund', 'Gold', 'Fixed Deposit', 'Crypto', 'Real Estate'}:
            return jsonify({'error': 'Choose a supported asset type.'}), 400
        if not name or len(name) > 120:
            return jsonify({'error': 'Enter an asset name of 1 to 120 characters.'}), 400
        try:
            invested_amount = float(data.get('amount'))
            current_value = float(data.get('current_value'))
        except (TypeError, ValueError):
            return jsonify({'error': 'Enter valid invested and current values.'}), 400
        if not math.isfinite(invested_amount) or not math.isfinite(current_value) or invested_amount <= 0 or current_value < 0:
            return jsonify({'error': 'Invested amount must be positive and current value cannot be negative.'}), 400

        now = datetime.datetime.now()
        investment = {
            'user_id': request.user['user_id'],
            'type': asset_type,
            'name': name,
            'amount': invested_amount,
            'current_value': current_value,
            'currency': str(data.get('currency', 'INR')).strip().upper(),
            'valuation_source': 'user-entered',
            'valuation_date': now,
            'created_at': now,
        }
        result = db.investments.insert_one(investment)
        return jsonify({'status': 'success', 'investment_id': str(result.inserted_id)}), 201

@app.route('/api/investments/delete', methods=['POST'])
@auth_required
def delete_investment():
    db = get_db()
    data = request.get_json(silent=True) or {}
    investment_id = str(data.get('investment_id', '')).strip()
    owner_id = request.user['user_id']
    if investment_id:
        if not ObjectId.is_valid(investment_id):
            return jsonify({'error': 'Investment not found.'}), 404
        result = db.investments.delete_one({'_id': ObjectId(investment_id), 'user_id': owner_id})
    else:
        name = str(data.get('name', '')).strip()
        if not name:
            return jsonify({'error': 'Investment not found.'}), 404
        result = db.investments.delete_one({'user_id': owner_id, 'name': name})
    if result.deleted_count != 1:
        return jsonify({'error': 'Investment not found.'}), 404
    return jsonify({'status': 'success'})

@app.route('/api/investments/analyze', methods=['POST'])
@auth_required
def analyze_portfolio_route():
    db = get_db()
    user_id = request.user['user_id']
    user = db.users.find_one({'user_id': user_id})
    investments = list(db.investments.find({'user_id': user_id}, {'_id': 0}))
    
    if not investments:
        return jsonify({'tips': "<p>No investments found. Add some stocks, funds, or gold to get an analysis.</p>"})

    # Simplify for AI
    portfolio_summary = [{'type': i['type'], 'name': i['name'], 'value': i['current_value']} for i in investments]
    
    risk_profile = user.get('risk_profile', 'Moderate')
    user_name = user.get('name', 'Investor')
    
    tips = genai_service.analyze_portfolio(portfolio_summary, risk_profile, user_name)
    return jsonify({'tips': tips})



# ==========================================
# LOAN MODULE
# ==========================================
@app.route('/loans')
def loans_page():
    return render_template('loans.html')

def _calculate_emi(principal, annual_rate, months):
    monthly_rate = annual_rate / 12 / 100
    if monthly_rate == 0:
        return principal / months
    rate_factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * rate_factor / (rate_factor - 1)


def _validated_loan_inputs(data):
    try:
        principal = float(data.get('loan_amount'))
        annual_rate = float(data.get('annual_interest_rate'))
        years = float(data.get('tenure_years'))
    except (TypeError, ValueError):
        raise ValueError('Enter valid amount, interest rate, and tenure values.')
    if not all(math.isfinite(value) for value in (principal, annual_rate, years)):
        raise ValueError('Loan values must be finite numbers.')
    if principal <= 0 or principal > 100_000_000:
        raise ValueError('Loan amount must be between 0 and 100,000,000.')
    if annual_rate < 0 or annual_rate > 100:
        raise ValueError('Annual interest rate must be between 0 and 100%.')
    if years <= 0 or years > 50:
        raise ValueError('Tenure must be greater than zero and no more than 50 years.')
    months = round(years * 12)
    if months < 1:
        raise ValueError('Tenure must be at least one month.')
    return principal, annual_rate, months


@app.route('/api/loan/emi', methods=['POST'])
@auth_required
def calculate_loan_emi():
    data = request.get_json(silent=True) or {}
    try:
        principal, annual_rate, months = _validated_loan_inputs(data)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    emi = _calculate_emi(principal, annual_rate, months)
    total_payment = emi * months
    return jsonify({
        'principal': principal,
        'monthly_emi': emi,
        'total_payment': total_payment,
        'total_interest': total_payment - principal,
        'currency': 'INR',
        'disclaimer': 'Illustrative estimate only; lender rates, fees, and approval may differ.'
    })


@app.route('/api/check-loan-eligibility', methods=['POST'])
@auth_required
def check_loan_eligibility():
    data = request.get_json(silent=True) or {}
    try:
        principal, annual_rate, months = _validated_loan_inputs(data)
        income = float(data.get('monthly_income'))
        existing_debt = float(data.get('monthly_debt', 0) or 0)
    except (TypeError, ValueError) as error:
        return jsonify({'error': str(error) or 'Enter monthly income and valid loan details.'}), 400
    if not math.isfinite(income) or not math.isfinite(existing_debt) or income <= 0 or existing_debt < 0:
        return jsonify({'error': 'Monthly income must be positive and existing debt cannot be negative.'}), 400

    emi = _calculate_emi(principal, annual_rate, months)
    debt_ratio = (existing_debt + emi) / income
    return jsonify({
        'within_affordability_guideline': debt_ratio <= 0.4,
        'monthly_emi': emi,
        'monthly_debt_ratio': debt_ratio,
        'message': (
            'Estimated monthly debt is within 40% of the income you entered.'
            if debt_ratio <= 0.4 else
            'Estimated monthly debt exceeds 40% of the income you entered.'
        ),
        'disclaimer': 'Illustrative affordability estimate only, not lender eligibility or approval.'
    })



# ==========================================
# BUDGET MODULE
# ==========================================
@app.route('/budget')
def budget_page():
    return render_template('budget.html')

@app.route('/api/budget-data', methods=['GET'])
@auth_required
def get_budget_data():
    db = get_db()
    user_id = request.user['user_id']
    
    now = datetime.datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spend_query = {
        'user_id': user_id,
        'direction': 'debit',
        'timestamp': {'$gte': month_start}
    }
    pipeline = [
        {'$match': spend_query},
        {'$group': {
            '_id': {'$ifNull': ['$category', 'Uncategorized']},
            'total': {'$sum': '$transaction_amount'}
        }}
    ]
    results = list(db.transactions.aggregate(pipeline))

    expense_count = db.transactions.count_documents(spend_query)
    total_spend = sum(r['total'] for r in results) if expense_count else None

    user = db.users.find_one({'user_id': user_id})
    budget_limit = user.get('budget_limit') if user else None
    
    return jsonify({
        'total_spend': total_spend,
        'budget_limit': budget_limit,
        'categories': results,
        'currency': user.get('currency') if user else None,
        'period_start': month_start.isoformat(),
        'spending_available': expense_count > 0
    })

@app.route('/api/update-budget', methods=['POST'])
@auth_required
def update_budget():
    data = request.get_json(silent=True) or {}
    try:
        limit = float(data.get('limit'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Enter a valid budget amount.'}), 400
    if not math.isfinite(limit) or limit <= 0:
        return jsonify({'error': 'Budget amount must be greater than zero.'}), 400
    db = get_db()
    if db is None:
        return jsonify({'error': 'Budget settings are temporarily unavailable.'}), 503
    db.users.update_one(
        {'user_id': request.user['user_id']},
        {'$set': {'budget_limit': limit}}
    )
    return jsonify({'status': 'success'})

# ==========================================
# CREDIT SCORE MODULE
# ==========================================
@app.route('/credit-score')
def credit_score_page():
    return render_template('credit_score.html')

@app.route('/api/credit-score', methods=['GET', 'POST'])
@auth_required
def handle_credit_score():
    db = get_db()
    if request.method == 'GET':
        user = db.users.find_one({'user_id': request.user['user_id']})
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify({'score': user.get('credit_score_simulation'), 'type': 'simulation'})
        
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            new_score = int(data.get('score'))
        except (TypeError, ValueError):
            return jsonify({'error': 'Enter a whole-number simulation score.'}), 400
        if new_score < 300 or new_score > 850:
            return jsonify({'error': 'Simulation score must be between 300 and 850.'}), 400
        db.users.update_one(
            {'user_id': request.user['user_id']},
            {'$set': {'credit_score_simulation': new_score, 'credit_score_simulation_updated_at': datetime.datetime.now()}}
        )
        return jsonify({'status': 'success', 'type': 'simulation', 'score': new_score})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='BFSI Backend Server')
    parser.add_argument('--server', action='store_true', help='Run server')
    parser.add_argument('--seed', action='store_true', help='Seed database')
    parser.add_argument('--test-ai', action='store_true', help='Test AI connection')
    parser.add_argument('--verify', action='store_true', help='Run verification suite')
    parser.add_argument('--setup', action='store_true', help='Setup demo data')
    
    args = parser.parse_args()
    
    # Default to server if no args provided
    if not (args.seed or args.test_ai or args.verify or args.setup):
        args.server = True
        
    if args.seed:
        seed_database()
    
    if args.test_ai:
        test_ai_connection()
        
    if args.verify:
        verify_chat_function()
        
    if args.setup:
        setup_demo_data()
        
    if args.server:
        print("Starting BFSI Backend Server (Debug Mode)...")
        # Enabled debug and reloader to pick up changes
        app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=True, threaded=True)
        