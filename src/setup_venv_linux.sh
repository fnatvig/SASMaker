#!/usr/bin/env bash



set -e







# --- check for python ---



if ! command -v python3 &> /dev/null; then



    echo "Python3 not found. Please install Python 3.10.11 and ensure it is in PATH."



    exit 1



fi







PYVER=$(python3 --version | awk '{print $2}')



MAJOR=$(echo "$PYVER" | cut -d. -f1)



MINOR=$(echo "$PYVER" | cut -d. -f2)







if [ "$MAJOR" -ne 3 ] || [ "$MINOR" -ne 10 ]; then



    echo "Python 3.10 is required. Found: $PYVER"



    exit 1



fi

# --- check for tshark (required by pyshark) ---
if ! command -v tshark &> /dev/null; then
    echo "Warning: tshark is not installed."
    echo "Please install it via your system package manager (e.g., sudo apt-get install tshark)"
    echo "Pyshark will not work properly without tshark available in PATH."
    echo
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

