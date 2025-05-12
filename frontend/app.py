import streamlit as st
import requests
import re
import sys
import os
import time
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

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
    result = r.json()
    
    # Extract the answer and any additional information
    answer = result["answer"]
    service = result.get("service", "unknown")
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
    
    # Add chain of thought if available
    if chain_of_thought:
        full_md += "\n\n---\n**🔄 Reasoning Process:**\n"
        for step in chain_of_thought:
            step_name = step.get("step", "Step")
            step_output = step.get("output", "")
            full_md += f"- **{step_name}**: {step_output}\n"
    
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
        response = requests.get(f"{BACKEND_URL}/news?limit={limit}", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data
    except Exception as e:
        st.error(f"Error fetching news: {str(e)}")
        return []

# Get recent social media posts from the backend API
def get_recent_social_posts(limit=5):
    """Get recent social media posts from the backend API"""
    try:
        response = requests.get(f"{BACKEND_URL}/social?limit={limit}", timeout=10)
        response.raise_for_status()
        data = response.json()
        return data
    except Exception as e:
        st.error(f"Error fetching social media posts: {str(e)}")
        return []

# Get stock prices from the backend API
def get_stock_prices(symbols="AAPL,MSFT,GOOGL,AMZN,META", retries=3, timeout=20):
    """Get stock prices from the backend API with retries"""
    for attempt in range(retries):
        try:
            with st.spinner(f"Loading stock data (attempt {attempt+1}/{retries})..."):
                response = requests.get(f"{BACKEND_URL}/stocks?symbols={symbols}", timeout=timeout)
                response.raise_for_status()
                data = response.json()
                return data
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                st.warning(f"Stock data request timed out. Retrying {attempt+1}/{retries}...")
                time.sleep(1)  # Wait a bit before retrying
            else:
                st.error(f"Error fetching stock prices: Timeout after {retries} attempts")
                return []
        except Exception as e:
            st.error(f"Error fetching stock prices: {str(e)}")
            return []

# Get detailed stock data for a specific symbol
def get_stock_details(symbol, period="1d", interval="15m", retries=2, timeout=20):
    """Get detailed stock data for a specific symbol with retries"""
    for attempt in range(retries):
        try:
            with st.spinner(f"Loading chart data (attempt {attempt+1}/{retries})..."):
                response = requests.get(
                    f"{BACKEND_URL}/stock/{symbol}?period={period}&interval={interval}", 
                    timeout=timeout
                )
                response.raise_for_status()
                return response.json()
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                st.warning(f"Chart data request timed out. Retrying {attempt+1}/{retries}...")
                time.sleep(1)  # Wait a bit before retrying
            else:
                st.error(f"Error fetching stock details: Timeout after {retries} attempts")
                return None
        except Exception as e:
            st.error(f"Error fetching stock details: {str(e)}")
            return None

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

# Create a layout with two columns: main content and sidebar
col_main, col_sidebar = st.columns([2, 1.5])

# Main chat area
with col_main:
    # Add a button for stock analysis
    st.markdown("### 📊 Stock Analysis")
    
    stock_analysis_container = st.container()
    
    with stock_analysis_container:
        # Create a form for stock analysis
        with st.form(key="stock_analysis_form"):
            col1, col2 = st.columns([3, 1])
            with col1:
                stock_symbol = st.text_input("Enter stock symbol (e.g., AAPL, MSFT, GOOGL)", value="AAPL").upper()
            with col2:
                days_lookback = st.selectbox("Analysis timeframe", [7, 14, 30, 60, 90, 180, 365], index=2)
            
            analyze_button = st.form_submit_button("🔍 Analyze Stock")
        
        # Handle stock analysis
        if analyze_button:
            with st.spinner(f"Analyzing {stock_symbol} based on price data, news, and social sentiment..."):
                try:
                    # Call the backend API
                    response = requests.get(f"{BACKEND_URL}/stock-analysis/{stock_symbol}?days={days_lookback}", timeout=30)
                    response.raise_for_status()
                    analysis = response.json()
                    
                    # Display analysis results
                    st.subheader(f"Analysis for {analysis['company_name']} ({analysis['symbol']})")
                    
                    # Stock price and basic info
                    col1, col2, col3 = st.columns([1, 1, 1])
                    col1.metric("Current Price", f"${analysis['current_price']:.2f}")
                    
                    # Price analysis section
                    if "price_analysis" in analysis and "error" not in analysis["price_analysis"]:
                        price_analysis = analysis["price_analysis"]
                        
                        col2.metric("Price Change", f"{price_analysis['total_change_pct']}%", 
                                   delta_color="normal" if price_analysis['total_change_pct'] >= 0 else "inverse")
                        
                        col3.metric("Volatility", f"{price_analysis['volatility_pct']}%")
                        
                        st.markdown(f"**Price Trend:** {price_analysis['summary']}")
                        
                        # Create a horizontal rule
                        st.markdown("---")
                    
                    # Create tabs for detailed analysis
                    news_tab, social_tab, signal_tab = st.tabs(["📰 News Analysis", "💬 Social Media", "🎯 Signal & Recommendation"])
                    
                    # News tab content
                    with news_tab:
                        if "news_analysis" in analysis and "error" not in analysis["news_analysis"]:
                            news = analysis["news_analysis"]
                            st.markdown(f"**News Sentiment:** {news['sentiment'].title()} ({news['sentiment_strength']})")
                            st.markdown(news["summary"])
                            
                            if "recent_articles" in news and news["recent_articles"]:
                                st.subheader("Recent News Articles")
                                for article in news["recent_articles"]:
                                    sentiment_color = "green" if article["sentiment"] == "positive" else (
                                        "red" if article["sentiment"] == "negative" else "gray")
                                    
                                    st.markdown(f"**{article['title']}**")
                                    st.markdown(f"Source: {article['source']} | Date: {article['date'][:10]} | "
                                              f"Sentiment: <span style='color:{sentiment_color}'>{article['sentiment'].title()}</span>",
                                              unsafe_allow_html=True)
                                    st.markdown(f"[Read more]({article['url']})")
                                    st.markdown("---")
                        else:
                            st.info("No news analysis available")
                    
                    # Social media tab content
                    with social_tab:
                        if "social_analysis" in analysis and "error" not in analysis["social_analysis"]:
                            social = analysis["social_analysis"]
                            st.markdown(f"**Social Media Sentiment:** {social['sentiment'].title()} ({social['sentiment_strength']})")
                            st.markdown(social["summary"])
                            
                            # Display platform distribution
                            if "platforms" in social and social["platforms"]:
                                st.markdown(f"**Platforms:** {', '.join(social['platforms'])}")
                            
                            # Display sentiment distribution
                            if all(k in social for k in ["positive_count", "neutral_count", "negative_count"]):
                                sentiment_data = {
                                    "Sentiment": ["Positive", "Neutral", "Negative"],
                                    "Count": [social["positive_count"], social["neutral_count"], social["negative_count"]]
                                }
                                sentiment_df = pd.DataFrame(sentiment_data)
                                
                                # Only show chart if there's meaningful data
                                if sum(sentiment_df["Count"]) > 0:
                                    st.markdown("**Sentiment Distribution:**")
                                    chart = go.Figure(data=[
                                        go.Bar(
                                            x=sentiment_df["Sentiment"],
                                            y=sentiment_df["Count"],
                                            marker_color=["green", "gray", "red"]
                                        )
                                    ])
                                    chart.update_layout(height=300)
                                    st.plotly_chart(chart, use_container_width=True)
                        else:
                            st.info("No social media analysis available")
                    
                    # Signal tab content
                    with signal_tab:
                        if "combined_analysis" in analysis and "error" not in analysis["combined_analysis"]:
                            combined = analysis["combined_analysis"]
                            
                            # Display recommendation prominently
                            if "recommendation" in combined:
                                rec = combined["recommendation"]
                                rec_parts = rec.split(" - ", 1)
                                if len(rec_parts) == 2:
                                    signal, explanation = rec_parts
                                    
                                    # Set color based on signal
                                    if "Buy" in signal:
                                        signal_color = "green"
                                    elif "Sell" in signal:
                                        signal_color = "red"
                                    else:
                                        signal_color = "gray"
                                        
                                    st.markdown(f"### <span style='color:{signal_color}'>{signal}</span>", unsafe_allow_html=True)
                                    st.markdown(explanation)
                                else:
                                    st.markdown(f"### {rec}")
                            
                            # Show reasoning
                            if "reasoning" in combined and combined["reasoning"]:
                                st.markdown("**Analysis Factors:**")
                                for reason in combined["reasoning"]:
                                    st.markdown(f"- {reason}")
                        else:
                            st.info("No combined signal analysis available")
                    
                except Exception as e:
                    st.error(f"Error analyzing stock: {str(e)}")
    
    # Separator before chat
    st.markdown("---")
    
    # Session state for chat history
    if "history" not in st.session_state:
        st.session_state.history = []

    # Chat title
    st.markdown("### 💬 Chat with FiNN AI")
    
    # Create a fixed-height container for chat history (prevents jumping)
    chat_container = st.container()
    # Apply the styling directly to the container
    st.markdown("""
    <style>
    /* Chat container styling */
    .stChatMessageContent {
        border-radius: 8px !important;
    }
    
    /* User message styling */
    .stChatMessage[data-testid="user-message"] .stChatMessageContent {
        background-color: #e6f2ff !important;
    }
    
    /* Assistant message styling */
    .stChatMessage[data-testid="assistant-message"] .stChatMessageContent {
        background-color: #f5f5f5 !important;
    }
    
    /* Custom height for chat area */
    [data-testid="stVerticalBlock"] > div:has(.stChatMessage) {
        max-height: 400px;
        overflow-y: auto;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
        background-color: #f9f9f9;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Display conversation history
    with chat_container:
        for msg in st.session_state.history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"], unsafe_allow_html=False)

    # Custom CSS for chat UI to prevent movement
    st.markdown("""
    <style>
    /* General chat styles */
    .stChatFloatingInputContainer {
        position: sticky !important;
        bottom: 20px !important;
        z-index: 999 !important;
        background-color: white !important;
        padding: 10px !important;
        border-top: 1px solid #eee !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
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

        # Store assistant response
        st.session_state.history.append({"role": "assistant", "content": assistant_md})
        
        # Force rerun to show the complete conversation
        st.rerun()

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
            if st.button("🔄 Refresh", key="refresh_stocks"):
                st.rerun()
        
        # Fetch stock data
        stock_data = get_stock_prices(user_symbols)
        
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
                        stock_details = get_stock_details(selected_symbol, period=period)
                        
                        if stock_details and "data" in stock_details:
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
            if st.button("🔄 Refresh", key="refresh_news"):
                st.rerun()
        
        with st.spinner("Loading news..."):
            news = get_recent_news(limit=limit)
        
        if news:
            for article in news:
                try:
                    with st.expander(f"{article['title']}", expanded=True):
                        # Format date nicely
                        try:
                            # Try to parse the date string to a datetime object
                            date_obj = datetime.fromisoformat(article['date'].replace('Z', '+00:00'))
                            # Format date and time separately
                            date_str = date_obj.strftime("%Y-%m-%d")
                            time_str = date_obj.strftime("%H:%M")
                            st.markdown(f"**Source:** {article['source']} • **Date:** {date_str} • **Time:** {time_str}")
                        except:
                            # Fallback if date parsing fails
                            st.markdown(f"**Source:** {article['source']} • **Date:** {article['date']}")
                            
                        st.markdown(article['content'])
                        st.markdown(f"[Read more]({article['url']})")
                except Exception as e:
                    st.error(f"Error displaying article: {str(e)}")
        else:
            st.warning("Could not fetch news articles. The database might be empty or there's a connection issue.")
    
    # Social tab
    with tabs[2]:
        st.subheader("Recent Social Media Posts")
        
        # Add refresh button for social
        col1, col2 = st.columns([3, 1])
        with col1:
            social_limit = st.slider("Number of posts", min_value=3, max_value=15, value=5)
        with col2:
            if st.button("🔄 Refresh", key="refresh_social"):
                st.rerun()
        
        with st.spinner("Loading social posts..."):
            posts = get_recent_social_posts(limit=social_limit)
        
        if posts:
            for post in posts:
                try:
                    # Format date object and improve display
                    try:
                        date_obj = datetime.fromisoformat(post['date'].replace('Z', '+00:00'))
                        date_str = date_obj.strftime("%Y-%m-%d")
                        time_str = date_obj.strftime("%H:%M")
                        header = f"{post['platform']} • Date: {date_str} • Time: {time_str}"
                    except:
                        # Fallback if date parsing fails
                        header = f"{post['platform']} - {post['date']}"
                        
                    with st.expander(header, expanded=True):
                        st.markdown(post['content'])
                        if post.get('url'):
                            st.markdown(f"[View original post]({post['url']})")
                except Exception as e:
                    st.error(f"Error displaying post: {str(e)}")
        else:
            st.warning("Could not fetch social media posts. The database might be empty or there's a connection issue.") 