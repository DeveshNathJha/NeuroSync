import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from src.utils.logger import logger

def render_history(logger_agent):
    """
    Renders the patient history view.
    """
    st.title("Longitudinal Patient Tracking")
    
    patient_id = st.sidebar.text_input("Patient ID Lookup:", "CHILD-001")
    history = logger_agent.load_history(patient_id)
    
    if not patient_id:
        st.info("Please enter a Patient ID.")
        return

    # 1. Try Fast Local Index (PatientDB)
    trends = logger_agent.get_patient_trends(patient_id)
    
    if not trends:
        st.info("No recorded history found for this patient.")
        # Optional: Add button to "Rebuild Index" if files exist but DB is empty
        return

    # 2. Build DataFrame
    data = []
    for t in trends:
        dt_object = datetime.fromtimestamp(t['timestamp'])
        data.append({
            "Date": dt_object.strftime('%Y-%m-%d %H:%M'),
            "Events": t['event_count'],
            "Avg HR": t['avg_hr'],
            "Duration (min)": round(t['duration_sec'] / 60, 1),
            "Dominant Symptom": t['dominant_symptom']
        })
    
    df = pd.DataFrame(data)
    
    # 3. Key Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Assessments", len(df))
    col2.metric("Total Critical Events", df['Events'].sum())
    col3.metric("Avg Heart Rate (Baseline)", f"{int(df['Avg HR'].mean())} BPM")
    col4.metric("Last Visit", df.iloc[-1]['Date'].split(" ")[0])

    st.markdown("---")
    
    # 4. Visualization (Split Charts)
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("📉 Behavior Frequency")
        fig_events = px.line(df, x="Date", y="Events", markers=True, 
                             title="Critical Events per Session",
                             template="plotly_dark", line_shape="spline")
        fig_events.update_traces(line_color='#FF4B4B', line_width=3)
        st.plotly_chart(fig_events, use_container_width=True)
        
    with c2:
        st.subheader("❤️ Anxiety Trend (Avg HR)")
        fig_hr = px.line(df, x="Date", y="Avg HR", markers=True, 
                         title="Physiological Baseline",
                         template="plotly_dark", line_shape="spline")
        fig_hr.update_traces(line_color='#00A3E0', line_width=3)
        st.plotly_chart(fig_hr, use_container_width=True)

    with st.expander("View Trend Data Details"):
        st.dataframe(df)
