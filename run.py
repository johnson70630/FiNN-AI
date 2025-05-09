#!/usr/bin/env python3
"""
FiNN-AI Launcher
----------------
This script launches both the backend API and Streamlit frontend.
"""
import os
import subprocess
import time
import sys
import webbrowser
import signal
import threading
import requests

def is_api_ready():
    """Check if the API is up and running"""
    try:
        response = requests.get("http://localhost:8000/")
        return response.status_code == 200
    except:
        return False

def main():
    print("=== FiNN-AI: Financial News AI ===")
    
    # Track processes to terminate them properly
    processes = []
    
    try:
        # Start the FastAPI backend server
        print("\n🚀 Starting API server...")
        api_process = subprocess.Popen(
            [sys.executable, "backend/main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(api_process)
        
        # Wait for the API server to start with verification
        max_attempts = 10
        attempts = 0
        while not is_api_ready() and attempts < max_attempts:
            time.sleep(1)
            attempts += 1
            if attempts == max_attempts // 2:
                print("   Waiting for API to be ready...")
        
        if not is_api_ready():
            print("⚠️ Warning: API server did not respond in time. Frontend might need a refresh.")
        else:
            print("   API server is ready!")
        
        # Start the Streamlit frontend
        print("🚀 Starting frontend...")
        streamlit_process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "frontend/app.py", "--server.port=8501"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(streamlit_process)
        
        # Wait a bit for Streamlit to start
        time.sleep(2)
        
        # Streamlit will open the browser automatically, so we don't need to do it here
        # webbrowser.open("http://localhost:8501")  # Commented out to prevent double browser opening
        
        print("\n✅ Application started!")
        print("   Frontend: http://localhost:8501")
        print("   Backend API: http://localhost:8000")
        print("\nPress Ctrl+C to stop all services")
        
        # Keep the script running and monitor stdout/stderr
        def monitor_output(process, prefix):
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"{prefix}: {line.strip()}")
        
        # Start monitoring threads
        api_thread = threading.Thread(target=monitor_output, args=(api_process, "API"), daemon=True)
        streamlit_thread = threading.Thread(target=monitor_output, args=(streamlit_process, "UI"), daemon=True)
        api_thread.start()
        streamlit_thread.start()
        
        # Wait for processes to complete or for keyboard interrupt
        while all(p.poll() is None for p in processes):
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Terminate all processes
        for process in processes:
            if process.poll() is None:  # If process is still running
                os.kill(process.pid, signal.SIGTERM)
                process.wait()
        
        print("Shutdown complete")

if __name__ == "__main__":
    main() 