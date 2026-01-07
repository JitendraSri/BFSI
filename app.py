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
import random
import sys
import hashlib
import uuid
import argparse

# Third-party imports
from flask import Flask, request, jsonify, send_from_directory, render_template
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
# SMTP Configuration (Secure)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp-relay.brevo.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 2525))
SMTP_LOGIN = os.getenv("SMTP_LOGIN")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

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

def send_otp_email(to_email, otp, subject="Your Verification Code"):
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

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_LOGIN, SMTP_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, to_email, text)
        server.quit()
        
        logger.info(f"OTP sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {str(e)}")
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

        # Model
        clf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42)
        clf.fit(X_train, y_train)

        # Evaluation
        y_pred = clf.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True)
        
        # Extract metrics safely
        precision = report.get('1', {}).get('precision', 0.0)
        recall = report.get('1', {}).get('recall', 0.0)
        f1 = report.get('1', {}).get('f1-score', 0.0)
        
        logger.info(f"Model trained. Accuracy: {accuracy:.2f}, F1: {f1:.2f}")

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
        logger.error(f"Training failed: {e}")
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
print(f"DEBUG: MONGO_URI loaded as: {MONGO_URI}")
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


db = client[DB_NAME]

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


@app.route('/register', methods=['POST'])
def register():
    print(f"DEBUG: Register request hit. Content-Type: {request.content_type}")
    print(f"DEBUG: Raw Register data: {request.get_data().decode('utf-8', errors='ignore')}")
    data = request.get_json(silent=True)
    if not data:
        print("DEBUG: Register failed - Invalid JSON or no data")
        return jsonify({'error': 'Invalid JSON or no data provided'}), 400
        
    try:
        db = get_db()
        if db.users.find_one({'email': data['email']}):
            return jsonify({'error': 'Email already exists'}), 400
            
        hashed_password = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
        
        initial_balance = 0.0
        if data.get('initial_balance'):
            try:
                initial_balance = float(data['initial_balance'])
            except ValueError:
                initial_balance = 0.0
        
        user_id = str(uuid.uuid4())
        otp = str(random.randint(100000, 999999))
        otp_expiry = datetime.datetime.now() + timedelta(minutes=10)

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
            'created_at': datetime.datetime.now(),
            'is_verified': False,
            'otp_code': otp,
            'otp_expiry': otp_expiry
        }
        
        db.users.insert_one(user)
        
        # Send OTP
        # Send OTP in background thread to avoid blocking
        print(f"\n=========================================")
        print(f" >>> DEBUG OTP for {data['email']}: {otp} <<<")
        print(f"=========================================\n")
        logger.info(f"Generated OTP for {data['email']}: {otp}")
        
        # Async email sending
        import threading
        def async_send_email(to_email, otp_code):
            try:
                send_otp_email(to_email, otp_code)
            except Exception as e:
                print(f"Failed to send async email: {e}")

        email_thread = threading.Thread(target=async_send_email, args=(data['email'], otp))
        email_thread.daemon = True
        email_thread.start()
        
        return jsonify({'message': 'Registration successful! OTP sent.', 'user_id': user_id}), 201
        
    except Exception as e:
        print(f"DB Error during register: {e}")
        return jsonify({'error': 'Registration Failed', 'detail': str(e)}), 503


