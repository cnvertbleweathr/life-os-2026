"""
ons_theme.py

Shared retro-futuristic theme for the Operating Narcisystem dashboard.
Import and call apply_theme() at the top of every page.

Color palette:
  Deep navy:     #061820  (background)
  Steel blue:    #0a2a36  (secondary bg)
  Cyan:          #4db8d4  (accent, links)
  Burnt orange:  #c8501a  (primary, headers)
  Amber gold:    #ffcc44  (highlights, stars)
  Warm cream:    #e8dcc8  (body text)
  Muted sand:    #a09880  (secondary text)
"""

import streamlit as st


ONS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@300;400;700&family=Alfa+Slab+One&family=Share+Tech+Mono&display=swap');

/* ── Root variables ────────────────────────────────────────────── */
:root {
  --ons-bg:        #061820;
  --ons-bg2:       #0a2a36;
  --ons-bg3:       #0e3347;
  --ons-cyan:      #4db8d4;
  --ons-orange:    #c8501a;
  --ons-gold:      #ffcc44;
  --ons-cream:     #e8dcc8;
  --ons-sand:      #a09880;
  --ons-green:     #2a7a5a;
  --ons-border:    rgba(77,184,212,0.25);
  --ons-border2:   rgba(200,80,26,0.4);
}

/* ── Global app frame ─────────────────────────────────────────── */
.stApp {
  background-color: var(--ons-bg) !important;
  background-image:
    radial-gradient(ellipse at 20% 0%, rgba(77,184,212,0.06) 0%, transparent 60%),
    radial-gradient(ellipse at 80% 100%, rgba(200,80,26,0.04) 0%, transparent 60%);
}

/* Sidebar */
section[data-testid="stSidebar"] {
  background-color: var(--ons-bg2) !important;
  border-right: 1px solid var(--ons-border) !important;
}
section[data-testid="stSidebar"] * {
  font-family: 'Josefin Sans', sans-serif !important;
}

/* ── Typography ───────────────────────────────────────────────── */
html, body, .stApp, p, div, span, label {
  font-family: 'Share Tech Mono', monospace !important;
  color: var(--ons-cream) !important;
}

h1 {
  font-family: 'Alfa Slab One', serif !important;
  color: var(--ons-orange) !important;
  letter-spacing: -1px !important;
  text-shadow: 2px 2px 0px rgba(200,80,26,0.3) !important;
  border-bottom: 2px solid var(--ons-orange) !important;
  padding-bottom: 0.3em !important;
  margin-bottom: 0.5em !important;
}

h2 {
  font-family: 'Josefin Sans', sans-serif !important;
  font-weight: 700 !important;
  color: var(--ons-cyan) !important;
  letter-spacing: 3px !important;
  text-transform: uppercase !important;
  font-size: 1rem !important;
  border-left: 3px solid var(--ons-orange) !important;
  padding-left: 0.6em !important;
  margin-top: 1.5em !important;
}

h3 {
  font-family: 'Josefin Sans', sans-serif !important;
  font-weight: 400 !important;
  color: var(--ons-gold) !important;
  letter-spacing: 2px !important;
  font-size: 0.85rem !important;
  text-transform: uppercase !important;
}

/* Caption / small text */
.stMarkdown small, .stCaption, [data-testid="stCaptionContainer"] {
  font-family: 'Josefin Sans', sans-serif !important;
  color: var(--ons-sand) !important;
  letter-spacing: 2px !important;
  font-size: 0.7rem !important;
  text-transform: uppercase !important;
}

/* ── Metric cards ─────────────────────────────────────────────── */
[data-testid="stMetric"] {
  background: var(--ons-bg2) !important;
  border: 1px solid var(--ons-border) !important;
  border-top: 2px solid var(--ons-orange) !important;
  border-radius: 0 !important;
  padding: 1rem !important;
  position: relative !important;
}
[data-testid="stMetric"]::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, var(--ons-orange), transparent);
}
[data-testid="stMetricLabel"] {
  font-family: 'Josefin Sans', sans-serif !important;
  color: var(--ons-sand) !important;
  letter-spacing: 3px !important;
  text-transform: uppercase !important;
  font-size: 0.65rem !important;
}
[data-testid="stMetricValue"] {
  font-family: 'Alfa Slab One', serif !important;
  color: var(--ons-cream) !important;
  font-size: 2rem !important;
}
[data-testid="stMetricDelta"] {
  font-family: 'Share Tech Mono', monospace !important;
  font-size: 0.75rem !important;
}

/* ── Progress bars ────────────────────────────────────────────── */
[data-testid="stProgressBar"] > div {
  background-color: var(--ons-bg3) !important;
  border-radius: 0 !important;
  height: 6px !important;
}
[data-testid="stProgressBar"] > div > div {
  background: linear-gradient(90deg, var(--ons-orange), var(--ons-gold)) !important;
  border-radius: 0 !important;
}

