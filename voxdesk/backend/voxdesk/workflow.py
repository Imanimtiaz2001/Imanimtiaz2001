import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .retrieval import retrieve
from .schemas import Answer, ModelAnswer, Source

PROMPT_VERSION = "voxdesk-grounded-v1"


class State(TypedDict, total=False):
    owner: str
    question: str
    history: list[dict]
    mode: str
    sources: list[Source]
    generated: ModelAnswer
    answer: Answer
    timings: dict[str, float]


class Workflow:
    def __init__(self, database, provider):
        self.database, self.provider = database, provider
        graph = StateGraph(State)
        graph.add_node("retrieve", self.retrieve)
        graph.add_node("generate", self.generate)
        graph.add_node("validate", self.validate)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", "validate")
        graph.add_edge("validate", END)
        self.graph = graph.compile()

    async def retrieve(self, state):
        start = time.perf_counter()
        query = state["question"]
        if (
            state["history"]
            and len(query.split()) <= 12
            and any(
                word in query.lower().split()
                for word in {"it", "that", "they", "this", "them", "those"}
            )
        ):
            query = state["history"][-1]["question"] + "\nFollow-up: " + query
        sources = (
            await retrieve(self.database, self.provider, state["owner"], query)
            if state["mode"] == "knowledge"
            else []
        )
        return {
            "sources": sources,
            "timings": {"retrieval_ms": round((time.perf_counter() - start) * 1000, 2)},
        }

    async def generate(self, state):
        start = time.perf_counter()
        if state["mode"] == "knowledge" and not state["sources"]:
            generated = ModelAnswer(
                answer="I couldn't find enough evidence in your notes. Add a relevant note or try general mode.",
                source_ids=[],
                abstained=True,
            )
        else:
            generated = await self.provider.generate(
                state["question"],
                state["history"],
                [
                    {"id": source.id, "text": source.excerpt, "name": source.name}
                    for source in state["sources"]
                ],
                state["mode"],
            )
        return {
            "generated": generated,
            "timings": {
                **state["timings"],
                "answer_ms": round((time.perf_counter() - start) * 1000, 2),
            },
        }

    def validate(self, state):
        generated = state["generated"]
        valid = {source.id: source for source in state["sources"]}
        ids = list(dict.fromkeys(generated.source_ids))
        if (
            state["mode"] == "knowledge"
            and not generated.abstained
            and (not ids or any(identifier not in valid for identifier in ids))
        ):
            answer = Answer(
                text="I couldn't verify the sources for that answer. Please rephrase your question.",
                sources=[],
                abstained=True,
            )
        elif generated.abstained:
            text = generated.answer.strip()
            if state["mode"] == "knowledge":
                text = (
                    "آپ کے نوٹس میں اس سوال کا جواب دینے کے لیے کافی معلومات نہیں ملیں۔"
                    if any("\u0600" <= ch <= "\u06ff" for ch in state["question"])
                    else "I couldn't find enough evidence in your notes to answer that question."
                )
            answer = Answer(text=text, sources=[], abstained=True)
        else:
            answer = Answer(
                text=generated.answer.strip(),
                sources=[valid[x] for x in ids] if state["mode"] == "knowledge" else [],
                abstained=False,
            )
        if not answer.text:
            answer = Answer(
                text="I couldn't produce a usable answer. Please rephrase.",
                sources=[],
                abstained=True,
            )
        return {"answer": answer}

    async def run(self, owner, question, history, mode):
        return await self.graph.ainvoke(
            {"owner": owner, "question": question, "history": history, "mode": mode}
        )
