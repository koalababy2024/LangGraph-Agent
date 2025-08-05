// 智能工具助手前端脚本
class ToolAssistant {
    constructor() {
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.messagesContainer = document.getElementById('messages');
        this.isProcessing = false;
        this.currentAssistantMessage = null;
        this.currentContent = '';
        this.forceNewMessage = false; // Flag to force a new message for the final reply

        this.initMarkdown();
        this.init();
    }

    initMarkdown() {
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                highlight: function(code, lang) {
                    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                    return hljs.highlight(code, { language }).value;
                },
                breaks: true,
                gfm: true
            });
        }
    }

    init() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        this.messageInput.focus();
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isProcessing) return;

        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.setProcessing(true);

        try {
            await this.streamResponse(message);
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessage('An error occurred. Please try again.', 'assistant');
            this.setProcessing(false);
        }
    }

    async streamResponse(message) {
        this.cleanupEmptyAssistantMessages();
        this.currentAssistantMessage = null;
        this.currentContent = '';
        this.aiResponseContainer = null;

        const encodedMessage = encodeURIComponent(message);
        this.currentEventSource = new EventSource(`/tool/stream?message=${encodedMessage}`);

        let contentDiv = null;

        const ensureAssistantMessage = () => {
            if (!this.currentAssistantMessage) {
                this.currentAssistantMessage = this.addMessage('', 'assistant', true);
                contentDiv = this.currentAssistantMessage.querySelector('.content');
            }
        };

        this.currentEventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('收到SSE事件:', data.type, data);

            switch (data.type) {
                case 'start':
                    ensureAssistantMessage();
                    contentDiv.innerHTML = '<p>正在思考...</p>';
                    break;

                case 'ai_decision':
                    console.log('处理AI决策事件:', data);
                    ensureAssistantMessage();
                    this.addAIDecisionInfo(this.currentAssistantMessage, data);
                    break;

                case 'tool_call':
                case 'tool_result':
                    console.log('处理工具事件:', data.type, data);
                    ensureAssistantMessage();
                    if (data.type === 'tool_call') {
                        this.addToolCallInfo(this.currentAssistantMessage, data);
                    } else {
                        this.addToolResultInfo(this.currentAssistantMessage, data);
                    }
                    break;

                case 'content':
                    ensureAssistantMessage();
                    
                    // 如果有AI回复容器（工具执行后），使用该容器
                    let targetContainer = this.aiResponseContainer;
                    
                    // 如果没有AI回复容器，且contentDiv中已有工具信息，创建一个新的回复区域
                    if (!targetContainer) {
                        const hasToolInfo = contentDiv.querySelector('.ai-decision-info, .tool-call-info, .tool-result-info');
                        if (hasToolInfo) {
                            // 创建 AI 回复区域
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
                    console.log('正在渲染内容到:', targetContainer, '内容:', this.currentContent);
                    this.renderMarkdownContent(targetContainer, this.currentContent);
                    break;

                case 'end':
                    this.currentEventSource.close();
                    this.setProcessing(false);
                    this.cleanupEmptyAssistantMessages();
                    break;

                case 'error':
                    ensureAssistantMessage();
                    contentDiv.innerHTML = `<p class="error-message">Error: ${data.content}</p>`;
                    this.currentEventSource.close();
                    this.setProcessing(false);
                    break;
            }
            this.scrollToBottom();
        };

        this.currentEventSource.onerror = (error) => {
            console.error('SSE Error:', error);
            if (this.currentEventSource) this.currentEventSource.close();
            this.setProcessing(false);
            if (!this.currentAssistantMessage || this.currentContent === ''){
                 this.addMessage('Connection failed. Please try again.', 'assistant');
            }
        };
    }

    cleanupEmptyAssistantMessages() {
        const messages = this.messagesContainer.querySelectorAll('.message.assistant');
        messages.forEach(msg => {
            const content = msg.querySelector('.content');
            if (content && content.innerHTML.trim() === '<p>正在思考...</p>') {
                msg.remove();
            }
        });
    }

    addMessage(content, type, isEmpty = false) {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${type}`;
        const avatar = type === 'user' ? '👤' : '🤖';
        const contentHtml = isEmpty ? '' : marked.parse(content);

        messageElement.innerHTML = `
            <div class="message-content">
                <div class="avatar">${avatar}</div>
                <div class="content">${contentHtml}</div>
            </div>
        `;
        this.messagesContainer.appendChild(messageElement);
        return messageElement;
    }

    addAIDecisionInfo(messageElement, data) {
        console.log('addAIDecisionInfo被调用:', messageElement, data);
        const contentDiv = messageElement.querySelector('.content');
        console.log('contentDiv查找结果:', contentDiv);
        
        if (!contentDiv) {
            console.error('contentDiv为空，无法添加AI决策信息');
            return;
        }
        
        if (contentDiv.innerHTML.includes('正在思考...')) {
            contentDiv.innerHTML = '';
        }

        // 添加AI决定调用工具的提示
        const decisionDiv = document.createElement('div');
        decisionDiv.className = 'ai-decision-info';
        decisionDiv.innerHTML = `
            <div class="decision-header">${data.content}</div>
        `;
        console.log('正在添加AI决策元素:', decisionDiv);
        contentDiv.appendChild(decisionDiv);
        console.log('AI决策元素已添加，contentDiv内容:', contentDiv.innerHTML);
    }

    addToolCallInfo(messageElement, toolData) {
        console.log('addToolCallInfo被调用:', messageElement, toolData);
        const contentDiv = messageElement.querySelector('.content');
        console.log('contentDiv查找结果:', contentDiv);
        
        if (!contentDiv) {
            console.error('contentDiv为空，无法添加工具调用信息');
            return;
        }
        
        // 添加工具调用详情
        const toolCallDiv = document.createElement('div');
        toolCallDiv.className = 'tool-call-info';
        const toolName = toolData.tool_name || toolData.name || 'unknown';
        const args = JSON.stringify(toolData.tool_args || toolData.args || {}, null, 2);
        toolCallDiv.innerHTML = `
            <div class="tool-header">🔍 调用工具: <strong>${toolName}</strong></div>
            <pre><code>${args}</code></pre>
        `;
        console.log('正在添加工具调用元素:', toolCallDiv);
        contentDiv.appendChild(toolCallDiv);
        console.log('工具调用元素已添加，contentDiv内容:', contentDiv.innerHTML);
    }

    addToolResultInfo(messageElement, toolData) {
        const contentDiv = messageElement.querySelector('.content');
        const toolResultDiv = document.createElement('div');
        toolResultDiv.className = 'tool-result-info';
        toolResultDiv.innerHTML = `
            <div class="tool-result-header">✅ 工具执行完成</div>
            <div class="tool-result-content">${toolData.result}</div>
        `;
        contentDiv.appendChild(toolResultDiv);
        
        // 添加AI回复分隔区域
        const aiResponseSection = document.createElement('div');
        aiResponseSection.className = 'ai-response-section';
        aiResponseSection.innerHTML = `
            <div class="ai-response-header">🤖 AI回复:</div>
            <div class="ai-response-content"></div>
        `;
        contentDiv.appendChild(aiResponseSection);
        
        // 设置标志，准备在同一消息中显示AI回复
        this.aiResponseContainer = aiResponseSection.querySelector('.ai-response-content');
        
        // 重设内容累积，避免重复
        this.currentContent = '';
    }

    setProcessing(processing) {
        this.isProcessing = processing;
        this.sendButton.disabled = processing;
        this.messageInput.disabled = processing;
        this.sendButton.querySelector('.send-text').style.display = processing ? 'none' : 'inline';
        this.sendButton.querySelector('.loading-spinner').style.display = processing ? 'inline' : 'none';
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    renderMarkdownContent(element, content) {
        element.innerHTML = marked.parse(content);
        element.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }

    cleanup() {
        if (this.currentEventSource) {
            this.currentEventSource.close();
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const assistant = new ToolAssistant();
    window.addEventListener('beforeunload', () => assistant.cleanup());
});
