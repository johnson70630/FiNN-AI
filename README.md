# Financial News AI Agent

This project implements an AI-powered financial news analysis system that collects and processes financial news, social media data, and financial terms to provide intelligent responses to user queries using a RAG (Retrieval-Augmented Generation) system.

## Features
- Real-time financial news data collection
- Social media sentiment analysis for financial markets
- Financial knowledge base integration
- Advanced RAG implementation for accurate responses
- Embeddings-based search and retrieval
- SQLite database for data persistence

## Prerequisites
- Python 3.8 or higher

## Installation

1. Clone the repository:
```bash
git clone https://github.com/johnson70630/Financial-News-AI-Agent.git
cd Financial-News-AI-Agent
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
Copy `.env.template` to `.env` and fill in your API keys:
```
# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key

# LangSmith (Optional)
LANGSMITH_TRACING=your_langsmith_tracing
LANGSMITH_ENDPOINT=your_langsmith_endpoint
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=your_langsmith_project

# Twitter Playwright Login (New)
TWITTER_USERNAME=your_twitter_username
TWITTER_PASSWORD=your_twitter_password

# Reddit API Keys
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=your_reddit_user_agent
```

## Running the Project

### Core Application
```bash
python app/main.py
```
Starts the FastAPI web server providing endpoints for accessing news, social media posts, financial terms, and querying the RAG system.

### Finance Data Tools
The `finance_data_tools.py` script is a comprehensive CLI tool for collecting, viewing, and managing financial data:
```bash
python finance_data_tools.py [command] [options]
```
Available commands:
- `collect`: Collect new financial data (news, social media posts, financial terms)
- `view`: View existing data in the database
- `schedule`: Set up scheduled data collection

Examples:
```bash
python finance_data_tools.py collect --all
python finance_data_tools.py collect --news
python finance_data_tools.py view --news --limit 10
python finance_data_tools.py schedule --interval 60
```

### API Query Client
Use `test_query.py` to interact with the running API:
```bash
python test_query.py "What are the latest trends in tech stocks?"
python test_query.py "Tell me about recent cryptocurrency news"
python test_query.py "Explain what a bear market is"
```

### Test Model and Interactive Chatbot
```bash
# Run tests
pytest test_model.py

# Start interactive chatbot
python test_model.py --chatbot
```

In chatbot mode:
- Use `stats` to view database stats
- Use `help` for available commands
- Ask financial questions naturally

## Project Structure
```
.
├── app/
│   ├── scrapers/
│   │   ├── news_scraper.py
│   │   ├── social_media_scraper.py   # Twitter (Playwright) + Reddit (API)
│   │   └── financial_knowledge.py
│   ├── services/
│   │   ├── rag_service.py
│   │   └── simple_query_service.py
│   ├── data_collection/
│   │   └── scraper_service.py
│   ├── database.py
│   └── main.py
├── data/                 # SQLite databases
├── finance_data_tools.py  # CLI tools
├── frontend/
│   └── index.html         # (Optional) Basic frontend
├── test_model.py
├── test_query.py
├── requirements.txt
└── README.md
```

## Usage

### Data Collection
1. Collect financial news, social media posts (Twitter via Playwright login, Reddit via API), and financial terms.
2. Data is stored in a local SQLite database in `data/`.
3. Set up hourly auto-collection using `finance_data_tools.py schedule`.

### Interactive Chatbot
1. Start with `python test_model.py --chatbot`.
2. Use commands or natural questions to retrieve and explore financial data.

### Web API
1. Start with `python app/main.py`
2. API endpoints:
   - `/news` – Get latest news articles
   - `/social` – Get recent social media posts
   - `/terms` – Get financial terms
   - `/query` – Ask questions via natural language

You can build your own frontend using the provided endpoints.

## Troubleshooting

### API Keys and Login Credentials
- Ensure `.env` has correct OpenAI key, Twitter username/password, Reddit credentials.
- Twitter now requires login via Playwright automation, not API Bearer Token.

### Data Collection Errors
- If Twitter/Reddit scraping fails, check account login, session timeout, or rate limits.
- If web structure changes (news sites), scraping scripts may need adjustments.

### RAG Errors
- Check OpenAI API usage limits.
- Ensure database has sufficient articles/posts/terms.
- Make sure query topics are finance-related.

## Current Database Status (Example)
- **News Articles**: 185 articles from Finviz, Yahoo Finance, CNBC
- **Social Media Posts**: 108 posts (Twitter + Reddit)
- **Financial Terms**: 70 terms from Investopedia

## License

This project is licensed under the MIT License - see the LICENSE file for details.

