"""setup_week3.py - installs the Week 3 packages (Streamlit, Plotly) into THIS Python environment."""
import subprocess
import sys

print(f"Installing into: {sys.executable}")
code = subprocess.call([sys.executable, "-m", "pip", "install", "streamlit", "plotly"])
if code != 0:
    sys.exit("STOPPED: install failed - see the messages above.")
import plotly
import streamlit
print(f"\nDone. streamlit {streamlit.__version__}, plotly {plotly.__version__}")
