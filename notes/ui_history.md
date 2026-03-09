# file: src/ui/history.py

## 1. File Overview
**Purpose**: **Longitudinal Tracking Interface**.
**Role**: Allows doctors to view a patient's progress over time (weeks/months).
**Architecture Fit**: Visualizes data stored by `DataLogger` and indexed by `PatientDB`.

## 2. Code Breakdown

### Data Loading (Lines 13-26)
-   **Input**: `patient_id` (Text Box).
-   **Source**: Calls `logger_agent.get_patient_trends(patient_id)`.
-   **Logic**: Checks if the ID exists in the local JSON index.

### DataFrame Construction (Lines 29-40)
-   Iterates through the list of session summaries.
-   Formats timestamps to readable dates (`%Y-%m-%d`).
-   Calculates `Duration (min)`.

### Key Metrics (Lines 43-47)
-   `st.metric`: Displays high-level stats:
    -   Total Assessments.
    -   Total Critical Events (Meltdowns).
    -   Avg HR Baseline (Anxiety Indicator).

### Visualization (Lines 51-68)
-   **Library**: `plotly.express`.
-   **Chart 1 (Behavior Frequency)**:
    -   X-Axis: Date.
    -   Y-Axis: Event Count.
    -   **Insight**: Downward trend = Therapy is working.
-   **Chart 2 (Anxiety Trend)**:
    -   X-Axis: Date.
    -   Y-Axis: Avg Heart Rate.
    -   **Insight**: Lower baseline = Reduced chronic anxiety.

## 3. Functions Explanation
-   `render_history(logger_agent)`: Main entry point.

## 4. Data Flow
1.  **PatientDB**: Reads `data/patient_db.json`.
2.  **Pandas**: Converts list of dicts to DataFrame.
3.  **Plotly**: Renders interactive SVG charts.

## 5. Internal Dependencies
-   `src.utils.patient_db`: The data source.
-   `plotly`: The charting engine.

## 6. Design Decisions
-   **Plotly over Matplotlib**: Plotly charts are interactive (zoom/pan/hover), which is essential for medical data review.
-   **Split View**: Separating "Behavior" from "Physiology" prevents clutter.

## 7. How to Modify
-   **Add New Metric**:
    1.  Update `PatientDB.register_session` to save the new metric (e.g., `avg_response_latency`).
    2.  In `history.py`, add it to the DataFrame.
    3.  Create a new `px.line` chart.

## 8. Limitations
-   **ID Lookup**: User must type the ID exacty. No fuzzy search or dropdown of "Recent Patients".

## 9. Future Improvements
-   **Drill-Down**: Clicking a data point on the graph should open the detailed PDF report for that specific session.
