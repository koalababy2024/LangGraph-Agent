/**
 * LangGraph Chat Frontend
 * 处理用户输入和流式响应显示
 */

class ChatApp {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.inputStatus = document.getElementById('inputStatus');
        this.loadingIndicator = document.getElementById('loadingIndicator');
        
        this.isStreaming = false;
        this.currentBotMessage = null;
        this.currentBotContent = '';  // 用于累积流式内容
        
        this.initMarkdown();
        this.init();
    }
    
    initMarkdown() {
        // 配置Marked渲染器
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                highlight: function(code, lang) {
                    if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                        try {
                            return hljs.highlight(code, { language: lang }).value;
                        } catch (err) {}
                    }
                    return code;
                },
                breaks: true,  // 支持换行
                gfm: true      // GitHub Flavored Markdown
            });
        }
    }
    
    init() {
        // 绑定事件监听器
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // 输入框字符计数
        this.messageInput.addEventListener('input', () => this.updateInputStatus());
        
        // 初始化状态
        this.updateInputStatus();
        this.scrollToBottom();
    }
    
    updateInputStatus() {
        const length = this.messageInput.value.length;
        const maxLength = this.messageInput.maxLength;
        this.inputStatus.textContent = `${length}/${maxLength} 字符`;
        
        if (length > maxLength * 0.8) {
            this.inputStatus.style.color = '#dc3545';
        } else {
            this.inputStatus.style.color = '#666';
        }
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isStreaming) return;
        
        // 显示用户消息
        this.addMessage(message, 'user');
        
        // 清空输入框
        this.messageInput.value = '';
        this.updateInputStatus();
        
        // 开始流式请求
        await this.streamChatResponse(message);
    }
    
    addMessage(content, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = type === 'user' ? '👤' : '🤖';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        const messageText = document.createElement('p');
        messageText.textContent = content;
        
        messageContent.appendChild(messageText);
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
        
        return messageDiv;
    }
    
    async streamChatResponse(message) {
        this.isStreaming = true;
        this.sendButton.disabled = true;
        this.loadingIndicator.classList.add('show');
        this.currentBotContent = '';  // 重置内容累积器
        
        // 创建机器人消息容器
        this.currentBotMessage = this.addMessage('', 'bot');
        const messageText = this.currentBotMessage.querySelector('p');
        messageText.classList.add('streaming-text');
        
        try {
            // 构建请求URL
            const url = `/chat/stream?message=${encodeURIComponent(message)}`;
            
            // 创建EventSource连接
            const eventSource = new EventSource(url);
            
            eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleStreamData(data, messageText);
                } catch (error) {
                    console.error('解析流数据时出错:', error);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('EventSource 错误:', error);
                this.handleStreamError('连接服务器时出现错误，请稍后重试。');
                eventSource.close();
            };
            
            // 监听连接关闭
            eventSource.addEventListener('error', () => {
                this.finishStreaming();
                eventSource.close();
            });
            
        } catch (error) {
            console.error('发送消息时出错:', error);
            this.handleStreamError('发送消息失败，请检查网络连接。');
        }
    }
    
    handleStreamData(data, messageElement) {
        switch (data.type) {
            case 'start':
                // 开始信号
                console.log('开始接收流数据');
                break;
                
            case 'content':
                // 内容数据 - 累积并渲染Markdown
                if (data.content) {
                    this.currentBotContent += data.content;
                    this.renderMarkdownContent(messageElement, this.currentBotContent);
                    this.scrollToBottom();
                }
                break;
                
            case 'metadata':
                // 元数据 - 可以用于显示处理状态
                console.log('处理状态:', data.metadata);
                break;
                
            case 'end':
                // 结束信号
                console.log('流数据接收完成');
                this.finishStreaming();
                break;
                
            case 'error':
                // 错误信号
                this.handleStreamError(data.content || '处理请求时出现错误');
                break;
                
            default:
                console.log('未知数据类型:', data);
        }
    }
    
    handleStreamError(errorMessage) {
        if (this.currentBotMessage) {
            const messageText = this.currentBotMessage.querySelector('p');
            messageText.textContent = errorMessage;
            messageText.classList.add('error-message');
            messageText.classList.remove('streaming-text');
        }
        this.finishStreaming();
    }
    
    finishStreaming() {
        this.isStreaming = false;
        this.sendButton.disabled = false;
        this.loadingIndicator.classList.remove('show');
        
        if (this.currentBotMessage) {
            const messageText = this.currentBotMessage.querySelector('p');
            messageText.classList.remove('streaming-text');
            
            // 如果消息为空，显示默认错误信息
            if (!messageText.textContent.trim()) {
                messageText.textContent = '抱歉，我现在无法回应。请稍后再试。';
                messageText.classList.add('error-message');
            }
        }
        
        this.currentBotMessage = null;
        this.currentBotContent = '';  // 清空内容累积器
        this.scrollToBottom();
    }
    
    renderMarkdownContent(element, content) {
        try {
            if (typeof marked !== 'undefined') {
                // 渲染Markdown内容
                const htmlContent = marked.parse(content);
                element.innerHTML = htmlContent;
                
                // 高亮代码块
                if (typeof hljs !== 'undefined') {
                    element.querySelectorAll('pre code').forEach((block) => {
                        hljs.highlightElement(block);
                    });
                }
            } else {
                // 如果Markdown库未加载，使用纯文本
                element.textContent = content;
            }
        } catch (error) {
            console.error('Markdown渲染错误:', error);
            element.textContent = content;
        }
    }
    
    scrollToBottom() {
        setTimeout(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }, 100);
    }
    
    // 工具方法：清空聊天记录
    clearChat() {
        // 保留欢迎消息
        const messages = this.chatMessages.querySelectorAll('.message');
        for (let i = 1; i < messages.length; i++) {
            messages[i].remove();
        }
    }
    
    // 工具方法：添加系统消息
    addSystemMessage(content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message bot-message';
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = '⚙️';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        const messageText = document.createElement('p');
        messageText.textContent = content;
        messageText.style.fontStyle = 'italic';
        messageText.style.opacity = '0.8';
        
        messageContent.appendChild(messageText);
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
}

// 页面加载完成后初始化聊天应用
document.addEventListener('DOMContentLoaded', () => {
    const chatApp = new ChatApp();
    
    // 全局暴露聊天应用实例（用于调试）
    window.chatApp = chatApp;
    
    // 添加键盘快捷键
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + K 清空聊天
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            chatApp.clearChat();
            chatApp.addSystemMessage('聊天记录已清空');
        }
    });
    
    // 处理页面可见性变化
    document.addEventListener('visibilitychange', () => {
        if (document.hidden && chatApp.isStreaming) {
            // 页面隐藏时，可以选择暂停流式传输
            console.log('页面已隐藏，流式传输继续进行');
        }
    });
});

// 错误处理
window.addEventListener('error', (e) => {
    console.error('全局错误:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('未处理的Promise拒绝:', e.reason);
});
