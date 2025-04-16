# Finance News AI Agent

This project implements a finance news AI agent using LangChain's RAG system with GPT-4 and AWS services.

## Features
- Real-time finance news data collection
- AWS-based data storage and retrieval
- LangChain RAG implementation
- GPT-4 powered responses
- REST API interface

## Setup
1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
Create a `.env` file with:
```
OPENAI_API_KEY=your_openai_api_key
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=your_aws_region
```

3. Run the application:
```bash
uvicorn app.main:app --reload
```
