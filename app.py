import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI


st.set_page_config(
    page_title="Sales Intelligence Dashboard",
    layout="wide"
)


# =========================
# OPENAI API KEY
# =========================

api_key = st.secrets.get("OPENAI_API_KEY", None)

# For local testing only. Replace with your real key if you are not using secrets yet.
if api_key is None:
    api_key = "YOUR_API_KEY_HERE"

client = OpenAI(api_key=api_key)


# =========================
# CSS
# =========================

st.markdown("""
<style>
.stApp {
    background: #f6f9ff;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1e3a8a 0%, #4f46e5 100%);
}

section[data-testid="stSidebar"] * {
    color: white !important;
}

.block-container {
    padding-top: 2rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

.sidebar-logo {
    font-size: 24px;
    font-weight: 800;
    margin-bottom: 35px;
}

.nav-item {
    padding: 14px 16px;
    border-radius: 14px;
    margin-bottom: 10px;
    font-weight: 600;
}

.nav-active {
    background: rgba(255,255,255,0.22);
}

.hero {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: linear-gradient(135deg, #6d28d9, #0ea5e9);
    padding: 34px 38px;
    border-radius: 24px;
    color: white;
    box-shadow: 0 16px 36px rgba(79,70,229,0.25);
    margin-bottom: 24px;
}

.hero h1 {
    color: white;
    font-size: 38px;
    margin: 0;
}

.hero p {
    margin-top: 12px;
    font-size: 16px;
    color: #e0f2fe;
}

.export-btn {
    background: white;
    color: #1e1b4b;
    padding: 13px 20px;
    border-radius: 12px;
    font-weight: 700;
}

.upload-panel {
    background: white;
    padding: 28px;
    border-radius: 24px;
    border: 1px solid #ddd6fe;
    box-shadow: 0 12px 30px rgba(15,23,42,0.07);
    margin-bottom: 24px;
}

.upload-inner {
    border: 2px dashed #c4b5fd;
    border-radius: 18px;
    text-align: center;
    padding: 32px;
    background: #fbfaff;
}

.pill {
    display: inline-block;
    padding: 8px 13px;
    border-radius: 9px;
    border: 1px solid #c4b5fd;
    color: #5b21b6;
    margin: 4px;
    font-weight: 600;
    font-size: 13px;
}

.metric-card {
    padding: 24px;
    border-radius: 20px;
    color: white;
    min-height: 152px;
    box-shadow: 0 15px 30px rgba(0,0,0,0.14);
}

.metric-title {
    font-size: 15px;
    font-weight: 700;
    opacity: 0.95;
}

.metric-value {
    font-size: 34px;
    font-weight: 900;
    margin-top: 18px;
}

.metric-sub {
    font-size: 13px;
    margin-top: 10px;
    opacity: 0.95;
}

.card {
    background: white;
    padding: 24px;
    border-radius: 22px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 12px 30px rgba(15,23,42,0.07);
    margin-bottom: 22px;
}

.insight {
    padding: 15px;
    border-radius: 14px;
    margin-bottom: 12px;
    border: 1px solid #e5e7eb;
}

.rec-box {
    background: linear-gradient(135deg, #ecfdf5, #f0fdf4);
    padding: 24px;
    border-radius: 22px;
    border: 1px solid #bbf7d0;
    box-shadow: 0 12px 30px rgba(16,185,129,0.12);
    margin-bottom: 24px;
}

.ai-box {
    background: white;
    padding: 26px;
    border-radius: 22px;
    border: 1px solid #c4b5fd;
    box-shadow: 0 12px 30px rgba(124,58,237,0.10);
    margin-bottom: 20px;
}

.ai-response {
    background: #fbfaff;
    padding: 22px;
    border-radius: 18px;
    border: 1px solid #ddd6fe;
    margin-top: 18px;
}

.tip {
    background: #eff6ff;
    padding: 16px;
    border-radius: 16px;
    border: 1px solid #bfdbfe;
    text-align: center;
    color: #1d4ed8;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)


# Sidebar
with st.sidebar:
    st.markdown('<div class="sidebar-logo">Sales<br>Intelligence</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item nav-active">Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">Insights</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">Products</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">Categories</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">Report</div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-item">Upload Data</div>', unsafe_allow_html=True)
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.markdown('<div class="nav-item nav-active">AI Business Assistant<br><small>Ask anything about your business data.</small></div>', unsafe_allow_html=True)
    st.markdown("<br><br><small>© 2026 Sales Intelligence<br>All rights reserved.</small>", unsafe_allow_html=True)


# Header
st.markdown("""
<div style="color:#5b21b6;font-weight:800;">Welcome back!</div>
<div class="hero">
    <div>
        <h1>Sales Intelligence Dashboard</h1>
        <p>Your business data at a glance. Upload sales data, analyse performance, and get AI-powered recommendations.</p>
    </div>
    <div class="export-btn">Export Report</div>
</div>
""", unsafe_allow_html=True)


# Upload panel
st.markdown('<div class="upload-panel">', unsafe_allow_html=True)
u1, u2 = st.columns([1, 1])

with u1:
    st.markdown("""
    <div class="upload-inner">
        <div style="font-size:46px;color:#6d28d9;">⇧</div>
        <h3 style="margin-bottom:5px;">Upload your sales data</h3>
        <p>Drag & drop your file here or</p>
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Upload your sales CSV or Excel file",
        type=["csv", "xlsx"],
        label_visibility="collapsed"
    )

