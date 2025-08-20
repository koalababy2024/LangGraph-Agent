from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt

# Import LLM from existing module
from .chat_graph import llm

class State(TypedDict):
    messages: Annotated[list, add_messages]
    name: str
    birthday: str

@tool
def human_assistance(
    name: str, birthday: str, tool_call_id: Annotated[str, InjectedToolCallId]
) -> str:
    """Request assistance from a human."""
    human_response = interrupt(
        {
            "question": "Is this correct?",
            "name": name,
            "birthday": birthday,
        },
    )
    if human_response.get("correct", "").lower().startswith("y"):
        verified_name = name
        verified_birthday = birthday
        response = "Correct"
    else:
        verified_name = human_response.get("name", name)
        verified_birthday = human_response.get("birthday", birthday)
        response = f"Made a correction: {human_response}"

    state_update = {
        "name": verified_name,
        "birthday": verified_birthday,
        "messages": [ToolMessage(response, tool_call_id=tool_call_id)],
    }
    return Command(update=state_update)

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

tools = [baidu_search, human_assistance]
llm_with_tools = llm.bind_tools(tools)

def chatbot(state: State):
    message = llm_with_tools.invoke(state["messages"])
    assert(len(message.tool_calls) <= 1)
    return {"messages": [message]}

graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")

memory = InMemorySaver()
graph = graph_builder.compile(checkpointer=memory)