/* ── Buttons ──────────────────────────────────────────────────── */
.stButton > button {
  background-color: transparent !important;
  border: 1px solid var(--ons-orange) !important;
  color: var(--ons-orange) !important;
  font-family: 'Josefin Sans', sans-serif !important;
  letter-spacing: 3px !important;
  text-transform: uppercase !important;
  font-size: 0.75rem !important;
  border-radius: 0 !important;
  transition: all 0.2s !important;
}
.stButton > button:hover {
  background-color: var(--ons-orange) !important;
  color: var(--ons-bg) !important;
}
.stButton > button[kind="primary"] {
  background-color: var(--ons-orange) !important;
  color: var(--ons-bg) !important;
}
.stButton > button[kind="primary"]:hover {
  background-color: var(--ons-gold) !important;
  border-color: var(--ons-gold) !important;
}

/* ── Dividers ─────────────────────────────────────────────────── */
hr {
  border: none !important;
  border-top: 1px solid var(--ons-border) !important;
  margin: 2rem 0 !important;
  position: relative !important;
}

/* ── Dataframes ───────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--ons-border) !important;
}

/* ── Expanders ────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid var(--ons-border) !important;
  border-radius: 0 !important;
  background: var(--ons-bg2) !important;
}
[data-testid="stExpander"] summary {
  font-family: 'Josefin Sans', sans-serif !important;
  letter-spacing: 2px !important;
  text-transform: uppercase !important;
  font-size: 0.8rem !important;
  color: var(--ons-cyan) !important;
}

/* ── Selectboxes / inputs ─────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div {
  background-color: var(--ons-bg2) !important;
  border: 1px solid var(--ons-border) !important;
  border-radius: 0 !important;
  color: var(--ons-cream) !important;
}
[data-testid="stTextInput"] input {
  background-color: var(--ons-bg2) !important;
  border: 1px solid var(--ons-border) !important;
  border-radius: 0 !important;
  color: var(--ons-cream) !important;
}

/* ── Checkboxes ───────────────────────────────────────────────── */
[data-testid="stCheckbox"] label {
  font-family: 'Share Tech Mono', monospace !important;
  color: var(--ons-cream) !important;
}

/* ── Alerts / info boxes ──────────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 0 !important;
  border-left: 3px solid var(--ons-cyan) !important;
  background: rgba(77,184,212,0.08) !important;
}
.stSuccess {
  border-left-color: var(--ons-gold) !important;
  background: rgba(255,204,68,0.08) !important;
}
.stWarning {
  border-left-color: var(--ons-orange) !important;
}

/* ── Tabs ─────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
  border-bottom: 1px solid var(--ons-border) !important;
  gap: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
  font-family: 'Josefin Sans', sans-serif !important;
  letter-spacing: 2px !important;
  text-transform: uppercase !important;
  font-size: 0.75rem !important;
  border-radius: 0 !important;
  color: var(--ons-sand) !important;
  padding: 0.5rem 1.2rem !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  color: var(--ons-orange) !important;
  border-bottom: 2px solid var(--ons-orange) !important;
}

/* ── Sidebar nav links ────────────────────────────────────────── */
[data-testid="stSidebarNav"] a {
  font-family: 'Josefin Sans', sans-serif !important;
  letter-spacing: 2px !important;
  text-transform: uppercase !important;
  font-size: 0.75rem !important;
  color: var(--ons-sand) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
  color: var(--ons-orange) !important;
  border-left: 2px solid var(--ons-orange) !important;
}

/* ── Section divider helper ───────────────────────────────────── */
.ons-section-header {
  font-family: 'Josefin Sans', sans-serif;
  font-size: 0.65rem;
  letter-spacing: 5px;
  text-transform: uppercase;
  color: var(--ons-sand);
  margin: 2rem 0 0.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}
.ons-section-header::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--ons-border);
}

/* ── Scanline overlay (subtle retro texture) ──────────────────── */
.stApp::after {
  content: '';
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    rgba(0,0,0,0.03) 2px,
    rgba(0,0,0,0.03) 4px
  );
  pointer-events: none;
  z-index: 9999;
}
</style>
"""


def apply_theme() -> None:
    """Inject the ONS retro-futuristic theme. Call at top of every page."""
    st.markdown(ONS_CSS, unsafe_allow_html=True)


def section_header(label: str) -> None:
    """Render a styled section divider with label."""
    st.markdown(
        f'<div class="ons-section-header">{label}</div>',
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "") -> None:
    """Render the page title with ONS branding."""
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)
