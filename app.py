from datetime import datetime
import base64
import json
import os
import hashlib
import binascii
import pandas as pd
import psycopg2
import streamlit as st
import streamlit.components.v1 as components
from xhtml2pdf import pisa

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="SKN Permata Resources - Business System",
    page_icon="logo.jpeg",
    layout="wide",
)

# --- DATABASE SETUP (SUPABASE / POSTGRESQL) ---
def run_query(query, params=(), fetch=True):
    pg_query = query.replace("?", "%s")
    conn = psycopg2.connect(st.secrets["postgres"]["connection_string"])
    cursor = conn.cursor()
    cursor.execute(pg_query, params)

    if fetch:
        result = cursor.fetchall()
        conn.close()
        return result

    conn.commit()
    conn.close()

# --- SECURITY & CRYPTOGRAPHY HELPERS ---
def hash_password(password, salt=None):
    if not salt:
        salt = os.urandom(32)
    elif isinstance(salt, str):
        salt = binascii.unhexlify(salt.encode("utf-8"))
    
    pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return binascii.hexlify(salt).decode('utf-8'), binascii.hexlify(pwdhash).decode('utf-8')

def verify_password(stored_salt, stored_hash, provided_password):
    _, pwdhash = hash_password(provided_password, salt=stored_salt)
    return pwdhash == stored_hash

def init_default_admin():
    """Automatically creates a default admin user using st.secrets if no users exist."""
    try:
        users = run_query("SELECT COUNT(*) FROM users", fetch=True)
        if users and users[0][0] == 0:
            admin_user = st.secrets["admin"]["username"]
            admin_pass = st.secrets["admin"]["password"]
            salt, pwd_hash = hash_password(admin_pass)
            run_query(
                "INSERT INTO users (username, password_hash, salt, role) VALUES (?, ?, ?, ?)",
                (admin_user, pwd_hash, salt, "admin"),
                fetch=False
            )
    except Exception:
        pass

init_default_admin()

