import os
import json
import csv
import random
import re
from datetime import datetime, timedelta
import time
# 1. Imports
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from openai import OpenAI
import base64
from email.mime.text import MIMEText

POLICY_CACHE = None


# 2. Initialize Flask App (DO THIS ONLY ONCE)
app = Flask(__name__, static_folder='static')
CORS(app)
today_str = datetime.now().strftime("%Y-%m-%d")  # Define today_str as today's date in "YYYY-MM-DD" format
calendar_events = {
    today_str: [
        {
            "id": "test-1", 
            "title": "✅ SYSTEM TEST EVENT", 
            "time": "10:00", 
            "description": "If you see this, the Calendar is working!"
        }
    ]
}
# 3. Configure Secret Key (CRITICAL FIX)
# We use a static string 'super-secret-key' so you don't get logged out when the server reloads
app.secret_key = 'super-secret-broker-dev-key' 
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# 4. API Keys
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/gmail.send' ,
    'https://www.googleapis.com/auth/gmail.readonly'

]

CLIENT_SECRETS_FILE = "client_secret.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_KEY = "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"

client = OpenAI(api_key=OPENAI_API_KEY)
def summarize_email_body(email_body):
        """
        Generates a short, plain-text summary of an email body.
        """
        if not email_body or len(email_body.strip()) < 30:
            return ""

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You summarize insurance-related emails for brokers. "
                            "Return 1–2 concise sentences in plain text. "
                            "Do not use markdown, bullets, or formatting symbols."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Summarize this email:\n\n{email_body[:4000]}"
                    }
                ],
                temperature=0.2,
                max_tokens=120
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f"⚠️ Email summarization failed: {e}")
            return ""

# ==================== CSV LOADER & UTILS ====================

def parse_datetime(datetime_str):
    if not datetime_str or datetime_str == '-': return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formats = ["%Y-%m-%d %H:%M:%S", "%d/%m/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S"]
    for fmt in formats:
        try: return datetime.strptime(datetime_str.strip(), fmt).strftime("%Y-%m-%d %H:%M:%S")
        except: continue
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_date(date_str):
    if not date_str or date_str == '-': return datetime.now().strftime("%Y-%m-%d")
    formats = ["%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"]
    for fmt in formats:
        try: return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except: continue
    return datetime.now().strftime("%Y-%m-%d")
def send_gmail_message(credentials_dict, to, subject, body):
    creds = Credentials(**credentials_dict)
    service = build('gmail', 'v1', credentials=creds)

    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    send_body = {'raw': raw_message}

    sent = service.users().messages().send(
        userId='me',
        body=send_body
    ).execute()

    return sent

def safe_float(value, default=0.0):
    try: return float(str(value).replace(',', '').replace('$', '').strip())
    except: return default

def safe_int(value, default=0):
    try: return int(float(str(value).replace(',', '').replace('$', '').strip()))
    except: return default

def load_csv_data(filename='Techfestsampledata_scrambled.csv'):
    print("🔥 CSV LOAD EXECUTED")
    """Loads policy data from CSV"""
    global POLICY_CACHE

    # ✅ RETURN CACHED DATA IF ALREADY LOADED
    if POLICY_CACHE is not None:
        return POLICY_CACHE

    policies = []
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                try:
                    policy = {
                        "placement_id": row.get('Placement Id', ''),
                        "client": row.get('Client', 'Unknown'),
                        "placement_name": row.get('Placement Name', ''),
                        "coverage": row.get('Coverage', ''),
                        "product_line": row.get('Product Line', ''),
                        "carrier": row.get('Carrier Group', ''),
                        "carrier_group_local_id": row.get('Carrier Group Local ID', ''),
                        
                        "created_at": parse_datetime(row.get('Placement Created Date/Time', '')),
                        "created_by": row.get('Placement Created By', ''),
                        "created_by_id": row.get('Placement Created By (ID)', ''),
                        "response_received_date": parse_date(row.get('Response Received Date', '')),
                        
                        "effective_date": parse_date(row.get('Placement Effective Date', '')),
                        "expiry_date": parse_date(row.get('Placement Expiry Date', '')),
                        
                        "renewing_status": row.get('Placement Renewing Status', ''),
                        "renewing_status_code": row.get('Placement Renewing Status Code', ''),
                        "placement_status": row.get('Placement Status', ''),
                        "declination_reason": row.get('Declination Reason', ''),
                        
                        "incumbent_indicator": row.get('Incumbent Indicator', ''),
                        "participation_status_code": row.get('Participation Status Code', ''),
                        "client_segment_code": row.get('Placement Client Segment Code', ''),
                        
                        "limit": safe_int(row.get('Limit', '0')),
                        "coverage_premium": safe_float(row.get('Coverage Premium Amount', '0')),
                        "tria_premium": safe_float(row.get('Tria Premium', '0')),
                        "premium": safe_float(row.get('Total Premium', '0')),
                        "commission_pct": safe_float(row.get('Comission %', '0')),
                        "commission_amount": safe_float(row.get('Comission Amount', '0')),
                        "participation_pct": safe_float(row.get('Participation Percentage', '0')),
                        
                        "production_code": row.get('Production Code', ''),
                        "submission_sent_date": parse_date(row.get('Submission Sent Date', '')),
                        "program_product_code": row.get('Program Product Local Code Text', ''),
                        "non_admitted_indicator": row.get('Approach Non Admitted Market Indicator', ''),
                        "carrier_integration": row.get('Carrier Integration', ''),
                        
                        "specialist": row.get('Placement Specialist', 'Unassigned'),
                    }

                    if policy["placement_id"] and policy["placement_id"] != '-':
                        policies.append(policy)
                except:
                    continue
        print(f"✅ Loaded {len(policies)} policies.")
    

    except Exception as e:
        print(f"⚠️ CSV Error: {e}. Using empty list.")


    # ✅ CACHE RESULT FOR FUTURE CALLS
    POLICY_CACHE = policies
    return policies


