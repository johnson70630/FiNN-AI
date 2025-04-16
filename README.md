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
Create a `.env` file in the project root with:
```
# API Keys
TWITTER_BEARER_TOKEN=your_twitter_token
OPENAI_API_KEY=your_openai_api_key
NEWS_API_KEY=your_news_api_key
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
