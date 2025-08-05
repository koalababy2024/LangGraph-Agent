# 简单的 eager_start 修复
import asyncio
import warnings

import os
from typing import Annotated

from langchain_core.tools import tool
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_tavily import TavilySearch
from langchain_community.tools import DuckDuckGoSearchRun

# Import shared LLM instance
from config import llm

class State(TypedDict):
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(State)

# Define local math calculation tools
@tool
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    result = a + b
    return f"The sum of {a} and {b} is {result}"

@tool
def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers together."""
    result = a * b
    return f"The product of {a} and {b} is {result}"

@tool
def calculate_square(number: float) -> float:
    """Calculate the square of a number."""
    result = number ** 2
    return f"The square of {number} is {result}"

@tool
def get_current_time() -> str:
    """Get the current time."""
    from datetime import datetime
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"Current time is: {current_time}"

# Initialize Tavily search tool
# tavily_search = TavilySearch(
#     api_key=os.environ["TAVILY_API_KEY"],
#     max_results=2
# )

# Create a Baidu search tool for better China network compatibility
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

tools = [add_numbers, multiply_numbers, calculate_square, get_current_time, baidu_search]
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    """LangGraph chatbot node with tool calling capability.
    
    LangGraph will automatically handle streaming when using stream_mode="messages".
    The framework will intercept and stream tokens from llm_with_tools.invoke() calls.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    response = llm_with_tools.invoke(state["messages"])
    logger.info(f"LLM with tools invoke Response: {response.content}")
    
    # Log tool calls if present
    if hasattr(response, 'tool_calls') and response.tool_calls:
        logger.info(f"Tool calls requested: {[tc.get('name', 'unknown') for tc in response.tool_calls]}")
    
    return {"messages": [response]}

graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)
# Any time a tool is called, we return to the chatbot to decide the next step
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")
graph = graph_builder.compile()