# ==================== DATA CONNECTORS ====================

class ConnectorBase:
    def __init__(self, source_name):
        self.source_name = source_name
    
    def wrap_response(self, data, record_id):
        return {
            "data": data,
            "metadata": {
                "source": self.source_name,
                "record_id": record_id,
                "timestamp": datetime.now().isoformat(),
                "confidence": 0.95 # High confidence for system data
            }
        }

class CRMConnector(ConnectorBase):
    def __init__(self):
        super().__init__("CRM-AMS")
        self.policies = load_csv_data() # Loads from the CSV function above
    
    def get_renewals(self, days_ahead=180):
        today = datetime.now()
        cutoff = today + timedelta(days=days_ahead)
        return [self.wrap_response(p, p["placement_id"]) for p in self.policies 
                if today <= datetime.strptime(p["expiry_date"], "%Y-%m-%d") <= cutoff]

    def get_policy(self, placement_id):
        for p in self.policies:
            if p["placement_id"] == placement_id:
                return self.wrap_response(p, placement_id)
        return None

class EmailConnector(ConnectorBase):
    """Gmail-backed Email Connector"""

    def __init__(self):
        super().__init__("Gmail")

    def get_emails(self, placement_id):
        # If user not authenticated with Google, return empty safely
        if "credentials" not in session:
            return []

        try:
            # ✅ NEW: Get policy data to extract client name
            policy_res = crm.get_policy(placement_id)
            if not policy_res:
                print(f"⚠️ Policy {placement_id} not found for email search")
                return []
            
            client_name = policy_res["data"].get("client", "")
            coverage = policy_res["data"].get("coverage", "")
            
            # ✅ NEW: Build smart search query
            search_terms = [placement_id]
            if client_name:
                search_terms.append(client_name)
            if coverage:
                search_terms.append(coverage)
            
            query = " OR ".join(f'"{term}"' for term in search_terms if term)
            print(f"🔍 Email Search Query: {query}")
            
            creds = Credentials(**session["credentials"])
            service = build("gmail", "v1", credentials=creds)

            # Search query: placement ID in subject or body
            # ✅ REMOVED: query = placement_id (now built above)

            results = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=20  # ✅ CHANGED: from 10 to 20
            ).execute()

            messages = results.get("messages", [])
            emails = []

            for msg in messages:
                msg_data = service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="full"
                ).execute()

                headers = msg_data.get("payload", {}).get("headers", [])
                body = self._extract_body(msg_data.get("payload", {}))

                subject = ""
                date = ""
                sender = ""  # ✅ NEW: Added sender tracking

                for h in headers:
                    if h["name"] == "Subject":
                        subject = h["value"]
                    if h["name"] == "Date":
                        date = h["value"]
                    if h["name"] == "From":  # ✅ NEW: Extract sender
                        sender = h["value"]

                # ✅ NEW: Filter out irrelevant emails (noise reduction)
                email_text = f"{subject} {body}".lower()
                is_relevant = (
                    placement_id.lower() in email_text or
                    (client_name and client_name.lower() in email_text) or
                    (coverage and coverage.lower() in email_text)
                )
                
                if not is_relevant:
                    continue  # Skip this email

                emails.append(
                    self.wrap_response(
                        {
                            "subject": subject,
                            "body": body,
                            "date": date,
                            "sender": sender  # ✅ NEW: Added sender to response
                        },
                        msg["id"]
                    )
                )

            print(f"✅ Found {len(emails)} relevant emails for {placement_id}")  # ✅ NEW: Success log
            return emails

        except Exception as e:
            print(f"⚠️ Gmail fetch error: {e}")
            return []

    def _extract_body(self, payload):
        """Extract plain text body safely"""
        if payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(
                payload["body"]["data"]
            ).decode(errors="ignore")

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(
                    part["body"]["data"]
                ).decode(errors="ignore")

        return ""


