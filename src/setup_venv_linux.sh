#!/usr/bin/env bash



set -e







# --- check for python ---



if ! command -v python3 &> /dev/null; then



    echo "Python3 not found. Please install Python 3.10.11 and ensure it is in PATH."



    exit 1



fi







PYVER=$(python3 --version | awk '{print $2}')   # e.g. 3.10.11



MAJOR=$(echo "$PYVER" | cut -d. -f1)



MINOR=$(echo "$PYVER" | cut -d. -f2)







if [ "$MAJOR" -ne 3 ] || [ "$MINOR" -ne 10 ]; then



    echo "Python 3.10 is required. Found: $PYVER"



    exit 1



fi







echo "Creating virtual environment in ./venv ..."



python3 -m venv venv







# activate it



source venv/bin/activate







echo "Upgrading pip..."



python -m pip install --upgrade pip







if [ -f requirements.txt ]; then



    echo "Installing dependencies from requirements.txt..."



    pip install -r requirements.txt



else



    echo "Installing default dependencies (pandapower core + pandas, matplotlib, openpyxl)..."



    pip install pandapower pandas matplotlib openpyxl



fi



echo "export PYTHONPATH=\$PYTHONPATH:$(pwd)/src" >> venv/bin/activate



echo "Virtual environment setup complete. To activate it later, run:"



echo "  source venv/bin/activate"

