import streamlit as st
import requests
import re
import sys
import os
import time
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random

# Add the project root to Python path when running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure page
st.set_page_config(page_title="FiNN AI", layout="wide")
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

# Get recent news from the backend API
def get_recent_news(limit=5):
    """Get recent news articles from the backend API"""
    try:
        response = requests.get(f"{BACKEND_URL}/news?limit={limit}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching news: {str(e)}")
        return []

# Get recent social media posts from the backend API
def get_recent_social_posts(limit=5):
    """Get recent social media posts from the backend API"""
    try:
        response = requests.get(f"{BACKEND_URL}/social?limit={limit}", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching social media posts: {str(e)}")
        return []

# Get stock prices from the backend API
def get_stock_prices(symbols="AAPL,MSFT,GOOGL,AMZN,META"):
    """Get stock prices from the backend API"""
    try:
        response = requests.get(f"{BACKEND_URL}/stocks?symbols={symbols}", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data
    except Exception as e:
        st.error(f"Error fetching stock prices: {str(e)}")
        # Return mock data as fallback
        return generate_mock_stocks(symbols.split(","))

# Get detailed stock data for a specific symbol
def get_stock_details(symbol, period="1d", interval="15m"):
    """Get detailed stock data for a specific symbol"""
    try:
        response = requests.get(f"{BACKEND_URL}/stock/{symbol}?period={period}&interval={interval}", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching stock details: {str(e)}")
        # Return mock data as fallback
        return generate_mock_stock_details(symbol, period, interval)

# Generate mock stock data for frontend fallback
def generate_mock_stocks(symbols):
    """Generate mock stock data when API is unavailable"""
    mock_data = []
    company_names = {
        "AAPL": "Apple Inc.",
        "MSFT": "Microsoft Corporation",
        "GOOGL": "Alphabet Inc.",
        "AMZN": "Amazon.com, Inc.",
        "META": "Meta Platforms, Inc."
    }
    
    for symbol in symbols:
        # Generate a stable price based on the symbol
        base_price = sum(ord(c) for c in symbol) % 1000
        if base_price < 50:
            base_price += 50
            
        mock_data.append({
            "symbol": symbol,
            "company_name": company_names.get(symbol, f"{symbol} Inc."),
            "current_price": base_price + (random.random() - 0.5) * 10,
            "currency": "USD",
            "note": "Frontend mock data"
        })
    
    return mock_data

# Generate mock stock details for frontend fallback
def generate_mock_stock_details(symbol, period="1d", interval="15m"):
    """Generate mock stock details when API is unavailable"""
    # Generate a stable price based on the symbol
    base_price = sum(ord(c) for c in symbol) % 1000
    if base_price < 50:
        base_price += 50
        
    # Company name mapping for common symbols
    company_names = {
        "AAPL": "Apple Inc.",
        "MSFT": "Microsoft Corporation",
        "GOOGL": "Alphabet Inc.",
        "AMZN": "Amazon.com, Inc.",
        "META": "Meta Platforms, Inc."
    }
    
    # Generate mock data points
    now = datetime.now()
    data_points = []
    
    # Determine number of points based on period and interval
    num_points = 20  # Default
    if period == "1d" and interval == "15m":
        num_points = 20
    elif period == "5d":
        num_points = 30
    elif "mo" in period:
        num_points = 40
    elif "y" in period:
        num_points = 50
    
    # Generate price movements
    for i in range(num_points):
        point_time = now - timedelta(hours=num_points-i)
        price_change = (random.random() - 0.5) * base_price * 0.02
        price = base_price * (1 + (i - num_points//2) * 0.001) + price_change
        
        data_points.append({
            "timestamp": point_time.isoformat(),
            "open": price - random.random() * 2,
            "high": price + random.random() * 3,
            "low": price - random.random() * 3,
            "close": price,
            "volume": int(random.random() * 1000000)
        })
        
    current_price = data_points[-1]["close"] if data_points else base_price
    
    return {
        "symbol": symbol,
        "company_name": company_names.get(symbol, f"{symbol} Inc."),
        "current_price": current_price,
        "currency": "USD",
        "data": data_points,
        "note": "Frontend mock data (API unavailable)"
    }

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
        st.experimental_rerun()
    st.stop()
else:
    st.success("✅ Connected to FiNN AI !!")

# Create a layout with two columns: main content and sidebar
col_main, col_sidebar = st.columns([2, 1.5])

# Main chat area
with col_main:
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

# Sidebar with market data
with col_sidebar:
    # Tab selection
    tabs = st.tabs(["📈 Stocks", "📰 News", "💬 Social"])
    
    # Stocks tab
    with tabs[0]:
        st.subheader("Recent Stock Prices")
        # Default symbols
        default_symbols = "AAPL,MSFT,GOOGL,AMZN,META"
        
        # Symbol input and refresh button in the same row
        col1, col2 = st.columns([4, 1])
        with col1:
            user_symbols = st.text_input("Enter stock symbols (comma-separated)", value=default_symbols)
        with col2:
            refresh_stocks = st.button("🔄 Refresh", key="refresh_stocks")
        
        # Fetch stock data
        stock_data = get_stock_prices(user_symbols)
        
        # Show mock data message if needed
        using_mock = any('note' in stock and 'mock' in stock.get('note', '').lower() for stock in stock_data)
        if using_mock:
            st.info("⚠️ Using demo data - real-time stock API is unavailable")
        
        if stock_data:
            # Create a DataFrame
            df = pd.DataFrame(stock_data)
            if not df.empty:
                # Format the prices in two columns
                cols = st.columns(2)
                for idx, row in df.iterrows():
                    col_idx = idx % 2
                    if "error" not in row:
                        # Handle missing current_price
                        price = row.get('current_price')
                        price_display = f"${price:.2f} {row.get('currency', 'USD')}" if price is not None else "N/A"
                        
                        cols[col_idx].metric(
                            label=f"{row['company_name']} ({row['symbol']})",
                            value=price_display
                        )
                    else:
                        cols[col_idx].error(f"{row['symbol']}: {row['error']}")
                
                # Add option to view detailed chart
                valid_symbols = [row['symbol'] for idx, row in df.iterrows() 
                                if "error" not in row and row.get('current_price') is not None]
                
                if valid_symbols:
                    selected_symbol = st.selectbox("Select stock for detailed chart", valid_symbols)
                    
                    period = st.selectbox("Select time period", ["1d", "5d", "1mo", "3mo", "6mo", "1y"])
                    
                    if selected_symbol:
                        with st.spinner("Loading chart data..."):
                            stock_details = get_stock_details(selected_symbol, period=period)
                            
                            if stock_details and "data" in stock_details:
                                # Check if we're using mock data
                                is_mock = 'note' in stock_details and 'mock' in stock_details.get('note', '').lower()
                                if is_mock:
                                    st.info(f"⚠️ Showing demo data for {selected_symbol}")
                                    
                                # Create Plotly chart
                                df_detail = pd.DataFrame(stock_details["data"])
                                if not df_detail.empty:
                                    df_detail["timestamp"] = pd.to_datetime(df_detail["timestamp"])
                                    
                                    fig = go.Figure()
                                    fig.add_trace(go.Scatter(
                                        x=df_detail["timestamp"],
                                        y=df_detail["close"],
                                        mode='lines',
                                        name='Close Price',
                                        line=dict(color='#4a90e2')
                                    ))
                                    
                                    # Add high/low range as a filled area
                                    fig.add_trace(go.Scatter(
                                        x=df_detail["timestamp"],
                                        y=df_detail["high"],
                                        mode='lines',
                                        line=dict(width=0),
                                        showlegend=False
                                    ))
                                    fig.add_trace(go.Scatter(
                                        x=df_detail["timestamp"],
                                        y=df_detail["low"],
                                        mode='lines',
                                        line=dict(width=0),
                                        fill='tonexty',
                                        fillcolor='rgba(74, 144, 226, 0.1)',
                                        showlegend=False
                                    ))
                                    
                                    fig.update_layout(
                                        title=f"{stock_details['company_name']} ({stock_details['symbol']})",
                                        xaxis_title="Date",
                                        yaxis_title=f"Price ({stock_details.get('currency', 'USD')})",
                                        height=400,
                                        margin=dict(l=10, r=10, t=40, b=10)
                                    )
                                    
                                    st.plotly_chart(fig, use_container_width=True)
                                    
                                    # Show latest price statistics
                                    latest = df_detail.iloc[-1] if not df_detail.empty else None
                                    if latest is not None:
                                        stats_cols = st.columns(4)
                                        stats_cols[0].metric("Open", f"${latest['open']:.2f}")
                                        stats_cols[1].metric("High", f"${latest['high']:.2f}")
                                        stats_cols[2].metric("Low", f"${latest['low']:.2f}")
                                        stats_cols[3].metric("Close", f"${latest['close']:.2f}")
                                else:
                                    st.warning(f"No data points available for {selected_symbol}")
                            else:
                                st.warning(f"Could not load detailed data for {selected_symbol}")
                else:
                    st.warning("No valid stocks available for charting")
        else:
            st.info("No stock data available")
    
    # News tab
    with tabs[1]:
        st.subheader("Recent Financial News")
        
        # Add refresh button
        col1, col2 = st.columns([3, 1])
        with col1:
            limit = st.slider("Number of articles", min_value=3, max_value=15, value=5)
        with col2:
            if st.button("🔄 Refresh"):
                st.experimental_rerun()
        
        news = get_recent_news(limit=limit)
        
        if news:
            for article in news:
                with st.expander(f"{article['title']}", expanded=True):
                    st.markdown(f"**Source:** {article['source']} • **Date:** {article['date']}")
                    st.markdown(article['content'])
                    st.markdown(f"[Read more]({article['url']})")
        else:
            st.info("No recent news available")
    
    # Social tab
    with tabs[2]:
        st.subheader("Recent Social Media Posts")
        
        # Add refresh button for social
        col1, col2 = st.columns([3, 1])
        with col1:
            social_limit = st.slider("Number of posts", min_value=3, max_value=15, value=5)
        with col2:
            if st.button("🔄 Refresh Posts"):
                st.experimental_rerun()
        
        posts = get_recent_social_posts(limit=social_limit)
        
        if posts:
            for post in posts:
                with st.expander(f"{post['platform']} - {post['date']}", expanded=True):
                    st.markdown(post['content'])
                    if post['url']:
                        st.markdown(f"[View original post]({post['url']})")
        else:
            st.info("No recent social media posts available") 