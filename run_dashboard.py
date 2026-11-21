"""run_dashboard.py - starts the Streamlit dashboard (app.py) and opens it in your browser.
Stop it with the bin (Kill Terminal) icon on the terminal panel, or Ctrl+C in the terminal."""
import os
import subprocess
import sys
import threading
import time
import webbrowser

URL = "http://localhost:8501"
os.chdir(os.path.dirname(os.path.abspath(__file__)))
threading.Thread(target=lambda: (time.sleep(4), webbrowser.open(URL)), daemon=True).start()
print(f"Starting dashboard at {URL} ...")
subprocess.call([sys.executable, "-m", "streamlit", "run", "app.py",
                 "--server.headless", "true", "--browser.gatherUsageStats", "false"])