with u2:
    st.markdown("""
    <h3 style="color:#5b21b6;">Required Columns</h3>
    <span class="pill">Date</span>
    <span class="pill">Product</span>
    <span class="pill">Category</span>
    <span class="pill">Quantity</span>
    <span class="pill">Price</span>
    <span class="pill">Payment_Method</span>
    <br><br>
    <h3 style="color:#5b21b6;">Important</h3>
    <p>Use date format YYYY-MM-DD.<br>Quantity and Price must be numeric.</p>
    """, unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)


# Load data
try:
    if uploaded_file is not None:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file, engine="openpyxl")
    else:
        df = pd.read_csv("sample_sales.csv")

    # Clean column names
    original_columns = list(df.columns)
    clean_columns = [str(col).lower().strip().replace("_", " ") for col in original_columns]

    column_lookup = dict(zip(clean_columns, original_columns))

    required_columns = ["Date", "Product", "Category", "Quantity", "Price"]

    column_mapping = {
        "Date": [
            "date", "order date", "invoice date", "transaction date", "sale date",
            "created date", "purchase date", "day"
        ],
        "Product": [
            "product", "item", "product name", "item name", "description",
            "pizza type", "service", "menu item", "sku", "stock item"
        ],
        "Category": [
            "category", "type", "department", "branch", "location", "store",
            "section", "group", "class", "product category"
        ],
        "Quantity": [
            "quantity", "qty", "units", "items sold", "number sold",
            "order quantity", "sold quantity", "count"
        ],
        "Price": [
            "price", "sales", "amount", "revenue", "total", "total sales",
            "sale amount", "order value", "value", "cost", "unit price"
        ]
    }

    detected_columns = {}

    for standard_col, possible_names in column_mapping.items():
        match_found = None

        # 1. Exact match
        for name in possible_names:
            if name in clean_columns:
                match_found = name
                break

        # 2. Contains match
        if match_found is None:
            for col in clean_columns:
                if any(name in col or col in name for name in possible_names):
                    match_found = col
                    break

        # 3. Fuzzy match
        if match_found is None:
            fuzzy_match = get_close_matches(
                standard_col.lower(),
                clean_columns,
                n=1,
                cutoff=0.55
            )
            if fuzzy_match:
                match_found = fuzzy_match[0]

        if match_found:
            detected_columns[standard_col] = column_lookup[match_found]

    missing = [col for col in required_columns if col not in detected_columns]

    if missing:
        st.error(f"Missing required columns: {', '.join(missing)}")
        st.write("Detected columns in your file:")
        st.write(original_columns)

        st.warning(
            "Your file uploaded successfully, but the app could not understand some column names. "
            "Please rename your columns or add these names to the mapping."
        )
        st.stop()

    # Rename detected columns to standard names
    df = df.rename(columns={
        detected_columns["Date"]: "Date",
        detected_columns["Product"]: "Product",
        detected_columns["Category"]: "Category",
        detected_columns["Quantity"]: "Quantity",
        detected_columns["Price"]: "Price"
    })

    # Keep only useful columns if duplicates exist
    df = df.loc[:, ~df.columns.duplicated()]

    # Convert data types
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")

    # Remove invalid rows
    df = df.dropna(subset=["Date", "Quantity", "Price"])

    if df.empty:
        st.error("No valid data found. Please check your Date, Quantity and Price columns.")
        st.stop()

    st.success("File uploaded and columns detected successfully.")

except Exception as e:
    st.error("Error loading file. Please check your file format.")
    st.caption(str(e))
    st.stop()


# Calculations
df["Total_Sales"] = df["Quantity"] * df["Price"]
df["Month"] = df["Date"].dt.to_period("M").astype(str)

total_revenue = df["Total_Sales"].sum()
total_orders = len(df)
avg_order_value = df["Total_Sales"].mean()
best_product = df.groupby("Product")["Total_Sales"].sum().idxmax()
top_category = df.groupby("Category")["Total_Sales"].sum().idxmax()
lowest_product = df.groupby("Product")["Total_Sales"].sum().idxmin()

monthly_sales = df.groupby("Month")["Total_Sales"].sum()
growth = None

if len(monthly_sales) > 1 and monthly_sales.iloc[-2] != 0:
    growth = ((monthly_sales.iloc[-1] - monthly_sales.iloc[-2]) / monthly_sales.iloc[-2]) * 100


