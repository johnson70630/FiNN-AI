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

1. Run tests to verify setup:
```bash
pytest test_model.py
```

2. Start the application:
```bash
python app/main.py
```

## Project Structure
```
.
├── app/
│   ├── scrapers/           # Data collection modules
│   ├── services/          # Core business logic
│   ├── database.py        # Database configuration
│   ├── models.py          # Data models
│   └── main.py           # Application entry point
├── data/                 # Data storage directory
├── tests/               # Test files
├── requirements.txt     # Project dependencies
└── README.md           # Project documentation
```

## Usage
1. The system will automatically start collecting financial news and data when running
2. Access the application through the provided interface
3. Query financial information using natural language

## Troubleshooting
- Check environment variables are correctly set in `.env`
- Ensure all API keys are valid and have necessary permissions
- For any issues, check the application logs for detailed error messages
