try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

from io import BytesIO

import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI
from supabase import create_client
from difflib import get_close_matches
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import numpy as np

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except Exception:
    PROPHET_AVAILABLE = False

try:
    import shap
    SHAP_AVAILABLE = True
except Exception:
    SHAP_AVAILABLE = False


# =========================
# PAGE CONFIG
# =========================

st.set_page_config(
    page_title="AI-Powered Business Growth Platform",
    page_icon="🚀",
    layout="wide"
)


# =========================
# PRODUCT SETTINGS
# =========================

APP_NAME = "AI-Powered Business Growth Platform"
STORAGE_BUCKET = "user-files"

PLAN_LIMITS = {
    "starter": {
        "max_rows": 500,
        "forecasting": False,
        "ai_assistant": False,
        "shap": False,
    },
    "pro": {
        "max_rows": 5000,
        "forecasting": True,
        "ai_assistant": True,
        "shap": False,
    },
    "premium": {
        "max_rows": 50000,
        "forecasting": True,
        "ai_assistant": True,
        "shap": True,
    },
}


# =========================
# SUPABASE CLIENT
# =========================

try:
    supabase = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_ANON_KEY"]
    )
except Exception:
    supabase = None


# =========================
# HELPER FUNCTIONS
# =========================

def get_current_plan():
    return st.session_state.get("plan", "starter").lower()


def feature_allowed(feature_name):
    plan = get_current_plan()
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"]).get(feature_name, False)


def enforce_row_limit(df):
    plan = get_current_plan()
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS["starter"])["max_rows"]

    if len(df) > limit:
        st.warning(
            f"Your {plan.title()} plan allows up to {limit:,} rows. "
            f"Only the first {limit:,} rows are being analysed."
        )
        return df.head(limit)

    return df


def upgrade_button(plan_name):
    key = f"STRIPE_{plan_name.upper()}_LINK"
    link = st.secrets.get(key, "")

    if link:
        st.link_button(
            f"Upgrade to {plan_name.title()}",
            link,
            use_container_width=True
        )
    else:
        st.info(f"{plan_name.title()} payment link not added yet.")


# =========================
# LANDING PAGE + LOGIN
# =========================

def landing_page():
    st.markdown(f"# {APP_NAME}")
    st.markdown(
        "A SaaS-style analytics platform that helps small businesses turn sales data "
        "into KPIs, forecasts, growth opportunities, AI recommendations and executive reports."
    )

    st.markdown("### Pricing Plans")

    p1, p2, p3 = st.columns(3)

    with p1:
        st.markdown("#### Starter")
        st.markdown("### £9/month")
        st.markdown("- Up to 500 rows\n- Sales dashboard\n- Product insights\n- Download reports")
        upgrade_button("starter")

    with p2:
        st.markdown("#### Pro")
        st.markdown("### £19/month")
        st.markdown("- Up to 5,000 rows\n- Forecasting\n- AI Assistant\n- Executive reports")
        upgrade_button("pro")

    with p3:
        st.markdown("#### Premium")
        st.markdown("### £39/month")
        st.markdown("- Up to 50,000 rows\n- SHAP Explainability\n- Advanced insights\n- Premium analytics")
        upgrade_button("premium")

    st.markdown("---")


