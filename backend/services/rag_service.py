"""
RAG Service – revised so the LLM actually *uses* the retrieved context.

Key fixes
---------
1. `_format_docs` → human-readable blocks for the prompt.
2. `_response_generation_node` now injects those blocks instead of raw dicts.
3. `terms_data` carries Investopedia hits (invpedia_results) as requested.
"""

from __future__ import annotations

import os, logging, torch
from typing import List, Dict, TypedDict, Annotated, Sequence
from typing_extensions import TypedDict
from dotenv import load_dotenv, find_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from backend.core.database import (
    get_db, NewsArticle, SocialMediaPost, FinancialTerm,
    InvestopediaDict, InvestingCom, store_embedding, search_by_embedding
)
from backend.scrapers.news_scraper import NewsScraperService
from backend.scrapers.financial_knowledge import FinancialKnowledgeService
from backend.scrapers.social_media_scraper import SocialMediaScraperService

# ------------------------------------------------------------------------------
# Logging / env
# ------------------------------------------------------------------------------
logger = logging.getLogger(__name__)
load_dotenv(find_dotenv())

# ------------------------------------------------------------------------------
# State definition
# ------------------------------------------------------------------------------
class AgentState(TypedDict):
    question: str
    task_list: str
    context_data: str 
    sentiment_analysis: List[Dict]
    final_response: str
    source_docs: List[Dict]      
    terms_data:  List[Dict]     

