import os
import streamlit as st
import pdfplumber
import docx
import google.generativeai as genai
from dotenv import load_dotenv
import pandas as pd
import json
import re

# --- Load API key ---
# Assumes GEMINI_API_KEY is set in a .env file or environment variable
load_dotenv()
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    else:
        # st.warning("GEMINI_API_KEY is not configured. Analysis functions will return fallback messages.")
        pass # Suppress warning on every load for cleaner UX
except Exception as e:
    st.error(f"Error configuring Gemini API: {e}. Please ensure GEMINI_API_KEY is set.")

# --- Risk color mapping (RAG) ---
risk_colors = {"GREEN": "green", "AMBER": "gold", "RED": "red", "Low": "green", "Medium": "gold", "High": "red"} 

# Define the 8 Main Heads for reference
BUCKET_HEADERS = [
    "Services & Scope", "Commercials & Pricing", "Invoicing/Acceptance/Disputes", 
    "Risk/Liability/Indemnities", "Compliance", "Remedies/Termination", 
    "IP/Confidentiality/Data/Security", "Assumptions/Dependencies"
]

# --- Helper: Extract text from uploaded file ---
def extract_text(file):
    if file.name.endswith(".pdf"):
        text = ""
        try:
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            st.error(f"Error extracting PDF text: {e}")
            return ""
        return text
    elif file.name.endswith(".docx"):
        try:
            doc = docx.Document(file)
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            st.error(f"Error extracting DOCX text: {e}")
            return ""
    else:  # TXT
        return file.read().decode("utf-8")

# --- Helper: Ask Gemini (Updated for complex JSON output) ---
def ask_gemini(prompt):
    if not os.getenv("GEMINI_API_KEY"):
        return "Analysis failed: Gemini API key is not configured."
        
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        st.error(f"Gemini API call failed: {e}")
        return "Analysis failed due to API error."

# --- Master Prompt Generation Function ---
def generate_analyst_prompt(contract_text):
    return f"""
Act as a senior contracts analyst with deep experience interpreting MSAs/SOWs. Your goal is to generate a comprehensive, structured risk report based on the provided contract text.

You MUST return a single JSON object that strictly conforms to the structure defined below. Do not include any text outside the JSON object or any markdown fences (like ```json).

The contract text to analyze is:
---
{contract_text}
---

***

# JSON Structure Requirements (Same as previous, required for parsing)

1.  **"TandCs_Summary"** (OBJECT): This contains the summarized clauses, risks, and solutions for the 8 Main Heads.
    * Each of the 8 Main Heads must be a key (e.g., "Services & Scope").
    * Each Main Head value must be an OBJECT with three keys: "Clauses" (LIST of strings, max 2 lines each), "Risks" (LIST of strings), "Solutions" (LIST of strings). Use "Not stated" as the item if information is unavailable.

2.  **"Risk_Categorization"** (OBJECT): This contains the results of Task 2.
    * **"Parameters"** (LIST of strings): List the parameters (Impact and Likelihood) considered for the categorization matrix.
    * **"Risk_Table"** (LIST of objects): The final categorized risk table. Each object must have these keys: "Main Head", "Subhead", "Identified Risk", "Clause Reference", "Final Risk Rating" (string, must be one of: RED, AMBER, GREEN).

3.  **"Final_Dashboard"** (OBJECT): This contains the comprehensive summary dashboard data.
    * **"Contract_Summary"** (OBJECT): Keys: "Start Date", "End Date", "Governing MSA", "Service Model".
    * **"Commercial_Snapshot"** (OBJECT): Keys: "Pricing Model", "VNF Base Volume", "Invoicing Trigger", "Cloud Cost Treatment".
    * **"Key_Financial_Metric_Risks"** (LIST of strings): List of critical financial risks (e.g., related to Automation/Profitability, Delay Liability, Shortfall Credit).
    * **"Top_5_High_Risks"** (LIST of strings): The five highest-rated (RED RAG) risks.
    * **"Final_Contract_Score"** (OBJECT): Keys: "WCRI", "Commercial Certainty", "Service Delivery Control", "Risk & Liability Caps", "Clarity & Completeness". All values must be valid numbers (0-100 for scores).

***
# Task Instructions

# Task 1: Summarize Key T&Cs
- Summarize key T&Cs that impact commercials and finance.
- Group under the fixed main heads/subheads listed below.
- Each clause must be concise (≤2 lines).
- Provide references to the corresponding agreement (e.g., Section 3.1).

**Main Heads/Subheads:**
Services & Scope: nature, deliverables, SLAs, locations, resource mix, exclusions, change control
Commercials & Pricing: model, rate card, milestones/billing triggers, minimums, indexation/COLA, currency/taxes, expenses, credits/rebates, discounts, advance/retention/holdbacks
Invoicing/Acceptance/Disputes: invoice frequency/docs, acceptance, payment terms, late fees, dispute process, partial payments, audit rights
Risk/Liability/Indemnities: caps, carve-outs, excluded damages, IP/data/third-party indemnities, vendor responsibilities, misconduct carve-outs
Compliance: regulatory/legal, security, audit/monitor, service credits, penalties/LDs, cure, suspension
Remedies/Termination: convenience/cause, notice/cure, step-in, transition/exit, termination fees, continuity, remedies
IP/Confidentiality/Data/Security: ownership, background vs foreground IP, licenses, confidentiality term/exclusions, data duties, breach notice, security controls, SOW deviations
Assumptions/Dependencies: customer duties, staffing assumptions, tool/env access, third-party deps, risks if fail, material impact

# Task 2: Risk Categorization and RAG Coding
- **High Impact Drivers:** Scope Creep, Schedule Variance, Litigation, and Commercial Impact must be treated as High Impact.
- **Matrix:** Apply a standard Risk Categorization Matrix (Impact x Likelihood, e.g., 5x5) to assign the Final Risk Rating (RED, AMBER, GREEN).

Return ONLY the single, complete JSON object.
"""

