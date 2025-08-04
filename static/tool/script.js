// 智能工具助手前端脚本
class ToolAssistant {
    constructor() {
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.messagesContainer = document.getElementById('messages');
        this.toolStatus = document.getElementById('toolStatus');
        this.charCount = document.querySelector('.char-count');
        
        this.isProcessing = false;
        this.currentEventSource = null;
        this.currentContent = '';  // 存储当前流式内容
        
        // 初始化 Markdown 渲染
        this.initMarkdown();
        
        this.init();
    }
    
    initMarkdown() {
        // 配置Marked渲染器
        if (typeof marked !== 'undefined') {
            console.log('marked.js 库已加载');
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
        } else {
            console.warn('marked.js 库未加载，将使用纯文本显示');
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
        
        // 字符计数
        this.messageInput.addEventListener('input', () => {
            const count = this.messageInput.value.length;
            this.charCount.textContent = `${count}/500`;
            
            if (count > 450) {
                this.charCount.style.color = '#ff4444';
            } else {
                this.charCount.style.color = '#666';
            }
        });
        
        // 自动聚焦输入框
        this.messageInput.focus();
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isProcessing) return;
        
        // 显示用户消息
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.charCount.textContent = '0/500';
        
        // 设置处理状态
        this.setProcessing(true);
        
        try {
            await this.streamResponse(message);
        } catch (error) {
            console.error('发送消息失败:', error);
            this.addMessage('抱歉，发送消息时出现了错误，请稍后重试。', 'assistant');
        } finally {
            this.setProcessing(false);
        }
    }
    
    async streamResponse(message) {
        // 创建助手消息容器
        const assistantMessage = this.addMessage('', 'assistant', true);
        const contentDiv = assistantMessage.querySelector('.content p');
        
        // 建立SSE连接
        const encodedMessage = encodeURIComponent(message);
        this.currentEventSource = new EventSource(`/tool/stream?message=${encodedMessage}`);
        
        let hasContent = false;
        let toolsUsed = false;
        
        this.currentEventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                switch (data.type) {
                    case 'tool_status':
                        // 显示工具状态
                        this.showToolStatus(data.content);
                        toolsUsed = true;
                        break;
                        
                    case 'tool_call':
                        // 显示工具调用信息
                        this.addToolInfo(assistantMessage, data);
                        break;
                        
                    case 'content':
                        // 流式添加内容
                        if (!hasContent) {
                            contentDiv.innerHTML = '';
                            hasContent = true;
                            this.currentContent = '';  // 重置内容缓存
                        }
                        
                        // 累积内容并渲染 Markdown
                        this.currentContent += data.content;
                        
                        // 累积内容并使用专门的渲染方法
                        this.renderMarkdownContent(contentDiv, this.currentContent);
                        
                        this.scrollToBottom();
                        break;
                        
                    case 'complete':
                        // 完成响应
                        this.hideToolStatus();
                        this.currentEventSource.close();
                        this.currentEventSource = null;
                        
                        // 如果没有内容，显示默认消息
                        if (!hasContent) {
                            contentDiv.innerHTML = '已完成处理，但没有返回内容。';
                        }
                        break;
                        
                    case 'error':
                        // 错误处理
                        this.hideToolStatus();
                        contentDiv.innerHTML = data.content || '处理请求时出现错误';
                        this.currentEventSource.close();
                        this.currentEventSource = null;
                        break;
                }
            } catch (error) {
                console.error('解析SSE数据失败:', error);
            }
        };
        
        this.currentEventSource.onerror = (error) => {
            console.error('SSE连接错误:', error);
            this.hideToolStatus();
            
            if (!hasContent) {
                contentDiv.innerHTML = '连接服务器时出现错误，请稍后重试。';
            }
            
            if (this.currentEventSource) {
                this.currentEventSource.close();
                this.currentEventSource = null;
            }
        };
    }
    
    addMessage(content, type, isEmpty = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        const avatar = type === 'user' ? '👤' : '🤖';
        
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="avatar">${avatar}</div>
                <div class="content">
                    <p>${isEmpty ? '正在思考...' : content}</p>
                </div>
            </div>
        `;
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
        
        return messageDiv;
    }
    
    addToolInfo(messageElement, toolData) {
        const contentDiv = messageElement.querySelector('.content');
        
        // 创建工具信息显示
        const toolInfoDiv = document.createElement('div');
        toolInfoDiv.className = 'tool-info';
        
        const argsText = Object.keys(toolData.args).length > 0 
            ? JSON.stringify(toolData.args, null, 2) 
            : '无参数';
        
        toolInfoDiv.innerHTML = `
            <div class="tool-name">🔧 调用工具: ${toolData.name}</div>
            <div class="tool-args">参数: ${argsText}</div>
        `;
        
        contentDiv.appendChild(toolInfoDiv);
        this.scrollToBottom();
    }
    
    showToolStatus(message) {
        const statusText = this.toolStatus.querySelector('.status-text');
        statusText.textContent = message;
        this.toolStatus.style.display = 'block';
    }
    
    hideToolStatus() {
        this.toolStatus.style.display = 'none';
    }
    
    setProcessing(processing) {
        this.isProcessing = processing;
        this.sendButton.disabled = processing;
        this.messageInput.disabled = processing;
        
        const sendText = this.sendButton.querySelector('.send-text');
        const loadingSpinner = this.sendButton.querySelector('.loading-spinner');
        
        if (processing) {
            sendText.style.display = 'none';
            loadingSpinner.style.display = 'inline';
        } else {
            sendText.style.display = 'inline';
            loadingSpinner.style.display = 'none';
        }
    }
    
    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
    
    renderMarkdownContent(element, content) {
        try {
            if (typeof marked !== 'undefined') {
                // 渲染Markdown内容
                const htmlContent = marked.parse(content);
                element.innerHTML = htmlContent;
                
                // 高亮代码块（如果hljs可用）
                if (typeof hljs !== 'undefined') {
                    element.querySelectorAll('pre code').forEach((block) => {
                        hljs.highlightElement(block);
                    });
                }
                console.log('Markdown 渲染成功:', content.substring(0, 50) + '...');
            } else {
                // 如果Markdown库未加载，使用纯文本但保留换行
                element.innerHTML = content.replace(/\n/g, '<br>');
                console.log('使用纯文本显示:', content.substring(0, 50) + '...');
            }
        } catch (error) {
            console.error('Markdown渲染错误:', error);
            element.innerHTML = content.replace(/\n/g, '<br>');
        }
    }
    
    // 清理资源
    cleanup() {
        if (this.currentEventSource) {
            this.currentEventSource.close();
            this.currentEventSource = null;
        }
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    const assistant = new ToolAssistant();
    
    // 页面卸载时清理资源
    window.addEventListener('beforeunload', () => {
        assistant.cleanup();
    });
});

// 添加一些实用功能
document.addEventListener('DOMContentLoaded', () => {
    // 添加快捷示例按钮（可选）
    const examples = [
        '今天北京的天气如何？',
        '最新的科技新闻有哪些？',
        '帮我搜索Python编程教程',
        '最近有什么热门电影？'
    ];
    
    // 可以在这里添加示例按钮的逻辑
    console.log('智能工具助手已加载完成');
    console.log('支持的示例问题:', examples);
});
