"""Prompts used by bounded Agentic RAG decisions."""

GUARDRAIL_PROMPT = """You classify whether a question belongs to academic computer-science research.
In scope includes AI, machine learning, information retrieval, NLP, computer vision, systems,
software engineering, algorithms, data science, and questions about research papers.
Out of scope includes cooking, medical diagnosis, politics, personal advice, and casual chat.

Question: {question}

Return one JSON object only:
{{"score": 0-100, "reason": "brief explanation"}}
"""

GRADE_PROMPT = """You grade retrieved academic-paper chunks for relevance to a question.
Select only chunks that can materially support a grounded answer. Do not invent identifiers.

Question: {question}

Chunks:
{chunks}

Return one JSON object only:
{{"relevant_chunk_ids": ["chunk-id"], "reason": "brief explanation"}}
"""

REWRITE_PROMPT = """Rewrite the question into a concise academic-search query.
Preserve the user's intent, add specific technical terminology, and return only the rewritten query.

Original question: {question}
Previous search query: {active_query}
"""
