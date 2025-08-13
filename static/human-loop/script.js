class HumanLoopApp {
    constructor() {
        this.threadId = this.initThreadId();
        this.isProcessing = false;
        this.currentEventSource = null;
        this.currentAssistantMessage = null;
        this.isWaitingForHumanInput = false;
        this.currentInterventionQuery = null;
        this.aiResponseContainer = null; // 用于在工具执行后分段展示AI最终回复
        
        this.initializeElements();
        this.attachEventListeners();
        this.updateThreadDisplay();
        this.initMarkdown();
    }
    
    addAIDecisionInfo(messageElement, data) {
        const contentDiv = messageElement.querySelector('.content');
        if (!contentDiv) return;
        if (contentDiv.innerHTML.includes('正在思考...')) {
            contentDiv.innerHTML = '';
        }
        const decisionDiv = document.createElement('div');
        decisionDiv.className = 'ai-decision-info';
        decisionDiv.innerHTML = `
            <div class="decision-header">${data.content || '🤖 AI决定调用工具'}</div>
        `;
        contentDiv.appendChild(decisionDiv);
    }

    addToolCallInfo(messageElement, toolData) {
        const contentDiv = messageElement.querySelector('.content');
        if (!contentDiv) return;
        const toolCallDiv = document.createElement('div');
        toolCallDiv.className = 'tool-call-info';
        const toolName = toolData.tool_name || toolData.name || 'unknown';
        const args = JSON.stringify(toolData.tool_args || toolData.args || {}, null, 2);
        toolCallDiv.innerHTML = `
            <div class="tool-header">🔍 调用工具: <strong>${toolName}</strong></div>
            <pre><code>${args}</code></pre>
        `;
        contentDiv.appendChild(toolCallDiv);
    }

    addToolResultInfo(messageElement, toolData) {
        const contentDiv = messageElement.querySelector('.content');
        if (!contentDiv) return;
        const toolResultDiv = document.createElement('div');
        toolResultDiv.className = 'tool-result-info';
        toolResultDiv.innerHTML = `
            <div class="tool-result-header">✅ 工具执行完成</div>
            <div class="tool-result-content">${toolData.result || ''}</div>
        `;
        contentDiv.appendChild(toolResultDiv);
        // 工具结果后准备 AI 回复区域
        const aiResponseSection = document.createElement('div');
        aiResponseSection.className = 'ai-response-section';
        aiResponseSection.innerHTML = `
            <div class="ai-response-header">🤖 AI回复:</div>
            <div class="ai-response-content"></div>
        `;
        contentDiv.appendChild(aiResponseSection);
        this.aiResponseContainer = aiResponseSection.querySelector('.ai-response-content');
        this.currentContent = '';
    }

    initMarkdown() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                highlight: function(code, lang) {
                    if (typeof hljs !== 'undefined') {
                        const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                        return hljs.highlight(code, { language }).value;
                    }
                    return code;
                },
                breaks: true,
                gfm: true
            });
        }
    }
    
    initializeElements() {
        this.chatMessages = document.getElementById('chat-messages');
        this.userInput = document.getElementById('user-input');
        this.sendButton = document.getElementById('send-button');
        this.threadIdDisplay = document.getElementById('thread-id');
        this.resetButton = document.getElementById('reset-button');
        this.statusIndicator = document.getElementById('status-indicator');
        this.notification = document.getElementById('notification');
    }
    
    attachEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.userInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        this.resetButton.addEventListener('click', () => this.resetConversation());
    }
    
    initThreadId() {
        // 生成新的thread_id
        const timestamp = Date.now();
        const randomStr = Math.random().toString(36).substring(2, 8);
        return `human_loop_${timestamp}_${randomStr}`;
    }
    
    updateThreadDisplay() {
        if (this.threadIdDisplay) {
            const shortThreadId = this.threadId.slice(-8);
            this.threadIdDisplay.textContent = `...${shortThreadId}`;
        }
    }
    
    resetConversation() {
        this.threadId = this.initThreadId();
        this.updateThreadDisplay();
        
        // 清空聊天记录
        const messages = this.chatMessages.querySelectorAll('.message:not(.welcome-message)');
        messages.forEach(msg => msg.remove());
        
        // 重置人工介入状态
        this.resetInterventionState();
        
        this.updateStatus('ready', '就绪');
        this.showNotification('已开始新对话');
    }
    
    adjustTextareaHeight() {
        this.userInput.style.height = 'auto';
        this.userInput.style.height = Math.min(this.userInput.scrollHeight, 150) + 'px';
    }
    
    async sendMessage() {
        const message = this.userInput.value.trim();
        if (!message || this.isProcessing) return;
        
        // 如果正在等待人工输入，则处理人工回复
        if (this.isWaitingForHumanInput) {
            await this.submitHumanResponse(message);
            return;
        }
        
        this.isProcessing = true;
        this.updateStatus('thinking', '思考中...');
        this.sendButton.disabled = true;
        
        // 显示用户消息
        this.addMessage('user', message);
        this.userInput.value = '';
        this.adjustTextareaHeight();
        
        try {
            await this.streamChatResponse(message);
        } catch (error) {
            console.error('发送消息失败:', error);
            this.addMessage('assistant', '抱歉，发送消息时出现错误。请稍后再试。');
            this.updateStatus('error', '错误');
            this.isProcessing = false;
            this.sendButton.disabled = false;
        }
    }
    
    async streamChatResponse(message) {
        // 清理状态
        this.currentAssistantMessage = null;
        this.currentContent = '';
        this.aiResponseContainer = null;
        
        // 使用EventSource进行流式连接
        const encodedMessage = encodeURIComponent(message);
        const url = `/human-loop/chat/stream?message=${encodedMessage}&thread_id=${encodeURIComponent(this.threadId)}`;
        
        this.currentEventSource = new EventSource(url);
        
        let contentDiv = null;
        
        const ensureAssistantMessage = () => {
            if (!this.currentAssistantMessage) {
                this.currentAssistantMessage = this.addMessage('assistant', '', true);
                contentDiv = this.currentAssistantMessage.querySelector('.content');
            }
        };
        
        this.currentEventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log('收到SSE事件:', data.type, data);
                
                switch (data.type) {
                    case 'start':
                        ensureAssistantMessage();
                        contentDiv.innerHTML = '<p>正在思考...</p>';
                        break;
                        
                    case 'content':
                        ensureAssistantMessage();
                        // 若之前展示了工具调用信息，则在单独的 AI 回复区域中渲染
                        let targetContainer = this.aiResponseContainer;
                        if (!targetContainer) {
                            const hasToolInfo = contentDiv.querySelector('.ai-decision-info, .tool-call-info, .tool-result-info');
                            if (hasToolInfo) {
                                const aiResponseSection = document.createElement('div');
                                aiResponseSection.className = 'ai-response-section';
                                aiResponseSection.innerHTML = `
                                    <div class="ai-response-header">🤖 AI回复:</div>
                                    <div class="ai-response-content"></div>
                                `;
                                contentDiv.appendChild(aiResponseSection);
                                targetContainer = aiResponseSection.querySelector('.ai-response-content');
                                this.aiResponseContainer = targetContainer;
                            } else {
                                targetContainer = contentDiv;
                            }
                        }
                        this.currentContent += data.content;
                        this.renderMarkdownContent(targetContainer, this.currentContent);
                        break;
                        
                    case 'ai_decision':
                        ensureAssistantMessage();
                        this.addAIDecisionInfo(this.currentAssistantMessage, data);
                        break;

                    case 'tool_call':
                        ensureAssistantMessage();
                        this.addToolCallInfo(this.currentAssistantMessage, data);
                        break;

                    case 'tool_result':
                        ensureAssistantMessage();
                        this.addToolResultInfo(this.currentAssistantMessage, data);
                        break;

                    case 'end':
                        this.currentEventSource.close();
                        this.updateStatus('ready', '就绪');
                        this.isProcessing = false;
                        this.sendButton.disabled = false;
                        break;
                        
                    case 'intervention_required':
                        this.currentEventSource.close();
                        this.showInterventionInChat(data.query);
                        this.updateStatus('intervention', '等待人工协助...');
                        this.isProcessing = false;
                        this.sendButton.disabled = false;
                        break;
                        
                    case 'error':
                        this.currentEventSource.close();
                        ensureAssistantMessage();
                        contentDiv.innerHTML = `<p class="error-message">错误: ${data.error}</p>`;
                        this.updateStatus('error', '错误');
                        this.isProcessing = false;
                        this.sendButton.disabled = false;
                        break;
                }
                
                this.scrollToBottom();
            } catch (e) {
                console.error('解析SSE数据失败:', e, event.data);
            }
        };
        
        this.currentEventSource.onerror = (error) => {
            console.error('SSE Error:', error);
            if (this.currentEventSource) {
                this.currentEventSource.close();
            }
            this.updateStatus('error', '连接错误');
            this.isProcessing = false;
            this.sendButton.disabled = false;
            
            if (!this.currentAssistantMessage || this.currentContent === '') {
                this.addMessage('assistant', '连接失败，请稍后再试。');
            }
        };
    }
    
    renderMarkdownContent(container, content) {
        if (typeof marked !== 'undefined') {
            container.innerHTML = marked.parse(content);
        } else {
            container.innerHTML = content.replace(/\n/g, '<br>');
        }
    }
    
    handleStreamEvent(data) {
        switch (data.type) {
            case 'start':
                this.currentAssistantMessage = this.addMessage('assistant', '', true);
                break;
                
            case 'content':
                if (this.currentAssistantMessage) {
                    const contentDiv = this.currentAssistantMessage.querySelector('.content');
                    contentDiv.innerHTML = marked.parse(data.content);
                }
                break;
                
            case 'end':
                this.updateStatus('ready', '就绪');
                this.isProcessing = false;
                this.sendButton.disabled = false;
                break;
                
            case 'intervention_required':
                this.showInterventionInChat(data.query);
                this.updateStatus('intervention', '等待人工协助...');
                this.isProcessing = false;
                this.sendButton.disabled = false;
                break;
                
            case 'error':
                this.addMessage('assistant', `错误: ${data.error}`);
                this.updateStatus('error', '错误');
                this.isProcessing = false;
                this.sendButton.disabled = false;
                break;
        }
    }
    
    addMessage(role, content, isEmpty = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const avatar = role === 'user' ? '👤' : '🤖';
        const contentHtml = isEmpty ? '' : (typeof marked !== 'undefined' ? marked.parse(content) : content);
        
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="avatar">${avatar}</div>
                <div class="content">${contentHtml}</div>
            </div>
        `;
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        return messageDiv;
    }
    
    showInterventionInChat(query) {
        this.currentInterventionQuery = query;
        this.isWaitingForHumanInput = true;
        
        // 清除之前的"正在思考..."消息
        if (this.currentAssistantMessage) {
            this.currentAssistantMessage.remove();
            this.currentAssistantMessage = null;
        }
        
        // 在聊天列表中显示人工介入提示
        const interventionMessage = this.addInterventionMessage(query);
        
        // 修改输入框提示
        this.userInput.placeholder = '请输入您的专业建议或回复...';
        this.userInput.focus();
        
        // 修改发送按钮文本
        const sendText = this.sendButton.querySelector('.send-text');
        if (sendText) {
            sendText.textContent = '提交回复';
        }
    }
    
    addInterventionMessage(query) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant intervention-message';
        
        const content = `🤝 **需要人工专家协助**\n\n**问题：** ${query}\n\n💡 请在下方输入框中提供您的专业建议或回复，然后点击"提交回复"按钮。`;
        
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="avatar">🤖</div>
                <div class="content">${typeof marked !== 'undefined' ? marked.parse(content) : content}</div>
            </div>
        `;
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        return messageDiv;
    }
    
    async submitHumanResponse(response) {
        if (!response) {
            this.showNotification('请输入回复内容', 'error');
            return;
        }

        // 显示专家回复消息
        this.addMessage('user', `💼 **专家回复：** ${response}`);

        // 清空输入框并调整高度
        this.userInput.value = '';
        this.adjustTextareaHeight();
        
        // 重置界面状态
        this.resetInterventionState();
        
        this.updateStatus('processing', '处理专家回复中...');
        this.isProcessing = true;
        this.sendButton.disabled = true;

        // 采用 SSE 流式恢复，实时展示最终回复
        try {
            const url = `/human-loop/respond/stream?thread_id=${encodeURIComponent(this.threadId)}&response=${encodeURIComponent(response)}`;
            const es = new EventSource(url);

            // 在界面上加入AI回复占位并流式渲染
            let assistantMsg = this.addMessage('assistant', '');
            const contentDiv = assistantMsg.querySelector('.content');
            let contentBuf = '';
            this.aiResponseContainer = null;
            this.renderMarkdownContent(contentDiv, contentBuf);

            es.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('respond/stream 事件:', data.type, data);

                    switch (data.type) {
                        case 'start':
                            // 已创建占位，不需要额外处理
                            break;
                        case 'content':
                            // 若之前展示了工具调用信息，则在单独的 AI 回复区域中渲染
                            let targetContainer = this.aiResponseContainer;
                            if (!targetContainer) {
                                const hasToolInfo = contentDiv.querySelector('.ai-decision-info, .tool-call-info, .tool-result-info');
                                if (hasToolInfo) {
                                    const aiResponseSection = document.createElement('div');
                                    aiResponseSection.className = 'ai-response-section';
                                    aiResponseSection.innerHTML = `
                                        <div class="ai-response-header">🤖 AI回复:</div>
                                        <div class="ai-response-content"></div>
                                    `;
                                    contentDiv.appendChild(aiResponseSection);
                                    targetContainer = aiResponseSection.querySelector('.ai-response-content');
                                    this.aiResponseContainer = targetContainer;
                                } else {
                                    targetContainer = contentDiv;
                                }
                            }
                            contentBuf += data.content;
                            this.renderMarkdownContent(targetContainer, contentBuf);
                            break;
                        case 'ai_decision':
                            this.addAIDecisionInfo(assistantMsg, data);
                            break;
                        case 'tool_call':
                            this.addToolCallInfo(assistantMsg, data);
                            break;
                        case 'tool_result':
                            this.addToolResultInfo(assistantMsg, data);
                            break;
                        case 'intervention_required':
                            es.close();
                            // 再次需要人工协助
                            this.showInterventionInChat(data.query || '需要人工协助');
                            this.updateStatus('intervention', '等待人工协助...');
                            break;
                        case 'end':
                            es.close();
                            this.updateStatus('ready', '就绪');
                            this.isProcessing = false;
                            this.sendButton.disabled = false;
                            this.showNotification('人工协助完成');
                            break;
                        case 'error':
                            es.close();
                            this.updateStatus('error', '错误');
                            alert('流式恢复失败：' + (data.error || '未知错误'));
                            break;
                    }
                    this.scrollToBottom();
                } catch (e) {
                    console.error('解析 respond/stream 事件失败:', e, event.data);
                }
            };

            es.onerror = (err) => {
                console.error('respond/stream SSE 错误:', err);
                es.close();
                this.updateStatus('error', '连接错误');
            };
        } catch (error) {
            console.error('提交人工回复失败:', error);
            this.showNotification('提交失败：' + error.message, 'error');
            this.updateStatus('error', '错误');
            this.isProcessing = false;
            this.sendButton.disabled = false;
        }
    }
    
    resetInterventionState() {
        this.isWaitingForHumanInput = false;
        this.currentInterventionQuery = null;
        
        // 重置输入框提示
        this.userInput.placeholder = '请输入您的问题...';
        
        // 重置发送按钮文本
        const sendText = this.sendButton.querySelector('.send-text');
        if (sendText) {
            sendText.textContent = '发送';
        }
    }
    
    updateStatus(status, text) {
        if (this.statusIndicator) {
            this.statusIndicator.className = `status ${status}`;
            this.statusIndicator.textContent = text;
        }
    }
    
    updateStatus(type, text) {
        this.statusIndicator.className = `status-indicator ${type}`;
        this.statusIndicator.querySelector('.status-text').textContent = text;
    }
    
    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }
    
    showNotification(message) {
        this.notification.textContent = message;
        this.notification.classList.add('show');
        
        setTimeout(() => {
            this.notification.classList.remove('show');
        }, 3000);
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new HumanLoopApp();
});
