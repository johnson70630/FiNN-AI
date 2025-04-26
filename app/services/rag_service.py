from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing import List, Dict, TypedDict, Annotated, Sequence
from typing_extensions import TypedDict
import os
import sys
import logging
from dotenv import load_dotenv, find_dotenv
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from ..scrapers.news_scraper import NewsScraperService
from ..scrapers.financial_knowledge import FinancialKnowledgeService
from ..scrapers.social_media_scraper import SocialMediaScraperService
from ..database import get_db, NewsArticle, SocialMediaPost, FinancialTerm, store_embedding, search_by_embedding, InvestopediaDict, InvestingCom

import logging

# Configure logging for this module
logger = logging.getLogger(__name__)


# Explicitly load environment variables
load_dotenv(find_dotenv())

class AgentState(TypedDict):
    """Type for tracking state in the graph"""
    question: str
    task_list: str
    context_data: str
    sentiment_analysis: List[Dict]
    final_response: str
    source_docs: List[Dict]
    terms_data: List[Dict]

class RAGService:
    def __init__(self, db: Session = None):
        # Initialize models and services
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Try to load the environment again
            load_dotenv(find_dotenv())
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not found in environment variables. Please check your .env file.")
        
        # Print API key info for debugging (masked)
        print(f"Using OpenAI API key: {api_key[:5]}...{api_key[-5:]}")
        
        self.task_llm = ChatOpenAI(
            model="gpt-4",
            temperature=0,
            api_key=api_key
        )
        self.finbert_tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.finbert_model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        self.finbert_model.eval()
        self.embeddings = OpenAIEmbeddings()
        
        # Initialize storage and services
        self.db = db or next(get_db())
        self.news_service = NewsScraperService(self.db)
        self.knowledge_service = FinancialKnowledgeService(self.db)
        self.social_service = SocialMediaScraperService(self.db)
        
        # Set up the graph
        self.graph = self._setup_graph()

    async def update_news_database(self):
        """Update all data sources"""
        total_new_items = 0
        
        # Update each data source
        news_count = await self.news_service.update_news_database()
        terms_count = await self.knowledge_service.update_terms_database()
        social_count = await self.social_service.update_posts_database()
        
        # Generate embeddings for all content
        # News articles
        for article in self.db.query(NewsArticle).filter(NewsArticle.embedding.is_(None)).all():
            embedding = await self.embeddings.aembed_query(article.title + "\n" + article.content)
            store_embedding(self.db, NewsArticle, article.id, embedding)
        
        # Social media posts
        for post in self.db.query(SocialMediaPost).filter(SocialMediaPost.embedding.is_(None)).all():
            embedding = await self.embeddings.aembed_query(post.content)
            store_embedding(self.db, SocialMediaPost, post.id, embedding)
        
        # Financial terms
        for term in self.db.query(FinancialTerm).filter(FinancialTerm.embedding.is_(None)).all():
            embedding = await self.embeddings.aembed_query(term.term + "\n" + term.definition)
            store_embedding(self.db, FinancialTerm, term.id, embedding)
        
        total_new_items = news_count + terms_count + social_count
        return total_new_items

    def _task_assignment_node(self, state: AgentState) -> AgentState:
        """Node for task assignment using GPT-4o"""
        prompt = ChatPromptTemplate.from_template("""
        You are a financial task coordinator. Break down the user's question 
        into specific analytical tasks. Focus on financial aspects that need to be analyzed.
        
        Question: {question}
        
        Break this down into 2-3 key tasks:
        """)
        
        runnable = prompt | self.task_llm | StrOutputParser()
        state["task_list"] = runnable.invoke({"question": state["question"]})
        return state

    # def _context_retrieval_node(self, state: AgentState) -> AgentState:
    #     """Node for retrieving relevant context"""
    #     # Get query embedding
    #     query_embedding = self.embeddings.embed_query(state["question"])
        
    #     # Search each content type
    #     news_results = search_by_embedding(self.db, NewsArticle, query_embedding)
    #     social_results = search_by_embedding(self.db, SocialMediaPost, query_embedding)
    #     term_results = search_by_embedding(self.db, FinancialTerm, query_embedding)

    #     invpedia_results = search_by_embedding(self.db, InvestopediaDict, query_embedding)
    #     invest_com_results = search_by_embedding(self.db, InvestingCom, query_embedding)

    #     # DEBUG: log how many hits came from each table
    #     logger.info(f"RAG retrieval counts — news: {len(news_results)}, social: {len(social_results)}, "
    #                 f"terms: {len(term_results)}, investopedia: {len(invpedia_results)}, "
    #                 f"investing_com: {len(invest_com_results)}")

        
    #     # Combine all results
    #     # state["source_docs"] = news_results + social_results
    #     # state["terms_data"] = term_results


    #     state["source_docs"] = (
    #         news_results
    #         + social_results
    #         + invest_com_results
    #     )

    #     state["terms_data"]  = invpedia_results

    #     return state
    
    def _context_retrieval_node(self, state: AgentState) -> AgentState:
        # Get query embedding
        query_embedding = self.embeddings.embed_query(state["question"])
        
        print("🔍 InvestopediaDict total rows:", self.db.query(InvestopediaDict).count())
        print("🔍 InvestopediaDict embedded rows:", self.db.query(InvestopediaDict).filter(InvestopediaDict.embedding.isnot(None)).count())

        # Retrieve from each table
        news_results       = search_by_embedding(self.db, NewsArticle,       query_embedding)
        social_results     = search_by_embedding(self.db, SocialMediaPost,   query_embedding)
        term_results       = search_by_embedding(self.db, FinancialTerm,     query_embedding)
        invpedia_results   = search_by_embedding(self.db, InvestopediaDict,  query_embedding)
        invest_com_results = search_by_embedding(self.db, InvestingCom,       query_embedding)

        # DEBUG: how many per table
        logger.info(
            f"RAG retrieval counts — "
            f"news: {len(news_results)}, social: {len(social_results)}, "
            f"terms: {len(term_results)}, investopedia: {len(invpedia_results)}, "
            f"investing_com: {len(invest_com_results)}"
        )

        # Now include FinancialTerm under terms_data
        state["terms_data"]  = term_results
        
        # …and everything else under source_docs
        state["source_docs"] = (
            news_results
            + social_results
            + invpedia_results
            + invest_com_results
        )
        return state

    async def _sentiment_analysis_node(self, state: AgentState) -> AgentState:
        """Node for FinBERT analysis"""
        sentiment_results = []
        for doc in state["source_docs"]:
            if "title" in doc:  # Only analyze news articles
                sentiment = await self._run_finbert_analysis(doc["title"])
                sentiment_results.append({
                    "title": doc["title"],
                    "sentiment": sentiment
                })
        
        state["sentiment_analysis"] = sentiment_results
        return state

    def _response_generation_node(self, state: AgentState) -> AgentState:
        """Node for generating the final response"""
        prompt = ChatPromptTemplate.from_template("""
        You are a financial analyst assistant. Use the provided context to answer the user's question.
        
        Question: {question}
        
        Tasks identified:
        {task_list}
        
        Relevant financial terms:
        {terms_data}
        
        Source documents:
        {source_docs}
        
        Sentiment analysis:
        {sentiment_analysis}
        
        Provide a comprehensive answer:
        """)
        
        runnable = prompt | self.task_llm | StrOutputParser()
        state["final_response"] = runnable.invoke(state)
        return state

    def _setup_graph(self) -> StateGraph:
        # """Set up the processing graph"""
        # workflow = StateGraph(AgentState)
        
        # # Add nodes
        # workflow.add_node("task_assignment", self._task_assignment_node)
        # workflow.add_node("context_retrieval", self._context_retrieval_node)
        # workflow.add_node("sentiment_analysis", self._sentiment_analysis_node)
        # workflow.add_node("response_generation", self._response_generation_node)
        
        # # Add edges
        # workflow.add_edge("task_assignment", "context_retrieval")
        # workflow.add_edge("context_retrieval", "sentiment_analysis")
        # workflow.add_edge("sentiment_analysis", "response_generation")
        # workflow.add_edge("response_generation", END)
        
        # # Set entry point
        # workflow.set_entry_point("task_assignment")
        
        # return workflow
    
        # Set up the graph with unique node IDs
        workflow = StateGraph(AgentState)

        # Add nodes (node IDs must NOT match state keys)
        workflow.add_node("assign_tasks",        self._task_assignment_node)
        workflow.add_node("retrieve_context",    self._context_retrieval_node)
        workflow.add_node("analyze_sentiment",   self._sentiment_analysis_node)
        workflow.add_node("generate_response",   self._response_generation_node)

        # Connect the flow
        workflow.add_edge("assign_tasks",      "retrieve_context")
        workflow.add_edge("retrieve_context",  "analyze_sentiment")
        workflow.add_edge("analyze_sentiment", "generate_response")
        workflow.add_edge("generate_response", END)

        # Entry point
        workflow.set_entry_point("assign_tasks")

        return workflow

    async def _run_finbert_analysis(self, text: str) -> str:
        """Run FinBERT sentiment analysis"""
        inputs = self.finbert_tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        with torch.no_grad():
            outputs = self.finbert_model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
            
        labels = ["negative", "neutral", "positive"]
        sentiment = labels[predictions.argmax().item()]
        confidence = predictions.max().item()
        
        return f"{sentiment} (confidence: {confidence:.2f})"

    async def process_question(self, question: str) -> str:
        """Process a user question through the RAG pipeline"""
        # Reset the graph to prevent state conflicts
        # self.graph = self._setup_graph()
        
        # Initialize the state
        state = AgentState(
            question=question,
            task_list="",
            context_data="",
            sentiment_analysis=[],
            final_response="",
            source_docs=[],
            terms_data=[]
        )
        
        # try:
        #     final_state = await self.graph.arun(state)
        #     return final_state["final_response"]

        try:
            # 1) Task assignment
            state = self._task_assignment_node(state)

            # 2) Context retrieval
            state = self._context_retrieval_node(state)

            # 3) Sentiment analysis (async)
            state = await self._sentiment_analysis_node(state)

            # 4) Final response generation
            state = self._response_generation_node(state)

            return state["final_response"]

        except Exception as e:
            # Provide a more helpful error message
            error_msg = f"Error processing question: {str(e)}"
            print(error_msg)
            return f"I'm sorry, I encountered an error while processing your question. Please try again with a different query related to finance. Error details: {str(e)[:100]}..."
