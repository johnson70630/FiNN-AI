import streamlit as st
import requests
import re
import sys
import os

# Add the project root to Python path when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure page
st.set_page_config(page_title="FiNN AI", layout="centered")
st.markdown("<style>#MainMenu,header,footer{visibility:hidden}</style>",
            unsafe_allow_html=True)
st.markdown("<h1 style='text-align:center;color:#4a90e2'>🤖 FiNN AI</h1>",
            unsafe_allow_html=True)

# Backend API URL
BACKEND_URL = "http://localhost:8000"

def call_backend(question: str, timeout: int = 60):
    """Make a query to the backend API and format the response"""
    r = requests.post(f"{BACKEND_URL}/query", json={"question": question}, timeout=timeout)
    r.raise_for_status()
    answer = r.json()["answer"]

    if "\n\nSources:\n" in answer:
        body, src = answer.split("\n\nSources:\n", 1)
    else:
        body, src = answer, ""

    # Build neat markdown with sources directly appended
    full_md = body.strip()
    if src:
        full_md += "\n\n---\n**📚 Sources:**\n"
        for line in src.splitlines():
            m = re.match(r"\s*\[(\d+)]\s+(.*?)\s+\((https?://.*?)\)\s*$", line)
            if m:
                num, title, url = m.groups()
                full_md += f"- [{num}] [{title}]({url})\n"
            else:
                full_md += f"- {line}\n"
    return full_md

# Check if API server is running
def is_api_running():
    """Check if the backend API is available"""
    try:
        response = requests.get(f"{BACKEND_URL}/")
        return response.status_code == 200
    except:
        return False

# Display API status
api_status = is_api_running()
if not api_status:
    st.warning("⚠️ The backend API is not running. Please start it with the command below in a terminal:")
    st.code("python backend/main.py", language="bash")
    st.stop()
else:
    st.success("✅ Connected to Financial News AI backend")

# Session state for chat history
if "history" not in st.session_state:
    st.session_state.history = []

# Display conversation history
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=False)

# User input / new turn
if prompt := st.chat_input("Ask a financial question…"):
    # Show + store user message
    with st.chat_message("user"):
        st.write(prompt)
    st.session_state.history.append({"role": "user", "content": prompt})

    # Spinner placeholder
    spinner_ph = st.empty()
    with spinner_ph.container():
        with st.chat_message("assistant"):
            st.write("FiNN AI is thinking…")

    # Backend call
    try:
        assistant_md = call_backend(prompt, timeout=60)
    except Exception as e:
        assistant_md = f"❌ Error: {e}"

    spinner_ph.empty()  # remove spinner

    # Show + store assistant response
    with st.chat_message("assistant"):
        st.markdown(assistant_md, unsafe_allow_html=False)
    st.session_state.history.append({"role": "assistant", "content": assistant_md}) 