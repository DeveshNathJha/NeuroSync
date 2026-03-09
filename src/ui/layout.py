import streamlit as st
from config.settings import settings

def init_page():
    """Initializes the Streamlit page configuration and styling."""
    st.set_page_config(
        page_title=settings.UI.PAGE_TITLE,
        page_icon=settings.UI.PAGE_ICON,
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # --- STYLING (Medical Grade / Dark Mode) ---
    st.markdown(f"""
        <style>
        .main {{ background-color: {settings.UI.BACKGROUND_COLOR}; }}
        
        /* Button Styling */
        .stButton>button {{ 
            width: 100%; 
            height: 3em; 
            font-weight: bold; 
            background-color: #1f2937; 
            color: white; 
            border: 1px solid #374151; 
            border-radius: 4px; 
        }}
        .stButton>button:hover {{ 
            border-color: {settings.UI.THEME_COLOR}; 
            color: {settings.UI.THEME_COLOR}; 
        }}
        
        /* Metric Styling */
        div[data-testid="stMetricValue"] {{ 
            color: {settings.UI.THEME_COLOR}; 
            font-weight: 600; 
        }}
        
        /* Report Box */
        .report-box {{ 
            background-color: #1a1c24; 
            padding: 25px; 
            border-radius: 4px; 
            border-left: 5px solid {settings.UI.THEME_COLOR}; 
            margin-top: 20px; 
        }}
        
        /* Log Container */
        .log-container {{
            font-family: 'Courier New', monospace;
            background-color: #000000;
            color: #00ff00;
            padding: 10px;
            border-radius: 5px;
            font-size: 12px;
            height: 150px;
            overflow-y: scroll;
            border: 1px solid #333;
        }}
        </style>
        """, unsafe_allow_html=True)

def render_sidebar():
    """Renders the common sidebar elements."""
    with st.sidebar:
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Tata_logo.svg/1200px-Tata_logo.svg.png", width=40) 
        st.title(settings.UI.PAGE_TITLE)
        st.caption("Agentic AI System") 
        st.markdown("---")
        
        app_mode = st.selectbox("Select Module:", ["New Assessment", "Patient History", "Patient Calibration"])
        st.markdown("---")
        return app_mode
