import os
import re
import io
import json
import time
import html
import smtplib
from email.message import EmailMessage
from typing import List, Dict, Any, Optional, Tuple

import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


# ----------------- Redirect Button -----------------
st.set_page_config(page_title="Competitor Discovery AI", layout="wide")
redirect_url = "http://127.0.0.1:5500/pages/homepage.html"  # Replace with your desired URL

st.markdown(
    f"""
    <style>
        .redirect-button {{
            background-color: #007BFF;
            color: white;
            padding: 10px 20px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            border-radius: 8px;
            font-weight: bold;
            font-size: 16px;
        }}
        .redirect-button:hover {{
            background-color: #0056b3;
            color: white;
        }}
        .top-bar {{
            display: flex;
            justify-content: center;
            margin-bottom: 15px;
        }}
    </style>
    <div class="top-bar">
        <a class="redirect-button" href="{redirect_url}" target="_blank">Home</a>
    </div>
    """,
    unsafe_allow_html=True
)



# ----------------- LOAD ENV -----------------
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek/deepseek-chat")
EMAIL_SENDER_ADDRESS = os.getenv("EMAIL_SENDER_ADDRESS")
EMAIL_SENDER_PASSWORD = os.getenv("EMAIL_SENDER_PASSWORD")

# ----------------- EMAIL FUNCTION -----------------
def send_email_with_pdf(to_email, pdf_bytes, filename="Competitor_Report.pdf"):
    msg = EmailMessage()
    msg['Subject'] = "Your Competitor Report is Ready!"
    msg['From'] = EMAIL_SENDER_ADDRESS
    msg['To'] = to_email
    msg.set_content("Hi,\n\nAttached is your generated Competitor Report PDF.\n\nBest regards,\nCompetitor Discovery AI")

    msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=filename)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER_ADDRESS, EMAIL_SENDER_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email sending failed: {e}")
        return False

# ----------------- TITLE -----------------
st.title("🔍 Competitor Discovery & Comparison AI")

# ----------------- INPUTS -----------------
product_name = st.text_input("Enter the name of your product or tool:")
niche = st.text_input("Enter the niche/industry of the product:")

st.markdown("### 🧩 What aspects do you want to compare?")
compare_ui = st.checkbox("User Interface (UI)", value=True)
compare_features = st.checkbox("Features", value=True)
compare_pricing = st.checkbox("Pricing", value=True)
compare_community = st.checkbox("Community Support")
compare_integrations = st.checkbox("Integrations")
compare_performance = st.checkbox("Speed / Performance")
compare_security = st.checkbox("Security / Compliance")
compare_scalability = st.checkbox("Scalability / Enterprise Readiness")

selected_aspects = []
if compare_ui: selected_aspects.append("User Interface")
if compare_features: selected_aspects.append("Features")
if compare_pricing: selected_aspects.append("Pricing")
if compare_community: selected_aspects.append("Community Support")
if compare_integrations: selected_aspects.append("Integrations")
if compare_performance: selected_aspects.append("Speed / Performance")
if compare_security: selected_aspects.append("Security / Compliance")
if compare_scalability: selected_aspects.append("Scalability / Enterprise Readiness")

# ----------------- SERP API -----------------
SERP_SEARCH_URL = "https://serpapi.com/search.json"