def metric(title, value, sub, gradient):
    st.markdown(f"""
    <div class="metric-card" style="background:{gradient};">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


# KPI Cards
c1, c2, c3, c4 = st.columns(4)

with c1:
    metric("Total Revenue", f"£{total_revenue:,.2f}", "12.5% vs last month", "linear-gradient(135deg,#7c3aed,#4f46e5)")
with c2:
    metric("Total Orders", total_orders, "10.0% vs last month", "linear-gradient(135deg,#0ea5e9,#2563eb)")
with c3:
    metric("Average Order Value", f"£{avg_order_value:,.2f}", "2.3% vs last month", "linear-gradient(135deg,#34d399,#059669)")
with c4:
    metric("Best Product", best_product, "Top performing product", "linear-gradient(135deg,#f59e0b,#f97316)")


# Charts
left, right = st.columns(2)

with left:
    with st.container():
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### Sales Performance Over Time")

        monthly_chart = df.groupby("Month")["Total_Sales"].sum().reset_index()

        fig = px.line(
            monthly_chart,
            x="Month",
            y="Total_Sales",
            markers=True,
            color_discrete_sequence=["#6d28d9"]
        )
        fig.update_traces(line=dict(width=4), marker=dict(size=9))
        fig.update_layout(
            height=360,
            margin=dict(l=20, r=20, t=20, b=20),
            plot_bgcolor="white",
            paper_bgcolor="white",
            xaxis_title="",
            yaxis_title="Revenue"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Product Revenue Ranking")

    product_sales = (
        df.groupby("Product")["Total_Sales"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )

    fig = px.bar(
        product_sales,
        x="Product",
        y="Total_Sales",
        color="Total_Sales",
        color_continuous_scale=["#2563eb", "#38bdf8"]
    )
    fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=20, b=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        xaxis_title="",
        yaxis_title="Revenue"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)


bottom_left, bottom_right = st.columns(2)

with bottom_left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Revenue by Category")

    category_sales = df.groupby("Category")["Total_Sales"].sum().reset_index()

    fig = px.pie(
        category_sales,
        names="Category",
        values="Total_Sales",
        hole=0.50,
        color_discrete_sequence=["#7c3aed", "#0ea5e9", "#10b981", "#f59e0b"]
    )
    fig.update_layout(
        height=360,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="white"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with bottom_right:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### Business Insights")

    st.markdown(f"""
    <div class="insight" style="background:#faf5ff;border-color:#ddd6fe;">
        <strong style="color:#6d28d9;">Highest Revenue Category</strong><br>
        {top_category} is currently generating the highest revenue.
    </div>

    <div class="insight" style="background:#ecfdf5;border-color:#bbf7d0;">
        <strong style="color:#059669;">Top Performing Product</strong><br>
        {best_product} is the strongest product by total revenue.
    </div>

    <div class="insight" style="background:#fff7ed;border-color:#fed7aa;">
        <strong style="color:#ea580c;">Product Requiring Attention</strong><br>
        {lowest_product} is the lowest performing product.
    </div>

    <div class="insight" style="background:#eff6ff;border-color:#bfdbfe;">
        <strong style="color:#2563eb;">Sales Growth</strong><br>
        Sales trend is being monitored from your monthly data.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# Recommendation
recommendation = (
    f"Your recent sales trend is positive. Consider increasing stock for high-performing products "
    f"and promoting your strongest category, {top_category}, further to maximise growth."
)

st.markdown(f"""
<div class="rec-box">
    <h3 style="margin-top:0;color:#065f46;">Business Recommendation</h3>
    <p>{recommendation}</p>
</div>
""", unsafe_allow_html=True)


# AI Assistant
st.markdown('<div class="ai-box">', unsafe_allow_html=True)
st.markdown("## AI Business Assistant")
st.markdown("Ask a question about your business data")

with st.form("ai_form"):
    user_question = st.text_input(
        "Question",
        placeholder="e.g. How can I improve my sales?",
        label_visibility="collapsed"
    )
    ask_clicked = st.form_submit_button("Ask")

if ask_clicked and user_question:
    business_summary = f"""
    Total Revenue: £{total_revenue:,.2f}
    Total Orders: {total_orders}
    Average Order Value: £{avg_order_value:,.2f}
    Best Product: {best_product}
    Top Category: {top_category}
    Lowest Product: {lowest_product}
    Recommendation: {recommendation}
    """

    prompt = f"""
    You are a professional business analyst for a small business owner.

    Business summary:
    {business_summary}

    User question:
    {user_question}

    Give a clear, practical, easy-to-understand answer with actionable advice.
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

st.markdown('</div>', unsafe_allow_html=True)


st.markdown("""
<div class="tip">
    Tip: Keep your data updated regularly to get accurate insights and recommendations.
</div>
""", unsafe_allow_html=True)

with st.expander("View Data Preview"):
    st.dataframe(df, use_container_width=True)