import logging
from typing import Optional, Dict, Any
import json
import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langgraph.types import Command
from langgraph.errors import GraphInterrupt

from graphs.customize_state_graph import graph


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customize-state", tags=["customize-state"])


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = "default"


class HumanReview(BaseModel):
    thread_id: str
    # 若提供 correct 且以 y/Y 开头，则视为确认无误；否则可提供 name/birthday 作为修正
    correct: Optional[str] = None
    name: Optional[str] = None
    birthday: Optional[str] = None


@router.post("/chat")
async def chat_customize_state(request: ChatRequest) -> Dict[str, Any]:
    """
    启动对话，请求 customize_state 图。若需要人工审阅，会触发 GraphInterrupt。
    返回：
    - 正常完成：{"response": str, "thread_id": str, "status": "completed"}
    - 需要人工审阅：{"intervention_required": True, "thread_id": str, "question": str, "name": str, "birthday": str, "status": "intervention_required"}
    """
    try:
        config = {"configurable": {"thread_id": request.thread_id}}
        initial_state = {"messages": [{"role": "user", "content": request.message}]}

        logger.info(f"[customize_state.chat] thread_id={request.thread_id} initial_state={initial_state}")

        try:
            result = await graph.ainvoke(initial_state, config)
            # 正常完成，返回最后一条消息内容
            if result and "messages" in result and result["messages"]:
                final_msg = result["messages"][-1]
                if hasattr(final_msg, "content") and final_msg.content:
                    content = final_msg.content
                elif hasattr(final_msg, "text"):
                    content = final_msg.text() if callable(final_msg.text) else final_msg.text
                else:
                    content = str(final_msg)

                return {"response": content, "thread_id": request.thread_id, "status": "completed"}
            else:
                return {"response": "抱歉，暂无可返回内容。", "thread_id": request.thread_id, "status": "completed"}

        except GraphInterrupt as e:
            # 捕获 human_assistance 工具触发的 interrupt()
            logger.info(f"[customize_state.chat] GraphInterrupt: {e}")
            data = e.interrupts[0] if e.interrupts else {}
            question = data.get("question", "需要人工审阅")
            name = data.get("name", "")
            birthday = data.get("birthday", "")
            return {
                "intervention_required": True,
                "thread_id": request.thread_id,
                "question": question,
                "name": name,
                "birthday": birthday,
                "status": "intervention_required",
            }

    except Exception as exc:
        logger.exception("/customize-state/chat 处理失败")
        raise HTTPException(status_code=500, detail=f"对话处理失败: {exc}")


@router.post("/respond")
async def respond_customize_state(request: HumanReview) -> Dict[str, Any]:
    """
    提交人工审阅结果，恢复图执行。
    - 若 correct 以 y/Y 开头，表示确认无误，仅传递 {"correct": correct}
    - 否则可传递修正后的 name/birthday
    返回：{"response": str, "thread_id": str, "status": "completed"}
    """
    try:
        config = {"configurable": {"thread_id": request.thread_id}}

        resume_payload: Dict[str, Any] = {}
        if request.correct:
            resume_payload["correct"] = request.correct
        if request.name is not None:
            resume_payload["name"] = request.name
        if request.birthday is not None:
            resume_payload["birthday"] = request.birthday

        # 保底：若用户既未提供 correct，也未提供 name/birthday，则仍提供空结构，避免 KeyError
        human_command = Command(resume=resume_payload or {"correct": "y"})
        logger.info(f"[customize_state.respond] thread_id={request.thread_id} resume={human_command}")

        final_msg = None
        async for event in graph.astream(human_command, config, stream_mode="values"):
            if isinstance(event, dict) and "messages" in event and event["messages"]:
                final_msg = event["messages"][-1]

        if final_msg is not None:
            if hasattr(final_msg, "content") and final_msg.content:
                content = final_msg.content
            elif hasattr(final_msg, "text"):
                content = final_msg.text() if callable(final_msg.text) else final_msg.text
            else:
                content = str(final_msg)

            return {"response": content, "thread_id": request.thread_id, "status": "completed"}

        return {"response": "人工审阅已处理。", "thread_id": request.thread_id, "status": "completed"}

    except Exception as exc:
        logger.exception("/customize-state/respond 处理失败")
        raise HTTPException(status_code=500, detail=f"人工审阅处理失败: {exc}")


