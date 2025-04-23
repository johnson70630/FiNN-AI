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

# LangSmith
LANGSMITH_TRACING=your_langsmith_tracing
LANGSMITH_ENDPOINT=your_langsmith_endpoint
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=your_langsmith_project

# Twitter API Key 
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

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
This starts the web API server that provides endpoints for accessing news, social media posts, and financial terms.

### Finance Data Tools

The `finance_data_tools.py` script is a comprehensive utility for collecting, viewing, and managing financial data:

```bash
python finance_data_tools.py [command] [options]
```

Available commands:
- `collect`: Collect new financial data (news, social media posts, financial terms)
- `view`: View existing data in the database
- `schedule`: Set up scheduled data collection

Examples:
```bash
# Collect all data sources
python finance_data_tools.py collect --all

# Collect only news articles
python finance_data_tools.py collect --news

# View recent news articles
python finance_data_tools.py view --news --limit 10

# Set up hourly data collection
python finance_data_tools.py schedule --interval 60
```

### Test Model and Interactive Chatbot

The `test_model.py` script serves two purposes: testing the system components and providing an interactive chatbot interface:

```bash
# Run tests to verify setup
pytest test_model.py

# Start the interactive chatbot
python test_model.py --chatbot
```

In chatbot mode, you can:
- View database statistics with the 'stats' command
- Ask questions about finance using natural language
- Search for specific financial terms and news
- Type 'help' for a list of available commands

## Project Structure
```
.
├── app/
│   ├── scrapers/           # Data collection modules
│   │   ├── news_scraper.py           # News article collection
│   │   ├── social_media_scraper.py   # Social media post collection
│   │   └── financial_knowledge.py    # Financial terms collection
│   ├── services/          # Core business logic
│   │   └── rag_service.py # RAG implementation for Q&A
│   ├── data_collection/   # Scheduling and coordination
│   ├── database.py        # Database configuration and models
│   └── main.py           # Web API entry point
├── data/                 # Data storage directory (SQLite database)
├── finance_data_tools.py # Comprehensive CLI tool for data management
├── test_model.py        # Testing and interactive chatbot
├── requirements.txt     # Project dependencies
└── README.md           # Project documentation
```

## Usage

### Data Collection
1. Collect financial news articles, social media posts, and financial terms using the `finance_data_tools.py` script
2. Data is stored in a SQLite database in the `data/` directory
3. Set up automated collection schedule to keep data fresh

### Interactive Chatbot
1. Start the chatbot with `python test_model.py --chatbot`
2. Use commands to browse and search the database:
   - `stats`: Show database statistics
   - `help`: Display available commands
   - `search [query]`: Search all content for a specific query
   - Ask natural language questions about finance

### Web API
1. Start the API server with `python app/main.py`
2. Access the following endpoints:
   - `/news`: Get latest news articles
   - `/social`: Get social media posts
   - `/terms`: Get financial terms
   - `/query`: Submit natural language queries
3. Integrate with your own frontend or applications

## Troubleshooting

### API Keys
- Check environment variables are correctly set in `.env`
- Ensure all API keys are valid and have necessary permissions
- OpenAI API key is required for the RAG functionality
- Twitter and Reddit API keys are needed for social media scraping

### Data Collection Issues
- If you encounter rate limiting with Twitter/Reddit APIs, wait and try again later
- For news scrapers, check that the website structures haven't changed
- Use `finance_data_tools.py view --stats` to verify data was collected

### RAG Service Errors
- If the chatbot fails to provide meaningful answers, check that:
  - Your OpenAI API key is valid and has sufficient credits
  - The database contains enough data (at least some news articles and terms)
  - The query is related to financial topics

### Detailed Logs
- For detailed error messages, check the application logs
- When using `test_model.py --chatbot`, errors will be displayed in the console

## Current Database Status

As of the latest update, the database contains:
- **News Articles**: 185 articles from Finviz, Yahoo Finance, and CNBC
- **Social Media Posts**: 108 posts from finance-related subreddits
- **Financial Terms**: 70 financial terms from Investopedia

This provides a robust foundation for financial analysis and research.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
