import streamlit as st
import cv2
import time
import numpy as np
import pandas as pd
import tempfile
from config.settings import settings
from src.utils.logger import logger
from src.sensors.camera import CameraSensor
from src.utils.pdf_generator import generate_pdf

def render_dashboard(vision, audio, bio, fusion, reasoner, logger_agent):
    """
    Renders the main dashboard for new assessments.
    """
    with st.sidebar:
        st.subheader("Configuration")
        
        # 1. INPUT SOURCE
        input_source = st.radio("Input Source Mode:", ("Live Webcam", "Upload Video Analysis"))
        
        # 2. REPORT STYLE
        audience_mode = st.selectbox("Report Audience Style:", ["Doctor (Clinical)", "Parent (Simplified)"])
        
        # 3. HARDWARE INTERFACE (Updated for rPPG)
        signal_mode = st.selectbox("Bio-Signal Interface:", [
            "Vision AI (Contactless Heart Rate)",
            "Digital Twin (Simulation)", 
            "EEG Headset (LSL Hardware)"
        ])
        
        # Handle Mode Switching
        if signal_mode == "Vision AI (Contactless Heart Rate)":
            bio.set_mode("MODE_WEBCAM")
            st.info("Using Webcam for Vitial Signs (rPPG)")
            
        elif signal_mode == "EEG Headset (LSL Hardware)":
            if st.button("Connect Hardware"):
                if bio.connect_hardware(): st.success("LSL Stream Active")
                else: st.error("Device Not Found. Using Twin.")
        
        else:
            bio.set_mode("MODE_TWIN")
            with st.expander("🛠️ Clinical Simulation Controls", expanded=True):
                st.caption("Inject Synthetic Events")
                sim_flapping = st.checkbox("Simulate Hand Flapping")
                sim_banging = st.checkbox("Simulate Head Banging")
                sim_spinning = st.checkbox("Simulate Spinning")
                sim_hr = st.slider("Simulate Heart Rate (BPM)", 50, 160, 75)
                
                # Store in session state for the loop to access
                st.session_state.sim_data = {
                    "flapping": sim_flapping,
                    "banging": sim_banging,
                    "spinning": sim_spinning,
                    "hr": sim_hr
                }
        
        st.markdown("---")
        
        # 4. AUDIO MONITOR
        st.markdown("**Audio Monitor**")
        audio_meter = st.progress(0)
        audio_status_text = st.empty()
        
        if input_source == "Live Webcam":
            if st.button("TRIGGER STRESS EVENT"):
                st.session_state.stress_active = not st.session_state.stress_active
        
        st.markdown("---")
        # 5. SYSTEM STATUS & TIMER
        status_placeholder = st.empty()
        timer_placeholder = st.empty() 

    # MAIN LAYOUT
    col_vis, col_bio = st.columns([1.6, 1])

    with col_vis:
        st.subheader(f"Perception Layer ({input_source})")
        video_placeholder = st.empty()
        cam = None
        stop_clicked = False 
        
        if input_source == "Live Webcam":
            if not st.session_state.live_session_active:
                if st.button("Start Live Session"):
                    st.session_state.live_session_active = True
                    st.session_state.generate_report_trigger = False 
                    st.session_state.start_time = time.time()
                    st.rerun() 
            else:
                if st.button("End Session & Generate Report"):
                    stop_clicked = True
                cam = CameraSensor(0)
                cam.start()

        else:
            uploaded_file = st.file_uploader("Upload Patient Video", type=['mp4', 'mov', 'avi'])
            if uploaded_file:
                tfile = tempfile.NamedTemporaryFile(delete=False) 
                tfile.write(uploaded_file.read())
                
                with st.spinner("Extracting Audio Profile..."):
                    st.session_state.audio_timeline = audio.analyze_video_file(tfile.name)
                
                cam = CameraSensor(tfile.name)
                cam.start()
                if st.button("Stop Analysis"):
                    stop_clicked = True
                    cam.stop()

    with col_bio:
        st.subheader("Bio-Digital Twin")
        chart_hr = st.empty()
        chart_eeg = st.empty()
        
        st.markdown("### Real-time Telemetry")
        c1, c2, c3, c4 = st.columns(4)
        metric_hr = c1.empty()
        metric_hrv = c2.empty()
        metric_alpha = c3.empty()
        metric_audio = c4.empty() 
        
        st.markdown("---")
        st.subheader("Fusion Engine Log")
        log_area = st.empty()
        logs = []

    # --- RUNTIME LOOP ---
    if cam and cam.running:
        frame_count = 0
        if not st.session_state.start_time: st.session_state.start_time = time.time()
        
        while cam.running:
            if stop_clicked:
                cam.stop()
                break
            
            ret, frame = cam.get_frame()
            if not ret: break
            frame_count += 1

            # 1. TIMER UPDATE (Safety Check added)
            if st.session_state.start_time:
                elapsed = int(time.time() - st.session_state.start_time)
                timer_text = f"⏱️ {elapsed // 60:02d}:{elapsed % 60:02d}"
                timer_placeholder.markdown(f"### {timer_text}")

            # 2. PROCESS SENSORS
            # 137. Extract Vision Data (Behavior) API
            vision_data, processed_frame = vision.process_frame(frame)
            
            # [SIMULATION OVERRIDE]
            if "sim_data" in st.session_state:
                if st.session_state.sim_data.get("flapping", False): vision_data["hand_flapping"] = True
                if st.session_state.sim_data.get("banging", False): vision_data["head_banging"] = True
                if st.session_state.sim_data.get("spinning", False): vision_data["spinning"] = True
            
            # [NEW] Extract Vision Data (Vitals/rPPG)
            # We see if we can get a face ROI from VisionAgent to help the rPPG sensor
            # VisionAgent implementation logic is needed here to extract ROI if possible,
            # For now passing full frame to rPPG update.
            bio.update_rppg(frame)
            
            # 3. AUDIO LOGIC (Fixed Type Casting)
            audio_packet = audio.process_chunk()
            is_meltdown = False
            vol_norm = 0.0
            
            if input_source == "Live Webcam":
                vol_norm = float(min(audio_packet['volume'] / 10.0, 1.0))
                is_meltdown = audio_packet['volume'] > settings.AUDIO.SCREAM_THRESH 
                audio_meter.progress(vol_norm)
            else:
                try:
                    current_vid_time = cam.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                    if any(abs(t - current_vid_time) < 1.0 for t in st.session_state.audio_timeline):
                        is_meltdown = True
                        vol_norm = 0.9 
                    else:
                        vol_norm = 0.1
                    audio_meter.progress(float(vol_norm))
                except:
                    pass

            if is_meltdown: audio_status_text.error("MELTDOWN DETECTED")
            elif audio_packet['is_speaking'] or vol_norm > 0.2: audio_status_text.markdown("Vocalizing")
            else: audio_status_text.caption("Silence")

            # 4. SYNC & FUSION LOGIC
            force_stress = False
            if input_source == "Live Webcam" and st.session_state.stress_active: force_stress = True
            
            if (vision_data['gaze_aversion'] or vision_data['hand_flapping'] or 
                vision_data['head_banging'] or vision_data['spinning'] or is_meltdown):
                force_stress = True
            
            # 6. BIO-GENERATION
            sim_settings = st.session_state.get("sim_data", None)
            bio_packet = bio.get_reading(force_stress, sim_settings=sim_settings)
            
            # [NEW] SIGNAL QUALITY CHECK
            if bio_packet.get("quality_error", False):
                status_placeholder.warning(f"⚠️ SIGNAL LOST ({bio_packet['source']}) - CHECK SENSOR")
                # Do not ingest bad data into fusion engine
            else:
                fusion.ingest_bio_event(bio_packet)
                match_event = fusion.correlate(vision_data)
                
                st.session_state.bio_data.append(bio_packet)
                if len(st.session_state.bio_data) > 60: st.session_state.bio_data.pop(0)
    
                # 7. ACTIVE LOGGING (Heartbeat)
                if match_event:
                    if not st.session_state.fusion_events or (match_event['timestamp'] - st.session_state.fusion_events[-1]['timestamp'] > 1.0):
                        st.session_state.fusion_events.append(match_event)
                        logs.append(f"⚠️ MATCH: {match_event['details']}")
                elif frame_count % 30 == 0:
                    src_label = bio_packet['source']
                    logs.append(f"Scanning... [HR: {int(bio_packet['heart_rate'])} | SRC: {src_label}]")
    
                # 5. UPDATE STATUS (Moved here to reflect valid state)
                state_text = "HIGH STRESS" if force_stress else "CALM"
                if force_stress: status_placeholder.error(f"NEURAL STATE: {state_text}")
                else: status_placeholder.success(f"NEURAL STATE: {state_text}")

            # 8. RENDER UI
            video_placeholder.image(processed_frame, channels="BGR", use_container_width=True)
            
            if st.session_state.bio_data:
                df = pd.DataFrame(st.session_state.bio_data)
                chart_hr.line_chart(df[['heart_rate']], height=120)
                chart_eeg.line_chart(df[['eeg_alpha', 'eeg_beta']], height=120)
                
                metric_hr.metric("Heart Rate", f"{int(bio_packet['heart_rate'])}")
                metric_hrv.metric("HRV", f"{int(bio_packet['hrv_ms'])} ms")
                metric_alpha.metric("Alpha Wave", f"{bio_packet['eeg_alpha']:.2f}")
                metric_audio.metric("Silence", f"{audio_packet['silence_latency_sec']}s")
            else:
                 metric_hr.metric("Heart Rate", "--")
                 
            if logs: log_area.code("\n".join(logs[-4:]), language="text")
            time.sleep(0.03)

    # --- AFTER LOOP CLEANUP ---
    if stop_clicked:
        st.session_state.live_session_active = False 
        st.session_state.generate_report_trigger = True
        st.rerun()

    # --- POST-SESSION REPORTING ---
    if st.session_state.generate_report_trigger:
        st.divider()
        st.subheader("Clinical Decision Support (AI Generated)")
        
        with st.spinner("🧠 NeuroSync Brain is analyzing session data..."):
            session_file = logger_agent.save_session("CHILD-001", {
                "fusion_events": st.session_state.fusion_events,
                "bio_summary": st.session_state.bio_data[-10:] if st.session_state.bio_data else []
            })
            
            report = "Analysis Failed."
            if reasoner:
                bio_df = pd.DataFrame(st.session_state.bio_data)
                avg_hr = bio_df['heart_rate'].mean() if not bio_df.empty else 0
                analysis_packet = {
                    "total_events": len(st.session_state.fusion_events),
                    "event_types": [e['symptoms'][0] for e in st.session_state.fusion_events] if st.session_state.fusion_events else [],
                    "avg_heart_rate": avg_hr
                }
                audience_mapping = "Doctor" if "Clinical" in audience_mode else "Parent"
                try: report = reasoner.analyze_session(analysis_packet, audience=audience_mapping)
                except Exception as e: 
                    report = f"Error: {e}"
                    logger.error(f"Reasoning Engine Error: {e}")
            else: report = "Reasoning Engine offline."
            
            st.session_state.session_report = report
            st.session_state.generate_report_trigger = False 
            st.rerun()

    if st.session_state.session_report:
        st.markdown(f"""<div class="report-box"><h3>Clinical Summary</h3></div>""", unsafe_allow_html=True)
        st.markdown(st.session_state.session_report) 
        
        stats = {
            "total_events": len(st.session_state.fusion_events),
            "avg_hr": np.mean([b['heart_rate'] for b in st.session_state.bio_data]) if st.session_state.bio_data else 0,
            "dominant_symptom": st.session_state.fusion_events[0]['symptoms'][0] if st.session_state.fusion_events else "None"
        }
        
        if not logger_agent.last_filename: logger_agent.last_filename = f"CHILD-001_SESSION_{int(time.time())}.json"
        
        c_pdf, c_json = st.columns(2)
        pdf_path = f"{settings.PATIENT_LOGS_DIR}/{logger_agent.last_filename.replace('.json', '.pdf')}"
        generate_pdf("CHILD-001", st.session_state.session_report, stats, pdf_path)
        
        with open(pdf_path, "rb") as pdf_file:
            c_pdf.download_button("📄 Download Medical Report (PDF)", pdf_file, "report.pdf", "application/pdf")
            
        json_path = f"{settings.PATIENT_LOGS_DIR}/{logger_agent.last_filename}"
        with open(json_path, "rb") as json_file:
            c_json.download_button("💾 Download Telemetry Logs (JSON)", json_file, logger_agent.last_filename, "application/json")