def get_user_plan(user_id):
    """Fetch the logged-in user's plan from Supabase profiles table."""
    try:
        result = (
            supabase
            .table("profiles")
            .select("plan")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if result.data and result.data.get("plan"):
            return result.data["plan"]

        return "starter"

    except Exception:
        return "starter"


def ensure_user_profile(user_id, business_name=""):
    """Create a starter profile for a new user if it does not already exist."""
    try:
        result = (
            supabase
            .table("profiles")
            .select("id, plan, business_name")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if result.data:
            return result.data

    except Exception:
        pass

    try:
        result = (
            supabase
            .table("profiles")
            .insert({
                "id": user_id,
                "plan": "starter",
                "business_name": business_name
            })
            .execute()
        )

        if result.data:
            return result.data[0]

    except Exception as e:
        st.warning("Profile could not be created automatically.")
        st.caption(str(e))

    return {"id": user_id, "plan": "starter", "business_name": business_name}


def set_logged_in_session(user, plan):
    """Save the logged-in user details in Streamlit session state."""
    st.session_state["logged_in"] = True
    st.session_state["user"] = user
    st.session_state["user_id"] = user.id
    st.session_state["email"] = user.email
    st.session_state["username"] = user.id
    st.session_state["role"] = "customer"
    st.session_state["plan"] = plan.lower()


def login():
    landing_page()

    if supabase is None:
        st.error("Supabase is not connected. Add SUPABASE_URL and SUPABASE_ANON_KEY in Streamlit Cloud secrets.")
        st.stop()

    dark_mode = st.toggle("🌙 Dark mode", value=False)

    if dark_mode:
        st.markdown("""
        <style>
        .stApp {
            background: #0f172a;
            color: white;
        }
        input {
            background: #1e293b !important;
            color: white !important;
        }
        </style>
        """, unsafe_allow_html=True)

    st.markdown("## 🔐 Secure Customer Login")

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown("""
        <div style="padding:40px;">
            <h2 style="color:#4f46e5;">Welcome to</h2>
            <h1 style="font-size:42px;">AI Business Growth Platform</h1>
            <p style="color:#6b7280;font-size:16px;">
                Turn your sales data into insights, forecasts, and AI-powered decisions.
            </p>
            <p style="color:#374151;font-size:17px;">📊 Real-time dashboards</p>
            <p style="color:#374151;font-size:17px;">📈 Revenue forecasting</p>
            <p style="color:#374151;font-size:17px;">🤖 AI-powered recommendations</p>
            <p style="color:#374151;font-size:17px;">📄 Executive reports</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        tab_login, tab_signup, tab_reset = st.tabs(["Login", "Sign Up", "Reset Password"])

        with tab_login:
            st.markdown("### Login to your account")

            email = st.text_input("Email address", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            st.checkbox("🔐 Remember me", key="remember_me")

            if st.button("Login", use_container_width=True):
                if not email or not password:
                    st.error("Please enter your email and password.")
                else:
                    try:
                        response = supabase.auth.sign_in_with_password({
                            "email": email.strip().lower(),
                            "password": password
                        })

                        user = response.user
                        ensure_user_profile(user.id)
                        plan = get_user_plan(user.id)
                        set_logged_in_session(user, plan)

                        st.success("Login successful.")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Login error: {e}")

        with tab_signup:
            st.markdown("### Create a new account")

            signup_email = st.text_input("Email address", key="signup_email")
            signup_password = st.text_input("Password", type="password", key="signup_password")
            business_name = st.text_input("Business name", key="signup_business_name")

            if st.button("Create Account", use_container_width=True):
                if not signup_email or not signup_password:
                    st.error("Please enter your email and password.")
                elif len(signup_password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    try:
                        response = supabase.auth.sign_up({
                            "email": signup_email.strip().lower(),
                            "password": signup_password
                        })

                        if response.user:
                            try:
                                ensure_user_profile(response.user.id, business_name)
                            except Exception as e:
                                st.warning("Account created, but profile was not created automatically.")
                                st.caption(str(e))

                            st.success("Account created. Please log in now.")

                    except Exception as e:
                        st.error("Could not create account.")
                        st.caption(str(e))

        with tab_reset:
            st.markdown("### Reset your password")

            reset_email = st.text_input("Registered email address", key="reset_email")

            if st.button("Send Password Reset Email", use_container_width=True):
                if not reset_email:
                    st.error("Please enter your email address.")
                else:
                    try:
                        supabase.auth.reset_password_email(reset_email.strip().lower())
                        st.success("Password reset email sent. Please check your inbox.")
                    except Exception as e:
                        st.error("Could not send password reset email.")
                        st.caption(str(e))


# =========================
# LOGIN CHECK
# =========================

if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login()
    st.stop()


# =========================
# OPENAI CLIENT
# =========================

api_key = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=api_key) if api_key else None


# =========================
# CSS
# =========================

st.markdown("""
<style>
.stApp { background: #f6f9ff; }
.block-container { padding-top: 2rem; padding-left: 2rem; padding-right: 2rem; }
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #111827 0%, #4f46e5 100%); }
section[data-testid="stSidebar"] * { color: white !important; }
.sidebar-logo { font-size: 26px; font-weight: 900; margin-bottom: 30px; line-height: 1.2; }
.nav-item { padding: 14px 16px; border-radius: 14px; margin-bottom: 10px; font-weight: 600; }
.nav-active { background: rgba(255,255,255,0.22); }
.hero { background: linear-gradient(135deg, #6d28d9, #0ea5e9); padding: 34px 38px; border-radius: 26px; color: white; box-shadow: 0 16px 36px rgba(79,70,229,0.25); margin-bottom: 24px; }
.hero h1 { color: white; font-size: 40px; margin: 0; }
.hero p { margin-top: 12px; font-size: 16px; color: #e0f2fe; }
.card { background: white; padding: 24px; border-radius: 22px; border: 1px solid #e5e7eb; box-shadow: 0 12px 30px rgba(15,23,42,0.06); margin-bottom: 24px; }
.upload-inner { border: 2px dashed #c4b5fd; border-radius: 18px; text-align: center; padding: 32px; background: #fbfaff; margin-bottom: 15px; }
.pill { display: inline-block; padding: 8px 13px; border-radius: 9px; border: 1px solid #c4b5fd; color: #5b21b6; margin: 4px; font-weight: 600; font-size: 13px; }
.metric-card { padding: 22px; border-radius: 20px; color: white; min-height: 155px; box-shadow: 0 15px 30px rgba(0,0,0,0.14); margin-bottom: 22px; }
.metric-title { font-size: 14px; font-weight: 700; opacity: 0.95; }
.metric-value { font-size: 28px; font-weight: 900; margin-top: 18px; word-break: break-word; }
.metric-sub { font-size: 13px; margin-top: 10px; opacity: 0.95; }
.insight { padding: 15px; border-radius: 14px; margin-bottom: 12px; border: 1px solid #e5e7eb; }
.rec-box { background: linear-gradient(135deg, #ecfdf5, #f0fdf4); padding: 24px; border-radius: 22px; border: 1px solid #bbf7d0; box-shadow: 0 12px 30px rgba(16,185,129,0.12); margin-bottom: 24px; }
.ai-response { background: #fbfaff; padding: 22px; border-radius: 18px; border: 1px solid #ddd6fe; margin-top: 18px; }
.tip { background: #eff6ff; padding: 16px; border-radius: 16px; border: 1px solid #bfdbfe; text-align: center; color: #1d4ed8; font-weight: 700; margin-top: 20px; margin-bottom: 20px; }
input { border-radius: 10px !important; border: 1px solid #d1d5db !important; padding: 10px !important; }
.stButton button { background: linear-gradient(135deg, #6366f1, #4f46e5) !important; color: white !important; border-radius: 10px !important; font-weight: 600 !important; height: 45px !important; border: none !important; }
.stButton button:hover { opacity: 0.92; transform: scale(1.01); transition: 0.2s; }
section[data-testid="stFileUploader"] label { display: none !important; }
section[data-testid="stFileUploader"] button { color: #111827 !important; background: white !important; border: 1px solid #d1d5db !important; border-radius: 10px !important; font-weight: 600 !important; }
button[data-baseweb="tab"] { font-weight: 700 !important; border-radius: 12px !important; }
</style>
""", unsafe_allow_html=True)


# =========================
# SIDEBAR
# =========================

with st.sidebar:
    st.markdown('<div class="sidebar-logo">Business<br>Growth AI</div>', unsafe_allow_html=True)
    st.markdown(f"**User:** {st.session_state.get('email', st.session_state.get('username', ''))}")
    st.markdown(f"**Plan:** {st.session_state['plan'].title()}")
    st.markdown(f"**Role:** {st.session_state['role'].title()}")
    st.markdown("---")
    st.markdown('<div class="nav-item nav-active">Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">Forecasting</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">SHAP Explainability</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">AI Assistant</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">Reports</div>', unsafe_allow_html=True)
    st.markdown("---")

    if st.session_state["plan"] == "starter":
        upgrade_button("pro")

    if st.session_state["plan"] in ["starter", "pro"]:
        upgrade_button("premium")

    if st.button("Logout"):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        st.session_state.clear()
        st.rerun()

    st.markdown("<br><small>© 2026 AI-Powered Business Growth Platform</small>", unsafe_allow_html=True)


# =========================
# HEADER
# =========================

st.markdown(f"""
<div style="color:#5b21b6;font-weight:800;">Welcome back!</div>
<div class="hero">
    <h1>{APP_NAME}</h1>
    <p>Upload sales data, analyse KPIs, forecast future revenue, detect growth products, explain sales drivers, and generate AI-powered business recommendations.</p>
</div>
""", unsafe_allow_html=True)


# =========================
# UPLOAD SECTION
# =========================

st.markdown('<div class="card">', unsafe_allow_html=True)
u1, u2 = st.columns([1, 1])

with u1:
    st.markdown("""
    <div class="upload-inner">
        <div style="font-size:46px;color:#6d28d9;">⬆️</div>
        <h3>Upload your sales data</h3>
        <p>Upload CSV or Excel file below</p>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload sales file",
        type=["csv", "xlsx"],
        label_visibility="collapsed",
        key="sales_file_upload"
    )

    if uploaded_file is not None:
        st.success(f"Selected file: {uploaded_file.name}")

with u2:
    st.markdown("""
    <h3 style="color:#5b21b6;">Required Data</h3>
    <span class="pill">Date</span>
    <span class="pill">Product</span>
    <span class="pill">Category</span>
    <span class="pill">Quantity</span>
    <span class="pill">Price</span>
    <br><br>
    <h3 style="color:#5b21b6;">Smart Column Detection</h3>
    <p>Accepts variations such as Sales, Revenue, Amount, Qty, Units, Order Date, Product Name and more.</p>
    <br>
    <h3 style="color:#5b21b6;">Secure Cloud Storage</h3>
    <p>Uploaded files are stored securely in Supabase Storage under your user account.</p>
    """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)


# =========================
# SUPABASE STORAGE FILE FUNCTIONS
# =========================

def save_uploaded_file(file):
    user_id = st.session_state["user_id"]
    safe_filename = file.name.replace("/", "_").replace("\\", "_")
    storage_path = f"{user_id}/{safe_filename}"
    file_bytes = file.getvalue()

    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(
            storage_path,
            file_bytes,
            {"content-type": file.type or "application/octet-stream", "upsert": "true"}
        )
    except Exception as e:
        error_text = str(e).lower()
        if "already exists" in error_text or "duplicate" in error_text:
            supabase.storage.from_(STORAGE_BUCKET).update(
                storage_path,
                file_bytes,
                {"content-type": file.type or "application/octet-stream"}
            )
        else:
            raise e

    return storage_path


def get_latest_user_file():
    user_id = st.session_state["user_id"]
    files = supabase.storage.from_(STORAGE_BUCKET).list(user_id)

    if not files:
        return None

    latest = sorted(
        files,
        key=lambda file: file.get("created_at", "") or file.get("updated_at", "") or file.get("name", ""),
        reverse=True
    )[0]

    return f"{user_id}/{latest['name']}"


def load_data(file):
    if file is not None:
        storage_path = save_uploaded_file(file)
        st.success("File uploaded and saved securely to Supabase Storage.")
    else:
        storage_path = get_latest_user_file()

        if storage_path:
            st.info("Using your previously uploaded file from Supabase Storage.")
        else:
            st.info("No file uploaded yet. Demo sample data is being used.")
            return pd.read_csv("sample_sales.csv")

    file_bytes = supabase.storage.from_(STORAGE_BUCKET).download(storage_path)
    file_buffer = BytesIO(file_bytes)

    if storage_path.lower().endswith(".csv"):
        return pd.read_csv(file_buffer)

    return pd.read_excel(file_buffer, engine="openpyxl")


def detect_and_clean_columns(df):
    original_columns = list(df.columns)
    clean_columns = [str(col).lower().strip().replace("_", " ") for col in original_columns]
    column_lookup = dict(zip(clean_columns, original_columns))

    required_columns = ["Date", "Product", "Category", "Quantity", "Price"]

    column_mapping = {
        "Date": ["date", "order date", "invoice date", "transaction date", "sale date", "purchase date", "created date"],
        "Product": ["product", "item", "product name", "item name", "description", "pizza type", "service", "menu item", "sku", "stock item"],
        "Category": ["category", "type", "department", "branch", "location", "store", "section", "group", "class", "product category"],
        "Quantity": ["quantity", "qty", "units", "items sold", "number sold", "order quantity", "sold quantity", "count"],
        "Price": ["price", "sales", "amount", "revenue", "total", "total sales", "sale amount", "order value", "value", "cost", "unit price"]
    }

    detected_columns = {}

    for standard_col, possible_names in column_mapping.items():
        match_found = None

        for name in possible_names:
            if name in clean_columns:
                match_found = name
                break

        if match_found is None:
            for col in clean_columns:
                if any(name in col or col in name for name in possible_names):
                    match_found = col
                    break

        if match_found is None:
            fuzzy_match = get_close_matches(standard_col.lower(), clean_columns, n=1, cutoff=0.55)
            if fuzzy_match:
                match_found = fuzzy_match[0]

        if match_found:
            detected_columns[standard_col] = column_lookup[match_found]

    missing = [col for col in required_columns if col not in detected_columns]

    if missing:
        st.error(f"Missing required columns: {', '.join(missing)}")
        st.write("Detected columns in your file:")
        st.write(original_columns)
        st.stop()

    df = df.rename(columns={
        detected_columns["Date"]: "Date",
        detected_columns["Product"]: "Product",
        detected_columns["Category"]: "Category",
        detected_columns["Quantity"]: "Quantity",
        detected_columns["Price"]: "Price"
    })

    df = df.loc[:, ~df.columns.duplicated()]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df = df.dropna(subset=["Date", "Quantity", "Price"])

    if df.empty:
        st.error("No valid data found after cleaning.")
        st.stop()

    df["Product"] = df["Product"].astype(str).str.strip()
    df["Category"] = df["Category"].astype(str).str.strip()
    df["Month"] = df["Date"].dt.to_period("M").dt.to_timestamp()
    df["Total_Sales"] = df["Quantity"] * df["Price"]

    return df, detected_columns


def metric(title, value, sub, gradient):
    st.markdown(f"""
    <div class="metric-card" style="background:{gradient};">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


def generate_pdf_report(report_summary, recommendation):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("AI-Powered Business Growth Report", styles["Title"]))
    story.append(Spacer(1, 16))
    story.append(Paragraph("Executive KPI Summary", styles["Heading2"]))
    story.append(Spacer(1, 8))

    table_data = [["Metric", "Value"]] + report_summary.values.tolist()
    table = Table(table_data, colWidths=[220, 260])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph("Business Recommendation", styles["Heading2"]))
    story.append(Paragraph(recommendation, styles["BodyText"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph("This report was generated by the AI-Powered Business Growth Platform.", styles["Italic"]))
    doc.build(story)
    buffer.seek(0)
    return buffer


# =========================
# LOAD DATA
# =========================

try:
    raw_df = load_data(uploaded_file)
    df, detected_columns = detect_and_clean_columns(raw_df)
    df = enforce_row_limit(df)
    st.success("Data loaded successfully and columns detected automatically.")
except Exception as e:
    st.error("Error loading file. Please check your file format or Supabase Storage policies.")
    st.caption(str(e))
    st.stop()


# =========================
# FILTERS
# =========================

st.markdown("### Filter Dashboard")
f1, f2, f3 = st.columns(3)

with f1:
    categories = sorted(df["Category"].dropna().unique())
    selected_categories = st.multiselect("Filter by Category", categories, default=categories)

with f2:
    products = sorted(df["Product"].dropna().unique())
    selected_products = st.multiselect("Filter by Product", products, default=products)

with f3:
    min_date = df["Date"].min().date()
    max_date = df["Date"].max().date()
    selected_date = st.date_input(
        "Filter by Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

if len(selected_date) == 2:
    start_date, end_date = selected_date
else:
    start_date, end_date = min_date, max_date

filtered_df = df[
    (df["Category"].isin(selected_categories)) &
    (df["Product"].isin(selected_products)) &
    (df["Date"].dt.date >= start_date) &
    (df["Date"].dt.date <= end_date)
]

if filtered_df.empty:
    st.warning("No data available for selected filters.")
    st.stop()


# =========================
# CALCULATIONS
# =========================

total_revenue = filtered_df["Total_Sales"].sum()
total_orders = len(filtered_df)
avg_order_value = filtered_df["Total_Sales"].mean()
product_revenue = filtered_df.groupby("Product")["Total_Sales"].sum()
category_revenue = filtered_df.groupby("Category")["Total_Sales"].sum()

best_product = product_revenue.idxmax()
lowest_product = product_revenue.idxmin()
top_category = category_revenue.idxmax()
monthly_sales = filtered_df.groupby("Month")["Total_Sales"].sum().sort_index()

growth = None
if len(monthly_sales) > 1 and monthly_sales.iloc[-2] != 0:
    growth = ((monthly_sales.iloc[-1] - monthly_sales.iloc[-2]) / monthly_sales.iloc[-2]) * 100

growth_text = f"{growth:.1f}% vs last month" if growth is not None else "Not enough monthly data"

monthly_product_sales = (
    filtered_df.groupby(["Product", "Month"])["Total_Sales"]
    .sum()
    .reset_index()
    .sort_values(["Product", "Month"])
)

growth_products = []
for product in monthly_product_sales["Product"].unique():
    product_df = monthly_product_sales[monthly_product_sales["Product"] == product]

    if len(product_df) >= 2 and product_df["Total_Sales"].iloc[-2] != 0:
        product_growth = (
            (product_df["Total_Sales"].iloc[-1] - product_df["Total_Sales"].iloc[-2])
            / product_df["Total_Sales"].iloc[-2]
        ) * 100
        growth_products.append((product, product_growth))

if growth_products:
    top_growth_product, top_growth_rate = max(growth_products, key=lambda x: x[1])
    top_growth_text = f"{top_growth_product} grew by {top_growth_rate:.1f}%"
else:
    top_growth_product = "Not enough data"
    top_growth_text = "Need at least 2 months of product data"

recommendation = (
    f"Consider increasing stock or marketing for high-performing products such as {best_product}. "
    f"Your strongest category is {top_category}, so this area may offer the best growth opportunity. "
    f"Review {lowest_product}, because it is currently the lowest-performing product. "
    f"Also monitor {top_growth_product}, because it may become a future high-value product."
)

report_summary = pd.DataFrame({
    "Metric": [
        "Total Revenue", "Total Orders", "Average Order Value", "Best Product",
        "Lowest Product", "Top Category", "Top Growth Product", "Sales Growth", "Current Plan"
    ],
    "Value": [
        f"£{total_revenue:,.2f}", total_orders, f"£{avg_order_value:,.2f}",
        best_product, lowest_product, top_category, top_growth_text, growth_text,
        st.session_state["plan"].title()
    ]
})


# =========================
# TABS
# =========================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Dashboard", "Forecasting", "AI Insights", "Reports", "Data Preview"
])


# =========================
# TAB 1: DASHBOARD
# =========================

with tab1:
    st.markdown("### Key Business Performance")
    st.caption("These KPIs summarise revenue, customer activity, average order value, product performance and growth momentum.")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        metric("Total Revenue", f"£{total_revenue:,.2f}", growth_text, "linear-gradient(135deg,#7c3aed,#4f46e5)")
    with c2:
        metric("Total Orders", f"{total_orders:,}", "Completed sales records", "linear-gradient(135deg,#0ea5e9,#2563eb)")
    with c3:
        metric("Average Order Value", f"£{avg_order_value:,.2f}", "Revenue per order", "linear-gradient(135deg,#34d399,#059669)")
    with c4:
        metric("Best Product", best_product, "Highest revenue product", "linear-gradient(135deg,#f59e0b,#f97316)")
    with c5:
        metric("Top Growth Product", top_growth_product, top_growth_text, "linear-gradient(135deg,#ec4899,#be185d)")

    left, right = st.columns(2)

    with left:
        st.markdown("### Sales Performance Over Time")
        monthly_chart = filtered_df.groupby("Month", as_index=False)["Total_Sales"].sum().sort_values("Month")
        fig = px.line(monthly_chart, x="Month", y="Total_Sales", markers=True)
        fig.update_traces(line=dict(width=4, color="#6d28d9"), marker=dict(size=9, color="#6d28d9"))
        fig.update_layout(height=420, template="plotly_white", xaxis_title="Month", yaxis_title="Revenue (£)", showlegend=False, hovermode="x unified")
        fig.update_yaxes(tickprefix="£", separatethousands=True)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("### Top 10 Products by Revenue")
        product_sales = filtered_df.groupby("Product", as_index=False)["Total_Sales"].sum().sort_values("Total_Sales", ascending=False).head(10)
        fig = px.bar(product_sales, x="Total_Sales", y="Product", orientation="h")
        fig.update_traces(marker_color="#2563eb")
        fig.update_layout(height=420, template="plotly_white", xaxis_title="Revenue (£)", yaxis_title="", showlegend=False)
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(tickprefix="£", separatethousands=True)
        st.plotly_chart(fig, use_container_width=True)

    bottom_left, bottom_right = st.columns(2)

    with bottom_left:
        st.markdown("### Revenue by Category")
        category_sales = filtered_df.groupby("Category", as_index=False)["Total_Sales"].sum()
        fig = px.pie(category_sales, names="Category", values="Total_Sales", hole=0.50)
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)

    with bottom_right:
        st.markdown("### Product Growth Ranking")
        if growth_products:
            growth_df = pd.DataFrame(growth_products, columns=["Product", "Growth_Rate"])
            growth_df = growth_df.sort_values("Growth_Rate", ascending=False).head(10)
            fig = px.bar(growth_df, x="Growth_Rate", y="Product", orientation="h")
            fig.update_traces(marker_color="#be185d")
            fig.update_layout(height=420, template="plotly_white", xaxis_title="Growth Rate (%)", yaxis_title="")
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough monthly product data to calculate growth ranking.")

    st.markdown("### Business Insights")
    st.markdown(f"""
    <div class="insight" style="background:#faf5ff;border-color:#ddd6fe;"><strong style="color:#6d28d9;">Highest Revenue Category</strong><br>{top_category} is currently generating the highest revenue.</div>
    <div class="insight" style="background:#ecfdf5;border-color:#bbf7d0;"><strong style="color:#059669;">Top Performing Product</strong><br>{best_product} is the strongest product by total revenue.</div>
    <div class="insight" style="background:#fff7ed;border-color:#fed7aa;"><strong style="color:#ea580c;">Product Requiring Attention</strong><br>{lowest_product} is the lowest performing product.</div>
    <div class="insight" style="background:#fdf2f8;border-color:#fbcfe8;"><strong style="color:#be185d;">Top Growth Product</strong><br>{top_growth_text}</div>
    <div class="insight" style="background:#eff6ff;border-color:#bfdbfe;"><strong style="color:#2563eb;">Sales Growth</strong><br>{growth_text}</div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="rec-box">
        <h3 style="margin-top:0;color:#065f46;">Business Recommendation</h3>
        <p>{recommendation}</p>
    </div>
    """, unsafe_allow_html=True)


# =========================
# TAB 2: FORECASTING
# =========================

with tab2:
    st.markdown("### Revenue Forecasting")

    if not feature_allowed("forecasting"):
        st.warning("Unlock Forecasting to predict future revenue and plan business growth.")
        upgrade_button("pro")
    else:
        forecast_method = st.radio("Choose forecasting method", ["Prophet Forecast", "Simple Linear Forecast"], horizontal=True)

        if len(monthly_sales) >= 3:
            forecast_df = monthly_sales.reset_index()
            forecast_df.columns = ["Month", "Total_Sales"]

            if forecast_method == "Prophet Forecast" and PROPHET_AVAILABLE:
                prophet_df = forecast_df.rename(columns={"Month": "ds", "Total_Sales": "y"})
                model = Prophet()
                model.fit(prophet_df)
                future = model.make_future_dataframe(periods=3, freq="MS")
                forecast = model.predict(future)

                forecast_display = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(3)
                forecast_display = forecast_display.rename(columns={
                    "ds": "Month", "yhat": "Forecast Sales", "yhat_lower": "Lower Estimate", "yhat_upper": "Upper Estimate"
                })
                plot_df = forecast[["ds", "yhat"]].rename(columns={"ds": "Month", "yhat": "Sales"})
                fig = px.line(plot_df, x="Month", y="Sales", markers=True)
                fig.update_traces(line=dict(width=4, color="#10b981"), marker=dict(size=9, color="#10b981"))
                fig.update_layout(height=420, template="plotly_white", yaxis_title="Revenue (£)", xaxis_title="Month")
                fig.update_yaxes(tickprefix="£", separatethousands=True)
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(forecast_display, use_container_width=True)
            else:
                if forecast_method == "Prophet Forecast" and not PROPHET_AVAILABLE:
                    st.warning("Prophet is not installed. Showing simple linear forecast instead.")

                forecast_df["t"] = np.arange(len(forecast_df))
                model = LinearRegression()
                model.fit(forecast_df[["t"]], forecast_df["Total_Sales"])
                future_t = np.arange(len(forecast_df), len(forecast_df) + 3)
                future_predictions = model.predict(future_t.reshape(-1, 1))
                last_month = forecast_df["Month"].max()
                future_months = pd.date_range(start=last_month + pd.DateOffset(months=1), periods=3, freq="MS")
                future_df = pd.DataFrame({"Month": future_months, "Forecast Sales": future_predictions})

                historical_plot = forecast_df[["Month", "Total_Sales"]].rename(columns={"Total_Sales": "Sales"})
                future_plot = future_df.rename(columns={"Forecast Sales": "Sales"})
                forecast_chart = pd.concat([historical_plot, future_plot])
                fig = px.line(forecast_chart, x="Month", y="Sales", markers=True)
                fig.update_traces(line=dict(width=4, color="#10b981"), marker=dict(size=9, color="#10b981"))
                fig.update_layout(height=420, template="plotly_white", yaxis_title="Revenue (£)", xaxis_title="Month")
                fig.update_yaxes(tickprefix="£", separatethousands=True)
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(future_df, use_container_width=True)
        else:
            st.info("At least 3 months of data are needed to generate a forecast.")


# =========================
# TAB 3: AI INSIGHTS
# =========================

with tab3:
    st.markdown("### SHAP Explainability")

    if not feature_allowed("shap"):
        st.warning("Unlock SHAP Explainability to understand the biggest drivers behind sales performance.")
        upgrade_button("premium")
    else:
        st.caption("This explains which factors are most important in predicting sales performance.")
        try:
            shap_df = filtered_df[["Product", "Category", "Quantity", "Price", "Total_Sales"]].copy()
            encoded_df = pd.get_dummies(shap_df[["Product", "Category", "Quantity", "Price"]], drop_first=True)
            target = shap_df["Total_Sales"]

            if len(encoded_df) >= 10 and SHAP_AVAILABLE:
                rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
                rf_model.fit(encoded_df, target)
                explainer = shap.TreeExplainer(rf_model)
                shap_values = explainer.shap_values(encoded_df)
                shap_importance = pd.DataFrame({
                    "Feature": encoded_df.columns,
                    "Importance": np.abs(shap_values).mean(axis=0)
                }).sort_values("Importance", ascending=False).head(10)
                fig = px.bar(shap_importance, x="Importance", y="Feature", orientation="h")
                fig.update_traces(marker_color="#7c3aed")
                fig.update_layout(height=420, template="plotly_white", xaxis_title="Average SHAP Importance", yaxis_title="")
                fig.update_yaxes(autorange="reversed")
                st.plotly_chart(fig, use_container_width=True)
                top_driver = shap_importance.iloc[0]["Feature"]
                st.success(f"Top sales driver detected: {top_driver}")
            elif not SHAP_AVAILABLE:
                st.warning("SHAP is not installed. Add shap to requirements.txt and redeploy.")
            else:
                st.info("Need at least 10 records to generate SHAP explainability.")
        except Exception as e:
            st.warning("SHAP explainability could not be generated for this dataset.")
            st.caption(str(e))

    st.markdown("## AI Business Assistant")

    if not feature_allowed("ai_assistant"):
        st.warning("Unlock AI Assistant to get personalised business recommendations from your sales data.")
        upgrade_button("pro")
    else:
        st.markdown("Ask a question about your business data.")
        with st.form("ai_form"):
            user_question = st.text_input("Question", placeholder="Example: How can I improve my sales next month?", label_visibility="collapsed")
            ask_clicked = st.form_submit_button("Ask AI Assistant")

        if ask_clicked and user_question:
            if client is None:
                st.error("OpenAI API key is missing. Add OPENAI_API_KEY in Streamlit Cloud secrets.")
            else:
                business_summary = f"""
                Total Revenue: £{total_revenue:,.2f}
                Total Orders: {total_orders}
                Average Order Value: £{avg_order_value:,.2f}
                Best Product: {best_product}
                Lowest Product: {lowest_product}
                Top Category: {top_category}
                Top Growth Product: {top_growth_text}
                Sales Growth: {growth_text}
                Recommendation: {recommendation}
                """
                prompt = f"""
                You are a professional business analyst for a small business owner.

                Business summary:
                {business_summary}

                User question:
                {user_question}

                Give a clear, practical, easy-to-understand answer with 3 to 5 actionable recommendations.
                """
                try:
                    with st.spinner("Analysing business data..."):
                        response = client.chat.completions.create(
                            model="gpt-4.1-mini",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.4
                        )
                        answer = response.choices[0].message.content
                    st.markdown(f"""
                    <div class="ai-response">
                        <strong>AI Response:</strong><br><br>
                        {answer}
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error("AI service error. Please check your OpenAI API key or billing.")
                    st.caption(str(e))


# =========================
# TAB 4: REPORTS
# =========================

with tab4:
    st.markdown("### Export Reports")
    cleaned_csv = filtered_df.to_csv(index=False).encode("utf-8")
    summary_csv = report_summary.to_csv(index=False).encode("utf-8")
    d1, d2, d3 = st.columns(3)

    with d1:
        st.download_button("Download Cleaned Data", data=cleaned_csv, file_name="cleaned_sales_data.csv", mime="text/csv")
    with d2:
        st.download_button("Download Executive CSV", data=summary_csv, file_name="executive_sales_report.csv", mime="text/csv")
    with d3:
        if REPORTLAB_AVAILABLE:
            pdf_report = generate_pdf_report(report_summary, recommendation)
            st.download_button("Download PDF Report", data=pdf_report, file_name="business_growth_report.pdf", mime="application/pdf")
        else:
            st.warning("PDF export is unavailable because reportlab is not installed.")

    st.markdown("### AI Executive Summary")

    if not feature_allowed("ai_assistant"):
        st.warning("AI Executive Summary is available on Pro and Premium plans.")
        upgrade_button("pro")
    else:
        if st.button("Generate Executive Summary"):
            if client is None:
                st.error("OpenAI API key is missing. Add OPENAI_API_KEY in Streamlit Cloud secrets.")
            else:
                summary_prompt = f"""
                You are a professional business analyst.

                Summarise this business performance in clear, simple business language.

                Total Revenue: £{total_revenue:,.2f}
                Total Orders: {total_orders}
                Average Order Value: £{avg_order_value:,.2f}
                Best Product: {best_product}
                Lowest Product: {lowest_product}
                Top Category: {top_category}
                Top Growth Product: {top_growth_text}
                Sales Growth: {growth_text}

                Give:
                1. 5 key insights
                2. 3 recommendations
                3. 1 risk to watch
                """
                try:
                    with st.spinner("Generating executive summary..."):
                        response = client.chat.completions.create(
                            model="gpt-4.1-mini",
                            messages=[{"role": "user", "content": summary_prompt}],
                            temperature=0.4
                        )
                    st.markdown(f"""
                    <div class="ai-response">
                        <strong>Executive Summary:</strong><br><br>
                        {response.choices[0].message.content}
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error("AI service error. Please check your OpenAI API key.")
                    st.caption(str(e))


# =========================
# TAB 5: DATA PREVIEW
# =========================

with tab5:
    st.markdown("""
    <div class="tip">
        Tip: Keep sales data updated regularly to improve forecasting, insights and AI recommendations.
    </div>
    """, unsafe_allow_html=True)

    with st.expander("View Cleaned Data Preview"):
        st.dataframe(filtered_df, use_container_width=True)

    with st.expander("View Detected Column Mapping"):
        st.write(detected_columns)

    with st.expander("View Executive Report Summary"):
        st.dataframe(report_summary, use_container_width=True)
