# file: run_app.sh

## 1. File Overview
**Purpose**: This is the **Startup Script**. It is the comprehensive "One-Click" launcher for the user.
**Role**: It handles the environment setup (venv) and executes the Python application.
**Why**: Users (doctors/researchers) should not need to remember complex `venv` activation commands.

## 2. Code Breakdown

### Venv Check (Lines 4-11)
```bash
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found..."
    exit 1
fi
```
-   **Logic**: Checks if the directory `venv` exists.
-   **Safety**: If missing, it halts and tells the user exactly how to fix it (`python3 -m venv ...`). This prevents "Module Not Found" errors that confuse non-tech users.

### Execution (Lines 14-15)
```bash
echo "Launching NeuroSync with correct environment..."
./venv/bin/streamlit run neuroapp.py
```
-   **Logic**: Uses the absolute path `./venv/bin/streamlit`.
-   **Why**: This avoids the need to "activate" the shell. It directly uses the interpreter inside the virtual environment to run `neuroapp.py`.

## 3. Data Flow
-   **Input**: User runs `./run_app.sh` in terminal.
-   **Process**: Checks filesystem.
-   **Output**: Launches the Streamlit Web Server (usually on `localhost:8501`).

## 4. Internal Dependencies
-   **Requires**:
    -   `venv/`: A valid Python virtual environment directory.
    -   `neuroapp.py`: The target script.

## 5. Design Decisions
-   **Shell Script**: Chosen because it works natively on Linux/macOS.
-   **Explicit Pathing**: `./venv/bin/streamlit` is safer than relying on the user's global `$PATH`.

## 6. How to Modify
-   **Change Port**: Modify the last line to `./venv/bin/streamlit run neuroapp.py --server.port 9000`.
-   **Add Flags**: Add `--server.headless true` for running on a remote server.

## 7. Limitations
-   **OS Specific**: This is a bash script. Windows users need a `.bat` or `.ps1` equivalent.
-   **No Auto-Install**: It checks for `venv` but doesn't create it automatically. (This is a safety choice to avoid unexpected download activity).
