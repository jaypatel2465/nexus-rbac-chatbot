from .rag_module import get_rag_chain


async def ask_rag(question: str, role: str) -> dict:
    chain_fn = get_rag_chain(user_role=role)
    result = chain_fn({"input": question})
    return {"answer": result["answer"]}