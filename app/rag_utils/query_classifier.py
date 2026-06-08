from groq import Groq
import re

from .secret_key import groq_api_key, groq_model

# Use key directly to avoid timing issues with env var loading
client = Groq(api_key=groq_api_key)

def detect_query_type_llm(question: str) -> str:
    prompt = f"""You are a query classifier. Decide if the question should be answered by:
- SQL: structured data queries (counts, averages, filters, employee details, numbers, comparisons)
- RAG: document search (summaries, policies, explanations, definitions, general knowledge)

Respond with exactly one word: SQL or RAG

Question: "{question}"

Answer:"""

    try:
        response = client.chat.completions.create(
            model=groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=5
        )
        raw = response.choices[0].message.content.strip()
        # Clean any markdown, punctuation, or extra text
        cleaned = re.sub(r"[^A-Za-z]", "", raw).upper()
        if cleaned.startswith("SQL"):
            return "SQL"
        return "RAG"
    except Exception as e:
        print(f"[Classifier Error] {e} — defaulting to RAG")
        return "RAG"
