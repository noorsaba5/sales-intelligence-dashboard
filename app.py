from io import BytesIO
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from difflib import get_close_matches
from openai import OpenAI
from sklearn.linear_model import LinearRegression
from supabase import create_client

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# =========================
# APP CONFIG
# =========================

st.set_page_config(
    page_title="AI-Powered Business Growth Platform",
    page_icon="🚀",
    layout="wide",
)

APP_NAME = "AI-Powered Business Growth Platform"
STORAGE_BUCKET = "user-files"

# Keep these names until payment is fully tested. Later you can rename starter -> free.
PLAN_LIMITS = {
    "starter": {"rows": 500, "forecasting": False, "ai": False, "shap": False},
    "pro": {"rows": 5000, "forecasting": True, "ai": True, "shap": False},
    "premium": {"rows": 50000, "forecasting": True, "ai": True, "shap": True},
}

PRICING = {
    "starter": {
        "price": "Free",
        "features": ["Up to 500 rows", "Dashboard", "Product insights", "CSV/PDF reports"],
    },
    "pro": {
        "price": "£19/month",
        "features": ["Up to 5,000 rows", "Forecasting", "AI Assistant", "Executive summaries"],
    },
    "premium": {
        "price": "£39/month",
        "features": ["Up to 50,000 rows", "SHAP explainability", "Advanced analytics", "Premium insights"],
    },
}

# =========================
# BASIC STYLES
# =========================

