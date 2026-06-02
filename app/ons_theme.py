"""
ons_theme.py

Operating Narcisystem — premium organic dark-mode theme.
Derived from ONS logo: charcoal-olive backgrounds, forest green brand,
warm cream text, amber accent.

Palette:
  --bg-main:       #2C312E  (charcoal-olive canvas)
  --bg-surface:    #373D39  (card / widget surface)
  --bg-raised:     #404740  (inputs, hover states)
  --brand-primary: #0B5324  (forest green — brand accent)
  --brand-light:   #1a7a38  (lighter green for hovers)
  --text-primary:  #F5EFEB  (warm cream — headers, critical text)
  --text-muted:    #A9B2AC  (desaturated gray-green — secondary text)
  --accent-orange: #D97706  (amber — progress, live, alerts)
  --border:        #434A45  (subtle surface separator)
  --border-brand:  rgba(11,83,36,0.6)
"""

import streamlit as st


ONS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Root variables ────────────────────────────────────────────── */
:root {
  --bg-main:       #2C312E;
  --bg-surface:    #373D39;
  --bg-raised:     #404740;
  --brand-primary: #0B5324;
  --brand-light:   #1a7a38;
  --text-primary:  #F5EFEB;
  --text-muted:    #A9B2AC;
  --accent-orange: #D97706;
  --accent-amber:  #F59E0B;
  --border:        #434A45;
  --border-brand:  rgba(11,83,36,0.5);
  --green-glow:    rgba(11,83,36,0.15);
  --orange-glow:   rgba(217,119,6,0.15);
}

/* ── Global reset & font ──────────────────────────────────────── */
@font-face {
  font-family: 'Inter';
  font-display: swap;
}

html, body, .stApp, p, div, span, label, a, li, td, th,
[class*="st-"], [data-testid] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont,
               'Segoe UI', system-ui, sans-serif !important;
  -webkit-font-smoothing: antialiased !important;
  -moz-osx-font-smoothing: grayscale !important;
}

/* ── App canvas ───────────────────────────────────────────────── */
.stApp {
  background-color: var(--bg-main) !important;
  background-image:
    radial-gradient(ellipse at 15% 0%, rgba(11,83,36,0.08) 0%, transparent 55%),
    radial-gradient(ellipse at 85% 100%, rgba(217,119,6,0.04) 0%, transparent 55%);
}

/* ── Sidebar ──────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
  background-color: var(--bg-surface) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * {
  font-family: 'Inter', sans-serif !important;
}

/* ── Typography ───────────────────────────────────────────────── */
html, body, .stApp, p, div, span, label {
  color: var(--text-primary) !important;
}

h1 {
  font-family: 'Inter', sans-serif !important;
  font-weight: 700 !important;
  font-size: 1.75rem !important;
  color: var(--text-primary) !important;
  letter-spacing: -0.5px !important;
  border-bottom: 2px solid var(--brand-primary) !important;
  padding-bottom: 0.4em !important;
  margin-bottom: 0.6em !important;
  text-shadow: none !important;
}

h2 {
  font-family: 'Inter', sans-serif !important;
  font-weight: 600 !important;
  color: var(--text-primary) !important;
  letter-spacing: 0.5px !important;
  text-transform: uppercase !important;
  font-size: 0.8rem !important;
  border-left: 3px solid var(--brand-primary) !important;
  padding-left: 0.6em !important;
  margin-top: 1.2em !important;
}

h3 {
  font-family: 'Inter', sans-serif !important;
  font-weight: 500 !important;
  color: var(--text-muted) !important;
  letter-spacing: 1px !important;
  font-size: 0.8rem !important;
  text-transform: uppercase !important;
}

/* Caption / small text */
.stMarkdown small, .stCaption, [data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
  font-family: 'Inter', sans-serif !important;
  color: var(--text-muted) !important;
  letter-spacing: 0.3px !important;
  font-size: 0.72rem !important;
  text-transform: none !important;
}

/* Links */
a { color: var(--brand-light) !important; text-decoration: none !important; }
a:hover { color: var(--text-primary) !important; }

/* ── Metric cards ─────────────────────────────────────────────── */
[data-testid="stMetric"] {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-top: 2px solid var(--brand-primary) !important;
  border-radius: 6px !important;
  padding: 0.9rem 1rem !important;
  position: relative !important;
}
[data-testid="stMetricLabel"] {
  font-family: 'Inter', sans-serif !important;
  font-weight: 500 !important;
  color: var(--text-muted) !important;
  letter-spacing: 0.5px !important;
  text-transform: uppercase !important;
  font-size: 0.62rem !important;
}
[data-testid="stMetricValue"] {
  font-family: 'Inter', sans-serif !important;
  font-weight: 700 !important;
  color: var(--text-primary) !important;
  font-size: 1.8rem !important;
  letter-spacing: -0.5px !important;
}
[data-testid="stMetricDelta"] {
  font-family: 'Inter', sans-serif !important;
  font-size: 0.75rem !important;
  font-weight: 500 !important;
}

