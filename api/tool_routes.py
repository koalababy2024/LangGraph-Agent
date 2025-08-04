"""Tool API routes using LangGraph tool graph."""

import json
import logging
import asyncio
import contextlib
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from graphs.tool_graph import graph as tool_graph

# 设置日志
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/tool", tags=["tool"])


@router.get("/")
async def tool_endpoint(message: str = Query(..., description="User input message")):
    """
    Blocking tool endpoint.
    
    Query parameter:
    - message: user input text
    
    Returns:
    - JSON response with AI response and tool usage info
    """
    try:
        # Create initial state with user message
        initial_state = {
            "messages": [HumanMessage(content=message)]
        }
        
        logger.info(f"Invoking tool graph for message: '{message}'")
        # Invoke the tool graph and get final result
        result = await tool_graph.ainvoke(initial_state)
        logger.info(f"Graph invocation finished. Final state: {result}")
        
        # Extract the assistant's response
        assistant_message = result["messages"][-1]
        
        # Check if tools were used by looking at message history
        tool_calls_used = []
        for msg in result["messages"]:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_calls_used.append({
                        "name": tool_call.get("name", "unknown"),
                        "args": tool_call.get("args", {})
                    })
        
        return {
            "success": True,
            "response": assistant_message.content,
            "message_count": len(result["messages"]),
            "tools_used": tool_calls_used,
            "used_tools": len(tool_calls_used) > 0
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "response": "抱歉，处理您的请求时出现了错误。"
        }


@router.get("/stream")
async def tool_stream_endpoint(message: str = Query(..., description="User input message")):
    """
    Streaming tool endpoint with tool usage display.
    
    Query parameter:
    - message: user input text
    
    Returns:
    - Server-Sent Events (SSE) stream of response tokens and tool info
    """
    
    async def generate_tool_stream():
        try:
            # Create initial state with user message
            initial_state = {
                "messages": [HumanMessage(content=message)]
            }
            
            # Stream through the tool graph
            stream = tool_graph.astream(initial_state)
            logger.info(f"Starting graph stream for message: '{message}'")
            try:
                async for event in stream:
                    # Log each event from the graph stream
                    if isinstance(event, dict):
                        for node_name, node_output in event.items():
                            logger.info(f"--- Graph Event ---")
                            logger.info(f"Node: {node_name}")
                            # Truncate long outputs for cleaner logs
                            output_str = f"{node_output}"
                            if len(output_str) > 250:
                                output_str = output_str[:250] + "..."
                            logger.info(f"Output: {output_str}")
                            logger.info(f"--------------------")
                    # Handle different node outputs
                    for node_name, node_output in event.items():
                        if node_name == "tools":
                            logger.debug(f"Tool node output: {node_output}")
                            # Tool node - show tool execution status
                            yield f"data: {json.dumps({'type': 'tool_status', 'content': '🔧 正在执行工具调用...', 'node': node_name})}\n\n"
                            await asyncio.sleep(0.1)
                        
                        elif node_name == "chatbot":
                            logger.debug(f"Chatbot node output: {node_output}")
                            # AI response node
                            if "messages" in node_output and node_output["messages"]:
                                latest_message = node_output["messages"][-1]
                                content = latest_message.content if hasattr(latest_message, 'content') else ''
                                
                                # Check if the message has tool calls
                                has_tool_calls = hasattr(latest_message, 'tool_calls') and latest_message.tool_calls
                                
                                if has_tool_calls:
                                    # Send tool call info
                                    for tool_call in latest_message.tool_calls:
                                        tool_info = {
                                            'type': 'tool_call',
                                            'name': tool_call.get('name', 'unknown'),
                                            'args': tool_call.get('args', {})
                                        }
                                        yield f"data: {json.dumps(tool_info)}\n\n"
                                        await asyncio.sleep(0.1)
                                
                                # Always check for content, regardless of tool calls
                                if content and len(content.strip()) > 0:
                                    # Stream AI response content in chunks for natural streaming effect
                                    chunk_size = 20  # Characters per chunk
                                    for i in range(0, len(content), chunk_size):
                                        chunk = content[i:i + chunk_size]
                                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                                        await asyncio.sleep(0.1)  # Natural streaming delay
            
                # Send completion signal after stream finishes
                yield f"data: {json.dumps({'type': 'complete'})}\n\n"

            finally:
                # Ensure the async generator is properly closed even if the client disconnects
                with contextlib.suppress(Exception):
                    await stream.aclose()
            
        except Exception as e:
            logger.error(f"Error in tool stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': f'处理请求时出现错误: {str(e)}'})}\n\n"
    
    return StreamingResponse(
        generate_tool_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )


@router.get("/test")
async def test_tool_endpoint():
    """Test endpoint to verify tool functionality"""
    try:
        test_message = "什么是Python编程语言？"
        
        initial_state = {
            "messages": [HumanMessage(content=test_message)]
        }
        
        logger.info(f"Invoking tool graph for test message: '{test_message}'")
        result = await tool_graph.ainvoke(initial_state)
        logger.info(f"Graph invocation for test finished. Final state: {{result}}")
        
        return {
            "success": True,
            "test_message": test_message,
            "response_count": len(result["messages"]),
            "final_response": result["messages"][-1].content if result["messages"] else "No response"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }