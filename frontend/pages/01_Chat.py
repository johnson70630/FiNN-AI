import streamlit as st
import requests
import re
import sys
import os
import time
from datetime import datetime

# Add the project root to Python path when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Configure page
st.set_page_config(page_title="FiNN AI - Chat", layout="wide", page_icon="💬")
st.markdown("<style>#MainMenu,header,footer{visibility:hidden}</style>",
            unsafe_allow_html=True)
st.markdown("<h1 style='text-align:center;color:#4a90e2'>💬 Chat with FiNN AI</h1>",
            unsafe_allow_html=True)

# Make the entire page dark first (before anything else)
st.markdown("""
<style>
/* Dark mode for the whole app */
.stApp {
    background-color: #121212;
    color: #e0e0e0;
}

/* All text elements should have light text color */
p, h1, h2, h3, h4, h5, h6, li, span, div, label {
    color: #e0e0e0 !important;
}

/* Override Streamlit's default white backgrounds */
div[data-testid="stDecoration"], 
div.stMarkdown, 
div.stButton > button,
div[data-testid="stVerticalBlock"] {
    background-color: #121212 !important;
    color: #e0e0e0 !important;
}

/* Success message styling for dark mode */
div[data-baseweb="notification"] {
    background-color: #0f3b20 !important;
    color: #e0e0e0 !important;
    border-color: #155724 !important;
}

/* Warning message styling for dark mode */
div[data-baseweb="toast"] {
    background-color: #3b320f !important;
    color: #e0e0e0 !important;
    border-color: #856404 !important;
}

/* Code block styling */
code {
    background-color: #2d2d2d !important;
    color: #e0e0e0 !important;
}
</style>
""", unsafe_allow_html=True)

# Backend API URL
BACKEND_URL = "http://localhost:8000"

def call_backend(question: str, timeout: int = 60):
    """Make a query to the backend API and format the response"""
    r = requests.post(f"{BACKEND_URL}/query", json={"question": question}, timeout=timeout)
    r.raise_for_status()
    result = r.json()
    
    # Extract the answer and any additional information
    answer = result["answer"]
    service = result.get("service", "unknown")
    # We'll still receive the chain_of_thought but won't display it
    chain_of_thought = result.get("chain_of_thought", [])

    # Process answer for display
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
    
    # Removed the chain of thought section - we don't want to display it
    
    return full_md

# Check if API server is running with retries
def is_api_running(max_retries=3, retry_delay=1):
    """Check if the backend API is available with retries"""
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{BACKEND_URL}/", timeout=5)
            if response.status_code == 200:
                return True
            time.sleep(retry_delay)
        except:
            if attempt < max_retries - 1:  # Don't sleep on the last attempt
                time.sleep(retry_delay)
    return False

# Session state for connection status
if "api_connected" not in st.session_state:
    st.session_state.api_connected = False

# Try to connect to API
api_status = is_api_running(max_retries=5, retry_delay=1)
st.session_state.api_connected = api_status

# Display API status
if not st.session_state.api_connected:
    st.warning("⚠️ The backend API is not running or not responding. Please check:")
    st.code("1. Ensure backend is running with 'python backend/main.py'")
    st.code("2. Try refreshing this page (API may still be starting up)")
    
    # Add auto-refresh button
    if st.button("🔄 Retry Connection"):
        st.rerun()
    st.stop()
else:
    st.success("✅ Connected to FiNN AI !!")

# Session state for chat history
if "history" not in st.session_state:
    st.session_state.history = []

# Create a larger chat container
chat_container = st.container()

