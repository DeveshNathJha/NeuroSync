import streamlit as st
import time
import pandas as pd
import numpy as np
from src.utils.logger import logger
from src.sensors.camera import CameraSensor

def render_calibration(vision, bio, logger_agent):
    """
    CLINICAL CALIBRATION MODE
    -------------------------
    Establishes a baseline for the specific patient to reduce false positives.
    Records 30-60 seconds of "Resting State" data.
    """
    st.title("Patient Calibration (Baseline Initialization)")
    st.info("Instructions: Ask the patient to sit comfortably. Minimise distractions. Click 'Start Calibration' to record 30 seconds of baseline behavior.")
    
    col_cam, col_stats = st.columns([1.5, 1])
    
    with col_cam:
        cam_placeholder = st.empty()
        
    with col_stats:
        progress_bar = st.progress(0)
        status_text = st.empty()
        metric_motion = st.empty()
        metric_hr = st.empty()

    # Session State for Calibration
    if 'calib_data' not in st.session_state: st.session_state.calib_data = []
    if 'is_calibrating' not in st.session_state: st.session_state.is_calibrating = False

    if not st.session_state.is_calibrating:
        if st.button("Start Calibration Routine"):
            st.session_state.is_calibrating = True
            st.session_state.calib_data = [] # Reset
            st.rerun()
    else:
        if st.button("Cancel"):
            st.session_state.is_calibrating = False
            st.rerun()

    # --- CALIBRATION LOOP ---
    if st.session_state.is_calibrating:
        cam = CameraSensor(0) 
        cam.start()
        
        start_time = time.time()
        duration = 30 # seconds
        
        while cam.running and (time.time() - start_time < duration):
            ret, frame = cam.get_frame()
            if not ret: break
            
            # Process Sensors
            vision_data, processed_frame = vision.process_frame(frame)
            bio.update_rppg(frame)
            bio_packet = bio.get_reading()
            
            # Store Data
            st.session_state.calib_data.append({
                "timestamp": time.time(),
                "motion_x": vision_data.get("raw_velocity_x", 0), # Assuming vision agent exposes this
                "motion_y": vision_data.get("raw_velocity_y", 0),
                "heart_rate": bio_packet["heart_rate"]
            })
            
            # Update UI
            elapsed = time.time() - start_time
            progress = min(elapsed / duration, 1.0)
            progress_bar.progress(progress)
            status_text.text(f"Calibrating... {int(duration - elapsed)}s remaining")
            
            cam_placeholder.image(processed_frame, channels="BGR", use_container_width=True)
            metric_motion.metric("Current Motion", f"{vision_data.get('raw_velocity_x', 0):.2f}")
            metric_hr.metric("Heart Rate", f"{int(bio_packet['heart_rate'])}")
            
            time.sleep(0.05)
            
        cam.stop()
        st.session_state.is_calibrating = False
        
        # --- CALCULATE THRESHOLDS ---
        df = pd.DataFrame(st.session_state.calib_data)
        if not df.empty:
            # Motion Baseline
            mean_motion = df['motion_x'].abs().mean()
            std_motion = df['motion_x'].abs().std()
            motion_thresh = mean_motion + (3 * std_motion) # 3-Sigma Rule
            
            # HR Baseline
            resting_hr = df['heart_rate'].mean()
            
            # Save Config (In real app, save to disk/DB)
            st.session_state.patient_config = {
                "motion_threshold": max(motion_thresh, 1.5), # Safety floor
                "resting_hr": resting_hr,
                "stress_hr_threshold": resting_hr + 20 # Simple heuristic
            }
            
            st.success("Calibration Complete!")
            st.json(st.session_state.patient_config)
            st.info("System is now tuned to this patient. Please return to 'New Assessment' to begin.")
