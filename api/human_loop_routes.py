import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import uuid

from langgraph.types import Command
from langgraph.errors import GraphInterrupt

from graphs.human_loop_graph import graph

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/human-loop", tags=["human-loop"])

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "default"

class HumanResponse(BaseModel):
    thread_id: str
    response: str


    query: Optional[str] = None

@router.post("/chat")
async def chat_with_human_loop(request: ChatRequest):
    """
    启动对话，支持人工干预
    """
    try:
        config = {"configurable": {"thread_id": request.thread_id}}
        initial_state = {"messages": [{"role": "user", "content": request.message}]}
        
        logger.info(f"开始处理对话，thread_id: {request.thread_id}")
        
        try:
            # 使用invoke进行阻塞调用，与chat_routes.py保持一致
            logger.info(f"开始执行图，初始状态: {initial_state}")
            
            result = await graph.ainvoke(initial_state, config)
            
            # 检查最终消息
            if result and "messages" in result and result["messages"]:
                final_message = result["messages"][-1]
                logger.info(f"最终消息: {final_message}")
                # 检查是否有工具调用（可能需要人工干预）
                if hasattr(final_message, 'tool_calls') and final_message.tool_calls:
                    # 检查是否调用了human_assistance工具
                    for tool_call in final_message.tool_calls:
                        if tool_call.get('name') == 'human_assistance':
                            query = tool_call.get('args', {}).get('query', '需要人工协助')
                            logger.info(f"检测到human_assistance工具调用，查询: {query}")
                            
                            return {
                                "intervention_required": True,
                                "thread_id": request.thread_id,
                                "query": query,
                                "status": "intervention_required"
                            }
                
                # 正常的AI回复
                if hasattr(final_message, 'content') and final_message.content:
                    response_text = final_message.content
                elif hasattr(final_message, 'text'):
                    response_text = final_message.text() if callable(final_message.text) else final_message.text
                else:
                    response_text = str(final_message)
                    
                logger.info(f"返回响应: {response_text}")
                return {
                    "response": response_text,
                    "thread_id": request.thread_id,
                    "status": "completed"
                }
            else:
                logger.warning("未收到任何消息")
                return {
                    "response": "抱歉，AI暂时无法回复，请稍后再试。",
                    "thread_id": request.thread_id,
                    "status": "completed"
                }
            
        except GraphInterrupt as e:
            # 捕获人工干预中断
            logger.info(f"捕获到人工干预请求: {e}")
            
            # 获取中断信息
            interrupt_data = e.interrupts[0] if e.interrupts else {}
            query = interrupt_data.get("query", "需要人工协助")
            
            return {
                "intervention_required": True,
                "thread_id": request.thread_id,
                "query": query,
                "status": "intervention_required"
            }
            
    except Exception as e:
        logger.error(f"对话处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"对话处理失败: {str(e)}")

@router.post("/respond")
async def provide_human_response(request: HumanResponse):
    """
    提供人工回复，恢复图执行
    """
    try:
        config = {"configurable": {"thread_id": request.thread_id}}
        
        # 创建恢复命令
        human_command = Command(resume={"data": request.response})
        
        logger.info(f"恢复图执行，thread_id: {request.thread_id}")
        
        # 恢复执行并获取结果
        final_message = None
        logger.info(f"恢复执行图，使用命令: {human_command}")
        
        async for event in graph.astream(human_command, config, stream_mode="values"):
            logger.info(f"恢复执行收到事件: {event}")
            if "messages" in event and event["messages"]:
                final_message = event["messages"][-1]
                logger.info(f"恢复执行最新消息: {final_message}")
        

        
        # 检查最终消息
        if final_message:
            if hasattr(final_message, 'content') and final_message.content:
                response_text = final_message.content
            elif hasattr(final_message, 'text'):
                response_text = final_message.text() if callable(final_message.text) else final_message.text
            else:
                response_text = str(final_message)
                
            logger.info(f"人工回复处理完成，返回: {response_text}")
            return {
                "response": response_text,
                "thread_id": request.thread_id,
                "status": "completed"
            }
        else:
            logger.warning("人工回复处理后未收到消息")
            return {
                "response": "人工协助处理完成",
                "thread_id": request.thread_id,
                "status": "completed"
            }
        
    except Exception as e:
        logger.error(f"人工回复处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"人工回复处理失败: {str(e)}")





@router.get("/chat/stream")
async def stream_chat_with_human_loop(message: str, thread_id: str = "default"):
    """
    流式对话，支持人工干预
    """
    async def generate():
        logger.info(f"开始工具流式请求: {message[:50]}...")
        try:
            # start 事件对齐 tool_routes.py
            start_data = {
                'type': 'start',
                'content': '',
                'metadata': {'node': 'system', 'step': 0}
            }
            yield f"data: {json.dumps(start_data)}\n\n"

            # initial_state 与 config
            config = {"configurable": {"thread_id": thread_id}}
            initial_state = {"messages": [{"role": "user", "content": message}]}

            # 累积变量对齐 tool_routes.py
            accumulated_content = ""
            chunk_count = 0
            current_node = None
            tool_decision_sent = False

            logger.info(f"[stream_chat] 调用 graph.astream，initial_state={initial_state}")
            try:
                # 同时获取 messages 与 updates
                async for stream_mode, chunk in graph.astream(
                    initial_state,
                    config,
                    stream_mode=["messages", "updates"]
                ):
                    if stream_mode == "messages":
                        # Handle LLM token streaming（对齐 tool_routes.py）
                        message_chunk, metadata = chunk
                        node_from_metadata = metadata.get('langgraph_node', 'unknown')
                        # 如果来自 tools 节点的消息，则跳过
                        if node_from_metadata == "tools":
                            logger.info(f"获取了LLM消息 - 调用工具返回: {getattr(message_chunk, 'content', '')}")
                            continue
                        if hasattr(message_chunk, 'content') and message_chunk.content:
                            logger.info(f"获取了LLM消息: {message_chunk.content}")
                            chunk_count += 1
                            accumulated_content += message_chunk.content
                            # 发送 content 事件（结构对齐）
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
                        # 处理节点更新（对齐 tool_routes.py）
                        for node_name, node_output in chunk.items():
                            current_node = node_name
                            logger.info(f"节点更新 - {node_name}: {str(node_output)}")

                            # 人工干预：LangGraph 在 updates 流中以中断节点形式上报，不一定抛异常
                            if node_name in {"__interrupt__", "interrupt", "graph:interrupt"}:
                                # 解析中断负载，兼容 tuple/list/obj 三种形式
                                interrupt_payload = None
                                try:
                                    candidate = None
                                    if isinstance(node_output, (list, tuple)) and node_output:
                                        candidate = node_output[0]
                                    else:
                                        candidate = node_output
                                    if hasattr(candidate, "value"):
                                        interrupt_payload = candidate.value
                                    elif isinstance(candidate, dict) and "value" in candidate:
                                        interrupt_payload = candidate.get("value")
                                except Exception:
                                    interrupt_payload = None

                                query = None
                                if isinstance(interrupt_payload, dict):
                                    query = interrupt_payload.get("query")
                                if not query:
                                    query = "需要人工协助"

                                logger.info(f"[stream_chat] 检测到中断节点，触发人工干预，query={query}")
                                intervention_event = {
                                    'type': 'intervention_required',
                                    'query': query,
                                    'thread_id': thread_id,
                                    'metadata': {'node': node_name}
                                }
                                yield f"data: {json.dumps(intervention_event, ensure_ascii=False)}\n\n"

                                # 发送结束事件并退出流
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
                                return

                            if node_name == "tools":
                                logger.info("🔧 工具节点正在执行...")
                                if "messages" in node_output and node_output["messages"]:
                                    tool_message = node_output["messages"][-1]
                                    if hasattr(tool_message, 'content'):
                                        logger.info(f"✅ 工具执行完成: {tool_message.content}")
                                        tool_data = {
                                            'type': 'tool_result',
                                            'content': '🔧 工具执行完成',
                                            'result': tool_message.content,
                                            'metadata': {'node': node_name}
                                        }
                                        yield f"data: {json.dumps(tool_data)}\n\n"

                            elif node_name == "chatbot":
                                if "messages" in node_output and node_output["messages"]:
                                    ai_message = node_output["messages"][-1]
                                    if hasattr(ai_message, 'tool_calls') and ai_message.tool_calls and not tool_decision_sent:
                                        logger.info(f"🔍 AI决定调用工具: {[tc.get('name', 'unknown') for tc in ai_message.tool_calls]}")
                                        tool_decision_sent = True
                                        decision_data = {
                                            'type': 'ai_decision',
                                            'content': '🤖 AI决定调用工具',
                                            'metadata': {'node': node_name}
                                        }
                                        logger.info(f"📤 发送AI决策事件: {decision_data}")
                                        yield f"data: {json.dumps(decision_data)}\n\n"
                                        import asyncio
                                        await asyncio.sleep(0.01)

                                        for tool_call in ai_message.tool_calls:
                                            tool_call_data = {
                                                'type': 'tool_call',
                                                'content': f"🔍 准备调用工具: {tool_call.get('name', 'unknown')}",
                                                'tool_name': tool_call.get('name', 'unknown'),
                                                'tool_args': tool_call.get('args', {}),
                                                'metadata': {'node': node_name}
                                            }
                                            logger.info(f"📤 发送工具调用事件: {tool_call_data}")
                                            yield f"data: {json.dumps(tool_call_data)}\n\n"
                                            await asyncio.sleep(0.01)

                # end 事件对齐 tool_routes.py
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
            except GraphInterrupt as e:
                # HITL: 捕获人工干预中断并通知前端
                interrupt_data = e.interrupts[0] if e.interrupts else {}
                query = interrupt_data.get("query", "需要人工协助")
                logger.info(f"[stream_chat] 触发人工干预，query={query}")
                yield f"data: {json.dumps({'type': 'intervention_required', 'query': query, 'thread_id': thread_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"[stream_chat] 流式对话失败: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
            logger.debug("[stream_chat] 已发送 error 事件")
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        },
    )


