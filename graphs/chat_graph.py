"""Simple LangGraph chat graph using Azure GPT-4o-mini.

Environment variables (define in a `.env` file):
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_KEY
- AZURE_OPENAI_DEPLOYMENT (optional, default "gpt-4o-mini")
- AZURE_OPENAI_API_VERSION (optional, default "2024-08-01-preview")
"""

from __future__ import annotations

import os
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_openai import AzureChatOpenAI


# Initialize Azure OpenAI LLM with streaming enabled
llm = AzureChatOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    openai_api_key=os.environ["AZURE_OPENAI_KEY"],
    openai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
    deployment_name=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
)


class State(TypedDict):
    """Graph state containing conversation messages."""
    messages: Annotated[list, add_messages]


def chatbot(state: State):
    """LangGraph node: call Azure LLM.
    
    LangGraph will automatically handle streaming when using stream_mode="messages".
    The framework will intercept and stream tokens from llm.invoke() calls.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    response = llm.invoke(state["messages"])
    logger.info(f"LLM invoke Response: {response.content}")
    
    return {"messages": [response]}


# Create the chat graph
# Note: LangGraph will handle streaming automatically when using stream_mode="messages"
graph = (
    StateGraph(State)
    .add_node("chatbot", chatbot)
    .add_edge(START, "chatbot")
    .add_edge("chatbot", END)
    .compile()
)