# --- Streamlit app setup ---
st.set_page_config(page_title="Contract Risk Analyst Dashboard", layout="wide")

# --- Initialize session state ---
if "page" not in st.session_state:
    st.session_state.page = "summary"
if "contract_text" not in st.session_state:
    st.session_state.contract_text = ""
if "full_report" not in st.session_state:
    st.session_state.full_report = {} 
if "show_risk_table" not in st.session_state:
    st.session_state.show_risk_table = False
if "active_bucket" not in st.session_state: # New state to track the clicked bucket
    st.session_state.active_bucket = None

# REMOVED EMOJI from title
st.title("Contract Risk Analyzer")

# --- Custom Styling for Tables ---
def style_general_table(df):
    """
    Applies custom styling for two-column tables:
    - Dark gray header.
    - First data column (Metric/Category) background is light gray.
    - Second data column (Value/Score) background is white.
    - IMPORTANT: Force text wrapping and set max-width for better display of long text.
    """
    
    # 1. Row-wise coloring logic for data cells
    def highlight_columns(s):
        # s is a pandas Series (a row of the DataFrame)
        # First column (index 0) is light gray, second (index 1) is white.
        return [
            'background-color: #f0f0f0; color: black; white-space: normal; max-width: 300px;', # Metric/Category column (Light Gray)
            'background-color: white; color: black; white-space: normal; max-width: 400px;'   # Value/Score column (White)
        ]

    # 2. Header styling
    header_styles = [
        {'selector': 'th', 'props': [
            ('background-color', '#333333'), 
            ('color', 'white'), 
            ('font-weight', 'bold')
        ]}
    ]
    
    # Apply row-wise coloring, then header styles
    styled_df = df.style.apply(highlight_columns, axis=1)
    return styled_df.set_table_styles(header_styles, overwrite=False)


# --- Helper: Extract text from uploaded file ---
# (Function extract_text remains the same)

# --- Helper: Ask Gemini (Updated for complex JSON output) ---
# (Function ask_gemini remains the same)

# --- Master Prompt Generation Function ---
# (Function generate_analyst_prompt remains the same)


