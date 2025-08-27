# SASMaker 

## How to setup

### Windows
Double-click the file `setup_venv.bat` to:
- Create a virtual environment in a folder called `venv`
- Activate it
- Install all required packages from `requirements.txt`

### macOS/Linux
```bash
sudo apt install python3.10 python3.10-venv python3.10-dev
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

```

## How to run examples
cd into the folder `src`.

### Windows
```bash
.\venv\Scripts\activate
python .\examples\minimal_example.py
```

### macOS/Linux
```bash
source venv/bin/activate
python examples/minimal_example.py
```