@app.route('/login', methods=['POST'])
def login():
    print(f"DEBUG: Login request hit. Content-Type: {request.content_type}")
    print(f"DEBUG: Raw Login data: {request.get_data().decode('utf-8', errors='ignore')}")
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
        
    if user.get('otp_code') == otp:
        # Check expiry
        if user.get('otp_expiry') and user['otp_expiry'] > datetime.datetime.now():
            db.users.update_one(
                {'email': email},
                {'$set': {'is_verified': True, 'otp_code': None, 'otp_expiry': None}}
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
    user = db.users.find_one({'email': email})
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    otp = str(random.randint(100000, 999999))
    otp_expiry = datetime.datetime.now() + timedelta(minutes=10)
    
    db.users.update_one(
        {'email': email},
        {'$set': {'otp_code': otp, 'otp_expiry': otp_expiry}}
    )
    
    print(f"\n=========================================")
    print(f" >>> DEBUG OTP for {email}: {otp} <<<")
    print(f"=========================================\n")
    sys.stdout.flush()
    # Force to stderr as well to guarantee visibility
    sys.stderr.write(f"\n>>> OTP: {otp} <<<\n")
    sys.stderr.flush()
    
    send_otp_email(email, otp, subject="Password Reset OTP")
    
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
    
    print(f"DEBUG: Comparing Stored '{stored_otp}' vs Received '{received_otp}'")

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


@app.route('/upload', methods=['POST'])
@auth_required
def upload_csv():
    if 'file' not in request.files:
        return jsonify({'error': 'file part missing'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'no selected file'}), 400

    # Detect file type
    file_ext = os.path.splitext(file.filename)[1].lower()
    
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
            temp_path = os.path.join(temp_dir, file.filename)
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
                
                # Override Timestamp with Upload Date (Current Time)
                df['timestamp'] = datetime.datetime.now()

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
    
    # Normalize column names (lowercase, strip whitespace)
    df.columns = df.columns.str.strip().str.lower()
    
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

    # prepare rows for insertion
    user_id = request.user.get('user_id')
    db = get_db()
    
    bulk_ops = []
    
    for _, r in df.iterrows():
        try:
            timestamp = pd.to_datetime(r['timestamp']) if not pd.isna(r['timestamp']) else datetime.datetime.now()
            
            doc = {
                'transaction_id': str(r['transaction_id']), # Keep raw ID
                'user_id': user_id,
                'customer_id': str(r['customer_id']) if not pd.isna(r['customer_id']) else None,
                'kyc_verified': 1 if r['kyc_verified'] == 'Yes' else 0,
                'account_age_days': int(r['account_age_days']) if not pd.isna(r['account_age_days']) else None,
                'transaction_amount': float(r['transaction_amount']) if not pd.isna(r['transaction_amount']) else 0.0,
                'channel': str(r['channel']) if not pd.isna(r['channel']) else None,
                'timestamp': timestamp,
                'is_fraud': int(r['is_fraud']) if not pd.isna(r['is_fraud']) else 0,
                'created_at': datetime.datetime.now()
            }
            # Upsert based on transaction_id
            bulk_ops.append(pymongo.UpdateOne({'transaction_id': doc['transaction_id']}, {'$set': doc}, upsert=True))
            
        except Exception as e:
            continue

    try:
        if bulk_ops:
            result = db.transactions.bulk_write(bulk_ops)
            inserted_count = result.upserted_count + result.modified_count
        else:
            inserted_count = 0
            
        # Invalidate dashboard cache
        cache.delete(f"dashboard_v2:{user_id}")
            
        # track upload
        db.file_uploads.insert_one({
            'user_id': user_id,
            'file_name': file.filename,
            'total_records': len(bulk_ops),
            'processed': 1,
            'created_at': datetime.datetime.now()
        })
        
        return jsonify({
            'status': 'ok', 
            'imported': inserted_count,
            'explanation': explanation,
            'risk_percentage': risk_percentage
        }), 201
    except Exception as e:
        return jsonify({'error': 'db error', 'detail': str(e)}), 500


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
        txn = db.transactions.find_one({'transaction_id': str(txn_id)})
        if not txn:
            return jsonify({'error': 'Transaction not found'}), 404
        
        if txn.get('user_id') != request.user['user_id']:
            return jsonify({'error': 'Unauthorized'}), 403
            
        db.transactions.delete_one({'transaction_id': str(txn_id)})
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
        
        # --- ENHANCED CHART DATA ---

        # A. Income vs Expense (Mock Income Mixed with Real Expenses)
        income_expense_data = []
        for item in chart_data:
            expense = item['value']
            income = expense * (1.2 + (0.1 * random.random())) 
            income_expense_data.append({
                'date': item['date'],
                'income': round(income, 2),
                'expense': expense
            })

        # B. Spending Categories (Donut)
        pipeline_cat = [
            { '$match': { 'user_id': user_id } },
            { '$group': { '_id': '$channel', 'total': { '$sum': '$transaction_amount' } } }
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

        # D. AI Prediction vs Actual (Line)
        prediction_data = []
        for item in chart_data:
            actual = item['value']
            predicted = actual * (1.0 + (random.uniform(-0.1, 0.1)))
            prediction_data.append({
                'date': item['date'],
                'actual': actual,
                'predicted': round(predicted, 2)
            })

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
        trust_score = user.get('trust_score', 0)
        if trust_score == 0:
            # Simple scoring logic
            if user.get('kyc_status') == 'Verified': trust_score += 40
            if total_txns > 20: trust_score += 30
            if user.get('security_status') == 'Strong': trust_score += 30
            trust_score = max(20, trust_score) # Baseline 20

        # 6. Intelligence
        intelligence = {
            'expense_prediction': round(user.get('balance', 0) * 0.12, 2),
            'fraud_risk_level': user.get('fraud_risk_level', 'Low')
        }

        response = {
            'user_stats': {
                'balance': user.get('balance', 0),
                'kyc_status': user.get('kyc_status', 'Pending'),
                'trust_score': trust_score,
                'security_status': user.get('security_status', 'Moderate'),
                'fraud_risk_level': user.get('fraud_risk_level', 'Low')
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
        
        upload_dir = os.path.join(os.path.dirname(__file__), 'uploads', 'profiles')
        # os.makedirs(upload_dir, exist_ok=True) # Not needed for DB storage
        
        # Read file data
        file_data = file.read()
        
        # Encode to Base64
        base64_data = base64.b64encode(file_data).decode('utf-8')
        
        # Create Data URI (e.g., data:image/png;base64,...)
        mime_type = file.mimetype or f'image/{file_ext}'
        profile_image_data_uri = f"data:{mime_type};base64,{base64_data}"
        
        db = get_db()
        db.users.update_one(
            {'user_id': user_id},
            {'$set': {'profile_image': profile_image_data_uri}}
        )
        
        return jsonify({
            'profile_image': profile_image_data_uri,
            'message': 'Profile image uploaded successfully (stored in DB)'
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
    try:
        result = train_model()
        
        if result.get('status') == 'error':
            return jsonify({'error': result.get('message', 'Training failed')}), 500
        
        load_ml_model()
        
        return jsonify({
            'status': 'success',
            'message': 'Model training completed',
            'metrics': result.get('metrics', {})
        })
    except Exception as e:
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
    
    print(f"API Key found: {api_key[:5]}...")
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
        investments = list(db.investments.find({'user_id': request.user['user_id']}, {'_id': 0}))
        return jsonify(investments)
    
    if request.method == 'POST':
        data = request.get_json()
        data['user_id'] = request.user['user_id']
        data['created_at'] = datetime.datetime.now()
        # Ensure numeric amount
        try:
            data['amount'] = float(data['amount'])
            data['current_value'] = float(data.get('current_value', data['amount']))
        except:
            return jsonify({'error': 'Invalid amount'}), 400
            
        db.investments.insert_one(data)
        return jsonify({'status': 'success'})

@app.route('/api/investments/delete', methods=['POST'])
@auth_required
def delete_investment():
    db = get_db()
    data = request.get_json()
    name = data.get('name')
    db.investments.delete_one({'user_id': request.user['user_id'], 'name': name})
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

@app.route('/api/check-loan-eligibility', methods=['POST'])
@auth_required
def check_loan_eligibility():
    data = request.get_json()
    amount = float(data.get('loan_amount', 0))
    income = float(data.get('monthly_income', 0))
    
    db = get_db()
    user = db.users.find_one({'user_id': request.user['user_id']})
    
    # Context for AI
    profile = {
        'balance': user.get('balance', 0),
        'trust_score': user.get('trust_score', 0),
        'kyc_status': user.get('kyc_status', 'Pending'),
        'account_age_days': (datetime.datetime.now() - user.get('created_at', datetime.datetime.now())).days,
        'fraud_risk': user.get('fraud_risk_level', 'Low'),
        'monthly_income_declared': income,
        'loan_amount_requested': amount
    }

    try:
        # Prompt Engineering
        prompt = f"""
        Act as a Senior bank Loan Officer. Evaluate this loan application.
        
        User Profile:
        {json.dumps(profile, indent=2)}
        
        Decision Rule Guidelines:
        1. Reject if KYC is not Verified.
        2. Reject if Fraud Risk is High.
        3. Reject if Loan Amount > 50x Monthly Income.
        4. Reject if Trust Score < 30.
        5. Otherwise, approve based on balance and income health.
        
        Output JSON ONLY:
        {{
            "eligible": true/false,
            "message": "A human-friendly, professional explanation (HTML format allowed, use <b> for emphasis). Explain WHY accepted or rejected."
        }}
        """
        
        if genai_service.model:
            response = genai_service.model.generate_content(prompt)
            clean_text = response.text.strip().replace('```json', '').replace('```', '')
            result = json.loads(clean_text)
            return jsonify(result)
        else:
            # Fallback if AI offline
            return jsonify({
                'eligible': False,
                'message': "AI Service unavailable. Manual review required."
            })

    except Exception as e:
        logger.error(f"AI Loan check failed: {e}")
        return jsonify({
            'eligible': False, 
            'message': "We encountered an error analyzing your profile. Please try again later."
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
    
    # 1. Total Spend (Aggregated from transactions)
    pipeline = [
        {'$match': {'user_id': user_id}}, # In real app, filter by date (this month)
        {'$group': {'_id': '$channel', 'total': {'$sum': '$transaction_amount'}}}
    ]
    results = list(db.transactions.aggregate(pipeline))
    
    # Calculate Total
    total_spend = sum(r['total'] for r in results)
    
    # 2. Budget Limit
    user = db.users.find_one({'user_id': user_id})
    budget_limit = user.get('budget_limit', 50000)
    
    return jsonify({
        'total_spend': total_spend,
        'budget_limit': budget_limit,
        'categories': results
    })

@app.route('/api/update-budget', methods=['POST'])
@auth_required
def update_budget():
    data = request.get_json()
    limit = float(data.get('limit', 0))
    db = get_db()
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
        return jsonify({'score': user.get('credit_score', 750)}) # Default 750
        
    if request.method == 'POST':
        data = request.get_json()
        new_score = int(data.get('score', 750))
        db.users.update_one(
            {'user_id': request.user['user_id']},
            {'$set': {'credit_score': new_score}}
        )
        return jsonify({'status': 'success'})

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
        print("Starting BFSI Backend Server (Optimized Mode)...")
        # debug=False for maximum speed. threaded=True for concurrency.
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False, threaded=True)
        