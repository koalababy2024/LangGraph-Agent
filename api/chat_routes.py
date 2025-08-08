"""Chat API routes using LangGraph chat graph."""

import json
import logging
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from graphs.chat_graph import graph as chat_graph

# 设置日志
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/")
async def chat_endpoint(
    message: str = Query(..., description="User input message"),
    thread_id: str = Query("default", description="Thread ID for conversation memory")
):
    """
    Blocking chat endpoint.
    
    Query parameter:
    - message: user input text
    
    Returns:
    - JSON response with AI chat response
    """
    try:
        # Create initial state with user message
        initial_state = {
            "messages": [HumanMessage(content=message)]
        }
        
        # Create config with thread_id for conversation memory
        config = {"configurable": {"thread_id": thread_id}}
        
        # Invoke the chat graph and get final result
        result = await chat_graph.ainvoke(initial_state, config)
        
        # Extract the assistant's response
        assistant_message = result["messages"][-1]
        
        return {
            "success": True,
            "response": assistant_message.content,
            "message_count": len(result["messages"])
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "response": "抱歉，处理您的请求时出现了错误。"
        }


@router.get("/stream")
async def chat_stream_endpoint(
    message: str = Query(..., description="User input message"),
    thread_id: str = Query("default", description="Thread ID for conversation memory")
):
    """
    Streaming chat endpoint using official LangGraph streaming.
    
    Query parameter:
    - message: user input text
    
    Returns:
    - Server-Sent Events (SSE) stream of chat response tokens
    """
    
    async def generate_chat_stream():
        try:
            logger.info(f"开始流式聊天请求: {message[:50]}...")
            
            # Send start signal
            start_data = {
                'type': 'start', 
                'content': '', 
                'metadata': {'node': 'system', 'step': 0}
            }
            yield f"data: {json.dumps(start_data)}\n\n"
            
            # Create initial state with user message
            initial_state = {
                "messages": [HumanMessage(content=message)]
            }
            logger.info(f"创建初始状态，消息数量: {len(initial_state['messages'])}")
            
            # Use LangGraph's official streaming with stream_mode="messages"
            logger.info("使用 LangGraph 官方流式输出模式")
            
            accumulated_content = ""
            chunk_count = 0
            
            # Create config with thread_id for conversation memory
            config = {"configurable": {"thread_id": thread_id}}
            
            # Stream using LangGraph's official streaming API
            async for message_chunk, metadata in chat_graph.astream(
                initial_state,
                config,
                stream_mode="messages"
            ):
                # Check if the message chunk has content
                if hasattr(message_chunk, 'content') and message_chunk.content:
                    logger.info(f"获取了LLM消息: {message_chunk.content}")
                    chunk_count += 1
                    accumulated_content += message_chunk.content
                    
                    # Send the streaming token
                    chunk_data = {
                        'type': 'content',
                        'content': message_chunk.content,
                        'metadata': {
                            'node': metadata.get('langgraph_node', 'unknown'),
                            'chunk_number': chunk_count,
                            'accumulated_length': len(accumulated_content),
                            'langgraph_metadata': metadata
                        }
                    }
                    yield f"data: {json.dumps(chunk_data)}\n\n"
                    logger.info(f"发送流式 token {chunk_count}: '{message_chunk.content}' (节点: {metadata.get('langgraph_node', 'unknown')})")
            
            # Send completion signal
            end_data = {
                'type': 'end',
                'content': '',
                'metadata': {
                    'total_chunks': chunk_count,
                    'total_length': len(accumulated_content)
                }
            }
            yield f"data: {json.dumps(end_data)}\n\n"
            logger.info(f"流式输出完成，总共 {chunk_count} 个 token，总长度: {len(accumulated_content)} 字符")
            
        except Exception as e:
            # Send error signal
            error_msg = f"处理请求时出现错误: {str(e)}"
            error_data = {
                'type': 'error', 
                'content': error_msg, 
                'metadata': {'node': 'system', 'error': True}
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            logger.error(f"流式聊天出错: {str(e)}", exc_info=True)
    
    return StreamingResponse(
        generate_chat_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )


@router.get("/test")
async def test_chat_endpoint():
    """Test endpoint to verify chat functionality"""
    test_message = "你好，请介绍一下你自己。"
    
    try:
        # Create initial state with test message
        initial_state = {
            "messages": [HumanMessage(content=test_message)]
        }
        
        # Invoke the chat graph
        result = await chat_graph.ainvoke(initial_state)
        
        return {
            "success": True,
            "test_message": test_message,
            "response": result["messages"][-1].content,
            "total_messages": len(result["messages"])
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "test_message": test_message
        }