# ========== SSE 流式端点 ==========

@router.get("/chat/stream")
async def stream_chat_customize_state(message: str, thread_id: str = "default"):
    """
    流式对话（SSE）。
    事件类型：start/content/ai_decision/tool_call/tool_result/intervention_required/end/error
    与 human_loop_routes.py 对齐，便于前端复用。
    """
    async def generate():
        logger.info(f"[customize_state.stream_chat] 开始请求: thread_id={thread_id}, message={message[:80]}...")
        try:
            # start 事件
            start_data = {
                'type': 'start',
                'content': '',
                'metadata': {'node': 'system', 'step': 0}
            }
            yield f"data: {json.dumps(start_data)}\n\n"

            # 初始化
            config = {"configurable": {"thread_id": thread_id}}
            initial_state = {"messages": [{"role": "user", "content": message}]}
            accumulated_content = ""
            chunk_count = 0
            current_node = None
            tool_decision_sent = False

            logger.info(f"[customize_state.stream_chat] 调用 graph.astream，initial_state={initial_state}")

            try:
                async for stream_mode, chunk in graph.astream(
                    initial_state,
                    config,
                    stream_mode=["messages", "updates"],
                ):
                    if stream_mode == "messages":
                        message_chunk, metadata = chunk
                        node_from_metadata = metadata.get('langgraph_node', 'unknown')
                        # 跳过 tools 节点的消息分片，避免重复/无用内容
                        if node_from_metadata == "tools":
                            logger.info(f"[customize_state.stream_chat] 跳过tools消息分片: {getattr(message_chunk, 'content', '')}")
                            continue
                        if hasattr(message_chunk, 'content') and message_chunk.content:
                            logger.info(f"[customize_state.stream_chat] 收到LLM内容分片: {message_chunk.content}")
                            chunk_count += 1
                            accumulated_content += message_chunk.content
                            chunk_data = {
                                'type': 'content',
                                'content': message_chunk.content,
                                'metadata': {
                                    'node': node_from_metadata,
                                    'chunk_number': chunk_count,
                                    'accumulated_length': len(accumulated_content),
                                    'langgraph_metadata': metadata,
                                }
                            }
                            yield f"data: {json.dumps(chunk_data)}\n\n"

                        # 无论是否有可见content，都检查是否包含工具调用计划
                        try:
                            tool_calls = getattr(message_chunk, 'tool_calls', None)
                        except Exception:
                            tool_calls = None

                        if node_from_metadata == "chatbot" and tool_calls:
                            # 记录并宣布AI的工具调用决策
                            logger.info(f"[customize_state.stream_chat] 🤖 检测到AI决定调用工具: {tool_calls}")
                            ai_decision_evt = {
                                'type': 'ai_decision',
                                'content': 'AI决定调用工具',
                                'metadata': {
                                    'node': node_from_metadata,
                                    'langgraph_metadata': metadata,
                                }
                            }
                            yield f"data: {json.dumps(ai_decision_evt)}\n\n"

                            # 逐个发送具体工具调用事件
                            for tc in tool_calls:
                                # 兼容dict与对象两种结构
                                tool_name = None
                                tool_args = {}
                                if isinstance(tc, dict):
                                    tool_name = tc.get('name') or tc.get('tool')
                                    tool_args = tc.get('args') or {}
                                else:
                                    tool_name = getattr(tc, 'name', None) or getattr(tc, 'tool', None)
                                    tool_args = getattr(tc, 'args', {}) or {}

                                logger.info(f"[customize_state.stream_chat] 🛠️ 工具调用计划 -> tool={tool_name}, args={tool_args}")
                                tool_call_evt = {
                                    'type': 'tool_call',
                                    'tool': tool_name,
                                    'args': tool_args,
                                    'metadata': {
                                        'node': node_from_metadata,
                                        'langgraph_metadata': metadata,
                                    }
                                }
                                yield f"data: {json.dumps(tool_call_evt)}\n\n"

                    elif stream_mode == "updates":
                        for node_name, node_output in chunk.items():
                            current_node = node_name
                            logger.info(f"[customize_state.stream_chat] 节点更新 - {node_name}: {str(node_output)}")

                            # 处理中断节点（人工审阅）
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

                                question = None
                                name = None
                                birthday = None
                                if isinstance(interrupt_payload, dict):
                                    question = interrupt_payload.get("question")
                                    name = interrupt_payload.get("name")
                                    birthday = interrupt_payload.get("birthday")
                                if not question:
                                    question = "需要人工审阅"

                                logger.info(f"[customize_state.stream_chat] 检测到中断，question={question} name={name} birthday={birthday}")
                                evt = {
                                    'type': 'intervention_required',
                                    'question': question,
                                    'name': name,
                                    'birthday': birthday,
                                    'thread_id': thread_id,
                                    'metadata': {'node': node_name}
                                }
                                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"

                                end_data = {
                                    'type': 'end',
                                    'content': '',
                                    'metadata': {
                                        'total_chunks': chunk_count,
                                        'total_length': len(accumulated_content),
                                        'final_node': current_node,
                                    }
                                }
                                yield f"data: {json.dumps(end_data)}\n\n"
                                return

                            if node_name == "tools":
                                logger.info("[customize_state.stream_chat] 🔧 工具节点执行中...")
                                # 先发送工具运行中事件，提供更好的用户反馈
                                running_evt = {
                                    'type': 'tool_running',
                                    'content': '🔧 正在执行工具...',
                                    'metadata': {'node': node_name}
                                }
                                yield f"data: {json.dumps(running_evt)}\n\n"
                                if "messages" in node_output and node_output["messages"]:
                                    tool_message = node_output["messages"][-1]
                                    if hasattr(tool_message, 'content'):
                                        logger.info(f"[customize_state.stream_chat] ✅ 工具执行完成")
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
                                        tool_decision_sent = True
                                        decision_data = {
                                            'type': 'ai_decision',
                                            'content': '🤖 AI决定调用工具',
                                            'metadata': {'node': node_name}
                                        }
                                        logger.info(f"[customize_state.stream_chat] 📤 发送AI决策事件: {decision_data}")
                                        yield f"data: {json.dumps(decision_data)}\n\n"
                                        await asyncio.sleep(0.01)
                                        for tool_call in ai_message.tool_calls:
                                            tool_call_data = {
                                                'type': 'tool_call',
                                                'content': f"🔍 准备调用工具: {tool_call.get('name','unknown')}",
                                                'tool_name': tool_call.get('name','unknown'),
                                                'tool_args': tool_call.get('args', {}),
                                                'metadata': {'node': node_name}
                                            }
                                            logger.info(f"[customize_state.stream_chat] 📤 发送工具调用事件: {tool_call_data}")
                                            yield f"data: {json.dumps(tool_call_data)}\n\n"
                                            await asyncio.sleep(0.01)

                end_data = {
                    'type': 'end',
                    'content': '',
                    'metadata': {
                        'total_chunks': chunk_count,
                        'total_length': len(accumulated_content),
                        'final_node': current_node,
                    }
                }
                logger.info(f"[customize_state.stream_chat] 发送结束事件: {end_data}")
                yield f"data: {json.dumps(end_data)}\n\n"

            except GraphInterrupt as e:
                data = e.interrupts[0] if e.interrupts else {}
                question = data.get("question", "需要人工审阅")
                name = data.get("name")
                birthday = data.get("birthday")
                logger.info(f"[customize_state.stream_chat] 捕获GraphInterrupt: question={question}")
                yield f"data: {json.dumps({'type':'intervention_required','question':question,'name':name,'birthday':birthday,'thread_id':thread_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"[customize_state.stream_chat] 流式对话失败: {str(e)}", exc_info=True)
            yield f"data: {json.dumps({'type':'error','error':str(e)}, ensure_ascii=False)}\n\n"

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
async def stream_respond_customize_state(
    thread_id: str,
    response: Optional[str] = None,
    correct: Optional[str] = None,
    name: Optional[str] = None,
    birthday: Optional[str] = None,
):
    """
    人工回复后流式恢复（SSE）。事件结构与 /chat/stream 对齐。
    """
    async def generate():
        logger.info(f"[customize_state.respond_stream] 开始流式恢复: thread_id={thread_id}, response={(response[:80] if response else '')}...")
        try:
            # start 事件
            start_data = {'type': 'start', 'content': '', 'metadata': {'node': 'system', 'step': 0}}
            yield f"data: {json.dumps(start_data)}\n\n"

            config = {"configurable": {"thread_id": thread_id}}
            # 构造 resume 负载：优先 correct，其次 name/birthday；保留 response 作为备注（不参与 resume）
            resume_payload: Dict[str, Any] = {}
            # 使用参数别名，避免后续在闭包中对 name/birthday 的赋值造成遮蔽
            req_name = name
            req_birthday = birthday
            if correct:
                resume_payload["correct"] = correct
            if req_name is not None:
                resume_payload["name"] = req_name
            if req_birthday is not None:
                resume_payload["birthday"] = req_birthday
            human_command = Command(resume=resume_payload or {"correct": "y"})
            logger.info(
                f"[customize_state.respond_stream] thread_id={thread_id} resume={resume_payload or {'correct':'y'}}, note={response[:80] if response else ''}"
            )

            accumulated_content = ""
            chunk_count = 0
            current_node = None
            tool_decision_sent = False

            async for stream_mode, chunk in graph.astream(
                human_command, config, stream_mode=["messages", "updates"]
            ):
                if stream_mode == "messages":
                    message_chunk, metadata = chunk
                    node_from_metadata = metadata.get('langgraph_node', 'unknown')
                    if node_from_metadata == "tools":
                        logger.info(f"[customize_state.respond_stream] 跳过tools消息分片: {getattr(message_chunk, 'content', '')}")
                        continue
                    if hasattr(message_chunk, 'content') and message_chunk.content:
                        logger.info(f"[customize_state.respond_stream] 收到LLM内容分片: {message_chunk.content}")
                        chunk_count += 1
                        accumulated_content += message_chunk.content
                        yield f"data: {json.dumps({'type':'content','content':message_chunk.content,'metadata':{'node':node_from_metadata,'chunk_number':chunk_count,'accumulated_length':len(accumulated_content),'langgraph_metadata':metadata}})}\n\n"

                elif stream_mode == "updates":
                    for node_name, node_output in chunk.items():
                        current_node = node_name
                        logger.info(f"[customize_state.respond_stream] 节点更新 - {node_name}: {str(node_output)}")

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
                            question = interrupt_payload.get("question") if isinstance(interrupt_payload, dict) else None
                            intr_name = interrupt_payload.get("name") if isinstance(interrupt_payload, dict) else None
                            intr_birthday = interrupt_payload.get("birthday") if isinstance(interrupt_payload, dict) else None
                            if not question:
                                question = "需要人工协助"
                            yield f"data: {json.dumps({'type':'intervention_required','question':question,'name':intr_name,'birthday':intr_birthday,'thread_id':thread_id,'metadata':{'node':node_name}}, ensure_ascii=False)}\n\n"
                            end_data = {'type':'end','content':'','metadata':{'total_chunks':chunk_count,'total_length':len(accumulated_content),'final_node':current_node}}
                            yield f"data: {json.dumps(end_data)}\n\n"
                            return

                        if node_name == "tools":
                            # 先告知工具正在执行（通用文案，避免与具体联网搜索绑定）
                            running_evt = {'type':'tool_running','content':'🔧 正在执行工具...','metadata':{'node':node_name}}
                            yield f"data: {json.dumps(running_evt)}\n\n"
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
            logger.info(f"[customize_state.respond_stream] 流式恢复完成: {str(end_data)}")
            yield f"data: {json.dumps(end_data)}\n\n"

        except Exception as e:
            logger.error(f"[customize_state.respond_stream] 流式恢复失败: {str(e)}", exc_info=True)
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

