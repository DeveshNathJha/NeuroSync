# file: src/orchestration/reasoner.py

## 1. File Overview
**Purpose**: The **Clinical Reasoning Engine**. It acts as the "Pre-frontal Cortex".
**Role**: It takes the raw data logs (JSON) and turns them into a human-readable medical report (Text).
**Technology**: Uses `llama-cpp-python` to run a **Quantized Small Language Model (SLM)**, specifically Microsoft's **Phi-3 Mini**.

## 2. Code Breakdown

### Impact of Imports (Lines 8-15)
```python
try:
    from llama_cpp import Llama
    AI_AVAILABLE = True
except ImportError: ...
```
-   **Safety**: Allows the app to start even if the 2GB model file is missing or the library fails to load.

### Initialization (Lines 27-46)
-   Loads the `.gguf` model file.
-   **Parameters**: `n_ctx=2048` (context window), `n_threads=4` (optimized for laptop CPUs).

### The `analyze_session` Method (Lines 53-120)
-   **Input**: Summary stats (Total Events, Avg HR).
-   **Audience Mode**:
    -   If "Doctor": Prompts the AI to use DSM-5 terminology.
    -   If "Parent": Prompts for compassionate, simple language.
-   **Prompt Engineering**:
    -   Uses a strict `<|user|>` / `<|assistant|>` template (ChatML format) required by Phi-3.
    -   Injects data as a bulleted list.
    -   Asks for specific sections (OBSERVATIONS, ASSESSMENT, PLAN).

## 3. Data Flow
1.  **Dashboard**: Aggregates `fusion_events` and `bio_data`.
2.  **Reasoner**: Receives dictionary.
3.  **Llama Loop**: Runs inference (takes 5-20 seconds on CPU).
4.  **Output**: String (Markdown text).

## 4. Internal Dependencies
-   `llama-cpp-python`: The execution engine.
-   `models/Phi-3...gguf`: The binary weights file.

## 5. Design Decisions
-   **Local LLM**: We use a local model instead of OpenAI/Claude API for **Privacy** (HIPAA) and **Offline** capability. Data never leaves the laptop.
-   **Phi-3**: Chosen because it is "State of the Art" for small sizes (3.8GB) and follows instructions better than Llama-2-7b.

## 6. How to Modify
-   **Change Model**:
    1.  Download a new `.gguf` (e.g., Llama-3-8B).
    2.  Update `settings.MODEL.PHI3_PATH`.
    3.  Update the Prompt Format if the new model doesn't use ChatML.
-   **Tune Output**: Edit the `system_prompt` string to add new rules (e.g., "Always mention the date").

## 7. Limitations
-   **Hardware**: Heavy on RAM (needs ~4GB free).
-   **Hallucination**: Like all LLMs, it can make things up if the input data is sparse.
-   **Latency**: Blocking call. The UI freezes while generating.

## 8. Future Improvements
-   **RAG (Retrieval Augmented Generation)**: Feed it previous patient reports to give context on "progress over time".
-   **Structure Output**: Force the LLM to output JSON instead of text for easier parsing.