def serp_search(query: str, engine: str = "google", num: int = 10) -> Dict[str, Any]:
    params = {
        "engine": engine,
        "q": query,
        "num": num,
        "api_key": SERPAPI_API_KEY,
    }
    try:
        r = requests.get(SERP_SEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[SERP ERROR] {e}")
        return {}

def fetch_product_description(product_name: str, niche: str) -> str:
    query = f"{product_name} {niche} tool description"
    data = serp_search(query)
    description = ""
    for result in data.get("organic_results", []):
        snippet = result.get("snippet")
        if snippet:
            description = snippet
            break
    if not description:
        description = f"{product_name} in the {niche} space."
    return description

# ----------------- LLM CALL -----------------
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

def llm_chat(messages: List[Dict[str, str]], model: Optional[str] = None, temperature: float = 0.2) -> str:
    model = model or LLM_MODEL
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": 1500}
    try:
        res = requests.post(OPENROUTER_CHAT_URL, headers=headers, json=payload, timeout=120)
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"]
    except requests.HTTPError as http_err:
        st.error(f"[LLM ERROR] HTTP {res.status_code}: {res.text}")
    except Exception as e:
        st.error(f"[LLM ERROR] {e}")
    return "⚠️ LLM error. Please retry."


def build_analyst_prompt(product_name: str, description: str, aspects: List[str]) -> str:
    aspects_str = ", ".join(aspects) if aspects else "Pricing, Features, User Interface"
    return f"""
You are an expert SaaS product analyst.

Given the product name and description below:

Product: {product_name}
Description: {description}
Aspects to compare: {aspects_str}

1. Identify 6 direct competitors.
2. Compare all 7 products on these aspects: {aspects_str}.
3. Present the comparison in a markdown table.
4. Highlight strengths and weaknesses of the given input.
5. Recommend best use cases.
6. Improvements needed for the product.
"""

def analyze_competitors(product_name: str, description: str, aspects: List[str]) -> str:
    prompt = build_analyst_prompt(product_name, description, aspects)
    messages = [
        {"role": "system", "content": "You are an expert SaaS product analyst."},
        {"role": "user", "content": prompt},
    ]
    return llm_chat(messages)

# ----------------- TRACKING COMPETITORS -----------------
KNOWN_CHANGELOG_PATTERNS = ["/changelog", "/release-notes", "/releases", "/updates"]

def guess_domain_from_name(name: str) -> Optional[str]:
    data = serp_search(name)
    for res in data.get("organic_results", []):
        link = res.get("link")
        if not link:
            continue
        m = re.match(r"https?://([^/]+)/?", link)
        if m:
            return m.group(1)
    return None

def fetch_changelog_html(url: str, timeout: int = 20) -> Optional[str]:
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[CHANGELOG FETCH ERROR] {url}: {e}")
        return None

def extract_top_text_from_html(html_text: str, max_items: int = 5) -> List[str]:
    soup = BeautifulSoup(html_text, "lxml")
    items: List[str] = []
    for li in soup.select("li"):
        txt = li.get_text(" ", strip=True)
        if txt and len(txt) > 20:
            items.append(txt)
        if len(items) >= max_items:
            break
    return items

def fetch_competitor_updates(name: str, max_items: int = 5) -> List[Tuple[str, str]]:
    snippets: List[Tuple[str, str]] = []
    serp_q = f"{name} changelog"
    data = serp_search(serp_q)
    for res in data.get("organic_results", []):
        snip = res.get("snippet")
        link = res.get("link") or ""
        if snip:
            snippets.append((link, snip))
        if len(snippets) >= max_items:
            break
    if len(snippets) < max_items:
        dom = guess_domain_from_name(name)
        if dom:
            for pat in KNOWN_CHANGELOG_PATTERNS:
                url = f"https://{dom}{pat}"
                html_text = fetch_changelog_html(url)
                if not html_text:
                    continue
                texts = extract_top_text_from_html(html_text, max_items=max_items)
                for t in texts:
                    snippets.append((url, t))
                    if len(snippets) >= max_items:
                        break
    return snippets[:max_items]

def summarize_competitor_updates(name: str, updates: List[Tuple[str, str]]) -> str:
    if not updates:
        return f"No recent updates found for **{name}**."
    lines = [f"- {text} (Source: {src})" for src, text in updates]
    body = "\n".join(lines)
    prompt = f"""
Summarize updates for {name}:
{body}
"""
    messages = [{"role": "user", "content": prompt}]
    return llm_chat(messages)

# ----------------- ANALYSIS BUTTON -----------------
analysis_md = None
if st.button("🔍 Discover Competitors & Analyze"):
    if product_name and niche:
        with st.spinner("Analyzing competitors..."):
            desc = fetch_product_description(product_name, niche)
            analysis_md = analyze_competitors(product_name, desc, selected_aspects)
            st.session_state["analysis_md"] = analysis_md
    else:
        st.warning("Enter both product name and niche.")

if "analysis_md" in st.session_state:
    analysis_md = st.session_state["analysis_md"]

# ----------------- SHOW ANALYSIS -----------------
if analysis_md:
    st.markdown("---")
    st.subheader("🔎 Competitor Analysis Report")
    st.markdown(analysis_md, unsafe_allow_html=True)

    # Export PDF 
    
    st.subheader("📄 Export Report")
    buffer = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CustomBody', fontSize=11, leading=16))
    flow = [Paragraph(line, styles['CustomBody']) for line in analysis_md.split("\n\n")]
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    doc.build(flow)
    pdf_bytes = buffer.getvalue()

    st.download_button("Download PDF", pdf_bytes, file_name="Competitor_Report.pdf", mime="application/pdf")

    

    # Competitor Tracking
   # ------------------------------------------------------------------
# Competitor Tracking with PDF Export
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# Competitor Tracking with PDF Export
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# Competitor Tracking with PDF Export and Email
# ------------------------------------------------------------------
st.markdown("---")
st.subheader("📢 Monitor Competitor Updates")

competitors = st.text_input("Enter competitor names (comma separated):")

if st.button("Fetch Updates"):
    if competitors.strip():
        comp_list = [c.strip() for c in competitors.split(",") if c.strip()]
        all_updates_md = ""

        with st.spinner("⏳ Fetching competitor updates..."):
            for comp in comp_list:
                updates = fetch_competitor_updates(comp)
                summary = summarize_competitor_updates(comp, updates)

                st.markdown(f"### 🔍 {comp}")
                st.markdown(summary)
                all_updates_md += f"## {comp}\n\n{summary}\n\n"

        st.success("✅ Updates fetched successfully!")

        # Generate PDF and store in session state
        if all_updates_md.strip():
            track_buffer = BytesIO()
            styles = getSampleStyleSheet()
            styles.add(ParagraphStyle(name='CustomBody', fontSize=11, leading=16, textColor=colors.black))
            link_style = ParagraphStyle(name='Link', fontSize=11, textColor=colors.HexColor("#0000FF"))

            flow = []
            for line in all_updates_md.split("\n\n"):
                if "http" in line:  # Make links blue
                    flow.append(Paragraph(f"<font color='blue'>{line}</font>", link_style))
                else:
                    flow.append(Paragraph(line, styles['CustomBody']))
                flow.append(Spacer(1, 8))

            track_doc = SimpleDocTemplate(track_buffer, pagesize=A4)
            track_doc.build(flow)
            st.session_state.track_pdf_bytes = track_buffer.getvalue()

    else:
        st.warning("Please enter competitor names to fetch updates.")

# Show Download and Email buttons if PDF exists
if "track_pdf_bytes" in st.session_state:
    st.download_button(
        "📄 Download Competitor Updates (PDF)",
        st.session_state.track_pdf_bytes,
        file_name="Competitor_Tracking_Report.pdf",
        mime="application/pdf"
    )

    email = st.text_input("Enter your email to receive the report:")
    if st.button("Send Report via Email"):
        if email:
            if send_email_with_pdf(email, st.session_state.track_pdf_bytes):
                st.success("✅ Email sent successfully!")
        else:
            st.warning("Please enter a valid email.")

    else:
        st.warning("Please enter competitor names to fetch updates.")
