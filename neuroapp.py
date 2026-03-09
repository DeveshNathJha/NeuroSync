import streamlit as st
import time

# --- ENTERPRISE IMPORTS ---
from config.settings import settings
from src.utils.logger import logger
from src.ui import layout, dashboard, history

from src.agents.vision_agent import NeuroVision
from src.agents.audio_agent import AudioAgent
from src.agents.bio_agent import BioAgent
from src.orchestration.fusion_engine import FusionEngine
from src.orchestration.reasoner import ClinicalReasoner
from src.utils.data_logger import DataLogger

# --- INITIALIZATION ---
layout.init_page()

# --- SESSION STATE MANAGEMENT ---
if 'bio_data' not in st.session_state: st.session_state.bio_data = [] 
if 'fusion_events' not in st.session_state: st.session_state.fusion_events = [] 
if 'stress_active' not in st.session_state: st.session_state.stress_active = False
if 'session_report' not in st.session_state: st.session_state.session_report = None
if 'audio_timeline' not in st.session_state: st.session_state.audio_timeline = [] 
if 'live_session_active' not in st.session_state: st.session_state.live_session_active = False
if 'generate_report_trigger' not in st.session_state: st.session_state.generate_report_trigger = False
if 'start_time' not in st.session_state: st.session_state.start_time = None 

# --- LOAD SYSTEM ---
@st.cache_resource
def load_system():
    """Initializes all AI Agents and Hardware Drivers."""
    logger.info("Initializing System Components...")
    vision = NeuroVision()
    audio = AudioAgent()       
    bio = BioAgent()
    fusion = FusionEngine()
    logger_agent = DataLogger()
    
    try:
        reasoner = ClinicalReasoner()
        logger.info("Clinical Reasoner Loaded.")
    except Exception as e:
        reasoner = None
        logger.error(f"Failed to load Clinical Reasoner: {e}")

    audio.start_stream()
    return vision, audio, bio, fusion, reasoner, logger_agent

# Get instances
vision, audio, bio, fusion, reasoner, logger_agent = load_system()

# --- NAVIGATION ---
app_mode = layout.render_sidebar()

# --- ROUTING ---
if app_mode == "New Assessment":
    dashboard.render_dashboard(vision, audio, bio, fusion, reasoner, logger_agent)

elif app_mode == "Patient History":
    history.render_history(logger_agent)

elif app_mode == "Patient Calibration":
    calibration.render_calibration(vision, bio, logger_agent)

# --- CLEANUP ---
# Note: Streamlit re-runs the script on interaction, so we rely on singleton/cached resources.