st.markdown(
    """
<style>
.stApp { background: #f6f9ff; }
.block-container { padding-top: 2rem; padding-left: 2rem; padding-right: 2rem; }
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #111827 0%, #4f46e5 100%); }
section[data-testid="stSidebar"] * { color: white !important; }
.hero { background: linear-gradient(135deg, #6d28d9, #0ea5e9); padding: 30px 36px; border-radius: 24px; color: white; box-shadow: 0 14px 30px rgba(79,70,229,0.25); margin-bottom: 24px; }
.hero h1 { color: white; font-size: 38px; margin: 0; }
.hero p { color: #e0f2fe; }
.card { background: white; padding: 24px; border-radius: 22px; border: 1px solid #e5e7eb; box-shadow: 0 12px 30px rgba(15,23,42,0.06); margin-bottom: 24px; }
.upload-inner { border: 2px dashed #c4b5fd; border-radius: 18px; text-align: center; padding: 32px; background: #fbfaff; margin-bottom: 15px; }
.pill { display: inline-block; padding: 8px 13px; border-radius: 9px; border: 1px solid #c4b5fd; color: #5b21b6; margin: 4px; font-weight: 600; font-size: 13px; }
.metric-card { padding: 20px; border-radius: 18px; color: white; min-height: 140px; box-shadow: 0 12px 25px rgba(0,0,0,0.14); margin-bottom: 18px; }
.metric-title { font-size: 14px; font-weight: 700; opacity: 0.95; }
.metric-value { font-size: 26px; font-weight: 900; margin-top: 14px; word-break: break-word; }
.metric-sub { font-size: 13px; margin-top: 8px; opacity: 0.95; }
.insight { padding: 15px; border-radius: 14px; margin-bottom: 12px; border: 1px solid #e5e7eb; }
.rec-box { background: linear-gradient(135deg, #ecfdf5, #f0fdf4); padding: 22px; border-radius: 20px; border: 1px solid #bbf7d0; box-shadow: 0 12px 30px rgba(16,185,129,0.12); margin-bottom: 24px; }
.ai-response { background: #fbfaff; padding: 22px; border-radius: 18px; border: 1px solid #ddd6fe; margin-top: 18px; }
.stButton button { background: linear-gradient(135deg, #6366f1, #4f46e5) !important; color: white !important; border-radius: 10px !important; font-weight: 600 !important; min-height: 42px !important; border: none !important; }
section[data-testid="stFileUploader"] label { display: none !important; }
/* Sidebar payment/link buttons: keep text visible and buttons clickable */
section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a {
    background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
    color: white !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    min-height: 42px !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    text-decoration: none !important;
}
section[data-testid="stSidebar"] div[data-testid="stLinkButton"] a * { color: white !important; }
section[data-testid="stSidebar"] .stButton button {
    background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
    color: white !important;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================
# CONNECTIONS
# =========================

def debug_enabled() -> bool:
    try:
        return bool(st.secrets.get("DEBUG_MODE", False))
    except Exception:
        return False


def log_error(context: str, error: Exception):
    print(f"[ERROR] {context}: {error}")


def show_error(message: str, context: str, error: Exception):
    log_error(context, error)
    st.error(message)
    if debug_enabled():
        st.caption(f"Debug detail: {error}")


try:
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])
    supabase_admin = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SERVICE_ROLE_KEY"])
except Exception as e:
    supabase = None
    supabase_admin = None
    st.error("Supabase connection failed. Check Streamlit secrets.")
    if debug_enabled():
        st.caption(str(e))

api_key = st.secrets.get("OPENAI_API_KEY", "")
client = OpenAI(api_key=api_key) if api_key else None

# =========================
# AUTH + PLAN HELPERS
# =========================

def current_plan() -> str:
    return st.session_state.get("plan", "starter").lower()


def feature_allowed(feature: str) -> bool:
    return bool(PLAN_LIMITS.get(current_plan(), PLAN_LIMITS["starter"]).get(feature, False))


def get_user_plan(user_id: str) -> str:
    try:
        result = supabase.table("profiles").select("plan").eq("id", user_id).single().execute()
        if result.data and result.data.get("plan"):
            return result.data["plan"].lower()
    except Exception:
        pass
    return "starter"


def ensure_user_profile(user_id: str, business_name: str = "", email: str = ""):
    try:
        existing = supabase.table("profiles").select("id, plan").eq("id", user_id).single().execute()
        if existing.data:
            return existing.data
    except Exception:
        pass

    payload = {"id": user_id, "plan": "starter", "business_name": business_name}
    if email:
        payload["email"] = email

    try:
        created = supabase.table("profiles").insert(payload).execute()
        if created.data:
            return created.data[0]
    except Exception as e:
        log_error("ensure_user_profile", e)

    return payload


def set_login_session(user):
    ensure_user_profile(user.id, email=user.email)
    st.session_state["logged_in"] = True
    st.session_state["user"] = user
    st.session_state["user_id"] = user.id
    st.session_state["email"] = user.email
    st.session_state["role"] = "customer"
    st.session_state["plan"] = get_user_plan(user.id)


def refresh_plan() -> str:
    """Force-read the latest plan from Supabase and update the current Streamlit session."""

    user_id = st.session_state.get("user_id")

    if not user_id:
        return st.session_state.get("plan", "starter")

    try:
        new_plan = get_user_plan(user_id)

        if new_plan:
            st.session_state["plan"] = new_plan
            return new_plan

    except Exception as e:
        st.error(f"Failed to refresh plan: {e}")

    return st.session_state.get("plan", "starter")

def logout():
    try:
        if supabase:
            supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.clear()
    st.session_state["logged_in"] = False
    st.rerun()


def upgrade_button(plan_name: str):
    """Render a Stripe Payment Link button for Pro or Premium.

    Required Streamlit secrets:
    STRIPE_PRO_LINK = "https://buy.stripe.com/..."
    STRIPE_PREMIUM_LINK = "https://buy.stripe.com/..."

    client_reference_id is added so the webhook can update the correct Supabase user.
    """
    plan_name = plan_name.lower().strip()
    key = f"STRIPE_{plan_name.upper()}_LINK"
    link = st.secrets.get(key, "")

    if not link:
        st.info(f"{plan_name.title()} payment link is missing. Add {key} to Streamlit secrets.")
        return

    user_id = st.session_state.get("user_id")
    if not user_id:
        st.info("Log in first to upgrade.")
        return

    separator = "&" if "?" in link else "?"
    checkout_link = f"{link}{separator}{urlencode({'client_reference_id': user_id})}"
    st.link_button(f"Upgrade to {plan_name.title()}", checkout_link, use_container_width=True)


def require_upgrade(feature_title: str, plan_name: str):
    st.warning(f"{feature_title} is available on the {plan_name.title()} plan.")
    if plan_name == "pro":
        upgrade_button("pro")
        upgrade_button("premium")
    else:
        upgrade_button("premium")

# =========================
# LOGIN PAGE
# =========================

def landing_page():
    st.markdown(f"# {APP_NAME}")
    st.write("Turn sales data into KPIs, forecasts, AI recommendations and executive reports.")
    p1, p2, p3 = st.columns(3)
    with p1:
        st.markdown("### Starter")
        st.markdown("## Free")
        st.write("Basic dashboards and reports.")
    with p2:
        st.markdown("### Pro")
        st.markdown("## £19/month")
        st.write("Forecasting and AI assistant.")
    with p3:
        st.markdown("### Premium")
        st.markdown("## £39/month")
        st.write("Advanced analytics and SHAP explainability.")
    st.markdown("---")


def login_page():
    landing_page()
    if supabase is None:
        st.stop()

    st.markdown("## 🔐 Secure Customer Login")
    left, right = st.columns([1.1, 1])

    with left:
        st.markdown("## Welcome to")
        st.markdown("# AI Business Growth Platform")
        st.write("📊 Real-time dashboards")
        st.write("📈 Revenue forecasting")
        st.write("🤖 AI-powered recommendations")
        st.write("📄 Executive reports")

    with right:
        tab_login, tab_signup, tab_reset = st.tabs(["Login", "Sign Up", "Reset Password"])

        with tab_login:
            email = st.text_input("Email address", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Login", use_container_width=True):
                if not email or not password:
                    st.error("Please enter your email and password.")
                else:
                    try:
                        response = supabase.auth.sign_in_with_password({"email": email.strip().lower(), "password": password})
                        set_login_session(response.user)
                        st.success("Login successful.")
                        st.rerun()
                    except Exception as e:
                        show_error("We couldn't log you in. Check your email and password.", "login", e)

        with tab_signup:
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
                        response = supabase.auth.sign_up({"email": signup_email.strip().lower(), "password": signup_password})
                        if response.user:
                            ensure_user_profile(response.user.id, business_name, response.user.email)
                            st.success("Account created. Please log in now.")
                        else:
                            st.info("Check your email to confirm your account, then log in.")
                    except Exception as e:
                        msg = str(e).lower()
                        if "already" in msg or "registered" in msg:
                            st.error("This email is already registered. Please use Login instead.")
                        else:
                            show_error("We couldn't create your account. Please try again.", "signup", e)

        with tab_reset:
            reset_email = st.text_input("Registered email address", key="reset_email")
            if st.button("Send Password Reset Email", use_container_width=True):
                try:
                    supabase.auth.reset_password_for_email(reset_email.strip().lower())
                    st.success("Password reset email sent.")
                except Exception as e:
                    show_error("We couldn't send the reset email.", "password reset", e)


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_page()
    st.stop()

# =========================
# SIDEBAR - REAL NAVIGATION
# =========================

with st.sidebar:
    st.markdown("## Business Growth AI")
    st.markdown(f"**User:** {st.session_state.get('email', '')}")
    st.markdown(f"**Plan:** {current_plan().title()}")

    if st.button("Refresh Plan", use_container_width=True):
        new_plan = refresh_plan()
        st.success(f"Current Plan: {new_plan.title()}")

    st.markdown("---")
    page = st.radio(
        "Navigation",
        ["Dashboard", "Forecasting", "AI Assistant", "Reports", "Data Preview", "Pricing", "Account"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("### Upgrade")
    if current_plan() == "starter":
        upgrade_button("pro")
        upgrade_button("premium")
    elif current_plan() == "pro":
        upgrade_button("premium")
    else:
        st.success("Premium active")

    st.markdown("---")
    if st.button("Logout / Switch Account", use_container_width=True):
        logout()

# =========================
# DATA LOADING
# =========================

def demo_data() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2026-01-01", periods=180, freq="D")
    products = ["Latte", "Cappuccino", "Americano", "Mocha", "Flat White", "Tea"]
    categories = ["Coffee", "Coffee", "Coffee", "Coffee", "Coffee", "Tea"]
    prices = {"Latte": 3.5, "Cappuccino": 3.8, "Americano": 2.9, "Mocha": 4.2, "Flat White": 3.7, "Tea": 2.5}
    rows = []
    for i, date in enumerate(dates):
        boost = 1.25 if date.dayofweek in [5, 6] else 1.0
        trend = 1 + i / len(dates) * 0.25
        for product, category in zip(products, categories):
            qty = int(max(1, rng.normal(18 * boost * trend, 5)))
            rows.append({"Date": date, "Product": product, "Category": category, "Quantity": qty, "Price": prices[product], "Cost": round(prices[product] * 0.45, 2)})
    return pd.DataFrame(rows)


def save_uploaded_file(file) -> str:
    user_id = st.session_state["user_id"]
    safe_name = file.name.replace("/", "_").replace("\\", "_")
    path = f"{user_id}/{safe_name}"
    data = file.getvalue()
    try:
        supabase_admin.storage.from_(STORAGE_BUCKET).upload(path, data, {"content-type": file.type or "application/octet-stream", "upsert": "true"})
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            supabase_admin.storage.from_(STORAGE_BUCKET).update(path, data, {"content-type": file.type or "application/octet-stream"})
        else:
            raise
    return path


def load_uploaded_or_demo(file):
    if file is None:
        st.info("Demo data is being displayed. Upload your own file to analyse your business.")
        return demo_data(), True

    path = save_uploaded_file(file)
    st.success("File uploaded and saved securely to Supabase Storage.")
    downloaded = supabase_admin.storage.from_(STORAGE_BUCKET).download(path)
    buffer = BytesIO(downloaded)
    if path.lower().endswith(".csv"):
        return pd.read_csv(buffer), False
    return pd.read_excel(buffer, engine="openpyxl"), False


def clean_columns(df: pd.DataFrame):
    original = list(df.columns)
    clean = [str(c).lower().strip().replace("_", " ") for c in original]
    lookup = dict(zip(clean, original))
    mapping = {
        "Date": ["date", "order date", "invoice date", "transaction date", "sale date", "created date"],
        "Product": ["product", "item", "product name", "item name", "description", "sku", "menu item"],
        "Category": ["category", "type", "department", "section", "group", "product category"],
        "Quantity": ["quantity", "qty", "units", "items sold", "sold quantity", "count"],
        "Price": ["price", "unit price", "selling price", "item price"],
        "Revenue": ["sales", "amount", "revenue", "total", "total sales", "sale amount", "order value", "value"],
        "Cost": ["cost", "unit cost", "cogs", "cost of goods", "cost price", "purchase price"],
    }
    detected = {}
    for standard, names in mapping.items():
        found = None
        for name in names:
            if name in clean:
                found = name
                break
        if not found:
            for col in clean:
                if any(name in col or col in name for name in names):
                    found = col
                    break
        if not found:
            fuzzy = get_close_matches(standard.lower(), clean, n=1, cutoff=0.55)
            if fuzzy:
                found = fuzzy[0]
        if found:
            detected[standard] = lookup[found]

    missing = [c for c in ["Date", "Product", "Category", "Quantity"] if c not in detected]
    if "Price" not in detected and "Revenue" not in detected:
        missing.append("Price or Revenue")
    if missing:
        st.error(f"Missing required columns: {', '.join(missing)}")
        st.write("Detected columns:", original)
        st.stop()

    rename = {detected["Date"]: "Date", detected["Product"]: "Product", detected["Category"]: "Category", detected["Quantity"]: "Quantity"}
    if "Price" in detected:
        rename[detected["Price"]] = "Price"
    if "Revenue" in detected and "Price" not in detected:
        rename[detected["Revenue"]] = "Revenue"
    if "Cost" in detected:
        rename[detected["Cost"]] = "Cost"

    df = df.rename(columns=rename).loc[:, ~df.rename(columns=rename).columns.duplicated()]
    before = len(df)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True)
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    required = ["Date", "Quantity"]
    if "Price" in df.columns:
        df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
        required.append("Price")
    if "Revenue" in df.columns:
        df["Revenue"] = pd.to_numeric(df["Revenue"], errors="coerce")
        required.append("Revenue")
    if "Cost" in df.columns:
        df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce")

    df = df.dropna(subset=required)
    dropped = before - len(df)
    if df.empty:
        st.error("No valid data found after cleaning.")
        st.stop()

    df["Product"] = df["Product"].astype(str).str.strip()
    df["Category"] = df["Category"].astype(str).str.strip()
    df["Month"] = df["Date"].dt.to_period("M").dt.to_timestamp()
    if "Revenue" in df.columns and "Price" not in df.columns:
        df["Total_Sales"] = df["Revenue"]
        df["Price"] = df["Total_Sales"] / df["Quantity"].replace(0, np.nan)
    else:
        df["Total_Sales"] = df["Quantity"] * df["Price"]
    if "Cost" in df.columns:
        df["Total_Cost"] = df["Quantity"] * df["Cost"]
        df["Profit"] = df["Total_Sales"] - df["Total_Cost"]
    return df, detected, dropped


def enforce_row_limit(df: pd.DataFrame) -> pd.DataFrame:
    limit = PLAN_LIMITS.get(current_plan(), PLAN_LIMITS["starter"])["rows"]
    if len(df) > limit:
        st.warning(f"Your {current_plan().title()} plan allows up to {limit:,} rows. Only the first {limit:,} rows are being analysed.")
        return df.head(limit)
    return df

# =========================
# HEADER + UPLOAD
# =========================

st.markdown(f"""
<div class="hero">
    <h1>{APP_NAME}</h1>
    <p>Upload sales data, analyse KPIs, forecast revenue and generate AI-powered business recommendations.</p>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="card">', unsafe_allow_html=True)
up_col, req_col = st.columns([1, 1])
with up_col:
    st.markdown("""
    <div class="upload-inner">
        <div style="font-size:46px;color:#6d28d9;">⬆️</div>
        <h3>Upload your sales data</h3>
        <p>Upload CSV or Excel file below</p>
    </div>
    """, unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload sales file", type=["csv", "xlsx"], label_visibility="collapsed")
    if uploaded_file:
        st.success(f"Selected file: {uploaded_file.name}")
with req_col:
    st.markdown("""
    <h3 style="color:#5b21b6;">Required Data</h3>
    <span class="pill">Date</span><span class="pill">Product</span><span class="pill">Category</span><span class="pill">Quantity</span><span class="pill">Price or Revenue</span>
    <br><br><h3 style="color:#5b21b6;">Smart Column Detection</h3>
    <p>Accepts variations such as Sales, Revenue, Amount, Qty, Units, Order Date and Product Name.</p>
    """, unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

try:
    raw_df, using_demo = load_uploaded_or_demo(uploaded_file)
    df, detected_columns, rows_dropped = clean_columns(raw_df)
    df = enforce_row_limit(df)
    if rows_dropped:
        st.warning(f"{rows_dropped:,} invalid row(s) were skipped.")
except Exception as e:
    show_error("We couldn't load your file. Please check the file format and columns.", "load data", e)
    st.stop()

# =========================
# FILTERS + CALCULATIONS
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
    min_date, max_date = df["Date"].min().date(), df["Date"].max().date()
    selected_date = st.date_input("Filter by Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

start_date, end_date = selected_date if isinstance(selected_date, tuple) and len(selected_date) == 2 else (min_date, max_date)
filtered_df = df[(df["Category"].isin(selected_categories)) & (df["Product"].isin(selected_products)) & (df["Date"].dt.date >= start_date) & (df["Date"].dt.date <= end_date)]
if filtered_df.empty:
    st.warning("No data available for selected filters.")
    st.stop()

total_revenue = filtered_df["Total_Sales"].sum()
total_orders = len(filtered_df)
avg_order_value = filtered_df["Total_Sales"].mean()
product_revenue = filtered_df.groupby("Product")["Total_Sales"].sum()
category_revenue = filtered_df.groupby("Category")["Total_Sales"].sum()
best_product = product_revenue.idxmax()
lowest_product = product_revenue.idxmin()
top_category = category_revenue.idxmax()
monthly_sales = filtered_df.groupby("Month")["Total_Sales"].sum().sort_index()
growth = ((monthly_sales.iloc[-1] - monthly_sales.iloc[-2]) / monthly_sales.iloc[-2] * 100) if len(monthly_sales) > 1 and monthly_sales.iloc[-2] != 0 else None
growth_text = f"{growth:.1f}% vs last month" if growth is not None else "Not enough monthly data"

monthly_product_sales = filtered_df.groupby(["Product", "Month"])["Total_Sales"].sum().reset_index().sort_values(["Product", "Month"])
growth_products = []
for product in monthly_product_sales["Product"].unique():
    p = monthly_product_sales[monthly_product_sales["Product"] == product]
    if len(p) >= 2 and p["Total_Sales"].iloc[-2] != 0:
        growth_products.append((product, (p["Total_Sales"].iloc[-1] - p["Total_Sales"].iloc[-2]) / p["Total_Sales"].iloc[-2] * 100))
if growth_products:
    top_growth_product, top_growth_rate = max(growth_products, key=lambda x: x[1])
    top_growth_text = f"{top_growth_product} grew by {top_growth_rate:.1f}%"
else:
    top_growth_product, top_growth_text = "Not enough data", "Need at least 2 months of product data"

recommendation = f"Increase focus on {best_product}. Your strongest category is {top_category}. Review {lowest_product}, which is currently the lowest-performing product. Monitor {top_growth_product} for future growth."

if "Profit" in filtered_df.columns:
    profit_df = filtered_df.dropna(subset=["Profit"])
    total_profit = profit_df["Profit"].sum() if not profit_df.empty else None
    margin = total_profit / profit_df["Total_Sales"].sum() * 100 if total_profit is not None and profit_df["Total_Sales"].sum() else None
else:
    total_profit = margin = None

report_summary = pd.DataFrame({
    "Metric": ["Total Revenue", "Total Orders", "Average Order Value", "Best Product", "Lowest Product", "Top Category", "Top Growth Product", "Sales Growth", "Current Plan"],
    "Value": [f"£{total_revenue:,.2f}", f"{total_orders:,}", f"£{avg_order_value:,.2f}", best_product, lowest_product, top_category, top_growth_text, growth_text, current_plan().title()],
})

# =========================
# UI HELPERS
# =========================

def metric(title, value, sub, gradient):
    st.markdown(f"""
    <div class="metric-card" style="background:{gradient};">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


def make_pdf(summary: pd.DataFrame, rec: str):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph("AI-Powered Business Growth Report", styles["Title"]), Spacer(1, 16), Paragraph("Executive KPI Summary", styles["Heading2"])]
    table = Table([["Metric", "Value"]] + summary.values.tolist())
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("PADDING", (0, 0), (-1, -1), 8)]))
    story += [table, Spacer(1, 18), Paragraph("Recommendation", styles["Heading2"]), Paragraph(rec, styles["BodyText"])]
    doc.build(story)
    buffer.seek(0)
    return buffer

# =========================
# PAGES
# =========================

if page == "Dashboard":
    st.markdown("### Key Business Performance")
    cols = st.columns(6 if total_profit is not None else 5)
    with cols[0]: metric("Total Revenue", f"£{total_revenue:,.2f}", growth_text, "linear-gradient(135deg,#7c3aed,#4f46e5)")
    with cols[1]: metric("Total Orders", f"{total_orders:,}", "Sales records", "linear-gradient(135deg,#0ea5e9,#2563eb)")
    with cols[2]: metric("Average Order Value", f"£{avg_order_value:,.2f}", "Revenue per order", "linear-gradient(135deg,#34d399,#059669)")
    with cols[3]: metric("Best Product", best_product, "Highest revenue", "linear-gradient(135deg,#f59e0b,#f97316)")
    with cols[4]: metric("Top Growth Product", top_growth_product, top_growth_text, "linear-gradient(135deg,#ec4899,#be185d)")
    if total_profit is not None:
        with cols[5]: metric("Total Profit", f"£{total_profit:,.2f}", f"{margin:.1f}% margin" if margin is not None else "Margin unavailable", "linear-gradient(135deg,#14b8a6,#0d9488)")

    left, right = st.columns(2)
    with left:
        st.markdown("### Sales Performance Over Time")
        monthly_chart = filtered_df.groupby("Month", as_index=False)["Total_Sales"].sum().sort_values("Month")
        fig = px.line(monthly_chart, x="Month", y="Total_Sales", markers=True)
        fig.update_layout(height=420, template="plotly_white", yaxis_title="Revenue (£)")
        fig.update_yaxes(tickprefix="£", separatethousands=True)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("### Top 10 Products by Revenue")
        product_sales = filtered_df.groupby("Product", as_index=False)["Total_Sales"].sum().sort_values("Total_Sales", ascending=False).head(10)
        fig = px.bar(product_sales, x="Total_Sales", y="Product", orientation="h")
        fig.update_layout(height=420, template="plotly_white", xaxis_title="Revenue (£)")
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(tickprefix="£", separatethousands=True)
        st.plotly_chart(fig, use_container_width=True)

    bl, br = st.columns(2)
    with bl:
        st.markdown("### Revenue by Category")
        fig = px.pie(filtered_df.groupby("Category", as_index=False)["Total_Sales"].sum(), names="Category", values="Total_Sales", hole=0.5)
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)
    with br:
        st.markdown("### Product Growth Ranking")
        if growth_products:
            growth_df = pd.DataFrame(growth_products, columns=["Product", "Growth_Rate"]).sort_values("Growth_Rate", ascending=False).head(10)
            fig = px.bar(growth_df, x="Growth_Rate", y="Product", orientation="h")
            fig.update_layout(height=420, template="plotly_white", xaxis_title="Growth Rate (%)")
            fig.update_yaxes(autorange="reversed")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough monthly product data to calculate growth ranking.")

    st.markdown(f"""
    <div class="rec-box"><h3 style="margin-top:0;color:#065f46;">Business Recommendation</h3><p>{recommendation}</p></div>
    """, unsafe_allow_html=True)

elif page == "Forecasting":
    st.markdown("### Revenue Forecasting")
    if not feature_allowed("forecasting"):
        require_upgrade("Forecasting", "pro")
    elif len(monthly_sales) < 3:
        st.info("At least 3 months of data are needed to generate a forecast.")
    else:
        forecast_df = monthly_sales.reset_index()
        forecast_df.columns = ["Month", "Total_Sales"]
        forecast_df["t"] = np.arange(len(forecast_df))
        model = LinearRegression().fit(forecast_df[["t"]], forecast_df["Total_Sales"])
        future_t = np.arange(len(forecast_df), len(forecast_df) + 3)
        preds = model.predict(future_t.reshape(-1, 1))
        months = pd.date_range(forecast_df["Month"].max() + pd.DateOffset(months=1), periods=3, freq="MS")
        future_df = pd.DataFrame({"Month": months, "Forecast Sales": preds})
        chart = pd.concat([forecast_df[["Month", "Total_Sales"]].rename(columns={"Total_Sales": "Sales"}), future_df.rename(columns={"Forecast Sales": "Sales"})])
        fig = px.line(chart, x="Month", y="Sales", markers=True)
        fig.update_layout(height=420, template="plotly_white", yaxis_title="Revenue (£)")
        fig.update_yaxes(tickprefix="£", separatethousands=True)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(future_df, use_container_width=True)

elif page == "AI Assistant":
    st.markdown("### AI Business Assistant")
    if not feature_allowed("ai"):
        require_upgrade("AI Assistant", "pro")
    else:
        question = st.text_input("Ask a question", placeholder="How can I improve sales next month?")
        if st.button("Ask AI", use_container_width=True):
            if not question:
                st.error("Please enter a question.")
            elif client is None:
                st.error("OPENAI_API_KEY is missing in Streamlit secrets.")
            else:
                prompt = f"""You are a business analyst. Use this summary to answer clearly with 3-5 practical recommendations.
Revenue: £{total_revenue:,.2f}
Orders: {total_orders}
Average order value: £{avg_order_value:,.2f}
Best product: {best_product}
Lowest product: {lowest_product}
Top category: {top_category}
Growth: {growth_text}
Question: {question}
"""
                try:
                    with st.spinner("Analysing..."):
                        response = client.chat.completions.create(model="gpt-4.1-mini", messages=[{"role": "user", "content": prompt}], temperature=0.4)
                    st.markdown(f"<div class='ai-response'>{response.choices[0].message.content}</div>", unsafe_allow_html=True)
                except Exception as e:
                    show_error("AI service error. Check your OpenAI key or billing.", "AI", e)
    st.markdown("---")
    st.markdown("### SHAP Explainability")
    if not feature_allowed("shap"):
        require_upgrade("SHAP Explainability", "premium")
    else:
        st.info("SHAP section is unlocked. Add your SHAP model visualisation here if needed.")

elif page == "Reports":
    st.markdown("### Export Reports")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button("Download Cleaned Data", filtered_df.to_csv(index=False).encode("utf-8"), "cleaned_sales_data.csv", "text/csv")
    with c2:
        st.download_button("Download Executive CSV", report_summary.to_csv(index=False).encode("utf-8"), "executive_sales_report.csv", "text/csv")
    with c3:
        if REPORTLAB_AVAILABLE:
            st.download_button("Download PDF Report", make_pdf(report_summary, recommendation), "business_growth_report.pdf", "application/pdf")
        else:
            st.warning("PDF export unavailable. Add reportlab to requirements.txt.")

elif page == "Data Preview":
    st.markdown("### Data Preview")
    st.dataframe(filtered_df, use_container_width=True)
    with st.expander("Detected Column Mapping"):
        st.write(detected_columns)
    with st.expander("Executive Summary Table"):
        st.dataframe(report_summary, use_container_width=True)

elif page == "Pricing":
    st.markdown("## Pricing and Upgrade")
    st.write(f"Current plan: **{current_plan().title()}**")
    cols = st.columns(3)
    for col, plan in zip(cols, ["starter", "pro", "premium"]):
        with col:
            st.markdown(f"### {plan.title()}")
            st.markdown(f"## {PRICING[plan]['price']}")
            for feature in PRICING[plan]["features"]:
                st.write(f"✓ {feature}")
            st.markdown("---")
            if current_plan() == plan:
                st.success("Current plan")
            elif plan != "starter":
                upgrade_button(plan)
            else:
                st.info("Default plan")

elif page == "Account":
    st.markdown("## Account")
    st.write(f"**Email:** {st.session_state.get('email', '')}")
    st.write(f"**User ID:** `{st.session_state.get('user_id', '')}`")
    st.write(f"**Current plan:** {current_plan().title()}")

    c1, c2 = st.columns(2)

    with c1:
        if st.button("Refresh Plan", use_container_width=True):
            refresh_plan()
            st.success(f"Current Plan: {st.session_state.get('plan', 'starter').title()}")

    with c2:
        if st.button("Logout / Switch Account", use_container_width=True):
            logout()

    st.markdown("### Upgrade")

    if current_plan() == "starter":
        upgrade_button("pro")
        upgrade_button("premium")
    elif current_plan() == "pro":
        upgrade_button("premium")
    else:
        st.success("Premium active")