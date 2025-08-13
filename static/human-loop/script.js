class HumanLoopApp {
    constructor() {
        this.threadId = this.initThreadId();
        this.isProcessing = false;
        this.currentEventSource = null;
        this.currentAssistantMessage = null;
        
        this.initializeElements();
        this.attachEventListeners();
        this.updateThreadDisplay();
        this.initMarkdown();
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
        
        // 干预面板元素
        this.interventionPanel = document.getElementById('intervention-panel');
        this.interventionQuery = document.getElementById('intervention-query');
        this.humanResponse = document.getElementById('human-response');
        this.submitResponse = document.getElementById('submit-response');
        this.cancelIntervention = document.getElementById('cancel-intervention');
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
        this.submitResponse.addEventListener('click', () => this.submitHumanResponse());
        this.cancelIntervention.addEventListener('click', () => this.cancelInterventionPanel());
        
        // 自动调整输入框高度
        this.userInput.addEventListener('input', () => this.adjustTextareaHeight());
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
        
        this.hideInterventionPanel();
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
                        this.currentContent += data.content;
                        this.renderMarkdownContent(contentDiv, this.currentContent);
                        break;
                        
                    case 'end':
                        this.currentEventSource.close();
                        this.updateStatus('ready', '就绪');
                        this.isProcessing = false;
                        this.sendButton.disabled = false;
                        break;
                        
                    case 'intervention_required':
                        this.currentEventSource.close();
                        this.showInterventionPanel(data.query);
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
                this.showInterventionPanel(data.query);
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
    
    showInterventionPanel(query) {
        this.interventionQuery.textContent = query;
        this.interventionPanel.style.display = 'flex';
        this.humanResponse.focus();
        
        // 显示干预提示消息
        this.addMessage('assistant', `🤝 我需要人工专家的协助来回答这个问题：\n\n"${query}"\n\n请等待专家提供专业建议...`);
    }
    
    hideInterventionPanel() {
        this.interventionPanel.style.display = 'none';
        this.humanResponse.value = '';
    }
    
    cancelInterventionPanel() {
        this.hideInterventionPanel();
        this.updateStatus('ready', '就绪');
        this.addMessage('assistant', '已取消人工协助请求。');
    }
    
    async submitHumanResponse() {
        const response = this.humanResponse.value.trim();
        if (!response) {
            alert('请输入回复内容');
            return;
        }

        this.updateStatus('processing', '处理人工回复中...');

        // 采用 SSE 流式恢复，实时展示最终回复
        try {
            const url = `/human-loop/respond/stream?thread_id=${encodeURIComponent(this.threadId)}&response=${encodeURIComponent(response)}`;
            const es = new EventSource(url);

            // 在界面上加入“专家回复”占位并流式渲染
            let assistantMsg = this.addMessage('assistant', '');
            const contentDiv = assistantMsg.querySelector('.content');
            let contentBuf = '💡 专家回复：\n\n';
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
                            contentBuf += data.content;
                            this.renderMarkdownContent(contentDiv, contentBuf);
                            break;
                        case 'ai_decision':
                        case 'tool_call':
                            // 可选：显示状态提示，不插入到正文
                            break;
                        case 'tool_result':
                            // 可选：可以在通知区域展示
                            break;
                        case 'intervention_required':
                            es.close();
                            // 再次需要人工协助
                            this.showInterventionPanel(data.query || '需要人工协助');
                            this.updateStatus('intervention', '等待人工协助...');
                            break;
                        case 'end':
                            es.close();
                            this.hideInterventionPanel();
                            this.updateStatus('ready', '就绪');
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
            alert('提交失败：' + error.message);
            this.updateStatus('error', '错误');
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