@router.get("/respond/stream")
async def stream_respond_with_human_input(response: str, thread_id: str):
    """
    人工回复后，流式恢复图执行并返回最终AI回复（SSE）。
    - 与 /human-loop/chat/stream 的事件结构保持一致：start/content/ai_decision/tool_call/tool_result/intervention_required/end
    - 避免工具节点消息被拆分为多段：跳过 messages 流中的 tools 节点分片
    """
    async def generate():
        logger.info(f"[respond_stream] 开始人工回复流式恢复: thread_id={thread_id}, response={response[:50]}...")
        try:
            # start 事件
            start_data = {'type': 'start', 'content': '', 'metadata': {'node': 'system', 'step': 0}}
            yield f"data: {json.dumps(start_data)}\n\n"

            config = {"configurable": {"thread_id": thread_id}}
            human_command = Command(resume={"data": response})

            accumulated_content = ""
            chunk_count = 0
            current_node = None
            tool_decision_sent = False

            # 恢复并以多模式流式返回
            async for stream_mode, chunk in graph.astream(
                human_command, config, stream_mode=["messages", "updates"]
            ):
                if stream_mode == "messages":
                    message_chunk, metadata = chunk
                    node_from_metadata = metadata.get('langgraph_node', 'unknown')
                    if node_from_metadata == "tools":
                        logger.info(f"[respond_stream] 跳过tools消息分片: {getattr(message_chunk, 'content', '')}")
                        continue
                    if hasattr(message_chunk, 'content') and message_chunk.content:
                        logger.info(f"[respond_stream] 收到LLM内容分片: {message_chunk.content}")
                        chunk_count += 1
                        accumulated_content += message_chunk.content
                        yield f"data: {json.dumps({'type':'content','content':message_chunk.content,'metadata':{'node':node_from_metadata,'chunk_number':chunk_count,'accumulated_length':len(accumulated_content),'langgraph_metadata':metadata}})}\n\n"

                elif stream_mode == "updates":
                    for node_name, node_output in chunk.items():
                        current_node = node_name
                        logger.info(f"[respond_stream] 节点更新 - {node_name}: {str(node_output)}")

                        # 处理中断节点（可能出现再次人工干预）
                        if node_name in {"__interrupt__", "interrupt", "graph:interrupt"}:
                            interrupt_payload = None
                            try:
                                candidate = node_output[0] if isinstance(node_output, (list, tuple)) and node_output else node_output
                                if hasattr(candidate, "value"):
                                    interrupt_payload = candidate.value
                                elif isinstance(candidate, dict) and "value" in candidate:
                                    interrupt_payload = candidate.get("value")
                            except Exception:
                                interrupt_payload = None
                            query = interrupt_payload.get("query") if isinstance(interrupt_payload, dict) else None
                            if not query:
                                query = "需要人工协助"
                            yield f"data: {json.dumps({'type':'intervention_required','query':query,'thread_id':thread_id,'metadata':{'node':node_name}}, ensure_ascii=False)}\n\n"
                            end_data = {'type':'end','content':'','metadata':{'total_chunks':chunk_count,'total_length':len(accumulated_content),'final_node':current_node}}
                            yield f"data: {json.dumps(end_data)}\n\n"
                            return

                        if node_name == "tools":
                            if "messages" in node_output and node_output["messages"]:
                                tool_message = node_output["messages"][-1]
                                if hasattr(tool_message, 'content'):
                                    tool_data = {'type':'tool_result','content':'🔧 工具执行完成','result':tool_message.content,'metadata':{'node':node_name}}
                                    yield f"data: {json.dumps(tool_data)}\n\n"

                        elif node_name == "chatbot":
                            if "messages" in node_output and node_output["messages"]:
                                ai_message = node_output["messages"][-1]
                                if hasattr(ai_message, 'tool_calls') and ai_message.tool_calls and not tool_decision_sent:
                                    tool_decision_sent = True
                                    decision_data = {'type':'ai_decision','content':'🤖 AI决定调用工具','metadata':{'node':node_name}}
                                    yield f"data: {json.dumps(decision_data)}\n\n"
                                    import asyncio
                                    await asyncio.sleep(0.01)
                                    for tool_call in ai_message.tool_calls:
                                        tool_call_data = {
                                            'type': 'tool_call',
                                            'content': f"🔍 准备调用工具: {tool_call.get('name','unknown')}",
                                            'tool_name': tool_call.get('name','unknown'),
                                            'tool_args': tool_call.get('args', {}),
                                            'metadata': {'node': node_name}
                                        }
                                        yield f"data: {json.dumps(tool_call_data)}\n\n"
                                        await asyncio.sleep(0.01)

            end_data = {'type':'end','content':'','metadata':{'total_chunks':chunk_count,'total_length':len(accumulated_content),'final_node':current_node}}
            yield f"data: {json.dumps(end_data)}\n\n"

        except Exception as e:
            logger.error(f"[respond_stream] 流式恢复失败: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        },
    )
