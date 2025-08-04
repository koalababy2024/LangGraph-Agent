# 简单的 eager_start 修复
import asyncio
import warnings

# 禁用相关警告
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

# 简单修复 eager_start 问题
original_create_task = asyncio.create_task
def patched_create_task(coro, *, name=None, **kwargs):
    # 移除 eager_start 参数
    kwargs.pop('eager_start', None)
    kwargs.pop('context', None)
    try:
        return original_create_task(coro, name=name)
    except TypeError:
        # 如果还有问题，使用最基本的方法
        loop = asyncio.get_running_loop()
        return loop.create_task(coro)

asyncio.create_task = patched_create_task

import os
from typing import Annotated

from langchain_core.tools import tool
from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

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

tools = [add_numbers, multiply_numbers, calculate_square, get_current_time]
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

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