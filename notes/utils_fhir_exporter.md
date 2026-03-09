# file: src/utils/fhir_exporter.py

## 1. File Overview
**Purpose**: **Interoperability Module**.
**Role**: Converts NeuroSync's proprietary JSON format into **HL7 FHIR R4** (Fast Healthcare Interoperability Resources).
**Why**: Hospitals cannot ingest random JSON files. They need standard FHIR bundles to import data into Epic, Cerner, or other EHR systems.

## 2. Code Breakdown

### `create_observation` (Lines 19-85)
-   **Header**: Creates a FHIR `Bundle` of type `collection`.
-   **Coding System**:
    -   Uses **LOINC Code 88031-0** ("Autism spectrum disorder behavior screening").
    -   This allows other systems to know *exactly* what this data represents.
-   **Structure**:
    -   `status`: "final".
    -   `subject`: Reference to `Patient/{id}`.
    -   `component`: A list of values (Behavior Name, Confidence Score).

## 3. Data Flow
-   **Input**: List of NeuroSync Events `[{'symptoms': ['Flapping'], ...}]`.
-   **Output**: A complex nested Dictionary adhering to the FHIR schema.

## 4. Design Decisions
-   **R4 Standard**: Chosen because it is the most widely adopted version of FHIR.
-   **Observation Resource**: We model each session as an "Observation" (like a Lab Result).

## 5. How to Modify
-   **Add New Codes**: If we add Heart Rate, we should add a component with LOINC code `8867-4` ("Heart rate").

## 6. Limitations
-   **Mock Export**: Currently, it just saves a JSON file. It does not actually *transmit* the data to a FHIR Server (HAPI FHIR).
-   **Minimal Fields**: A real FHIR resource needs many more fields (Practitioner, Encounter, Device). We are only populating the bare minimum.

## 7. Future Improvements
-   **REST API**: Add a `send_to_server(url)` method to POST the bundle to a hospital's API.