/* ── Progress bars ────────────────────────────────────────────── */
[data-testid="stProgressBar"] > div {
  background-color: var(--bg-raised) !important;
  border-radius: 2px !important;
  height: 5px !important;
}
[data-testid="stProgressBar"] > div > div {
  background: linear-gradient(90deg, var(--brand-primary), var(--accent-orange)) !important;
  border-radius: 2px !important;
}

/* ── Buttons ──────────────────────────────────────────────────── */
.stButton > button {
  background-color: transparent !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 500 !important;
  letter-spacing: 0.3px !important;
  font-size: 0.8rem !important;
  border-radius: 5px !important;
  transition: all 0.15s !important;
}
.stButton > button:hover {
  background-color: var(--bg-raised) !important;
  border-color: var(--brand-primary) !important;
}
.stButton > button[kind="primary"] {
  background-color: var(--brand-primary) !important;
  border-color: var(--brand-primary) !important;
  color: var(--text-primary) !important;
}
.stButton > button[kind="primary"]:hover {
  background-color: var(--brand-light) !important;
}

/* ── Dividers ─────────────────────────────────────────────────── */
hr {
  border: none !important;
  border-top: 1px solid var(--border) !important;
  margin: 1.5rem 0 !important;
}

/* ── Containers with border ───────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
  background-color: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
}

/* ── Dataframes ───────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
}

/* ── Expanders ────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
  background: var(--bg-surface) !important;
}
[data-testid="stExpander"] summary {
  font-family: 'Inter', sans-serif !important;
  font-weight: 500 !important;
  letter-spacing: 0.3px !important;
  text-transform: uppercase !important;
  font-size: 0.75rem !important;
  color: var(--text-muted) !important;
}

/* ── Selectboxes / inputs ─────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stSelectbox"] > div > div > div {
  background-color: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 5px !important;
  color: var(--text-primary) !important;
}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
  background-color: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 5px !important;
  color: var(--text-primary) !important;
}

/* ── Segmented control / pills ────────────────────────────────── */
[data-testid="stSegmentedControl"] {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  border-radius: 5px !important;
}
[data-testid="stSegmentedControl"] [role="radio"][aria-checked="true"] {
  background: var(--brand-primary) !important;
  color: var(--text-primary) !important;
}

/* ── Checkboxes / toggles ─────────────────────────────────────── */
[data-testid="stCheckbox"] label,
[data-testid="stToggle"] label {
  font-family: 'Inter', sans-serif !important;
  color: var(--text-primary) !important;
}

/* ── Alerts ───────────────────────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 5px !important;
  border-left: 3px solid var(--brand-primary) !important;
  background: var(--green-glow) !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="positive"] {
  border-left-color: var(--brand-primary) !important;
  background: var(--green-glow) !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
  border-left-color: var(--accent-orange) !important;
  background: var(--orange-glow) !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="error"] {
  border-left-color: #dc2626 !important;
  background: rgba(220,38,38,0.08) !important;
}

/* ── Tabs ─────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
  border-bottom: 1px solid var(--border) !important;
  gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
  font-family: 'Inter', sans-serif !important;
  font-weight: 500 !important;
  letter-spacing: 0.3px !important;
  text-transform: uppercase !important;
  font-size: 0.72rem !important;
  border-radius: 0 !important;
  color: var(--text-muted) !important;
  padding: 0.5rem 1.2rem !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: var(--text-primary) !important;
  border-bottom: 2px solid var(--brand-primary) !important;
}

/* ── Sidebar nav ──────────────────────────────────────────────── */
[data-testid="stSidebarNav"] a {
  font-family: 'Inter', sans-serif !important;
  font-weight: 400 !important;
  letter-spacing: 0.3px !important;
  font-size: 0.82rem !important;
  color: var(--text-muted) !important;
  border-radius: 4px !important;
  padding: 0.3rem 0.6rem !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
  color: var(--text-primary) !important;
  background: var(--green-glow) !important;
  border-left: 2px solid var(--brand-primary) !important;
}

/* ── Number input spinners ────────────────────────────────────── */
[data-testid="stNumberInput"] button {
  background: var(--bg-raised) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
}

/* ── Multiselect tags ─────────────────────────────────────────── */
[data-testid="stMultiSelect"] span[data-baseweb="tag"] {
  background: var(--brand-primary) !important;
  color: var(--text-primary) !important;
  border-radius: 3px !important;
}

/* ── Section header helper ────────────────────────────────────── */
.ons-section-header {
  font-family: 'Inter', sans-serif;
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--text-muted);
  margin: 0.8rem 0 0.4rem;
  display: flex;
  align-items: center;
  gap: 0.8rem;
}
.ons-section-header::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

/* ── Spinner ──────────────────────────────────────────────────── */
[data-testid="stSpinner"] {
  color: var(--brand-primary) !important;
}

/* ── Toast ────────────────────────────────────────────────────── */
[data-testid="stToast"] {
  background: var(--bg-surface) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
}
</style>
"""


def apply_theme() -> None:
    """Inject the ONS theme. Call at the top of every page."""
    st.markdown(ONS_CSS, unsafe_allow_html=True)


def section_header(label: str) -> None:
    """Render a styled section divider with label."""
    st.markdown(
        f'<div class="ons-section-header">{label}</div>',
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "") -> None:
    """Render the page title."""
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)
