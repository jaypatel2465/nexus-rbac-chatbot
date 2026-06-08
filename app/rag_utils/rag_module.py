# ========== CONFIG ==========
from pathlib import Path
import os
import pandas as pd
import sqlite3

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableMap

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

from .secret_key import groq_api_key, groq_model

# Disable LangSmith tracing (no valid key provided)
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["GROQ_API_KEY"] = groq_api_key


# ==============================
# ====Split, load, embed========
# ==============================

# Using free HuggingFace embeddings — no API key required
hf_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Chroma(
    collection_name="my_collection",
    persist_directory="chroma_db",
    embedding_function=hf_embeddings
)


def embed_documents_to_vectorstore(docs):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    vectorstore.add_documents(splits)
    print(f"[Indexer] Embedded {len(splits)} chunks into vectorstore.")


def load_file(filepath, role):
    ext = Path(filepath).suffix.lower()
    try:
        if ext == ".csv":
            df1 = pd.read_csv(filepath)
            documents = []
            for row in df1.to_dict(orient="records"):
                content = "\n".join(f"{k}: {v}" for k, v in row.items())
                documents.append(
                    Document(
                        page_content=content,
                        metadata={"role": role.lower(), "source": Path(filepath).name}
                    )
                )
            return documents

        elif ext == ".md":
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return [
                Document(
                    page_content=content,
                    metadata={"role": role.lower(), "source": Path(filepath).name}
                )
            ]
        else:
            return None

    except Exception as e:
        print(f"[Indexer] Failed to process {filepath}: {e}")
        return None


def run_indexer():
    conn = sqlite3.connect("roles_docs.db")
    c = conn.cursor()
    c.execute("SELECT id, filepath, role FROM documents WHERE embedded = 0")

    all_docs = []

    for doc_id, path, role in c.fetchall():
        docs = load_file(path, role)
        if docs:
            if isinstance(docs, list):
                all_docs.extend(docs)
            else:
                all_docs.append(docs)
            c.execute("UPDATE documents SET embedded = 1 WHERE id = ?", (doc_id,))

    if all_docs:
        embed_documents_to_vectorstore(all_docs)
        conn.commit()

    conn.close()
    print(f"[Indexer] Indexed {len(all_docs)} document chunks.")


# ==============================
# ========== PROMPT ==========
# ==============================
system_prompt = (
    "You are an assistant for answering queries from internal company documents.\n"
    "Use the retrieved context below to answer accurately and concisely.\n"
    "If the answer is not in the context, say so clearly.\n"
    "Format your response with:\n"
    "- Headers where appropriate\n"
    "- Bullet points for lists\n"
    "- Tables for structured/CSV data\n"
    "- Source document name when available\n\n"
    "Context:\n{context}"
)

chat_prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "{input}"),
])

# ==============================
# ========== MODEL ==========
# ==============================
model = ChatGroq(
    model=groq_model,
    temperature=0.2
)


def _format_docs(docs):
    """Format retrieved documents into a single context string."""
    parts = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        parts.append(f"[Source: {source}]\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


def get_rag_chain(user_role: str):
    """Build and return a role-filtered RAG chain using LCEL."""
    user_role = user_role.lower()

    if user_role == "c-level":
        retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    elif user_role == "general":
        retriever = vectorstore.as_retriever(search_kwargs={
            "k": 4,
            "filter": {"role": "general"}
        })

    else:
        retriever = vectorstore.as_retriever(search_kwargs={
            "k": 4,
            "filter": {"role": {"$in": [user_role, "general"]}}
        })

    # LCEL chain: input → retrieve → format → prompt → model → parse
    chain = (
        RunnableMap({
            "context": (lambda x: x["input"]) | retriever | _format_docs,
            "input":   RunnablePassthrough() | (lambda x: x["input"]),
        })
        | chat_prompt
        | model
        | StrOutputParser()
    )

    # Wrap to return {"answer": ...} dict to match existing callers
    def invoke_chain(inputs: dict) -> dict:
        answer = chain.invoke(inputs)
        return {"answer": answer}

    return invoke_chain
