"""Simple LangGraph chat graph using Azure GPT-4o-mini.

Environment variables (define in a `.env` file):
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_KEY
- AZURE_OPENAI_DEPLOYMENT (optional, default "gpt-4o-mini")
- AZURE_OPENAI_API_VERSION (optional, default "2024-02-15-preview")
"""

from __future__ import annotations

import os
from typing import Dict, Any

from dataclasses import dataclass
from typing import Annotated, TypedDict, Any, Dict

from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langchain_openai import AzureChatOpenAI


llm =AzureChatOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        openai_api_key=os.environ["AZURE_OPENAI_KEY"],
        openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
        deployment_name=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
    )


@dataclass
class State(TypedDict):
    messages: Annotated[list, add_messages]


def chatbot(state: "State"):
    """LangGraph node: call Azure LLM and append response message."""
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

# Create the chat graph directly as a module-level object
graph = (
    StateGraph(State)
    .add_node("chatbot", chatbot)
    .add_edge("__start__", "chatbot")
    .add_edge("chatbot", "__end__")
    .compile(name="Azure OpenAI Chatbot")
)

