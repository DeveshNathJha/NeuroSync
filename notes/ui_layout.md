# file: src/ui/layout.py

## 1. File Overview
**Purpose**: Defines the **Global Stylistic Theme** and Navigation.
**Role**: Ensures consistency across all pages (CSS, Headers, Sidebar).
**Architecture Fit**: Imported by `neuroapp.py` to initialize the app shell.

## 2. Code Breakdown

### `init_page` (Lines 4-61)
-   `st.set_page_config`: Sets the browser tab title and icon.
-   **CSS Injection**:
    -   `st.markdown(<style>...</style>)`: Injects custom CSS.
    -   **Dark Mode**: Sets background to `#0e1117` (from settings).
    -   **Buttons**: Styles buttons to look like "Medical Equipment" (Dark grey/blue).
    -   **Metrics**: Colors the numbers (Data) with the primary theme color.

### `render_sidebar` (Lines 63-74)
-   Adds the Logo.
-   Adds the Navigation Dropdown (`New Assessment`, `History`, etc.).
-   **Return**: The selected page name (`app_mode`).

## 3. Design Decisions
-   **CSS Injection**: Streamlit's native theming is limited. We use raw CSS injection to achieve a "Cyber-Medical" aesthetic (Dark mode + Neon accents).
-   **Centralization**: Putting all CSS in one file makes it easy to rebrand the app later.

## 4. How to Modify
-   **Change Color Scheme**: Go to `config/settings.py` and change `THEME_COLOR`.
-   **Add Logo**: Update the URL in `st.image`.

## 5. Limitations
-   **Fragile CSS**: Streamlit class names (e.g., `stButton>button`) are not guaranteed to stay the same in future Streamlit versions. This styling might break if Streamlit updates their DOM structure.