# --- CUSTOM CSS FOR UI ---
st.markdown(
    """
    <style>
    .stRadio label { font-size: 18px !important; font-weight: bold !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox select { font-size: 16px !important; }
    h1 { color: #1f4e78; }
    
    .stFormSubmitButton button {
        background-color: #2e7d32 !important;
        color: white !important;
        font-size: 20px !important;
        font-weight: bold !important;
        width: 100% !important;
        padding: 12px 20px !important;
        border-radius: 10px !important;
        border: none !important;
        box-shadow: 0px 4px 6px rgba(0,0,0,0.1) !important;
    }
    .stFormSubmitButton button:hover {
        background-color: #1b5e20 !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# AUTHENTICATION & SECURITY GATE
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "failed_attempts" not in st.session_state:
    st.session_state.failed_attempts = 0

if not st.session_state.logged_in:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    
    with col_l2:
        if os.path.exists("logo.jpeg"):
            st.image("logo.jpeg", width=120)
        st.title("🔒 System Login")
        st.write("Please enter your credentials to access SKN Permata Resources.")

        if st.session_state.failed_attempts >= 5:
            st.error("🚨 Too many failed login attempts. Account access temporarily throttled for security.")
        else:
            with st.form("login_form"):
                username_input = st.text_input("Username", help="Enter your assigned staff/admin username.")
                password_input = st.text_input("Password", type="password", help="Enter your secret account password.")
                submit_login = st.form_submit_button("🔑 Login Securely")

                if submit_login:
                    try:
                        res = run_query(
                            "SELECT username, password_hash, salt, role FROM users WHERE username = ?",
                            (username_input,),
                            fetch=True
                        )
                        if res:
                            db_user, db_hash, db_salt, db_role = res[0]
                            if verify_password(db_salt, db_hash, password_input):
                                st.session_state.logged_in = True
                                st.session_state.username = db_user
                                st.session_state.role = db_role
                                st.session_state.failed_attempts = 0
                                st.success("✅ Login successful! Loading system...")
                                st.rerun()
                            else:
                                st.session_state.failed_attempts += 1
                                st.error(f"❌ Invalid password. Attempt {st.session_state.failed_attempts}/5")
                        else:
                            st.session_state.failed_attempts += 1
                            st.error(f"❌ User not found. Attempt {st.session_state.failed_attempts}/5")
                    except Exception as e:
                        st.error(f"Database connection error during login: {e}")
    st.stop()

# ==========================================
# LOGGED-IN APP CODE (Protected Routes)
# ==========================================

def get_next_invoice_no():
    res = run_query("SELECT COUNT(*) FROM invoices", fetch=True)
    next_id = (res[0][0] if res else 0) + 1
    return f"INV-{datetime.now().strftime('%y%m')}-{next_id:03d}"

def get_next_quote_no():
    res = run_query("SELECT COUNT(*) FROM quotations", fetch=True)
    next_id = (res[0][0] if res else 0) + 1
    return f"QT-{datetime.now().strftime('%y%m')}-{next_id:03d}"

# --- LOAD LOGO FOR HTML TEMPLATES ---
logo_base64 = ""
if os.path.exists("logo.jpeg"):
    with open("logo.jpeg", "rb") as img_file:
        logo_base64 = base64.b64encode(img_file.read()).decode("utf-8")

logo_html = (
    f'<img src="data:image/jpeg;base64,{logo_base64}" style="max-height: 55px; margin-bottom: 5px;" />'
    if logo_base64
    else "<h3 style='margin-bottom: 2px;'>SKN PERMATA RESOURCES</h3>"
)

# --- PDF GENERATION HELPERS ---
def generate_invoice_html(inv_no, client_name, client_address, date, terms, items, total_amount, status):
    phone_number = st.secrets["company"]["phone"]
    bank_name = st.secrets["company"]["bank_name"]
    bank_account = st.secrets["company"]["bank_account"]

    items_html = ""
    for idx, item in enumerate(items, 1):
        items_html += f"""
        <tr>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: center;">{idx}</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px;">{item['item']}</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: center;">{item['qty']} unit</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: right;">{item['price']:,.2f}</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: right;">{item['subtotal']:,.2f}</td>
        </tr>
        """

    return f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; max-width: 800px; margin: auto; background: white; color: black;">
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 5px;">
            <tr>
                <td style="border: none; width: 65px; vertical-align: middle; padding: 0 10px 0 0;">
                    {logo_html}
                </td>
                <td style="border: none; vertical-align: middle; padding: 0;">
                    <p style="font-size: 11px; margin: 0; color: #555;"><strong>SKN PERMATA RESOURCES. (202603006346 / JM1037858-H)</strong><br>
                    No 13 Jalan Tingkat Bawah, Jalan Pak Sako 6<br>
                    Bandar Sri Semantan, 28000 Temerloh Pahang<br>
                    Email: sknpermataresources@gmail.com | Tel: {phone_number}</p>
                </td>
            </tr>
        </table>
        <hr style="margin: 10px 0;">
        <table style="width: 100%; font-size: 14px;">
            <tr>
                <td><strong>Attn:</strong><br>{client_name}<br>{client_address}</td>
                <td style="text-align: right; vertical-align: top;">
                    <strong>Bil/inv:</strong> {inv_no}<br>
                    <strong>Date:</strong> {date}<br>
                    <strong>Terms:</strong> {terms if terms else '-'}<br>
                    <strong>Status:</strong> {status}
                </td>
            </tr>
        </table>
        <br>
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px;">
            <thead>
                <tr style="background-color: #f2f2f2; border-top: 1px solid #000; border-bottom: 1px solid #000;">
                    <th style="padding: 6px; text-align: center; width: 40px;">No</th>
                    <th style="padding: 6px; text-align: left;">Description</th>
                    <th style="padding: 6px; text-align: center;">Qty</th>
                    <th style="padding: 6px; text-align: right;">Rate (RM)</th>
                    <th style="padding: 6px; text-align: right;">Amount (RM)</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>
        <br>
        <table style="width: 100%; font-size: 14px;">
            <tr>
                <td style="vertical-align: top; font-size: 12px;">
                    <strong>{bank_name}</strong><br>
                    SKN PERMATA RESOURCES<br>
                    <strong>BANK ACC: {bank_account} - {bank_name}</strong>
                </td>
                <td style="text-align: right;">
                    <strong>Sub Total:</strong> RM {total_amount:,.2f}<br>
                    <h3 style="margin: 5px 0;">Total: RM {total_amount:,.2f}</h3>
                </td>
            </tr>
        </table>
    </div>
    """

def generate_quotation_html(quote_no, client_name, client_address, date, terms, items, total_amount):
    phone_number = st.secrets["company"]["phone"]

    items_html = ""
    for idx, item in enumerate(items, 1):
        items_html += f"""
        <tr>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: center;">{idx}</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px;">{item['item']}</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: center;">{item['qty']} unit</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: right;">{item['price']:,.2f}</td>
            <td style="border-bottom: 1px solid #ddd; padding: 6px; text-align: right;">{item['subtotal']:,.2f}</td>
        </tr>
        """

    return f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; max-width: 800px; margin: auto; background: white; color: black;">
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 5px;">
            <tr>
                <td style="border: none; width: 65px; vertical-align: middle; padding: 0 10px 0 0;">
                    {logo_html}
                </td>
                <td style="border: none; vertical-align: middle; padding: 0;">
                    <p style="font-size: 11px; margin: 0; color: #555;"><strong>SKN PERMATA RESOURCES. (202603006346 / JM1037858-H)</strong><br>
                    No 13 Jalan Tingkat Bawah, Jalan Pak Sako 6<br>
                    Bandar Sri Semantan, 28000 Temerloh Pahang<br>
                    Email: sknpermataresources@gmail.com | Tel: {phone_number}</p>
                </td>
            </tr>
        </table>
        <hr style="margin: 10px 0;">
        <table style="width: 100%; font-size: 14px;">
            <tr>
                <td><strong>Quotation For:</strong><br>{client_name}<br>{client_address}</td>
                <td style="text-align: right; vertical-align: top;">
                    <strong>Quotation No:</strong> {quote_no}<br>
                    <strong>Date:</strong> {date}<br>
                    <strong>Terms:</strong> {terms if terms else '-'}<br>
                </td>
            </tr>
        </table>
        <br>
        <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px;">
            <thead>
                <tr style="background-color: #f2f2f2; border-top: 1px solid #000; border-bottom: 1px solid #000;">
                    <th style="padding: 6px; text-align: center; width: 40px;">No</th>
                    <th style="padding: 6px; text-align: left;">Description</th>
                    <th style="padding: 6px; text-align: center;">Qty</th>
                    <th style="padding: 6px; text-align: right;">Rate (RM)</th>
                    <th style="padding: 6px; text-align: right;">Amount (RM)</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
        </table>
        <br>
        <table style="width: 100%; font-size: 14px;">
            <tr>
                <td></td>
                <td style="text-align: right;">
                    <strong>Sub Total:</strong> RM {total_amount:,.2f}<br>
                    <h3 style="margin: 5px 0;">Total: RM {total_amount:,.2f}</h3>
                </td>
            </tr>
        </table>
    </div>
    """

def generate_payslip_html(employee_name, ic_no, bank_info, month_year, date, basic_salary, additions, deductions, gross_total, total_deduction, net_pay, payment_method):
    phone_number = st.secrets["company"]["phone"]

    if isinstance(additions, str):
        try:
            additions = json.loads(additions)
        except Exception:
            additions = {}
    
    if isinstance(deductions, str):
        try:
            deductions = json.loads(deductions)
        except Exception:
            deductions = {}

    earnings_rows = f"""
    <tr>
        <td style="padding: 6px 8px; border-bottom: 1px solid #e0e0e0;">Basic Salary</td>
        <td style="padding: 6px 8px; border-bottom: 1px solid #e0e0e0; text-align: right;">{basic_salary:,.2f}</td>
    </tr>
    """
    for key, val in additions.items():
        if val > 0:
            earnings_rows += f"""
            <tr>
                <td style="padding: 6px 8px; border-bottom: 1px solid #e0e0e0;">{key}</td>
                <td style="padding: 6px 8px; border-bottom: 1px solid #e0e0e0; text-align: right;">{val:,.2f}</td>
            </tr>
            """

    deductions_rows = ""
    has_deductions = False
    for key, val in deductions.items():
        if val > 0:
            has_deductions = True
            deductions_rows += f"""
            <tr>
                <td style="padding: 6px 8px; border-bottom: 1px solid #e0e0e0;">{key}</td>
                <td style="padding: 6px 8px; border-bottom: 1px solid #e0e0e0; text-align: right;">{val:,.2f}</td>
            </tr>
            """
    if not has_deductions:
        deductions_rows = """
        <tr>
            <td style="padding: 6px 8px; border-bottom: 1px solid #e0e0e0; color: #777;" colspan="2">No deductions</td>
        </tr>
        """

    return f"""
    <div style="font-family: Helvetica, Arial, sans-serif; padding: 25px; max-width: 800px; margin: auto; background: white; color: #333; font-size: 13px; line-height: 1.4;">
        <!-- Header Table -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">
            <tr>
                <td style="border: none; width: 70px; vertical-align: middle; padding: 0 15px 0 0;">
                    {logo_html}
                </td>
                <td style="border: none; vertical-align: middle; padding: 0;">
                    <h2 style="margin: 0 0 3px 0; color: #1f4e78; font-size: 18px;">SKN PERMATA RESOURCES</h2>
                    <p style="font-size: 11px; margin: 0; color: #555;">
                    (202603006346 / JM1037858-H)<br>
                    No 13 Jalan Tingkat Bawah, Jalan Pak Sako 6, Bandar Sri Semantan, 28000 Temerloh Pahang<br>
                    </p>
                </td>
                <td style="border: none; text-align: right; vertical-align: top; padding: 0;">
                    <span style="background-color: #eee; padding: 5px 10px; font-weight: bold; font-size: 11px; color: #444; border-radius: 4px;">CONFIDENTIAL</span>
                </td>
            </tr>
        </table>
        
        <div style="border-bottom: 2px solid #1f4e78; margin-bottom: 15px;"></div>
        
        <h3 style="text-align: center; margin: 0 0 15px 0; color: #333; font-size: 15px; letter-spacing: 0.5px;">MONTHLY PAYSLIP — {month_year.upper()}</h3>
        
        <!-- Employee & Pay Info Box -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; border: 1px solid #ccc; background-color: #fafafa;">
            <tr>
                <td style="padding: 10px 12px; width: 50%; vertical-align: top; border-right: 1px solid #ccc;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="border:none; padding: 3px 0; width: 110px; color: #666;">Employee Name:</td>
                            <td style="border:none; padding: 3px 0; font-weight: bold;">{employee_name}</td>
                        </tr>
                        <tr>
                            <td style="border:none; padding: 3px 0; color: #666;">I.C. / Passport:</td>
                            <td style="border:none; padding: 3px 0;">{ic_no}</td>
                        </tr>
                        <tr>
                            <td style="border:none; padding: 3px 0; color: #666;">Bank Details:</td>
                            <td style="border:none; padding: 3px 0;">{bank_info}</td>
                        </tr>
                    </table>
                </td>
                <td style="padding: 10px 12px; width: 50%; vertical-align: top;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="border:none; padding: 3px 0; width: 110px; color: #666;">Pay Date:</td>
                            <td style="border:none; padding: 3px 0;">{date}</td>
                        </tr>
                        <tr>
                            <td style="border:none; padding: 3px 0; color: #666;">Payment Mode:</td>
                            <td style="border:none; padding: 3px 0;">{payment_method}</td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>

        <!-- Earnings and Deductions Side-by-Side Tables -->
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">
            <tr>
                <td style="width: 49%; vertical-align: top; border: none; padding: 0 10px 0 0;">
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #ccc;">
                        <thead>
                            <tr style="background-color: #1f4e78; color: white;">
                                <th style="padding: 8px; text-align: left; font-size: 12px;">Earnings</th>
                                <th style="padding: 8px; text-align: right; font-size: 12px; width: 100px;">Amount (RM)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {earnings_rows}
                            <tr>
                                <td style="padding: 8px; font-weight: bold; background-color: #f2f2f2; border-top: 1px solid #bbb;">Gross Total</td>
                                <td style="padding: 8px; text-align: right; font-weight: bold; background-color: #f2f2f2; border-top: 1px solid #bbb;">{gross_total:,.2f}</td>
                            </tr>
                        </tbody>
                    </table>
                </td>
                <td style="width: 49%; vertical-align: top; border: none; padding: 0 0 0 10px;">
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #ccc;">
                        <thead>
                            <tr style="background-color: #555; color: white;">
                                <th style="padding: 8px; text-align: left; font-size: 12px;">Deductions</th>
                                <th style="padding: 8px; text-align: right; font-size: 12px; width: 100px;">Amount (RM)</th>
                            </tr>
                        </thead>
                        <tbody>
                            {deductions_rows}
                            <tr>
                                <td style="padding: 8px; font-weight: bold; background-color: #f2f2f2; border-top: 1px solid #bbb;">Total Deductions</td>
                                <td style="padding: 8px; text-align: right; font-weight: bold; background-color: #f2f2f2; border-top: 1px solid #bbb;">{total_deduction:,.2f}</td>
                            </tr>
                        </tbody>
                    </table>
                </td>
            </tr>
        </table>

        <!-- Net Pay Box -->
        <table style="width: 100%; border-collapse: collapse; margin-top: 15px; border: 2px solid #1f4e78; background-color: #f0f4f8;">
            <tr>
                <td style="padding: 12px 15px; border: none; vertical-align: middle;">
                    <span style="font-size: 15px; font-weight: bold; color: #1f4e78;">NET PAY (GAJI BERSIH):</span>
                </td>
                <td style="padding: 12px 15px; border: none; text-align: right; vertical-align: middle;">
                    <span style="font-size: 18px; font-weight: bold; color: #1f4e78;">RM {net_pay:,.2f}</span>
                </td>
            </tr>
        </table>

        <!-- Footer Notes / Signatures -->
        <table style="width: 100%; border-collapse: collapse; margin-top: 40px; font-size: 11px; color: #666;">
            <tr>
                <td style="border: none; width: 60%; vertical-align: bottom;">
                    <p style="margin: 0; font-style: italic;">This is a computer-generated document. No signature is required.</p>
                </td>
                <td style="border: none; width: 40%; text-align: center; vertical-align: bottom;">
                    <div style="border-bottom: 1px solid #666; margin-bottom: 5px; height: 35px;"></div>
                    <p style="margin: 0;">Authorized Signature / Employer Stamp</p>
                </td>
            </tr>
        </table>
    </div>
    """

def save_html_as_pdf(html_content, file_path):
    with open(file_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(html_content, dest=pdf_file)
    return not pisa_status.err

def save_invoice_pdf(inv_no, client_name, client_address, date, terms, items, total_amount, status):
    os.makedirs("invoices_folder", exist_ok=True)
    html_content = generate_invoice_html(inv_no, client_name, client_address, date, terms, items, total_amount, status)
    file_path = os.path.join("invoices_folder", f"Invoice_{inv_no}.pdf")
    save_html_as_pdf(html_content, file_path)
    return html_content, file_path

def save_quotation_pdf(quote_no, client_name, client_address, date, terms, items, total_amount):
    os.makedirs("quotations_folder", exist_ok=True)
    html_content = generate_quotation_html(quote_no, client_name, client_address, date, terms, items, total_amount)
    file_path = os.path.join("quotations_folder", f"Quotation_{quote_no}.pdf")
    save_html_as_pdf(html_content, file_path)
    return html_content, file_path

def save_payslip_pdf(employee_name, ic_no, bank_info, month_year, date, basic_salary, additions, deductions, gross_total, total_deduction, net_pay, payment_method):
    os.makedirs("payroll_folder", exist_ok=True)
    html_content = generate_payslip_html(employee_name, ic_no, bank_info, month_year, date, basic_salary, additions, deductions, gross_total, total_deduction, net_pay, payment_method)
    file_path = os.path.join("payroll_folder", f"Payslip_{employee_name}_{month_year}.pdf")
    save_html_as_pdf(html_content, file_path)
    return html_content, file_path


# --- SIDEBAR NAVIGATION ---
if os.path.exists("logo.jpeg"):
    st.sidebar.image("logo.jpeg", width=140)
else:
    st.sidebar.title("SKN Permata Resources")

st.sidebar.success(f"👤 Logged in as: **{st.session_state.get('username', 'Admin')}**")
if st.sidebar.button("🚪 Log Out"):
    st.session_state.logged_in = False
    st.session_state.failed_attempts = 0
    st.rerun()

st.sidebar.write("---")
st.sidebar.write("### 🧭 Quick Menu")

menu = st.sidebar.radio(
    "Select Page:",
    [
        "📊 Dashboard & Earnings",
        "🧾 Create Invoice",
        "📑 Create Quotation",
        "📂 View Invoices & Quotes",
        "💵 Payroll & Payslips",
        "📦 Products & Price List",
        "👥 Worker Attendance",
        "💸 Expense Tracker",
    ],
    label_visibility="collapsed",
)

# ==========================================
# 1. DASHBOARD & TOTAL EARNINGS
# ==========================================
if menu == "📊 Dashboard & Earnings":
    st.title("📊 SKN Permata Resources - Dashboard")
    st.info("💡 **Welcome!** This system helps you easily create invoices, quotations, payroll slips, and track expenses without needing technical IT knowledge. Use the left menu to navigate between pages.")

    invoices = run_query("SELECT total_amount, status FROM invoices", fetch=True)
    expenses = run_query("SELECT amount FROM expenses", fetch=True)
    payroll_list = run_query("SELECT net_pay FROM payroll", fetch=True)

    total_earnings = sum([inv[0] for inv in invoices if inv[1] == "Paid"])
    total_invoiced = sum([inv[0] for inv in invoices])
    total_expenses = sum([exp[0] for exp in expenses])
    total_payroll = sum([p[0] for p in payroll_list])
    net_profit = total_earnings - (total_expenses + total_payroll)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Invoiced", f"RM {total_invoiced:,.2f}")
    col2.metric("Total Collected", f"RM {total_earnings:,.2f}")
    col3.metric("Total Expenses", f"RM {total_expenses + total_payroll:,.2f}")
    col4.metric("Net Profit", f"RM {net_profit:,.2f}")

    st.divider()
    st.subheader("📌 Quick Guide for Beginners:")
    st.success(
        "1. **Create Invoice/Quotation:** Choose how many items you want, type a few letters in the **🔍 Search Item** box to quickly find products, fill in quantities, and click the big green button at the bottom.\n"
        "2. **Payroll & Payslips:** Pick the employee month and year from dropdown calendars, enter salary details, and download the PDF instantly.\n"
        "3. **Products & Price List:** Add your inventory items once here so they automatically appear in your invoices and quotations."
    )

# ==========================================
# 2. CREATE INVOICE
# ==========================================
elif menu == "🧾 Create Invoice":
    st.title("🧾 Create New Invoice")
    st.info("💡 **Tip for Users:** First, select how many different items are in this invoice and click **'🔄 Apply Count'**. Then fill in the client info and search for your items easily below.")

    products = run_query("SELECT item_name, price FROM products")
    product_dict = {p[0]: p[1] for p in products}

    if "inv_count" not in st.session_state:
        st.session_state.inv_count = 1

    col_ic1, col_ic2 = st.columns([3, 1])
    with col_ic1:
        st.session_state.inv_count = st.number_input(
            "How many items in this invoice?", min_value=1, max_value=20, value=st.session_state.inv_count, key="inv_count_widget",
            help="Select the total number of product rows you want to add."
        )
    with col_ic2:
        st.write("")
        if st.button("🔄 Apply Count", key="apply_inv_count", help="Click this after changing the number of items above."):
            st.rerun()

    with st.form("create_invoice_form"):
        col1, col2 = st.columns(2)
        with col1:
            invoice_no = st.text_input("Invoice Number (Auto-Generated)", value=get_next_invoice_no(), help="Generated automatically for you.")
            client_name = st.text_input("Client Name (Attn)", help="Type the customer or company name here.")
        with col2:
            date = st.date_input("Invoice Date (Calendar)", value=datetime.today(), help="Click to select transaction date.")
            terms = st.text_input("Payment Terms (e.g., Cash / 30 Days)", value="Cash", help="Specify payment method or credit terms.")

        client_address = st.text_area("Client Address", help="Enter full billing address.")
        st.divider()
        st.subheader("Select Items")

        selected_items = []
        total_calc = 0.0

        for i in range(int(st.session_state.inv_count)):
            search_filter = st.text_input(f"🔍 Search Item {i+1}", placeholder="Type to filter product...", key=f"inv_search_{i}", help="Type 2-3 letters to instantly filter your product list.")
            
            if search_filter:
                filtered_options = [p for p in product_dict.keys() if search_filter.lower() in p.lower()]
            else:
                filtered_options = list(product_dict.keys())

            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                item_name = st.selectbox(f"Select Product {i+1}", options=filtered_options if filtered_options else ["No matching product"], key=f"inv_item_{i}")
            with cols[1]:
                default_price = product_dict.get(item_name, 0.0) if product_dict and item_name in product_dict else 0.0
                price = st.number_input(f"Rate (RM) {i+1}", value=float(default_price), key=f"inv_price_{i}", help="Unit price in RM.")
            with cols[2]:
                qty = st.number_input(f"Qty {i+1}", min_value=1, value=1, key=f"inv_qty_{i}", help="Quantity ordered.")
            with cols[3]:
                subtotal = price * qty
                st.write(f"**Amt:** RM {subtotal:,.2f}")
                selected_items.append({"item": item_name, "price": price, "qty": qty, "subtotal": subtotal})
                total_calc += subtotal

        status = st.selectbox("Invoice Status", ["Unpaid", "Paid"], help="Choose whether customer has paid.")
        submit_invoice = st.form_submit_button("💾 CLICK HERE TO GENERATE & SAVE INVOICE")

    if submit_invoice:
        if not client_name:
            st.error("⚠️ Please enter a Client Name.")
        else:
            items_json = json.dumps(selected_items)
            try:
                run_query(
                    "INSERT INTO invoices (invoice_no, client_name, client_address, date, due_date, terms, items_json, total_amount, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (invoice_no, client_name, client_address, str(date), str(date), terms, items_json, total_calc, status),
                    fetch=False,
                )
                html_content, pdf_path = save_invoice_pdf(invoice_no, client_name, client_address, str(date), terms, selected_items, total_calc, status)
                st.success(f"✅ Invoice #{invoice_no} successfully saved and stored as PDF in `invoices_folder/`!")

                st.subheader("📄 Generated Invoice Preview")
                components.html(html_content, height=550, scrolling=True)

                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pdf_file:
                        st.download_button("📥 Download This PDF File", pdf_file, file_name=f"Invoice_{invoice_no}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Error saving invoice: {e}")

# ==========================================
# 3. CREATE QUOTATION
# ==========================================
elif menu == "📑 Create Quotation":
    st.title("📑 Create New Quotation")
    st.info("💡 **Tip:** Set the item count, click **'🔄 Apply Count'**, fill in the client details, and use the quick search box to pick your products.")

    products = run_query("SELECT item_name, price FROM products")
    product_dict = {p[0]: p[1] for p in products}

    if "qt_count" not in st.session_state:
        st.session_state.qt_count = 1

    col_qc1, col_qc2 = st.columns([3, 1])
    with col_qc1:
        st.session_state.qt_count = st.number_input("How many items?", min_value=1, max_value=20, value=st.session_state.qt_count, key="qt_count_widget")
    with col_qc2:
        st.write("")
        if st.button("🔄 Apply Count", key="apply_qt_count"):
            st.rerun()

    with st.form("create_quotation_form"):
        col1, col2 = st.columns(2)
        with col1:
            quote_no = st.text_input("Quotation Number (Auto-Generated)", value=get_next_quote_no())
            client_name = st.text_input("Client Name (Attn)")
        with col2:
            date = st.date_input("Quotation Date (Calendar)", value=datetime.today())
            terms = st.text_input("Terms")

        client_address = st.text_area("Client Address")
        st.divider()
        st.subheader("Select Items")

        selected_items = []
        total_calc = 0.0

        for i in range(int(st.session_state.qt_count)):
            search_filter_q = st.text_input(f"🔍 Search Item {i+1}", placeholder="Type to filter product...", key=f"q_search_{i}", help="Type keywords to filter the item list.")
            
            if search_filter_q:
                filtered_options_q = [p for p in product_dict.keys() if search_filter_q.lower() in p.lower()]
            else:
                filtered_options_q = list(product_dict.keys())

            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                item_name = st.selectbox(f"Select Product {i+1}", options=filtered_options_q if filtered_options_q else ["No matching product"], key=f"q_item_{i}")
            with cols[1]:
                default_price = product_dict.get(item_name, 0.0) if product_dict and item_name in product_dict else 0.0
                price = st.number_input(f"Rate (RM) {i+1}", value=float(default_price), key=f"q_price_{i}")
            with cols[2]:
                qty = st.number_input(f"Qty {i+1}", min_value=1, value=1, key=f"q_qty_{i}")
            with cols[3]:
                subtotal = price * qty
                st.write(f"**Amt:** RM {subtotal:,.2f}")
                selected_items.append({"item": item_name, "price": price, "qty": qty, "subtotal": subtotal})
                total_calc += subtotal

        submit_quote = st.form_submit_button("💾 CLICK HERE TO GENERATE & SAVE QUOTATION")

    if submit_quote:
        if not client_name:
            st.error("⚠️ Please enter a Client Name.")
        else:
            items_json = json.dumps(selected_items)
            try:
                run_query(
                    "INSERT INTO quotations (quote_no, client_name, client_address, date, valid_until, terms, items_json, total_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (quote_no, client_name, client_address, str(date), str(date), terms, items_json, total_calc),
                    fetch=False,
                )
                html_content, pdf_path = save_quotation_pdf(quote_no, client_name, client_address, str(date), terms, selected_items, total_calc)
                st.success(f"✅ Quotation #{quote_no} successfully saved and stored as PDF in `quotations_folder/`!")

                st.subheader("📄 Generated Quotation Preview")
                components.html(html_content, height=550, scrolling=True)

                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pdf_file:
                        st.download_button("📥 Download This PDF File", pdf_file, file_name=f"Quotation_{quote_no}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Error saving quotation: {e}")

# ==========================================
# 4. VIEW INVOICES & QUOTATIONS
# ==========================================
elif menu == "📂 View Invoices & Quotes":
    st.title("📂 Invoices & Quotations List")
    st.info("💡 **Tip:** Type part of a client name or invoice number in the search box below to quickly find past documents.")
    tab_inv, tab_qt = st.tabs(["🧾 Invoices List", "📑 Quotations List"])

    with tab_inv:
        search_inv = st.text_input("🔍 Search Invoice (by Number or Client Name):")
        query = "SELECT id, invoice_no, client_name, client_address, date, terms, items_json, total_amount, status FROM invoices"
        params = ()
        if search_inv:
            query += " WHERE invoice_no LIKE ? OR client_name LIKE ?"
            params = (f"%{search_inv}%", f"%{search_inv}%")

        invoices = run_query(query, params)
        if invoices:
            inv_options = {f"Inv #{inv[1]} - {inv[2]} (RM {inv[7]:,.2f})": inv for inv in invoices}
            selected_inv_label = st.selectbox("Select invoice from list:", list(inv_options.keys()))
            inv = inv_options[selected_inv_label]

            items = json.loads(inv[6])
            invoice_html, pdf_path = save_invoice_pdf(inv[1], inv[2], inv[3], inv[4], inv[5], items, inv[7], inv[8])
            components.html(invoice_html, height=650, scrolling=True)
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pdf_file:
                        st.download_button("📥 Download Invoice PDF file", pdf_file, file_name=f"Invoice_{inv[1]}.pdf", mime="application/pdf", key="dl_inv_btn")
            with col_d2:
                if st.button("🗑️ Delete Invoice", key="del_inv_btn"):
                    run_query("DELETE FROM invoices WHERE id=?", (inv[0],), fetch=False)
                    st.success(f"✅ Invoice #{inv[1]} deleted successfully!")
                    st.rerun()
        else:
            st.info("No matching invoices found.")

    with tab_qt:
        search_qt = st.text_input("🔍 Search Quotation (by Number or Client Name):", key="search_qt")
        query_qt = "SELECT id, quote_no, client_name, client_address, date, terms, items_json, total_amount FROM quotations"
        params_qt = ()
        if search_qt:
            query_qt += " WHERE quote_no LIKE ? OR client_name LIKE ?"
            params_qt = (f"%{search_qt}%", f"%{search_qt}%")

        quotations = run_query(query_qt, params_qt)
        if quotations:
            qt_options = {f"Quote #{qt[1]} - {qt[2]} (RM {qt[7]:,.2f})": qt for qt in quotations}
            selected_qt_label = st.selectbox("Select quotation from list:", list(qt_options.keys()), key="select_qt_list")
            qt = qt_options[selected_qt_label]

            items = json.loads(qt[6])
            quote_html, pdf_path = save_quotation_pdf(qt[1], qt[2], qt[3], qt[4], qt[5], items, qt[7])
            components.html(quote_html, height=650, scrolling=True)
            
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pdf_file:
                        st.download_button("📥 Download Quotation PDF file", pdf_file, file_name=f"Quotation_{qt[1]}.pdf", mime="application/pdf", key="dl_qt_btn")
            with col_q2:
                if st.button("🗑️ Delete Quotation", key="del_qt_btn"):
                    run_query("DELETE FROM quotations WHERE id=?", (qt[0],), fetch=False)
                    st.success(f"✅ Quotation #{qt[1]} deleted successfully!")
                    st.rerun()
        else:
            st.info("No matching quotations found.")

# ==========================================
# 5. PAYROLL & PAYSLIPS
# ==========================================
elif menu == "💵 Payroll & Payslips":
    st.title("💵 Staff Payroll & Payslips")
    st.info("💡 **Tip:** EPF, SOCSO, and SIP are pre-filled with standard fixed rates but can be edited if needed.")
    tab_create, tab_view = st.tabs(["➕ Create Payslip", "📂 View / Print Payslips"])

    with tab_create:
        with st.form("create_payslip_form"):
            col1, col2 = st.columns(2)
            with col1:
                employee_name = st.text_input("Employee Name", value="", help="Full name of staff member.")
                ic_no = st.text_input("I.C. No", value="", help="Staff IC or Passport number.")
                bank_info = st.text_input("Bank Account Details", value="", help="Bank name and account number.")
            with col2:
                st.write("📅 **Select Payslip Month & Year**")
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    sel_month = st.selectbox("Month", ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], index=datetime.today().month-1)
                with col_m2:
                    sel_year = st.selectbox("Year", [2024, 2025, 2026, 2027], index=2)
                month_year = f"{sel_month} {sel_year}"

                date = st.date_input("Pay Date (Calendar)", value=datetime.today())
                payment_method = st.text_input("Payment Method / Cheque No", value="Autocredit")

            st.divider()
            st.subheader("💰 Salary & Additions")
            
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                basic_salary = st.number_input("Basic Salary (RM)", value=0.00, format="%.2f")
                perfect_attendance = st.number_input("Perfect Attendance (RM)", value=0.00, format="%.2f")
                performance_allowance = st.number_input("Performance Allowance (RM)", value=0.00, format="%.2f")
                transport_allowance = st.number_input("Transport Allowance (RM)", value=100.00, format="%.2f")
            with col_a2:
                outstation_allowance = st.number_input("Outstation Allowance (RM)", value=0.00, format="%.2f")
                last_month_addition = st.number_input("Last Month Addition (RM)", value=0.00, format="%.2f")

            # --- OVERTIME CALCULATION SECTION ---
            st.divider()
            st.subheader("⏱️ Overtime Calculation")
            st.caption("Formula: Basic Salary ÷ 26 Days ÷ 8 Hours × Multiplier × Hours Worked")
            
            hourly_rate = (basic_salary / 26.0 / 8.0) if basic_salary > 0 else 0.0
            st.write(f"Calculated Hourly Rate: **RM {hourly_rate:,.2f} / hour**")

            ot_col1, ot_col2, ot_col3 = st.columns(3)
            with ot_col1:
                ot_15_hours = st.number_input("1.5x OT Hours", min_value=0.0, value=0.0, format="%.2f", key="ot_15_h")
                ot_15_rate = hourly_rate * 1.5
                ot_15_amt = ot_15_rate * ot_15_hours
                st.text(f"Rate: RM {ot_15_rate:.2f}/h\nAmt: RM {ot_15_amt:.2f}")
            with ot_col2:
                ot_20_hours = st.number_input("2.0x OT Hours", min_value=0.0, value=0.0, format="%.2f", key="ot_20_h")
                ot_20_rate = hourly_rate * 2.0
                ot_20_amt = ot_20_rate * ot_20_hours
                st.text(f"Rate: RM {ot_20_rate:.2f}/h\nAmt: RM {ot_20_amt:.2f}")
            with ot_col3:
                ot_30_hours = st.number_input("3.0x OT Hours", min_value=0.0, value=0.0, format="%.2f", key="ot_30_h")
                ot_30_rate = hourly_rate * 3.0
                ot_30_amt = ot_30_rate * ot_30_hours
                st.text(f"Rate: RM {ot_30_rate:.2f}/h\nAmt: RM {ot_30_amt:.2f}")

            total_overtime_amount = ot_15_amt + ot_20_amt + ot_30_amt

            st.divider()
            st.subheader("📉 Deductions")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                epf = st.number_input("EPF (RM)", value=187.00, format="%.2f", help="Fixed standard employee EPF deduction.")
                socso = st.number_input("SOCSO (RM)", value=49.45, format="%.2f", help="Fixed standard employee SOCSO deduction.")
                sip = st.number_input("SIP (Employment Ins. Sch) (RM)", value=6.60, format="%.2f", help="Fixed standard employee SIP deduction.")
            with col_d2:
                loan = st.number_input("Loan Deduction (RM)", value=0.00, format="%.2f")
                unpaid_leave = st.number_input("Unpaid Leave (RM)", value=0.00, format="%.2f")
                last_month_deduction = st.number_input("Last Month Deduction (RM)", value=0.00, format="%.2f")

            additions_dict = {
                "Perfect Attendance": perfect_attendance,
                "Performance Allowance": performance_allowance,
                "Transport Allowance": transport_allowance,
                "Overtime": total_overtime_amount,
                "Outstation Allowance": outstation_allowance,
                "Last Month Addition": last_month_addition,
            }
            deductions_dict = {
                "EPF": epf,
                "SOCSO": socso,
                "SIP (Emplymnt Ins. Sch)": sip,
                "Loan": loan,
                "Unpaid Leave": unpaid_leave,
                "Last Month Deduction": last_month_deduction,
            }

            gross_total = basic_salary + sum(additions_dict.values())
            total_deduction = sum(deductions_dict.values())
            net_pay = gross_total - total_deduction

            st.info(f"**Summary Preview -> Gross Total:** RM {gross_total:,.2f} | **Total Deduction:** RM {total_deduction:,.2f} | **Net Pay:** RM {net_pay:,.2f}")
            submit_payslip = st.form_submit_button("💾 CLICK HERE TO GENERATE & SAVE PAYSLIP")

        if submit_payslip:
            try:
                run_query(
                    "INSERT INTO payroll (payslip_no, employee_name, ic_no, bank_info, month_year, date, basic_salary, additions_json, deductions_json, gross_total, total_deduction, net_pay, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("-", employee_name, ic_no, bank_info, month_year, str(date), basic_salary, json.dumps(additions_dict), json.dumps(deductions_dict), gross_total, total_deduction, net_pay, payment_method),
                    fetch=False,
                )
                html_content, pdf_path = save_payslip_pdf(employee_name, ic_no, bank_info, month_year, str(date), basic_salary, additions_dict, deductions_dict, gross_total, total_deduction, net_pay, payment_method)
                st.success(f"✅ Payslip for {employee_name} ({month_year}) successfully created and saved!")

                st.subheader("📄 Payslip Preview")
                components.html(html_content, height=500, scrolling=True)

                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pdf_file:
                        st.download_button("📥 Download Payslip PDF", pdf_file, file_name=f"Payslip_{employee_name}_{month_year}.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Error saving payslip: {e}")

    with tab_view:
        search_p = st.text_input("🔍 Search Payslip (by Employee Name or Month):")
        query_pr = "SELECT id, payslip_no, employee_name, ic_no, bank_info, month_year, date, basic_salary, additions_json, deductions_json, gross_total, total_deduction, net_pay, payment_method FROM payroll"
        params_pr = ()
        if search_p:
            query_pr += " WHERE employee_name LIKE ? OR month_year LIKE ?"
            params_pr = (f"%{search_p}%", f"%{search_p}%")

        payslips = run_query(query_pr, params_pr)
        if payslips:
            p_options = {f"Payslip - {p[2]} ({p[5]}) [Net: RM {p[12]:,.2f}]": p for p in payslips}
            selected_p_label = st.selectbox("Select payslip to view:", list(p_options.keys()), key="select_payslip_list")
            p_data = p_options[selected_p_label]

            additions_loaded = json.loads(p_data[8])
            deductions_loaded = json.loads(p_data[9])

            html_content, pdf_path = save_payslip_pdf(p_data[2], p_data[3], p_data[4], p_data[5], p_data[6], p_data[7], additions_loaded, deductions_loaded, p_data[10], p_data[11], p_data[12], p_data[13])
            components.html(html_content, height=550, scrolling=True)
            
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pdf_file:
                        st.download_button("📥 Download Selected Payslip PDF", pdf_file, file_name=f"Payslip_{p_data[2]}_{p_data[5]}.pdf", mime="application/pdf", key="dl_pay_btn")
            with col_p2:
                if st.button("🗑️ Delete Payslip", key="del_pay_btn"):
                    run_query("DELETE FROM payroll WHERE id=?", (p_data[0],), fetch=False)
                    st.success(f"✅ Payslip for {p_data[2]} ({p_data[5]}) deleted successfully!")
                    st.rerun()
        else:
            st.info("No saved payslips found.")

# ==========================================
# 6. PRODUCTS & PRICE LIST
# ==========================================
elif menu == "📦 Products & Price List":
    st.title("📦 Products & Price List")
    st.info("💡 **Tip:** Add your products and default prices here once. They will then automatically show up with quick-search when you write invoices and quotations!")
    tab1, tab2 = st.tabs(["➕ Add New Item", "📋 Price List & Search"])

    with tab1:
        with st.form("add_product_form"):
            item_name = st.text_input("Item Name / Description")
            description = st.text_area("Extra Details (Optional)")
            price = st.number_input("Rate / Price (RM)", min_value=0.0, format="%.2f")
            submit_prod = st.form_submit_button("💾 Save Item")

            if submit_prod and item_name:
                try:
                    run_query("INSERT INTO products (item_name, description, price) VALUES (?, ?, ?)", (item_name, description, price), fetch=False)
                    st.success(f"✅ Added '{item_name}' successfully!")
                except Exception as e:
                    st.error(f"Error: {e}")

    with tab2:
        search_price = st.text_input("🔍 Search Price List (by Item Name):")
        query_p = "SELECT id, item_name, description, price FROM products"
        params_p = ()
        if search_price:
            query_p += " WHERE item_name LIKE ?"
            params_p = (f"%{search_price}%",)

        products = run_query(query_p, params_p)
        if products:
            for p in products:
                p_id, p_name, p_desc, p_price = p
                with st.expander(f"🔹 {p_name} — RM {p_price:,.2f}"):
                    with st.form(f"update_form_{p_id}"):
                        new_name = st.text_input("Item Name", value=p_name)
                        new_desc = st.text_area("Description", value=p_desc)
                        new_price = st.number_input("Price (RM)", value=float(p_price), format="%.2f")

                        col1, col2 = st.columns(2)
                        update_btn = col1.form_submit_button("🔄 Update Price")
                        delete_btn = col2.form_submit_button("🗑️ Delete Item")

                        if update_btn:
                            run_query("UPDATE products SET item_name=?, description=?, price=? WHERE id=?", (new_name, new_desc, new_price, p_id), fetch=False)
                            st.success("✅ Updated successfully! Refresh page.")
                        elif delete_btn:
                            run_query("DELETE FROM products WHERE id=?", (p_id,), fetch=False)
                            st.success("✅ Deleted successfully! Refresh page.")
        else:
            st.info("No items found.")

# ==========================================
# 7. WORKER ATTENDANCE
# ==========================================
elif menu == "👥 Worker Attendance":
    st.title("👥 Worker Attendance - Monthly Summary")
    st.info("💡 **Tip:** Track daily attendance easily and view monthly summary reports automatically.")
    col_y, col_m = st.columns(2)
    with col_y:
        selected_year = st.selectbox("Select Year", [2024, 2025, 2026, 2027], index=2)
    with col_m:
        months_dict = {"January": "01", "February": "02", "March": "03", "April": "04", "May": "05", "June": "06", "July": "07", "August": "08", "September": "09", "October": "10", "November": "11", "December": "12"}
        selected_month_name = st.selectbox("Select Month", list(months_dict.keys()), index=9)
        selected_month_num = months_dict[selected_month_name]

    month_prefix = f"{selected_year}-{selected_month_num}"
    tab1, tab2, tab3 = st.tabs(["📅 Monthly Summary Report", "🔍 Monthly Detailed Log", "✏️ Quick Daily Entry"])

    with tab1:
        st.subheader(f"Attendance Summary for {selected_month_name} {selected_year}")
        query_month = "SELECT worker_name, status, COUNT(*) FROM attendance WHERE date LIKE ? GROUP BY worker_name, status"
        month_data = run_query(query_month, (f"{month_prefix}%",))

        workers_list = [r[0] for r in run_query("SELECT DISTINCT worker_name FROM attendance", fetch=True)]
        if not workers_list:
            workers_list = ["Syed Aidil", "Ahmad", "Ali", "Chow", "Muthu"]

        summary_dict = {w: {"Present": 0, "Absent": 0, "Late": 0, "MC": 0} for w in workers_list}
        for row in month_data:
            w_name, status, count = row
            if w_name not in summary_dict:
                summary_dict[w_name] = {"Present": 0, "Absent": 0, "Late": 0, "MC": 0}
            if status in summary_dict[w_name]:
                summary_dict[w_name][status] = count

        summary_rows = []
        for w, counts in summary_dict.items():
            summary_rows.append({
                "Worker Name": w,
                "Present": counts["Present"],
                "Absent": counts["Absent"],
                "Late": counts["Late"],
                "MC": counts["MC"],
                "Total Days Logged": sum(counts.values()),
            })

        if summary_rows:
            df_summary = pd.DataFrame(summary_rows)
            st.dataframe(df_summary, use_container_width=True)
        else:
            st.info(f"No attendance records found for {selected_month_name} {selected_year}.")

    with tab2:
        st.subheader(f"Detailed Logs for {selected_month_name} {selected_year}")
        search_worker = st.text_input("🔍 Filter by Worker Name (Optional):", key="att_search_worker")
        query_detail = "SELECT date, worker_name, status, notes FROM attendance WHERE date LIKE ?"
        params_detail = [f"{month_prefix}%"]
        if search_worker:
            query_detail += " AND worker_name LIKE ?"
            params_detail.append(f"%{search_worker}%")
        query_detail += " ORDER BY date DESC, worker_name ASC"

        detail_data = run_query(query_detail, tuple(params_detail))
        if detail_data:
            df_detail = pd.DataFrame(detail_data, columns=["Date", "Worker Name", "Status", "Notes"])
            st.dataframe(df_detail, use_container_width=True)
        else:
            st.info("No detailed records found for this month.")

    with tab3:
        st.subheader("Quick Daily Entry / Update")
        entry_date = st.date_input("Attendance Date (Calendar)", value=datetime.strptime(f"{month_prefix}-01", "%Y-%m-%d"))
        worker_input = st.text_area(
            "Worker Names (comma separated)",
            value=", ".join([r[0] for r in run_query("SELECT DISTINCT worker_name FROM attendance", fetch=True)] or ["Syed Aidil", "Ahmad", "Ali", "Chow", "Muthu"])
        )
        workers = [w.strip() for w in worker_input.split(",") if w.strip()]

        with st.form("monthly_daily_entry_form"):
            st.write(f"### Checklist for: {entry_date}")
            attendance_data = {}
            for worker in workers:
                cols = st.columns([2, 2, 3])
                with cols[0]:
                    st.write(f"**{worker}**")
                with cols[1]:
                    status = st.selectbox("Status", ["Present", "Absent", "Late", "MC"], key=f"m_status_{worker}")
                with cols[2]:
                    notes = st.text_input("Notes", placeholder="Optional", key=f"m_notes_{worker}")
                attendance_data[worker] = {"status": status, "notes": notes}

            save_att = st.form_submit_button("💾 Save Attendance for this Date")
            if save_att:
                date_str = str(entry_date)
                run_query("DELETE FROM attendance WHERE date=?", (date_str,), fetch=False)
                for worker, data in attendance_data.items():
                    run_query("INSERT INTO attendance (date, worker_name, status, notes) VALUES (?, ?, ?, ?)", (date_str, worker, data["status"], data["notes"]), fetch=False)
                st.success(f"✅ Attendance saved successfully for {date_str}!")

# ==========================================
# 8. EXPENSE TRACKER
# ==========================================
elif menu == "💸 Expense Tracker":
    st.title("💸 Expense Tracker")
    st.info("💡 **Tip:** Log daily business expenses quickly to keep your net profit calculations accurate.")
    with st.form("expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            exp_date = st.date_input("Expense Date (Calendar)", value=datetime.today())
            category = st.selectbox("Category", ["Materials / Supplies", "Worker Wages", "Transport & Fuel", "Utilities", "Others"])
        with col2:
            amount = st.number_input("Amount (RM)", min_value=0.0, format="%.2f")
            description = st.text_input("Description / Vendor")

        submit_exp = st.form_submit_button("💾 Save Expense")
        if submit_exp:
            run_query("INSERT INTO expenses (date, category, description, amount) VALUES (?, ?, ?, ?)", (str(exp_date), category, description, amount), fetch=False)
            st.success(f"✅ Saved expense of RM {amount:,.2f}!")

    st.divider()
    search_exp = st.text_input("🔍 Search Expenses (by Description or Category):")
    query_exp = "SELECT date, category, description, amount FROM expenses"
    params_exp = ()
    if search_exp:
        query_exp += " WHERE category LIKE ? OR description LIKE ?"
        params_exp = (f"%{search_exp}%", f"%{search_exp}%")
    query_exp += " ORDER BY date DESC"

    expenses_data = run_query(query_exp, params_exp)
    if expenses_data:
        df_expenses = pd.DataFrame(expenses_data, columns=["Date", "Category", "Description", "Amount (RM)"])
        st.dataframe(df_expenses, use_container_width=True)
    else:
        st.info("No expenses found.")
