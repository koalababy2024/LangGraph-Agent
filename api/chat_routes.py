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
async def chat_endpoint(message: str = Query(..., description="User input message")):
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
        
        # Invoke the chat graph and get final result
        result = await chat_graph.ainvoke(initial_state)
        
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
async def chat_stream_endpoint(message: str = Query(..., description="User input message")):
    """
    Streaming chat endpoint.
    
    Query parameter:
    - message: user input text
    
    Returns:
    - Server-Sent Events (SSE) stream of chat response tokens
    """
    
    async def generate_chat_stream():
        try:
            logger.info(f"开始流式聊天请求: {message[:50]}...")
            
            # Send start signal
            start_data = {'type': 'start', 'content': '', 'metadata': {'node': 'system', 'step': 0}}
            yield f"data: {json.dumps(start_data)}\n\n"
            logger.info(f"发送开始信号: {start_data}")
            
            # Create initial state with user message
            initial_state = {
                "messages": [HumanMessage(content=message)]
            }
            logger.info(f"创建初始状态，消息数量: {len(initial_state['messages'])}")
            
            # Stream the chat graph execution
            step_count = 0
            logger.info("开始流式执行聊天图")
            
            async for event in chat_graph.astream(initial_state):
                step_count += 1
                logger.info(f"步骤 {step_count}: 接收到事件 {list(event.keys())}")
                
                # Process each node's output
                for node_name, node_output in event.items():
                    logger.info(f"处理节点 '{node_name}' 的输出")
                    
                    if "messages" in node_output:
                        # Get the latest message
                        latest_message = node_output["messages"][-1]
                        logger.info(f"获取到最新消息，类型: {latest_message.type}, 长度: {len(latest_message.content) if hasattr(latest_message, 'content') else 0}")
                        
                        if hasattr(latest_message, 'content') and latest_message.content:
                            # For assistant messages, stream the content token by token
                            if latest_message.type == "ai":
                                content = latest_message.content
                                logger.info(f"开始流式发送AI回复，总长度: {len(content)} 字符")
                                
                                # Stream content in chunks for typewriter effect
                                chunk_size = 3
                                total_chunks = (len(content) + chunk_size - 1) // chunk_size
                                
                                for i in range(0, len(content), chunk_size):
                                    chunk = content[i:i+chunk_size]
                                    chunk_data = {'type': 'content', 'content': chunk, 'metadata': {'node': node_name, 'step': step_count}}
                                    yield f"data: {json.dumps(chunk_data)}\n\n"
                                    
                                    # 记录每个chunk的详细信息
                                    chunk_index = i // chunk_size + 1
                                    logger.info(f"发送内容块 {chunk_index}/{total_chunks}: '{chunk}' (长度: {len(chunk)})")
                                    
                                    # Small delay for typewriter effect
                                    import asyncio
                                    await asyncio.sleep(0.05)
                                
                                logger.info(f"AI回复流式发送完成")
                            else:
                                # For other message types, send as metadata
                                yield f"data: {json.dumps({'type': 'metadata', 'content': latest_message.content, 'metadata': {'node': node_name, 'step': step_count, 'message_type': latest_message.type}})}\n\n"
            
            # Send completion signal
            end_data = {'type': 'end', 'content': '', 'metadata': {'node': 'system', 'step': step_count + 1}}
            yield f"data: {json.dumps(end_data)}\n\n"
            logger.info(f"流式聊天完成，总步骤数: {step_count + 1}")
            
        except Exception as e:
            # Send error signal
            error_msg = f"处理请求时出现错误: {str(e)}"
            error_data = {'type': 'error', 'content': error_msg, 'metadata': {'node': 'system', 'error': True}}
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