# ------------------------------------------------------------------------------
# RAG Service
# ------------------------------------------------------------------------------
class RAGService:
    # --------------------------------------------------------------------------
    # Init
    # --------------------------------------------------------------------------
    def __init__(self, db: Session | None = None):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            load_dotenv(find_dotenv())
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY missing")
        print(f"Using OpenAI key: {api_key[:5]}…{api_key[-5:]}")

        self.task_llm  = ChatOpenAI(model="gpt-4o", temperature=0.0, api_key=api_key)
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

        # FinBERT sentiment
        self.finbert_tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.finbert_model     = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert").eval()

        # DB/session & scrapers
        self.db = db or next(get_db())
        self.news_service     = NewsScraperService(self.db)
        self.knowledge_service= FinancialKnowledgeService(self.db)
        self.social_service   = SocialMediaScraperService(self.db)

        self.graph = self._setup_graph()

    # --------------------------------------------------------------------------
    # Helper – doc formatter
    # --------------------------------------------------------------------------
    @staticmethod
    def _format_docs(docs: List[Dict]) -> str:
        """Pretty-print retrieved docs so the LLM actually reads them."""
        if not docs:
            return "None"
        out = []
        for i, d in enumerate(docs, 1):
            title   = d.get("title")   or d.get("term", "Untitled")
            source  = d.get("source")  or d.get("platform", "Source?")   # InvestingCom, X, etc.
            date    = d.get("date", "")
            content = (d.get("content") or d.get("definition", ""))[:600]
            out.append(f"[{i}] {title}\nSource: {source}  Date: {date}\n{content}\n")
        return "\n".join(out)

    # --------------------------------------------------------------------------
    # Nodes
    # --------------------------------------------------------------------------
    def _task_assignment_node(self, state: AgentState) -> AgentState:
        prompt = ChatPromptTemplate.from_template(
            "Break the financial question into 2-3 concise tasks.\n\nQuestion: {q}"
        )
        state["task_list"] = (prompt | self.task_llm | StrOutputParser()).invoke({"q": state["question"]})
        return state    

    # ------------------------------------------------------------------
    # helper – turn {id, url, similarity} into a rich dict  -------------
    # ------------------------------------------------------------------
    def _as_dict_investing(self, hit) -> Dict:
        row = self.db.query(InvestingCom).get(hit["id"])
        if not row:
            return {}
        return {
            "title":   row.title,
            "content": row.content,
            "source":  "Investing.com",
            "url":     row.url,
            "date":    row.published,
            "similarity": hit.get("similarity", 0.0)
        }

    def _as_dict_investopedia(self, hit) -> Dict:
        row = self.db.query(InvestopediaDict).get(hit["id"])
        if not row:
            return {}
        return {
            "term":        row.title,              # e.g. "10-K: Definition…"
            "definition":  row.content,            # your column is named content
            "url":         row.url,
            "similarity":  hit.get("similarity",0)
        }

    # ------------------------------------------------------------------
    # CONTEXT RETRIEVAL  – hydrated & keyword-filtered  -----------------
    # ------------------------------------------------------------------
    def _context_retrieval_node(self, state: AgentState) -> AgentState:
        q_emb  = self.embeddings.embed_query(state["question"])
        kwords = [w.lower() for w in state["question"].split() if len(w) > 2]

        # 1. vector search (limit enlarged a bit)
        raw_news = search_by_embedding(self.db, InvestingCom,     q_emb, limit=25)
        raw_defs = search_by_embedding(self.db, InvestopediaDict, q_emb, limit=25)

        # 2. hydrate hits into full docs
        news_docs = [self._as_dict_investing(hit)   for hit in raw_news]
        def_docs  = [self._as_dict_investopedia(hit)for hit in raw_defs]

        # 3. keyword filter (keep rows that mention ANY keyword)
        def kw_filter(docs):
            out = []
            for d in docs:
                blob = f"{d.get('title','')} {d.get('content','')} {d.get('definition','')}".lower()
                if any(k in blob for k in kwords):
                    out.append(d)
            return out

        state["source_docs"] = kw_filter(news_docs)
        state["terms_data"]  = kw_filter(def_docs)

        logger.info(
            "Post-filter hits | news:%d  investopedia:%d",
            len(state["source_docs"]), len(state["terms_data"])
        )
        return state

    async def _sentiment_analysis_node(self, state: AgentState) -> AgentState:
        results = []
        for d in state["source_docs"]:
            if d.get("title"):
                sent = await self._run_finbert(d["title"])
                # Add content sentiment if available
                content_sentiment = ""
                if d.get("content"):
                    # Get first 100 chars for a summary
                    content_snippet = d.get("content", "")[:100] + "..."
                    content_sent = await self._run_finbert(content_snippet)
                    content_sentiment = f"Content: {content_sent}"
                
                # Calculate market impact based on sentiment
                impact = "neutral"
                if "positive" in sent:
                    impact = "potentially positive"
                elif "negative" in sent:
                    impact = "potentially negative"
                
                results.append({
                    "title": d["title"], 
                    "sentiment": sent,
                    "content_sentiment": content_sentiment,
                    "market_impact": impact,
                    "source": d.get("source", "Unknown"),
                    "date": d.get("date", "Unknown")
                })
        
        state["sentiment_analysis"] = results
        return state    

    # ------------------------------------------------------------------
    # RESPONSE GENERATION  – fallback if context empty
    # ------------------------------------------------------------------
    def _response_generation_node(self, state: AgentState) -> AgentState:

        # -------- 0. zero-context fallback  --------
        if not state["source_docs"] and not state["terms_data"]:
            prompt = ChatPromptTemplate.from_template("""
You are a helpful financial assistant. Answer the question from your own knowledge.

Question: {q}
""")
            state["final_response"] = (
                prompt | self.task_llm | StrOutputParser()
            ).invoke({"q": state["question"]})
            return state

        # -------- 1. build context blocks --------
        docs_txt  = self._format_docs(state["source_docs"])
        terms_txt = self._format_docs(state["terms_data"])

        prompt = ChatPromptTemplate.from_template("""
SYSTEM:
You are a financial advisor assistant who specializes in providing accurate, up-to-date information about financial markets, investments, and economic topics.

GUIDELINES:
1. Use the Context information whenever possible and cite sources with [n] notation.
2. Include ONLY factual information from the provided context.
3. When citing, use the exact number from the context (e.g., [1], [2]) at the end of sentences that use that information.
4. If the Context is insufficient, you may supplement with your general knowledge but clearly mark these additions with "(general knowledge)".
5. Prioritize recent news over older information.
6. Provide balanced perspectives when there are conflicting viewpoints.
7. For financial terms, use definitions from Investopedia when available.
8. When explaining complex concepts, break them down into simple terms.

USER QUESTION:
{q}

=== Context: News & Social ===
{docs}

=== Context: Investopedia ===
{terms}
""")

        # 1. Generate main answer
        final_answer = (
            prompt | self.task_llm | StrOutputParser()
        ).invoke({
            "q":     state["question"],
            "docs":  docs_txt,
            "terms": terms_txt
        })

        # 2. Detect which [n] were actually cited
        cited_numbers = set()
        import re
        for match in re.findall(r'\[(\d+)\]', final_answer):
            cited_numbers.add(int(match))

        # 3. Build sources list only for cited docs
        all_docs = state["source_docs"] + state["terms_data"]
        numbered_sources = []
        for idx, doc in enumerate(all_docs, 1):
            if idx in cited_numbers:
                title = doc.get("title") or doc.get("term", "Untitled")
                url   = doc.get("url", "#")
                numbered_sources.append(f"[{idx}] {title} ({url})")

        sources_text = "\n\nSources:\n" + "\n".join(numbered_sources) if numbered_sources else ""

        # 4. Combine answer + sources
        state["final_response"] = final_answer.strip() + "\n\n" + sources_text.strip()


        return state

    # --------------------------------------------------------------------------
    # Sentiment helper
    # --------------------------------------------------------------------------
    async def _run_finbert(self, text: str) -> str:
        toks = self.finbert_tokenizer(text, return_tensors="pt", truncation=True)
        with torch.no_grad():
            logits = self.finbert_model(**toks).logits
            scores = torch.nn.functional.softmax(logits, dim=-1)[0]
        label = ["negative", "neutral", "positive"][scores.argmax().item()]
        return f"{label} ({scores.max().item():.2f})"

    # --------------------------------------------------------------------------
    # Graph assembly
    # --------------------------------------------------------------------------
    def _setup_graph(self) -> StateGraph:
        g = StateGraph(AgentState)
        g.add_node("task",      self._task_assignment_node)
        g.add_node("retrieve",  self._context_retrieval_node)
        g.add_node("sentiment", self._sentiment_analysis_node)
        g.add_node("answer",    self._response_generation_node)

        g.add_edge("task", "retrieve")
        g.add_edge("retrieve", "sentiment")
        g.add_edge("sentiment", "answer")
        g.add_edge("answer", END)

        g.set_entry_point("task")
        return g

    # --------------------------------------------------------------------------
    # Public entry
    # --------------------------------------------------------------------------
    async def process_question(self, question: str) -> str:
        state = AgentState(
            question=question,
            task_list="",
            sentiment_analysis=[],
            final_response="",
            source_docs=[],
            terms_data=[]
        )

        # run nodes sequentially (sync + async mixed)
        state = self._task_assignment_node(state)
        state = self._context_retrieval_node(state)
        state = await self._sentiment_analysis_node(state)
        state = self._response_generation_node(state)

        return state["final_response"]