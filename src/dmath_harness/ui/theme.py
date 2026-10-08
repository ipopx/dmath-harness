"""Visual tokens mirrored from https://ipopx.github.io."""

from __future__ import annotations

# Light theme (default on the personal site)
BG = "#f8f4ec"
SURFACE = "#faf8f3"
TEXT = "#3d3630"
TEXT_MUTED = "#5a544a"
ACCENT = "#0076a3"
ACCENT_HOVER = "#00597a"
BORDER = "#e5ded3"
NAV_BG = "#ffffff"
BADGE_GREEN = "#56ae5d"
BADGE_BLUE = "#1988b8"
BADGE_AMBER = "#d99a2b"
RADIUS = "4px"
FONT = "'DM Sans', system-ui, -apple-system, sans-serif"

CUSTOM_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&display=swap');

html, body, [class*="css"] {{
  font-family: {FONT};
  color: {TEXT};
}}

.stApp {{
  background: {BG};
}}

/* Hide Streamlit chrome chrome that fights the academic look */
#MainMenu {{visibility: hidden;}}
footer {{visibility: hidden;}}
header[data-testid="stHeader"] {{
  background: transparent;
}}

section[data-testid="stSidebar"] {{
  background: {NAV_BG};
  border-right: 1px solid {BORDER};
}}

section[data-testid="stSidebar"] * {{
  font-family: {FONT};
}}

h1, h2, h3, h4 {{
  font-family: {FONT} !important;
  color: {TEXT} !important;
  letter-spacing: -0.015em;
  font-weight: 600 !important;
}}

.stMarkdown, .stCaption, label, p {{
  color: {TEXT};
}}

div[data-testid="stMetric"] {{
  background: {SURFACE};
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
  padding: 0.85rem 1rem;
}}

div[data-testid="stMetric"] label {{
  color: {TEXT_MUTED} !important;
}}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
  color: {TEXT} !important;
  font-weight: 600;
}}

.stButton > button {{
  background: {ACCENT};
  color: #fff;
  border: none;
  border-radius: {RADIUS};
  font-family: {FONT};
  font-weight: 600;
  padding: 0.5rem 1.1rem;
  transition: background 150ms ease-out;
}}

.stButton > button:hover {{
  background: {ACCENT_HOVER};
  color: #fff;
  border: none;
}}

.stButton > button:focus {{
  box-shadow: 0 0 0 2px color-mix(in srgb, {ACCENT} 35%, transparent);
}}

/* Secondary / ghost buttons */
.stButton > button[kind="secondary"] {{
  background: transparent;
  color: {ACCENT};
  border: 1px solid {BORDER};
}}

.stButton > button[kind="secondary"]:hover {{
  background: color-mix(in srgb, {ACCENT} 10%, transparent);
  color: {ACCENT_HOVER};
  border-color: {ACCENT};
}}

div[data-baseweb="select"] > div,
.stTextInput input,
.stNumberInput input,
.stMultiSelect [data-baseweb="select"] > div {{
  background: {SURFACE} !important;
  border-color: {BORDER} !important;
  border-radius: {RADIUS} !important;
  color: {TEXT} !important;
}}

.stExpander {{
  background: {SURFACE};
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
}}

.stTabs [data-baseweb="tab-list"] {{
  gap: 0.5rem;
  border-bottom: 1px solid {BORDER};
}}

.stTabs [data-baseweb="tab"] {{
  color: {TEXT_MUTED};
  font-weight: 500;
}}

.stTabs [aria-selected="true"] {{
  color: {ACCENT} !important;
}}

hr {{
  border-color: {BORDER};
}}

/* Custom message chrome */
.dmath-hero {{
  max-width: 920px;
  margin: 0 auto 1.25rem auto;
  padding: 0.25rem 0 0.5rem 0;
  border-bottom: 1px solid {BORDER};
}}
.dmath-hero h1 {{
  font-size: 1.75rem;
  margin-bottom: 0.35rem;
}}
.dmath-hero p {{
  color: {TEXT_MUTED};
  font-size: 0.95rem;
  margin: 0;
}}

.dmath-msg {{
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
  background: {SURFACE};
  padding: 0.85rem 1rem;
  margin: 0.55rem 0;
}}
.dmath-msg-role {{
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: {TEXT_MUTED};
  margin-bottom: 0.4rem;
}}
.dmath-msg-user .dmath-msg-role {{ color: {BADGE_BLUE}; }}
.dmath-msg-assistant .dmath-msg-role {{ color: {ACCENT}; }}
.dmath-msg-tool .dmath-msg-role {{ color: {BADGE_AMBER}; }}
.dmath-msg-system .dmath-msg-role {{ color: {TEXT_MUTED}; }}

.dmath-msg-body {{
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.55;
  font-size: 0.92rem;
  color: {TEXT};
}}

.dmath-tool-call {{
  margin-top: 0.65rem;
  padding: 0.65rem 0.75rem;
  background: color-mix(in srgb, {ACCENT} 8%, {SURFACE});
  border-left: 3px solid {ACCENT};
  border-radius: 0 {RADIUS} {RADIUS} 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.82rem;
}}
.dmath-tool-name {{
  font-weight: 600;
  color: {ACCENT};
  margin-bottom: 0.35rem;
  font-family: {FONT};
  font-size: 0.8rem;
}}

.dmath-badge {{
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-right: 0.35rem;
}}
.dmath-badge-ok {{
  background: color-mix(in srgb, {BADGE_GREEN} 18%, {SURFACE});
  color: {BADGE_GREEN};
}}
.dmath-badge-warn {{
  background: color-mix(in srgb, {BADGE_AMBER} 18%, {SURFACE});
  color: {BADGE_AMBER};
}}
.dmath-badge-info {{
  background: color-mix(in srgb, {BADGE_BLUE} 18%, {SURFACE});
  color: {BADGE_BLUE};
}}

.dmath-grade-box {{
  border: 1px solid {BORDER};
  border-radius: {RADIUS};
  background: {SURFACE};
  padding: 0.9rem 1rem;
  margin-top: 0.75rem;
}}
.dmath-grade-score {{
  font-size: 1.15rem;
  font-weight: 600;
  color: {ACCENT};
}}
.dmath-muted {{
  color: {TEXT_MUTED};
  font-size: 0.88rem;
}}
"""
