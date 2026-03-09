#!/bin/bash

# ==========================================
# NeuroSync Enterprise - Automated Launcher
# ==========================================
# This script handles:
# 1. Virtual Environment Creation (venv)
# 2. Dependency Installation
# 3. AI Driver Binding (llama-cpp-python)
# 4. Application Launch

VENV_DIR="venv"
PYTHON_CMD="python3"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   NeuroSync Enterprise Environment Setup   ${NC}"
echo -e "${GREEN}========================================${NC}"

# 1. Check Python Version
PY_VERSION=$($PYTHON_CMD --version 2>&1)
echo -e "Detected System Python: ${YELLOW}$PY_VERSION${NC}"

# 2. Virtual Environment Check
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[SETUP] Creating virtual environment ($VENV_DIR)...${NC}"
    $PYTHON_CMD -m venv $VENV_DIR
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to create venv. Is 'python3-venv' installed?${NC}"
        exit 1
    fi
else
    echo -e "[INFO] Virtual environment found."
fi

# 3. Activate Environment
source $VENV_DIR/bin/activate
echo -e "[INFO] Virtual environment activated."

# 4. Dependency Check & Install
# We check if 'streamlit' is installed. If not, we assume a fresh install is needed.
if ! pip show streamlit > /dev/null; then
    echo -e "${YELLOW}[SETUP] Installing dependencies (This may take a few minutes)...${NC}"
    pip install --upgrade pip
    
    # Core Dependencies
    pip install -r requirements.txt
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to install requirements.${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}[SUCCESS] Core dependencies installed.${NC}"

    # SYSTEM AUDIO FIX
    # Note: On some Linux systems, you might need: sudo apt-get install portaudio19-dev
    if ! pip show pyaudio > /dev/null; then
        echo -e "${YELLOW}[SETUP] Installing PyAudio...${NC}"
        pip install pyaudio || echo -e "${RED}[WARNING] PyAudio failed (Missing system libs?)${NC}"
    fi

    # LLM DRIVER FIX (Critical for "The Brain")
    echo -e "${YELLOW}[SETUP] Installing AI Brain Driver (llama-cpp-python)...${NC}"
    # Force reinstall to ensure correct binding to current hardware
    CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_NATIVE=ON" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
    
else
    echo -e "[INFO] Dependencies appear to be installed."
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   Environment Ready. Launching App...   ${NC}"
echo -e "${GREEN}========================================${NC}"

# 5. Launch Application
streamlit run neuroapp.py
