from typing import Annotated
from typing_extensions import TypedDict

from langchain_core.tools import tool
from duckduckgo_search import DDGS

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt

from config import llm

import logging
logger = logging.getLogger(__name__)

class State(TypedDict):
    messages: Annotated[list, add_messages]


@tool
def human_assistance(query: str) -> str:
    """Request assistance from a human."""
    logger.info(f"[human_assistance] 请求人工协助: {query}")
    human_response = interrupt({"query": query})
    logger.info(f"[human_assistance] 收到人工回复: {human_response.get('data')}")
    return human_response["data"]


@tool
def baidu_search(query: str) -> str:
    """Search Baidu for current information and web results.
    Use this when you need to find recent news, current events, or general web information.
    This search tool works well in China network environment.

    Args:
        query: The search query string

    Returns:
        Search results as formatted text
    """
    try:
        from baidusearch.baidusearch import search

        # Use Baidu search with max 5 results
        results = search(query, num_results=5)

        if not results:
            return f"No search results found for: {query}"

        # Format results
        formatted_results = []
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            abstract = result.get('abstract', 'No description')
            url = result.get('url', 'No URL')

            formatted_results.append(
                f"{i}. **{title}**\n"
                f"   {abstract}\n"
                f"   URL: {url}\n"
            )

        return "\n".join(formatted_results)

    except Exception as e:
        return f"Baidu search failed due to: {str(e)}. Please try a different search query or try again later."

# 工具列表
tools = [baidu_search, human_assistance]
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    logger.debug(f"[chatbot] 当前状态: {state}")
    """聊天机器人节点"""
    message = llm_with_tools.invoke(state["messages"])
    logger.debug(f"[chatbot] LLM 返回消息: {message}")
    # 确保最多只有一个工具调用
    if hasattr(message, 'tool_calls') and len(message.tool_calls) > 1:
        logger.warning("[chatbot] 检测到多个工具调用，仅保留第一个")
        # 如果有多个工具调用，只保留第一个
        message.tool_calls = message.tool_calls[:1]
    return {"messages": [message]}

# 构建图
graph_builder = StateGraph(State)

# 添加节点
graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

# 添加边
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")

# 编译图（带内存）
memory = InMemorySaver()
graph = graph_builder.compile()