class BrokerAppConnector(ConnectorBase):
    """Simulated Claims/Risk Data"""
    def __init__(self):
        super().__init__("BrokerApp")
        # FIXED: Renamed 'total_incurred' back to 'claims_total' to match Frontend expectations
        self.claims_data = {
            "SCR-76fd0b40a1cb": {
                "claims_count": 2, 
                "claims_total": 45000,  # <--- Was 'total_incurred', caused the crash
                "loss_ratio": 0.67
            },
            "SCR-abc123def456": {
                "claims_count": 0, 
                "claims_total": 0, 
                "loss_ratio": 0.0
            }
        }
    
    def get_claims(self, placement_id):
        # Default safety object to prevent 'undefined' errors if ID missing
        default_data = {"claims_count": 0, "claims_total": 0, "loss_ratio": 0.0}
        data = self.claims_data.get(placement_id, default_data)
        return self.wrap_response(data, f"claims-{placement_id}")

# Re-initialize connectors
crm = CRMConnector()
email = EmailConnector()
broker_app = BrokerAppConnector()

# ==================== INTELLIGENCE & ORCHESTRATION ====================

class LLMEngine:
    """Handles all interaction with OpenAI"""
    
    @staticmethod
    def generate_dynamic_email(policy_context, claims_context, user_instruction=""):
        # ... (Same AI Logic as before) ...
        system_prompt = "You are an expert Insurance Broker Copilot. Write a professional email."
        
        context_str = f"""
        CLIENT: {policy_context.get('client')}
        COVERAGE: {policy_context.get('coverage')}
        PREMIUM: ${policy_context.get('premium', 0):,.2f}
        LOSS RATIO: {claims_context.get('loss_ratio', 0):.1%}
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{context_str}\nINSTRUCTION: {user_instruction}"}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"

    

@staticmethod
def answer_question_with_context(query, policy_data, claims_data, email_data):
    try:
        # ---- 1. REDUCE CONTEXT (CRITICAL FIX) ----
        context = {
            "Policy": {
                "placement_id": policy_data.get("placement_id"),
                "client": policy_data.get("client"),
                "coverage": policy_data.get("coverage"),
                "carrier": policy_data.get("carrier"),
                "expiry_date": policy_data.get("expiry_date"),
                "premium": policy_data.get("premium"),
                "renewing_status": policy_data.get("renewing_status"),
                "placement_status": policy_data.get("placement_status")
            },
            "Claims": {
                "claims_count": claims_data.get("claims_count"),
                "claims_total": claims_data.get("claims_total"),
                "loss_ratio": claims_data.get("loss_ratio")
            },
            "Recent_Emails": [
                {
                    "subject": e.get("subject"),
                    "date": e.get("date"),
                    "body": e.get("body")
                }
                for e in email_data[:3]
            ]
        }

        context_str = json.dumps(context, default=str)

        # ---- 2. OPENAI CALL (FIXED) ----
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Broker Copilot chatbot. Respond clearly and professionally, "
                        "as if assisting a broker in real time. Keep the tone neutral, helpful, "
                        "and business-friendly. Use sections and bullet points but keep it detailed. "
                        "Avoid sounding like a formal report or audit note."
                    )
                },
                {
                    "role": "user",
                    "content": f"""
Context:
{context_str}

Question:
{query}

