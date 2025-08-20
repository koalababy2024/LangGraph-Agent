"""Tool API routes using LangGraph tool graph."""

import json
import logging
import asyncio
import contextlib
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from graphs.tool_graph import graph as tool_graph

# 设置日志
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/tool", tags=["tool"])


@router.get("/")
async def tool_endpoint(
    message: str = Query(..., description="User input message"),
    thread_id: str = Query("default", description="Thread ID for conversation memory")
):
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
        
        # Create config with thread_id for conversation memory
        config = {"configurable": {"thread_id": thread_id}}
        
        logger.info(f"Invoking tool graph for message: '{message}' with thread_id: {thread_id}")
        # Invoke the tool graph and get final result
        result = await tool_graph.ainvoke(initial_state, config)
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
async def tool_stream_endpoint(
    message: str = Query(..., description="User input message"),
    thread_id: str = Query("default", description="Thread ID for conversation memory")
):
    """
    Streaming tool endpoint using official LangGraph streaming with tool usage display.
    
    Query parameter:
    - message: user input text
    
    Returns:
    - Server-Sent Events (SSE) stream of response tokens and tool info
    """
    
    async def generate_tool_stream():
        try:
            logger.info(f"[tool_routes][start] 开始工具流式请求: {message[:50]}...")
            
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
            logger.info(f"[tool_routes][init] 创建初始状态，消息数量: {len(initial_state['messages'])}")
            
            # Use LangGraph's official streaming with multiple modes
            logger.info("[tool_routes][stream] 使用 LangGraph 官方多模式流式输出: stream_mode=['messages','updates']")
            
            accumulated_content = ""
            chunk_count = 0
            current_node = None
            tool_decision_sent = False  # 标记是否已发送AI决策事件
            
            # Create config with thread_id for conversation memory
            config = {"configurable": {"thread_id": thread_id}}
            
            # Stream using LangGraph's official streaming API with multiple modes
            async for stream_mode, chunk in tool_graph.astream(
                initial_state,
                config,
                stream_mode=["messages", "updates"]
            ):
                # stream_mode="messages" 和 stream_mode="updates" 发回来的 数据粒度完全不同，因此两种日志看起来会很不一样——这正是官方设计的结果。
                #
                # 1. messages —— LLM 字符级 / token 级流
                # 进入 任何 LLM 节点（如
                # chatbot
                # ）时，LangGraph 会把 LLM 产生的 token 按 最小颗粒度 依次推送。
                # 你的循环里收到的是
                # (message_chunk, metadata)
                # ，其中 message_chunk.content 往往只是一小段（几个 token）。
                # 这些 token 因为被你 逐个 yield 给前端，所以前端才能实时打字机式渲染。
                # 在 messages 模式下，你已经过滤掉来自 tools 节点的 chunk，因此现在只会看到真正的 LLM token 流。
                # 2. updates —— 节点级 / 步骤级状态快照
                # 每当图中任意节点执行完成，LangGraph 就会发一次 updates。
                # 数据结构是：
                # python
                # {
                #    "<node_name>": <node_output>
                # }
                # 这里的 <node_output> 往往已经是 完整的对象 ——
                #
                # chatbot
                #  节点：{"messages": [AIMessage(...)]}
                # tools 节点：{"messages": [ToolMessage(...)]}
                # 因为它本来就是“节点完成后，把结果整体打包给你”，所以看起来内容一次就很“完整”。
                # 换句话说：
                #
                # 模式	何时触发	典型内容	用途
                # messages	LLM 正在生成回复时	很短的 token 片段	打字机流
                # updates	图中某节点刚结束时	整个 AIMessage / ToolMessage 列表	进度 & 结果通知
                if stream_mode == "messages":
                    # Handle LLM token streaming
                    message_chunk, metadata = chunk
                    node_from_metadata = metadata.get('langgraph_node', 'unknown')
                    # 统一的 messages 分支日志前缀
                    prefix = f"[tool_routes][messages][node={node_from_metadata}]"
                    logger.info(
                        f"{prefix} chunk 到达: content='{getattr(message_chunk, 'content', '')}', has_tool_calls={hasattr(message_chunk, 'tool_calls')}")

                    # 如果来自 ToolNode（tools 节点）的消息，则跳过，避免将工具返回值显示为 AI 回复
                    if node_from_metadata == "tools":
                        # 这是工具节点的 token 流（通常代表 ToolMessage 相关输出片段，工具tool node执行后的返回值），跳过显示，仅记录日志。
                        logger.info(f"{prefix}[ToolMessageChunk][skip] 工具节点 chunk 已跳过，content='{getattr(message_chunk, 'content', '')}'")
                        continue
                    if hasattr(message_chunk, 'content') and message_chunk.content:
                        # 对于 chatbot 节点，这些 chunk 属于 AIMessage 的 token 级输出
                        logger.info(f"{prefix}[AIMessageChunk] token='{message_chunk.content}'")
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
                        
                elif stream_mode == "updates":
                    # Handle node state updates
                    for node_name, node_output in chunk.items():
                        current_node = node_name
                        prefix = f"[tool_routes][updates][node={node_name}]"
                        logger.info(f"{prefix} 节点状态更新到达")
                        
                        if node_name == "tools":
                            # Tool node execution
                            logger.info(f"{prefix}[ToolNode] 🔧 工具节点正在执行...")
                            if "messages" in node_output and node_output["messages"]:
                                # ToolMessage（完整对象）
                                tool_message = node_output["messages"][-1]
                                if isinstance(tool_message, ToolMessage):
                                    logger.info(f"{prefix}[ToolMessage] ✅ 工具执行完成，content_len={len(tool_message.content) if hasattr(tool_message, 'content') else 0}")
                                else:
                                    logger.info(f"{prefix}[ToolMessage?] ✅ 工具执行完成，类型={type(tool_message)}")
                                if hasattr(tool_message, 'content'):
                                    tool_data = {
                                        'type': 'tool_result',
                                        'content': f"🔧 工具执行完成",
                                        'result': tool_message.content,
                                        'metadata': {'node': node_name}
                                    }
                                    yield f"data: {json.dumps(tool_data)}\n\n"
                        
                        elif node_name == "chatbot":
                            # Chatbot node - check for tool calls
                            if "messages" in node_output and node_output["messages"]:
                                # AIMessage（完整对象）
                                ai_message = node_output["messages"][-1]

                                # 详细记录 AIMessage 信息
                                if isinstance(ai_message, AIMessage):
                                    logger.info(f"{prefix}[AIMessage] 🤖 Chatbot节点返回AIMessage，content_len={len(ai_message.content) if hasattr(ai_message, 'content') else 0}")
                                else:
                                    logger.info(f"{prefix}[AIMessage?] 🤖 Chatbot节点返回消息，但类型={type(ai_message)}")
                                logger.info(f"{prefix}[AIMessage] has_tool_calls={hasattr(ai_message, 'tool_calls') and bool(ai_message.tool_calls)}")
                                if hasattr(ai_message, 'tool_calls') and ai_message.tool_calls:
                                    logger.info(f"{prefix}[AIMessage] tool_calls={[tc.get('name', 'unknown') for tc in ai_message.tool_calls]}")
                                    for i, tc in enumerate(ai_message.tool_calls):
                                        logger.info(f"{prefix}[AIMessage]   [{i}] name={tc.get('name', 'unknown')} args={tc.get('args', {})}")
                                
                                # Check if the message has tool calls and not already sent
                                if hasattr(ai_message, 'tool_calls') and ai_message.tool_calls and not tool_decision_sent:
                                    logger.info(f"{prefix}[AIMessage] 🔍 AI决定调用工具: {[tc.get('name', 'unknown') for tc in ai_message.tool_calls]}")
                                    
                                    # 标记已发送，避免重复
                                    tool_decision_sent = True
                                    
                                    # 发送AI决定调用工具的事件
                                    decision_data = {
                                        'type': 'ai_decision',
                                        'content': '🤖 AI决定调用工具',
                                        'metadata': {'node': node_name}
                                    }
                                    logger.info(f"{prefix}[AIMessage] 📤 发送AI决策事件: {decision_data}")
                                    yield f"data: {json.dumps(decision_data)}\n\n"
                                    
                                    # 稍微延迟以确保事件顺序
                                    import asyncio
                                    await asyncio.sleep(0.01)
                                    
                                    # 发送每个工具调用的详细信息
                                    for tool_call in ai_message.tool_calls:
                                        tool_call_data = {
                                            'type': 'tool_call',
                                            'content': f"🔍 准备调用工具: {tool_call.get('name', 'unknown')}",
                                            'tool_name': tool_call.get('name', 'unknown'),
                                            'tool_args': tool_call.get('args', {}),
                                            'metadata': {'node': node_name}
                                        }
                                        logger.info(f"{prefix}[AIMessage] 📤 发送工具调用事件: {tool_call_data}")
                                        yield f"data: {json.dumps(tool_call_data)}\n\n"
                                        await asyncio.sleep(0.01)  # 小延迟确保事件顺序

            
            # Send completion signal
            end_data = {
                'type': 'end',
                'content': '',
                'metadata': {
                    'total_chunks': chunk_count,
                    'total_length': len(accumulated_content),
                    'final_node': current_node
                }
            }
            yield f"data: {json.dumps(end_data)}\n\n"
            logger.info(f"[tool_routes][end] 工具流式输出完成，总共 {chunk_count} 个 token，总长度: {len(accumulated_content)} 字符")
            
        except Exception as e:
            # Send error signal
            error_msg = f"处理请求时出现错误: {str(e)}"
            error_data = {
                'type': 'error', 
                'content': error_msg, 
                'metadata': {'node': 'system', 'error': True}
            }
            yield f"data: {json.dumps(error_data)}\n\n"
            logger.error(f"[tool_routes][error] 工具流式输出出错: {str(e)}", exc_info=True)
    
    return StreamingResponse(
        generate_tool_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )
