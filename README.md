# LangGraph-Agent
LangGraph Agent&amp;Workflow



chatbot 决策并返回含 tool_calls 的 AIMessage
代码位置：
graphs/tool_graph.py
chatbot 节点：llm_with_tools.invoke(...) → return {"messages": [response]}
add_conditional_edges("chatbot", tools_condition)
发生的事：
LLM 在 messages 流里产生 token（若有可见文本）。
chatbot 函数 return 时，LangGraph 用 add_messages 合并新 AIMessage，state 更新。
因为 state 变了，LangGraph 立刻发一条 updates： {"chatbot": {"messages": [AIMessage(content="", tool_calls=[...])]}}
tools_condition 看到 tool_calls 存在 → 路由到 "tools" 节点。
进入 ToolNode 并执行工具
代码位置：
graphs/tool_graph.py
tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)
发生的事：
ToolNode 读取 AIMessage.tool_calls，逐个匹配你在 tools 列表里注册的函数（如 baidu_search）。
ToolNode 调用对应函数，拿到结果。
ToolNode 将结果包装为 ToolMessage，作为节点输出返回。
注意：ToolNode 不调用 LLM，所以不会产生 stream_mode == "messages" 的 token 流。
ToolNode 完成 → 触发 updates
这一步就是你问的“tools 分支如何被触发”的关键：
ToolNode 函数返回时，LangGraph 再次用 add_messages 合并 ToolMessage 到 state（把工具结果追加到 messages）。
state 更新 → LangGraph 发送一条 updates： {"tools": {"messages": [ToolMessage(content=工具结果...)]}}
你的 SSE 循环中：
命中 elif stream_mode == "updates":
for node_name, node_output in chunk.items(): node_name == "tools" → 进入 tools 分支 logger.info("🔧 工具节点正在执行...") / “✅ 工具执行完成...”) 并 yield 'tool_result' 事件给前端
回到 chatbot 生成最终答案
代码位置：
graph_builder.add_edge("tools", "chatbot")
发生的事：
根据边定义，tools → chatbot
chatbot 再次调用 LLM 基于 ToolMessage 生成最终回复：
生成过程中有 stream_mode == "messages" 的 token 流（打字机）
节点完成后再发一条 updates： {"chatbot": {"messages": [AIMessage(content="最终答案", tool_calls=None)]}}
补充要点

为什么 updates 正好在这里来？
updates 的语义就是“某个节点执行完成时发送一次节点级状态快照”。ToolNode 执行完毕 → 自然就会来一条 {"tools": ...} 的 updates。
为什么 ToolNode 不产生 messages 流？
messages 只在 LLM 生成 token 时产生。ToolNode 调用的是 Python 工具函数，不是 LLM。
多个工具调用的情况
如果同一轮 AIMessage 里包含多个 tool_calls，ToolNode 会逐个执行并最终返回 ToolMessage 列表；通常你会在一次 {"tools": {...}} updates 里看到最后一个 ToolMessage（实现细节依 LangGraph 版本，但本质都是“节点完成后发 updates”）。
对应你代码中的触发点

api/tool_routes.py
async for stream_mode, chunk in tool_graph.astream(...):
stream_mode == "updates" 分支
for node_name, node_output in chunk.items():
node_name == "tools" → 这就是 ToolNode 完成后由 LangGraph 推送的 updates，被你捕获并处理成日志与 SSE 的 tool_result 事件。