# --- PAGE 1: Input (Only Uploader and Analyze Button) ---
if st.session_state.page == "summary":
    st.header("Upload Contract for Review")
    st.info("Upload your Statement of Work (SOW) or Master Service Agreement (MSA) below to begin the detailed risk analysis.")
    
    uploaded = st.file_uploader("Upload your contract (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])

    if uploaded and st.button("Analyze Contract"):
        with st.spinner("Analyzing contract, please wait (this is a complex, multi-task analysis and may take a moment)..."):
            st.session_state.contract_text = extract_text(uploaded)
            if not st.session_state.contract_text:
                st.error("Could not extract text from the file. Please check the file format.")
                st.session_state.full_report = {}
                st.stop()

            # Generate the master prompt
            analyst_prompt = generate_analyst_prompt(st.session_state.contract_text)
            details_text = ask_gemini(analyst_prompt)

            # --- Parse single JSON output for the full report ---
            try:
                clean_text = details_text.strip().replace("```json", "").replace("```", "")
                st.session_state.full_report = json.loads(clean_text)
                
                if not all(k in st.session_state.full_report for k in ["Final_Dashboard", "TandCs_Summary", "Risk_Categorization"]):
                    raise ValueError("JSON structure is incomplete or missing required keys.")
                
                # Success: Move to the detailed dashboard page
                st.session_state.page = "details"
                st.session_state.show_risk_table = True # Show the risk table by default now, since it is higher up
                st.session_state.active_bucket = None # Reset active bucket on new analysis
                st.rerun()

            except (json.JSONDecodeError, ValueError) as e:
                st.error(f"Error parsing full analysis report: {e}. The AI may not have returned a valid JSON structure. Please try simplifying the contract text or re-running the analysis.")
                st.session_state.full_report = {}
                # st.write(f"Raw Response: {details_text}") # Debugging aid


# --- PAGE 2: Output (Full Dashboard) ---
elif st.session_state.page == "details":
    
    if not st.session_state.full_report.get("Final_Dashboard"):
        st.warning("Analysis data is missing. Please go back to the summary page and re-run the analysis.")
        if st.button("← Go Back to Input"):
            st.session_state.page = "summary"
            st.rerun()
        st.stop() 

    dashboard = st.session_state.full_report["Final_Dashboard"]
    tcs_summary = st.session_state.full_report.get("TandCs_Summary", {})
    risk_cat_data = st.session_state.full_report.get("Risk_Categorization", {})
    risk_table_list = risk_cat_data.get("Risk_Table", [])

    # --- Inject Custom CSS for Scrollable Lists and Table Text Wrapping ---
    # UPDATED: Set fixed height to 305px and enforced black text color for visibility.
    st.markdown("""
    <style>
    /* Fixed Height Container for Risk Lists (Aligns with two tables on the left) */
    .scrollable-list-box {
        height: 305px; /* Adjusted height to 305px for precise vertical alignment */
        overflow-y: auto; 
        padding: 10px; 
        border: 1px solid #ddd; 
        border-radius: 6px;
        background-color: #ffffff; 
        margin-bottom: 20px; 
        color: #000000 !important; /* FORCED BLACK TEXT COLOR */
    }
    .scrollable-list-box ul {
        padding-left: 20px;
        margin-top: 5px;
        list-style-type: disc;
    }
    .scrollable-list-box li {
        margin-bottom: 5px;
        font-size: 14px;
        color: #000000 !important; /* Ensure list items are also black */
    }
    
    /* General Styling for forcing wrapping in dataframes */
    .stDataFrame td, .stDataFrame th {
        white-space: normal !important; 
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.header("Comprehensive Contract Risk Dashboard")
    
    # ----------------------------------------------------
    # TOP SECTION: WCRI and Risk Counts (Fixed Height/Layout)
    # ----------------------------------------------------
    score_data = dashboard.get("Final_Contract_Score", {})
    
    # Calculate RAG counts from the Risk Table
    risk_counts = {"RED": 0, "AMBER": 0, "GREEN": 0}
    for item in risk_table_list:
        rating = item.get("Final Risk Rating", "").upper()
        if rating in risk_counts:
            risk_counts[rating] += 1
    
    # NOTE: The variable 'wcr_score' used in the f-string below seems to be a typo for 'wcri_score'.
    # Assuming 'wcri_score' is intended for consistency.
    wcri_score = score_data.get("WCRI", 0) 
    total_risks = sum(risk_counts.values())
    high_risks = risk_counts["RED"]

    # Modified columns to show WCRI, Total Risks, and High Risks
    col_wcri, col_total, col_high = st.columns([1.5, 1, 1])

    # 1. Overall Risk Score in Percentage (Using 3-line structure for alignment)
    with col_wcri:
        # Using wcr_score variable here causes an error as it's not defined, replacing with wcri_score
        wcri_color = risk_colors.get("RED" if wcri_score < 50 else ("AMBER" if wcri_score < 75 else "GREEN"), "gray")
        st.markdown(
            f"""
            <div style='
                border-left: 8px solid {wcri_color};
                border-radius: 8px;
                padding: 15px;
                background-color: #f0f2f6;
                text-align: center;
                /* Enhanced Shadow */
                box-shadow: 0 6px 15px rgba(0, 0, 0, 0.25); 
            '>
                <p style='margin: 0; font-size: 14px; color: #555;'>Weighted Contract Risk Index (WCRI)</p>
                <h3 style='margin: 5px 0 0 0; font-size: 36px; color: {wcri_color};'>{wcri_score:.1f}%</h3>
                <p style='margin: 0; font-size: 12px; color: #555;'>Score out of 100 (Higher is better)</p>
            </div>
            """, 
            unsafe_allow_html=True
        )

    # 2. Total Number of Risks (Using 3-line structure for alignment)
    with col_total:
        st.markdown(
            f"""
            <div style='
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                text-align: center;
                background-color: #ffffff;
                /* Enhanced Shadow */
                box-shadow: 0 6px 15px rgba(0, 0, 0, 0.15);
            '>
                <p style='margin: 0; font-size: 14px; color: #555;'>Total Identified Risks</p>
                <h3 style='color: #4A90E2; margin: 5px 0 0 0; font-size: 36px;'>{total_risks}</h3>
                <p style='margin: 0; font-size: 12px; color: #555;'>Across all categories</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 3. High Risk Number (RED) (Using 3-line structure for alignment)
    with col_high:
        color = risk_colors["RED"]
        st.markdown(
            f"""
            <div style='
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 15px;
                text-align: center;
                background-color: #ffffff;
                /* Enhanced Shadow */
                box-shadow: 0 6px 15px rgba(0, 0, 0, 0.15);
            '>
                <p style='margin: 0; font-size: 14px; color: #555;'>Number of Critical Risks</p>
                <h3 style='color: {color}; margin: 5px 0 0 0; font-size: 36px;'>{high_risks}</h3>
                <p style='margin: 0; font-size: 12px; color: #555;'>Requires immediate mitigation</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ----------------------------------------------------
    # MIDDLE SECTION: Summary Tables and Top Risks (Aligned 2x2)
    # ----------------------------------------------------

    st.markdown("### Contract Details and Risk Scores")
    
    # Contract Summary Table
    summary = dashboard.get("Contract_Summary", {})
    snapshot = dashboard.get("Commercial_Snapshot", {})

    col_tables, col_risks = st.columns([1, 1])
    
    with col_tables:
        st.markdown("#### Contract & Commercial Snapshot")
        summary_data = {
            "Start Date": summary.get("Start Date", "N/A"),
            "End Date": summary.get("End Date", "N/A"),
            "Governing MSA": summary.get("Governing MSA", "N/A"),
            "Service Model": summary.get("Service Model", "N/A"),
            "Pricing Model": snapshot.get("Pricing Model", "N/A"),
            "VNF Base Volume": snapshot.get("VNF Base Volume", "N/A"),
            "Invoicing Trigger": snapshot.get("Invoicing Trigger", "N/A"),
            "Cloud Cost Treatment": snapshot.get("Cloud Cost Treatment", "N/A"),
        }
        # Convert to DataFrame and style for better visual
        df_summary = pd.DataFrame(list(summary_data.items()), columns=['Metric', 'Value'])
        # Apply custom styling
        st.dataframe(style_general_table(df_summary), use_container_width=True, hide_index=True)

        # Risk Score Table (WCRI Breakdown)
        st.markdown("#### Weighted Contract Risk Index (WCRI) Breakdown")
        score_items = [(k, f"{v:.0f}/100") for k, v in score_data.items() if k != "WCRI"]
        df_score = pd.DataFrame(score_items, columns=['Category', 'Score'])
        # Apply custom styling
        st.dataframe(style_general_table(df_score), use_container_width=True, hide_index=True)

    with col_risks:
        # Commercial/Financial Data (Key Financial Metric Risks)
        st.markdown("#### Key Financial Metric Risks")
        financial_risks = dashboard.get("Key_Financial_Metric_Risks", ["Not stated."])
        
        # Wrapped in a fixed-height scrollable container
        st.markdown(
            f"""
            <div class='scrollable-list-box'>
            <ul>
            {"".join(f"<li>{r}</li>" for r in financial_risks)}
            </ul>
            </div>
            """, 
            unsafe_allow_html=True
        )

        # Top 5 High Risks (RED RAG)
        st.markdown("#### Top 5 High Risks")
        top_risks = dashboard.get("Top_5_High_Risks", ["Not stated."])
        
        # Wrapped in a fixed-height scrollable container
        st.markdown(
            f"""
            <div class='scrollable-list-box'>
            <ul>
            {"".join(f"<li>{r}</li>" for r in top_risks)}
            </ul>
            </div>
            """, 
            unsafe_allow_html=True
        )
    
    st.markdown("---")

    # ----------------------------------------------------
    # 1. Risk Table 
    # ----------------------------------------------------

    st.markdown("## RAG-Coded Risk Table")
    
    # Hide/Show logic toggle
    if st.button("Toggle Risk Table Visibility", use_container_width=True):
        st.session_state.show_risk_table = not st.session_state.show_risk_table
        st.rerun()

    if st.session_state.show_risk_table:
        if risk_table_list:
            df_risks = pd.DataFrame(risk_table_list)
            
            # 1. Define header style (matching the other tables)
            header_styles_risk = [
                {'selector': 'th', 'props': [('background-color', '#333333'), ('color', 'white'), ('font-weight', 'bold')]}
            ]

            # 2. Define function for RAG coloring in the last column
            def color_risk_rating(val):
                color = risk_colors.get(str(val).upper(), 'white')
                if val in risk_colors:
                    return f'background-color: {color}; color: white; font-weight: bold;'
                return 'background-color: white; color: black;'

            # Define general cell properties for wrapping and max-width
            cell_props = [{'selector': 'td', 'props': [
                ('white-space', 'normal'),  # Force wrapping
                ('max-width', '250px'),     # Set max width to encourage wrapping
                ('text-align', 'left')      # Ensure alignment is left
            ]}]

            # Apply general white background, RAG colors for the rating, and new header style
            styled_df = (
                df_risks.style
                .map(lambda x: 'background-color: white; color: black;') # Default background for all data cells
                .applymap(color_risk_rating, subset=['Final Risk Rating']) # Apply RAG color to the specific column
                .set_table_styles(header_styles_risk + cell_props, overwrite=False) # Apply header and cell properties
            )
            
            # Use fixed height for the Risk Table for better alignment if needed, or rely on wrapper
            st.dataframe(styled_df, use_container_width=True, hide_index=True)

        else:
            st.warning("No risk data was returned in the structured report.")
            
    st.markdown("---")

    # ----------------------------------------------------
    # 2. 8 Buckets (4x2 Grid Layout & Full-Width Content)
    # ----------------------------------------------------

    st.markdown("## Detailed T&Cs Summary and Analysis (8 Buckets)")
    st.info("Click on any category box below to view the Key Clauses, Risks, and Solutions.")

    def render_tcs_summary_button(bucket, column):
        """Renders a button styled like a box and updates the active_bucket state on click."""
        
        with column:
            # Custom CSS to style the st.button widget to look like the old styled container
            # The CSS targets the button based on the unique key to prevent leakage
            button_key = bucket.replace(' ', '-').replace('/', '-')
            
            # --- START DESIGN IMPROVEMENT: Match WCRI Card Style ---
            button_style = f"""
            <style>
                /* Style for the button itself (not the container) */
                .stButton[data-testid="stButton-btn-{button_key}"] > button {{
                    /* Background similar to WCRI card */
                    background-color: #f0f2f6; 
                    color: #333333; /* Dark text */
                    
                    /* Structure & Shape */
                    border: none; /* Remove standard border */
                    border-left: 8px solid #4A90E2; /* Prominent left border (using blue accent) */
                    border-radius: 8px; 
                    padding: 15px 10px 15px 15px; /* Adjust padding due to thick left border */
                    margin: 0 0 15px 0; 
                    width: 100%;
                    
                    /* Stronger Shadow to match WCRI dashboard card (0.2 is close to 0.25) */
                    box-shadow: 0 6px 15px rgba(0, 0, 0, 0.2);
                    
                    /* Typography & Layout */
                    font-weight: 700;
                    font-size: 16px; 
                    height: 85px; 
                    line-height: 1.3;
                    text-align: center; 
                    transition: all 0.2s ease;
                }}
                
                /* Hover effect to show interactivity */
                .stButton[data-testid="stButton-btn-{button_key}"] > button:hover {{
                    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3); /* Slightly stronger hover shadow */
                    transform: translateY(-2px); 
                    /* Use pure white background on hover for a lift effect */
                    background-color: white; 
                }}
            </style>
            """
            # --- END DESIGN IMPROVEMENT ---
            
            st.markdown(button_style, unsafe_allow_html=True)
            
            # Use a unique key for the button based on the bucket name
            if st.button(bucket, key=f"btn_{button_key}"):
                # Toggle: if the active bucket is clicked again, close it (set to None)
                if st.session_state.active_bucket == bucket:
                    st.session_state.active_bucket = None
                else:
                    st.session_state.active_bucket = bucket
                st.rerun() # Rerun to trigger content display instantly


    # Render the 4x2 grid of buttons (Titles only)
    
    # First Row (4 columns)
    cols1 = st.columns(4)
    for i in range(4):
        render_tcs_summary_button(BUCKET_HEADERS[i], cols1[i])
        
    # Second Row (4 columns)
    cols2 = st.columns(4)
    for i in range(4):
        render_tcs_summary_button(BUCKET_HEADERS[i+4], cols2[i])

    # ----------------------------------------------------
    # Full-Width Content Display (appears below the grid)
    # ----------------------------------------------------
    if st.session_state.active_bucket:
        active_bucket = st.session_state["active_bucket"]
        data = tcs_summary.get(active_bucket, {"Clauses": ["N/A"], "Risks": ["N/A"], "Solutions": ["N/A"]})

        st.markdown(f"---")
        st.markdown(f"### Details for: {active_bucket}")
        
        # --- Create and Style the Combined Table (Refactored to 3-Column Layout) ---
        
        # 1. Extract raw data lists
        clauses = data["Clauses"]
        risks = data["Risks"]
        solutions = data["Solutions"]
        
        # 2. Determine the maximum length for uniform columns
        max_len = max(len(clauses), len(risks), len(solutions))
        
        # 3. Pad shorter lists with 'N/A'
        # Note: We must ensure the list lengths are equal for DataFrame construction
        clauses_list = (clauses + ["N/A"] * max_len)[:max_len]
        risks_list = (risks + ["N/A"] * max_len)[:max_len]
        solutions_list = (solutions + ["N/A"] * max_len)[:max_len]

        # 4. Create DataFrame with three horizontal columns
        df_bucket = pd.DataFrame({
            'Key Clause': clauses_list,
            'Identified Risk': risks_list,
            'Solution/Mitigation': solutions_list
        })
        
        # 5. Define custom styling for the new 3-column table
        def style_bucket_table(df):
            # Define header style
            header_styles_bucket = [
                {'selector': 'th', 'props': [('background-color', '#333333'), ('color', 'white'), ('font-weight', 'bold')]}
            ]
            
            # Define cell properties for wrapping and max-width (applied to all data cells)
            cell_props = [{'selector': 'td', 'props': [
                ('white-space', 'normal'),
                ('max-width', '300px'),
                ('text-align', 'left')
            ]}]

            # Apply styling 
            return (
                df.style
                .set_table_styles(header_styles_bucket + cell_props, overwrite=False) 
            )


        # 6. Display the styled table
        st.dataframe(
            style_bucket_table(df_bucket), 
            use_container_width=True, 
            hide_index=True
        )

    # Back to Summary Button
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("← Back to Input Page"):
        st.session_state.page = "summary"
        st.rerun()