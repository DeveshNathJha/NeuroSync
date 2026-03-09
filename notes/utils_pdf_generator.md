# file: src/utils/pdf_generator.py

## 1. File Overview
**Purpose**: **Clinical Reporting Engine**.
**Role**: Generates a professional PDF document summarizing the session.
**Library**: Wraps `fpdf2`.

## 2. Code Breakdown

### `MedicalReportPDF` Class (Lines 5-45)
-   Inherits from `FPDF`.
-   **Overrides `header()`**: Draws the Tata Blue logo and line.
-   **Overrides `footer()`**: Adds page numbers and "AI Generated" disclaimer.
-   **Helpers**: `chapter_title`, `body_text`, `bullet_point` ensure consistent styling.

### `generate_pdf` Function (Lines 46-104)
-   **Input**: `summary_text` (from LLM), `stats` (from Sensors).
-   **Parsing Logic**:
    -   The LLM output is Markdown-ish.
    -   This function *parses* that text:
        -   If line starts with `###` -> Make it a **Bold Blue Header**.
        -   If line starts with `-` -> Make it a **Bullet Point**.
    -   **Why**: FPDF doesn't support Markdown natively. We built a mini-parser.

## 3. Data Flow
1.  **Reasoner**: Outputs "### ASSSESSMENT\n - Patient looks calm."
2.  **PDF Generator**: Converts to PDF drawing commands.
3.  **File System**: Saves `report.pdf`.

## 4. Design Decisions
-   **FPDF**: chosen because it is standalone (no dependency on `wkhtmltopdf` or OS binaries).
-   **Disclaimer**: Hardcoded red text at the bottom is a crucial Legal/Ethical safeguard for AI medical tools.

## 5. Limitations
-   **Unicode**: FPDF has trouble with some Unicode characters (Emojis). We stick to standard ASCII/Latin-1 where possible.
-   **Layout**: The layout is hardcoded. It cannot dynamically adjust if the text is too long (it just spills to the next page, usually okay).