# Make the chat interface more prominent
st.markdown("""
<style>
/* Chat container styling */
[data-testid="stVerticalBlock"] > div:has(.stChatMessage) {
    max-height: 600px;  /* Increased height for chat-focused page */
    overflow-y: auto;
    border: 1px solid #444;
    border-radius: 10px;
    padding: 15px;
    margin-bottom: 20px;
    background-color: #1e1e1e;  /* Slightly lighter than page background */
}

/* Message container styling */
.stChatMessage {
    margin-bottom: 12px;
}

/* Message content styling */
.stChatMessageContent {
    border-radius: 8px !important;
    padding: 10px 14px !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3) !important;
    line-height: 1.5 !important;
}

/* User message styling */
.stChatMessage[data-testid="user-message"] .stChatMessageContent {
    background-color: #1a73e8 !important;
    color: white !important;
    border-left: 3px solid #1a73e8 !important;
}

/* Assistant message styling */
.stChatMessage[data-testid="assistant-message"] .stChatMessageContent {
    background-color: #2d2d2d !important;
    color: #e0e0e0 !important; 
    border-left: 3px solid #5f6368 !important;
}

/* Improve the appearance of code blocks */
.stChatMessage code {
    background-color: rgba(255, 255, 255, 0.1) !important;
    border-radius: 4px !important;
    padding: 2px 4px !important;
    color: #e0e0e0 !important;
}

/* Special styling for code in user messages */
.stChatMessage[data-testid="user-message"] code {
    background-color: rgba(255, 255, 255, 0.2) !important;
    color: white !important;
}

/* General chat styles */
.stChatFloatingInputContainer {
    position: sticky !important;
    bottom: 20px !important;
    z-index: 999 !important;
    background-color: transparent !important;
    padding: 10px !important;
    border-top: 1px solid #444 !important;
}

/* Chat input styling */
.stChatInputContainer {
    background-color: #2d2d2d !important;
    border-radius: 20px !important;
    border: 1px solid #444 !important;
    padding: 5px !important;
    color: #e0e0e0 !important;
}

/* Chat input text styling */
.stChatInputContainer textarea {
    color: #e0e0e0 !important;
}

/* Chat avatar styling for dark background */
.stChatMessage .stAvatar {
    background-color: transparent !important;
}

/* Status message styling */
div[data-testid="stStatus"] {
    background-color: #2d2d2d !important;
    color: #e0e0e0 !important;
}

/* Make links stand out */
a {
    color: #4a90e2 !important;
    text-decoration: underline !important;
}

/* Buttons in dark mode */
button {
    background-color: #2d2d2d !important;
    color: #e0e0e0 !important;
    border: 1px solid #444 !important;
}
button:hover {
    background-color: #3d3d3d !important;
    border: 1px solid #555 !important;
}
</style>
""", unsafe_allow_html=True)

# Instructions for the chat - adjusted for dark mode
st.markdown("""
Ask FiNN AI anything about:
- Financial news and market trends
- Stock analysis and investment advice
- Economic concepts and terms
- Company information and performance
- Market data and statistics
""")

# Display conversation history in a scrollable container
with chat_container:
    for msg in st.session_state.history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"], unsafe_allow_html=False)

# User input (fixed at bottom)
if prompt := st.chat_input("Ask a financial question…"):
    # Add question to history first
    st.session_state.history.append({"role": "user", "content": prompt})
    
    # Rerun to display the updated history (this will automatically display the user's message)
    st.rerun()
    
# Check if we need to process a message
if st.session_state.history and len(st.session_state.history) % 2 == 1:
    # There's a user message without an AI response - process it
    prompt = st.session_state.history[-1]["content"]
    
    # Add a temporary "thinking" message directly to the chat history
    with chat_container:
        with st.chat_message("assistant"):
            thinking_placeholder = st.empty()
            thinking_placeholder.markdown("*FiNN AI is thinking...*")
    
    # Backend call
    try:
        assistant_md = call_backend(prompt, timeout=60)
    except Exception as e:
        assistant_md = f"❌ Error: {e}"
    
    # Replace the thinking message with the actual response (don't add a new message)
    thinking_placeholder.markdown(assistant_md)
    
    # Store assistant response in session state 
    st.session_state.history.append({"role": "assistant", "content": assistant_md})
    
    # No need to rerun here since we've already updated the UI 