Respond like a helpful Broker Copilot assisting in real time.
Start with a brief, direct summary that answers the question.
Then, where useful, include concise bullet points to highlight key observations, suggested next steps, or important context.
Use headings only if they genuinely improve clarity, and feel free to adapt or omit them.
Do not follow a fixed template, do not force a specific number of points, and avoid sounding like a formal report.
Keep the tone professional, practical, and conversational.
Return the response in plain text only.
Do not use Markdown or any formatting symbols such as *, **, #, ###, or backticks.
Use simple sentences and hyphenated bullet points only if needed.
"""
                }
            ],
            temperature=0.3,
            max_tokens=400
        )

        # ---- 3. SAFE OUTPUT EXTRACTION (FIXED) ----
        output_text = response.choices[0].message.content

        return output_text.strip() if output_text else "No relevant information found."

    except Exception as e:
        print(f"❌ AI Error: {e}")
        return "AI Connection Error. Check your API key."




class OrchestrationEngine:
    """Core intelligence layer"""

    @staticmethod
    def calculate_priority_score(policy_data, claims_data, email_data, meeting_data):
        """
        RESTORED ORIGINAL LOGIC: The frontend needs 'factors' and 'total_score' to render.
        """
        score = 0
        factors = {}
        
        # 1. Premium
        premium = policy_data.get("premium", 0)
        premium_score = 30 if premium > 100000 else 20 if premium > 50000 else 10
        score += premium_score
        factors["premium_at_risk"] = {"score": premium_score, "value": f"${premium:,.2f}"}
        
        # 2. Expiry
        try:
            expiry = datetime.strptime(policy_data.get("expiry_date", ""), "%Y-%m-%d")
            days = (expiry - datetime.now()).days
            expiry_score = 25 if days < 30 else 15 if days < 90 else 5
            val_str = f"{days} days"
        except:
            expiry_score = 5
            val_str = "Unknown"
        score += expiry_score
        factors["time_to_expiry"] = {"score": expiry_score, "value": val_str}
        
        # 3. Claims
        loss_ratio = claims_data.get("loss_ratio", 0)
        claims_score = 5 if loss_ratio > 0.7 else 20 if loss_ratio < 0.3 else 12
        score += claims_score
        factors["claims_performance"] = {"score": claims_score, "value": f"{loss_ratio:.1%} LR"}
        
        # 4. Engagement (simplified for safe fallback)
        carrier_score = 15 if len(email_data) > 0 else 5
        score += carrier_score
        factors["carrier_responsiveness"] = {"score": carrier_score, "value": "Active" if len(email_data) > 0 else "Pending"}
        
        return {
            "total_score": score,
            "max_score": 100,
            "priority_level": "High" if score > 70 else "Medium" if score > 40 else "Low",
            "factors": factors
        }

engine = OrchestrationEngine()

# ==================== API ENDPOINTS ====================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')
# ==================== DASHBOARD STATS (RESTORED) ====================

@app.route('/api/stats')
def get_stats():
    """
    Calculates the top-level numbers for the Dashboard Cards.
    """
    # 1. Get all upcoming renewals (next 6 months)
    renewals = crm.get_renewals(180)
    
    total = len(renewals)
    
    # 2. Calculate Urgent (less than 30 days to expiry)
    today = datetime.now()
    urgent_count = 0
    for r in renewals:
        try:
            expiry = datetime.strptime(r["data"]["expiry_date"], "%Y-%m-%d")
            if (expiry - today).days < 30:
                urgent_count += 1
        except:
            continue

    # 3. Calculate Premium totals (with safety checks for None values)
    total_premium = sum((r["data"].get("premium") or 0) for r in renewals)
    
    return jsonify({
        "total_renewals": total,
        "urgent_renewals": urgent_count,
        "total_premium_at_risk": total_premium,
        "avg_premium": total_premium / total if total > 0 else 0
    })

@app.route('/api/renewals')
def get_renewals():
    """
    Get renewal pipeline with TWO filters:
    1. Days (Time Horizon)
    2. Priority Level (High/Medium/Low)
    """
    # 1. Get Query Parameters
    days = request.args.get('days', 180, type=int)
    priority_filter = request.args.get('priority', 'All') # Default to 'All'
    
    # 2. Fetch raw data based on Days
    raw_renewals = crm.get_renewals(days)
    
    enriched = []
    for r in raw_renewals:
        pid = r["data"]["placement_id"]
        
        # Safe Fetching to prevent crashes
        claims = broker_app.get_claims(pid)
        emails = []
        meetings = [] 
        
        # Calculate Score
        priority = engine.calculate_priority_score(
            r["data"], 
            claims["data"], 
            emails, 
            meetings
        )
        
        enriched.append({
            **r,
            "priority": priority
        })
    
    # 3. APPLY PRIORITY FILTER
    if priority_filter and priority_filter != 'All':
        enriched = [
            r for r in enriched 
            if r['priority']['priority_level'] == priority_filter
        ]
    
    # 4. Sort by Score (High -> Low)
    enriched.sort(key=lambda x: x["priority"]["total_score"], reverse=True)
    
    return jsonify(enriched)
@app.route('/api/system/status')
def get_system_status():
    """
    Returns the health status of all connected systems.
    In a real app, this would ping the actual APIs.
    """
    # Simulate a check (Randomly highly reliable)
    crm_status = "active" if len(crm.policies) > 0 else "error"
    
    return jsonify({
        "integrations": [
            {
                "id": "crm",
                "name": "Salesforce CRM",
                "status": crm_status, 
                "last_sync": datetime.now().strftime("%H:%M"),
                "icon": "☁️"
            },
            {
                "id": "email",
                "name": " Mail",
                "status": "active" if session.get('credentials') else "inactive",
                "last_sync": "Live Stream",
                "icon": "✉️"
            },
            {
                "id": "calendar",
                "name": "Calendar",
                "status": "active" if session.get('credentials') else "inactive",
                "last_sync": "Real-time",
                "icon": "📅"
            },
            {
                "id": "broker",
                "name": "Applied Epic (Claims)",
                "status": "active",
                "last_sync": datetime.now().strftime("%H:%M"),
                "icon": "🛡️"
            }
        ]
    })
@app.route('/api/brief/<placement_id>')
def get_brief(placement_id):
    """
    Generate brief with strict type safety to prevent .toLocaleString() crashes
    """
    # 1. Fetch Data
    policy_res = crm.get_policy(placement_id)
    if not policy_res: 
        return jsonify({"error": "Policy not found"}), 404
    
    claims_res = broker_app.get_claims(placement_id)
    emails_res = email.get_emails(placement_id)
    
    # 2. Safety Check: Ensure numeric fields exist
    # If CSV loaded 'None', force 0 to prevent frontend crash on .toLocaleString()
    p_data = policy_res["data"]
    if p_data.get("premium") is None: p_data["premium"] = 0
    if p_data.get("limit") is None: p_data["limit"] = 0

    # 3. Calculate Priority
    priority = engine.calculate_priority_score(
        p_data, 
        claims_res["data"], 
        emails_res, 
        []
    )
        # Derive days to expiry safely
    derived_days = None
    try:
        expiry_dt = datetime.strptime(p_data.get("expiry_date", ""), "%Y-%m-%d")
        derived_days = (expiry_dt - datetime.now()).days
    except:
        derived_days = None


    # 4. Construct Brief with Validated Data
    brief = {
        "placement_id": placement_id,
        "client_name": p_data.get("client", "Unknown"),
        "coverage": p_data.get("coverage", "Unknown"),
        "expiry_date": p_data.get("expiry_date", "-"),
        "priority": priority,

                "summary": {
            "policy_details": {
                "data": p_data,
                "source": policy_res["metadata"]
            },
            "claims_history": {
                "data": claims_res["data"],
                "source": claims_res["metadata"]
            },
            "recent_communications": {
                "data": [e["data"] for e in emails_res],
                "source": [e["metadata"] for e in emails_res]
            },
            "meetings": {
                "data": [],
                "source": []
            }
        },

        
        "overview": {
    "client": p_data.get("client"),
    "placement_name": p_data.get("placement_name"),
    "placement_id": placement_id,
    "product_line": p_data.get("product_line"),
    "coverage": p_data.get("coverage"),
    "carrier": p_data.get("carrier"),
    "carrier_integration": p_data.get("carrier_integration"),
    "client_segment": p_data.get("client_segment_code"),
    "incumbent": p_data.get("incumbent_indicator")
},
"timeline": {
    "created_at": p_data.get("created_at"),
    "created_by": p_data.get("created_by"),
    "specialist": p_data.get("specialist"),
    "submission_sent": p_data.get("submission_sent_date"),
    "response_received": p_data.get("response_received_date"),
    "effective_date": p_data.get("effective_date"),
    "expiry_date": p_data.get("expiry_date"),
    "days_to_expiry": derived_days
},
"financials": {
    "total_premium": p_data.get("premium"),
    "coverage_premium": p_data.get("coverage_premium"),
    "tria_premium": p_data.get("tria_premium"),
    "limit": p_data.get("limit"),
    "participation_pct": p_data.get("participation_pct"),
    "commission_pct": p_data.get("commission_pct"),
    "commission_amount": p_data.get("commission_amount")
},
"renewal_status": {
    "placement_status": p_data.get("placement_status"),
    "renewing_status": p_data.get("renewing_status"),
    "renewing_status_code": p_data.get("renewing_status_code"),
    "declination_reason": p_data.get("declination_reason"),
    "non_admitted": p_data.get("non_admitted_indicator"),
    "program_product": p_data.get("program_product_code")
}
,
        "recommended_actions": [
            "Review Renewal Terms", 
            "Check Claims History"
        ]
    }
    
    return jsonify(brief)

@app.route('/api/email/send', methods=['POST'])
def send_email():
    if 'credentials' not in session:
        return jsonify({"error": "Not authenticated with Google"}), 401

    data = request.json
    to = data.get('to')
    subject = data.get('subject')
    body = data.get('body')

    if not to or not subject or not body:
        return jsonify({"error": "Missing email fields"}), 400

    try:
        result = send_gmail_message(
            session['credentials'],
            to,
            subject,
            body
        )
        return jsonify({
            "status": "sent",
            "gmail_id": result.get('id')
        })
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


@app.route('/api/qa', methods=['POST'])
def qa_endpoint():
    """
    Smart Q&A that can switch context dynamically.
    If the user asks about a specific ID (e.g., "Status of SCR-123?"), 
    it fetches THAT specific policy instead of the current one.
    """
    data = request.json
    question = data.get('question', '')
    
    # 1. DEFAULT: Use the ID from the current page/context
    context = data.get('context', {})
    target_id = context.get('placement_id')

    

    # 2. OVERRIDE: Did the user type a specific ID in the question?
    # Regex looks for patterns like "SCR-" followed by alphanumeric characters
    match = re.search(r'(SCR-[a-zA-Z0-9]+)', question)
    if match:
        target_id = match.group(1) # Switch focus to the requested ID
        print(f"🔍 User asked about specific ID: {target_id}")

    if not target_id:
        return jsonify({
            "answer": "I don't see a specific policy selected. Please mention a Policy ID (like SCR-xxxx) or select one from the list.",
            "confidence": 1.0
        })

    # 3. Fetch Data for the TARGET ID
    policy_res = crm.get_policy(target_id)
    
    if not policy_res:
        return jsonify({
            "answer": f"I tried looking up {target_id}, but I couldn't find it in the database. Are you sure that ID is correct?",
            "confidence": 0.0
        })

    claims_res = broker_app.get_claims(target_id)
    emails_res = email.get_emails(target_id)

    # 4. Generate Answer
    ai_answer = answer_question_with_context(
        question, 
        policy_res['data'], 
        claims_res['data'], 
        [e['data'] for e in emails_res]
    )

    return jsonify({
        "answer": ai_answer,
        "sources": [policy_res['metadata']],
        "confidence": 0.95
    })
# ==================== TEMPLATE ENDPOINTS (RESTORED) ====================

@app.route('/api/templates')
def get_templates():
    """Restores the list of templates for the dropdown"""
    templates = [
        {
    "id": "renewal-initial",
    "name": "Initial Renewal Outreach",
    "subject": "Upcoming Renewal | {{client_name}} – {{coverage}} (Expiring {{expiry_date}})",
    "body": "Dear {{client_name}},\n\nI hope you are doing well.\n\nWe are approaching the renewal of your {{coverage}} policy, which is scheduled to expire on {{expiry_date}}.\n\nAt this stage, we are reviewing market conditions, carrier appetite, and your current program structure to ensure we present you with the most competitive and appropriate renewal options.\n\nKey details of your current placement:\n• Carrier: {{carrier}}\n• Limit: {{limit}}\n• Current Premium: {{premium}}\n\nOver the coming weeks, we will evaluate renewal terms and identify any opportunities to optimize coverage, pricing, or structure.\n\nPlease let us know if there have been any material changes in operations, exposure, or risk profile that we should consider as part of this renewal.\n\nWe will follow up shortly with our initial renewal strategy and recommendations.\n\nBest regards,\n{{specialist_name}}"
  },
  {
    "id": "renewal-followup",
    "name": "Renewal Follow-Up & Next Steps",
    "subject": "Renewal Follow-Up | {{client_name}} – {{coverage}}",
    "body": "Hi {{client_name}},\n\nI wanted to follow up regarding the renewal of your {{coverage}} policy expiring on {{expiry_date}}.\n\nWe have received preliminary feedback from the market and are currently assessing renewal terms, including pricing, coverage considerations, and any potential adjustments required given current underwriting conditions.\n\nAt this point, it would be helpful to confirm:\n• Any changes in operations or exposures\n• Loss activity not yet reported\n• Coverage or limit adjustments you would like us to explore\n\nOnce confirmed, we will finalize our negotiations with carriers and prepare a clear renewal summary for your review.\n\nPlease let me know a convenient time if you would like to discuss this in more detail.\n\nKind regards,\n{{specialist_name}}"
  },
        {
            "id": "ai-generate",
            "name": "✨ Generate with AI (Custom)",
            "subject": "AI Generated Subject",
            "body": "AI will generate this content based on policy data..."
        }
    ]
    return jsonify(templates)

# ==================== GOOGLE AUTHENTICATION ====================

@app.route('/google/login')
def google_login():
    """Initiates the OAuth 2.0 Flow"""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return "Error: client_secret.json not found.", 500

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, 
        scopes=SCOPES,
        redirect_uri=url_for('google_callback', _external=True)
    )
    
    authorization_url, state = flow.authorization_url(access_type='offline')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/google/callback')
def google_callback():
    """Handles the callback from Google"""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return "Error: client_secret.json missing", 500

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, 
        scopes=SCOPES, 
        state=session.get('state'),
        redirect_uri=url_for('google_callback', _external=True)
    )

    # Exchange authorization code for tokens
    flow.fetch_token(authorization_response=request.url)
    
    # Store credentials in the session
    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    
    # Redirect back to dashboard
    return redirect('/')

@app.route('/api/auth/status')
def auth_status():
    """Checks if user is logged in"""
    return jsonify({"logged_in": 'credentials' in session})

@app.route('/api/templates/render', methods=['POST'])
def render_template():
    """
    Renders the selected template. 
    If 'ai-generate' is selected, it triggers the LLM.
    """
    data = request.json
    template_id = data.get('template_id')  # Frontend sends ID here
    template_body = data.get('template')   # Or raw body here
    placement_id = data.get('placement_id')
    
    # 1. Fetch Policy Data
    policy_res = crm.get_policy(placement_id)
    if not policy_res:
        return jsonify({"error": "Policy not found"}), 404
    
    p = policy_res["data"]
    claims_res = broker_app.get_claims(placement_id)

    # SUBJECT TEMPLATE MAP (minimal + explicit)
    subject_map = {
        "renewal-initial": "Upcoming Renewal | {{client_name}} – {{coverage}} (Expiring {{expiry_date}})",
        "renewal-followup": "Renewal Follow-Up | {{client_name}} – {{coverage}}",
        "ai-generate": "Renewal Discussion | {{client_name}} – {{coverage}}"
    }

    # COMMON REPLACEMENTS (used for body + subject)
    replacements = {
        "{{client_name}}": p.get("client", ""),
        "{{coverage}}": p.get("coverage", ""),
        "{{carrier}}": p.get("carrier", ""),
        "{{expiry_date}}": p.get("expiry_date", ""),
        "{{effective_date}}": p.get("effective_date", ""),
        "{{limit}}": f"{p.get('limit', 0):,}",
        "{{premium}}": f"{p.get('premium', 0):,.2f}",
        "{{specialist_name}}": p.get("specialist", "Account Manager")
    }

    # RENDER SUBJECT
    rendered_subject = subject_map.get(template_id, "")
    for key, value in replacements.items():
        rendered_subject = rendered_subject.replace(key, str(value))

    # 2. AI INTERCEPTION
    if template_id == 'ai-generate' or 'AI will generate' in str(template_body):
        ai_body = LLMEngine.generate_dynamic_email(
            p, 
            claims_res["data"], 
            user_instruction="Draft a renewal email."
        )
        rendered = ai_body

        return jsonify({
            "rendered": rendered,
            "rendered_subject": rendered_subject,
            "source": policy_res["metadata"]
        })

    # 3. STANDARD TEMPLATE RENDERING
    rendered = template_body or ""
    for key, value in replacements.items():
        rendered = rendered.replace(key, str(value))
    
    return jsonify({
        "rendered": rendered,
        "rendered_subject": rendered_subject,
        "source": policy_res["metadata"]
    })

    
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/api/email/generate', methods=['POST'])
def generate_email_endpoint():
    data = request.json
    placement_id = data.get('placement_id')
    user_instruction = data.get('instruction', 'Standard renewal notice')

    policy_res = crm.get_policy(placement_id)
    claims_res = broker_app.get_claims(placement_id)
    
    if not policy_res:
        return jsonify({"error": "Policy not found"}), 404

    generated_text = LLMEngine.generate_dynamic_email(
        policy_res['data'],
        claims_res['data'],
        user_instruction
    )

    return jsonify({
        "subject": f"Renewal Discussion: {policy_res['data']['client']} - {policy_res['data']['coverage']}",
        "body": generated_text,
        "source": "Generated by GPT-4o-mini based on CRM Data"
    })
@app.route("/api/calendar")
def get_all_events():
    final_events = []

    # 1. FETCH LOCAL MANUAL EVENTS
    for date_key, event_list in calendar_events.items():
        for evt in event_list:
            # Combine Date and Time for FullCalendar
            start_iso = date_key
            if evt.get("time"):
                start_iso = f"{date_key}T{evt['time']}" # e.g. 2025-10-25T14:30

            final_events.append({
                "id": evt["id"],
                "title": evt["title"],
                "start": start_iso, 
                "description": evt.get("description", ""),
                "className": "fc-event-local", # Green
                "extendedProps": {
                    "description": evt.get("description", "")
                }
            })

    # 2. FETCH GOOGLE EVENTS (Existing logic...)
    if "credentials" in session:
        try:
            creds = Credentials(**session["credentials"])
            service = build("calendar", "v3", credentials=creds)
            now = datetime.utcnow().isoformat() + "Z"
            events_result = service.events().list(
                calendarId="primary", timeMin=now, maxResults=50, singleEvents=True, orderBy="startTime"
            ).execute()
            
            for event in events_result.get("items", []):
                start = event["start"].get("dateTime", event["start"].get("date"))
                final_events.append({
                    "id": event["id"],
                    "title": "📅 " + event.get("summary", "Busy"),
                    "start": start,
                    "className": "fc-event-google", # Blue
                    "url": event.get("htmlLink")
                })
        except:
            pass

    return jsonify(final_events)

# ==========================================
# CALENDAR EVENT MANAGEMENT (SAVE / DELETE)

@app.route('/api/emails/<placement_id>')
def get_emails_for_placement(placement_id):
    emails_res = email.get_emails(placement_id)

    # Sort by date ascending (safe)
    def safe_date(e):
        try:
            return datetime.strptime(e["data"].get("date", ""), "%Y-%m-%d")
        except:
            return datetime.min

    emails_sorted = sorted(emails_res, key=safe_date)

    # ---- Conversation State Badge Logic ----
    state = "NO_COMMUNICATION"
    label = "🟢 No Prior Communication"

    if emails_sorted:
        last_email = emails_sorted[-1]["data"]
        body = (last_email.get("body") or "").lower()
        subject = (last_email.get("subject") or "").lower()
        text = body + " " + subject

        if any(k in text for k in ["rate increase", "market", "capacity", "decline"]):
            state = "CARRIER_CONSTRAINT"
            label = "🔴 Carrier Constraint / Market Issue"
        elif any(k in text for k in ["can we", "please", "request", "lower", "deductible"]):
            state = "CLIENT_REPLIED"
            label = "🟡 Client Replied – Broker Action Pending"
        else:
            state = "ACTIVE"
            label = "🟡 Active Conversation"

    return jsonify({
        "state": state,
        "label": label,
        "emails": [
            {
                "date": e["data"].get("date"),
                "subject": e["data"].get("subject"),
                "summary": summarize_email_body(e["data"].get("body"))
            }
            for e in emails_sorted
        ]
    })

# ==========================================

# ==========================================
# PASTE THIS ABOVE THE "if __name__" BLOCK
# ==========================================

@app.route("/api/calendar/events", methods=["POST"])
def add_calendar_event():
    try:
        data = request.json
        print(f"📥 Received Event Data: {data}")

        if not data or not data.get("date") or not data.get("title"):
            return jsonify({"error": "Title and Date are required"}), 400

        # FIX: Use Timestamp for a truly UNIQUE ID every time
        import time
        unique_id = f"evt-{int(time.time() * 1000)}"

        new_event = {
            "id": unique_id, # <--- UPDATED LINE
            "title": data["title"],
            "time": data.get("time", ""),
            "description": data.get("description", "")
        }

        # Save to Global Dictionary
        date_key = data["date"]
        if date_key not in calendar_events:
            calendar_events[date_key] = []
        
        calendar_events[date_key].append(new_event)
        
        return jsonify({"status": "success", "event": new_event})

    except Exception as e:
        print(f"❌ Error saving event: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/events/<date_str>/<event_id>", methods=["DELETE"])
def delete_calendar_event(date_str, event_id):
    try:
        if date_str in calendar_events:
            # Filter out the deleted event
            calendar_events[date_str] = [
                e for e in calendar_events[date_str] if e["id"] != event_id
            ]
        return jsonify({"status": "deleted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==========================================
# END OF PASTE
# ==========================================

if __name__ == '__main__':
    print("🚀 BROKER COPILOT AI SERVER STARTED")
    app.run(host="127.0.0.1", port=5050, debug=False)