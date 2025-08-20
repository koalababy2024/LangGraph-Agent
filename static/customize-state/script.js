class CustomizeStateApp {
  constructor() {
    this.threadId = this.initThreadId();
    this.isProcessing = false;
    this.currentEventSource = null;
    this.currentAssistantMessage = null;
    this.isWaitingForHumanInput = false;
    this.currentIntervention = null; // {question, name, birthday}
    this.aiResponseContainer = null;

    this.initializeElements();
    this.attachEventListeners();
    this.updateThreadDisplay();
    this.initMarkdown();
  }

  // 显示工具运行中的提示
  addToolRunningInfo(messageElement, data) {
    const contentDiv = messageElement.querySelector('.content');
    if (!contentDiv) return;
    const runDiv = document.createElement('div');
    runDiv.className = 'tool-running-info';
    const text = data && data.content ? data.content : '🔍 正在联网搜索相关信息...';
    runDiv.innerHTML = `<div class="tool-running-header">${text}</div>`;
    contentDiv.appendChild(runDiv);
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
    this.interventionQuestion = document.getElementById('intervention-question');
    this.interventionName = document.getElementById('intervention-name');
    this.interventionBirthday = document.getElementById('intervention-birthday');
    this.interventionCorrect = document.getElementById('intervention-correct');
    this.interventionSubmit = document.getElementById('intervention-submit');
    this.interventionCancel = document.getElementById('intervention-cancel');
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
    if (this.interventionSubmit) {
      this.interventionSubmit.addEventListener('click', () => this.submitInterventionForm());
    }
    if (this.interventionCancel) {
      this.interventionCancel.addEventListener('click', () => this.closeInterventionPanel());
    }
  }

  initThreadId() {
    const ts = Date.now();
    const rnd = Math.random().toString(36).slice(2, 8);
    return `customize_${ts}_${rnd}`;
  }

  updateThreadDisplay() {
    if (this.threadIdDisplay) {
      const shortId = this.threadId.slice(-8);
      this.threadIdDisplay.textContent = `...${shortId}`;
    }
  }

  resetConversation() {
    this.threadId = this.initThreadId();
    this.updateThreadDisplay();

    const messages = this.chatMessages.querySelectorAll('.message:not(.welcome-message)');
    messages.forEach(m => m.remove());

    this.resetInterventionState();
    this.updateStatus('ready', '就绪');
    this.showNotification('已开始新对话');
  }

  updateStatus(type, text) {
    this.statusIndicator.className = `status-indicator ${type}`;
    this.statusIndicator.querySelector('.status-text').textContent = text;
  }

  showNotification(message) {
    this.notification.textContent = message;
    this.notification.classList.add('show');
    setTimeout(() => this.notification.classList.remove('show'), 3000);
  }

  addMessage(role, content, isEmpty = false) {
    const div = document.createElement('div');
    div.className = `message ${role}`;
    const avatar = role === 'user' ? '👤' : '🤖';
    const html = isEmpty ? '' : (typeof marked !== 'undefined' ? marked.parse(content) : content);
    div.innerHTML = `
      <div class="message-content">
        <div class="message-avatar">${avatar}</div>
        <div class="content">${html}</div>
      </div>
    `;
    this.chatMessages.appendChild(div);
    this.scrollToBottom();
    return div;
  }

  scrollToBottom() {
    this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
  }

  adjustTextareaHeight() {
    this.userInput.style.height = 'auto';
    this.userInput.style.height = Math.min(this.userInput.scrollHeight, 150) + 'px';
  }

  async sendMessage() {
    const text = this.userInput.value.trim();
    if (!text || this.isProcessing) return;

    // 正在等待人工输入 -> 视为人工回复
    if (this.isWaitingForHumanInput) {
      await this.submitHumanResponse(text);
      return;
    }

    this.isProcessing = true;
    this.updateStatus('thinking', '思考中...');
    this.sendButton.disabled = true;

    this.addMessage('user', text);
    this.userInput.value = '';
    this.adjustTextareaHeight();

    try {
      await this.streamChat(text);
    } catch (e) {
      console.error('发送消息失败:', e);
      this.addMessage('assistant', '抱歉，发送消息时出现错误，请稍后再试。');
      this.updateStatus('error', '错误');
      this.isProcessing = false;
      this.sendButton.disabled = false;
    }
  }

  async streamChat(message) {
    this.currentAssistantMessage = null;
    this.currentContent = '';
    this.aiResponseContainer = null;

    const url = `/customize-state/chat/stream?message=${encodeURIComponent(message)}&thread_id=${encodeURIComponent(this.threadId)}`;
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
        console.log('SSE事件:', data.type, data);
        switch (data.type) {
          case 'start':
            ensureAssistantMessage();
            contentDiv.innerHTML = '<p>正在思考...</p>';
            break;
          case 'content':
            ensureAssistantMessage();
            let target = this.aiResponseContainer;
            if (!target) {
              const hasToolInfo = contentDiv.querySelector('.ai-decision-info, .tool-call-info, .tool-result-info');
              if (hasToolInfo) {
                const sec = document.createElement('div');
                sec.className = 'ai-response-section';
                sec.innerHTML = '<div class="ai-response-header">🤖 AI回复:</div><div class="ai-response-content"></div>';
                contentDiv.appendChild(sec);
                target = sec.querySelector('.ai-response-content');
                this.aiResponseContainer = target;
              } else {
                target = contentDiv;
              }
            }
            this.currentContent += data.content;
            this.renderMarkdown(target, this.currentContent);
            break;
          case 'ai_decision':
            ensureAssistantMessage();
            this.addAIDecisionInfo(this.currentAssistantMessage, data);
            break;
          case 'tool_running':
            ensureAssistantMessage();
            this.addToolRunningInfo(this.currentAssistantMessage, data);
            break;
          case 'tool_call':
            ensureAssistantMessage();
            this.addToolCallInfo(this.currentAssistantMessage, data);
            break;
          case 'tool_result':
            ensureAssistantMessage();
            this.addToolResultInfo(this.currentAssistantMessage, data);
            break;
          case 'intervention_required':
            this.currentEventSource.close();
            // 仅在聊天中内联展示干预表单，不弹窗
            this.showInterventionInline(data);
            this.updateStatus('intervention', '等待人工协助...');
            this.isProcessing = false;
            this.sendButton.disabled = false;
            break;
          case 'end':
            this.currentEventSource.close();
            this.updateStatus('ready', '就绪');
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
        console.error('解析SSE失败:', e, event.data);
      }
    };

    this.currentEventSource.onerror = (err) => {
      console.error('SSE错误:', err);
      if (this.currentEventSource) this.currentEventSource.close();
      this.updateStatus('error', '连接错误');
      this.isProcessing = false;
      this.sendButton.disabled = false;
      if (!this.currentAssistantMessage || this.currentContent === '') {
        this.addMessage('assistant', '连接失败，请稍后再试。');
      }
    };
  }

  // 供内联表单直接调用的提交逻辑
  submitInterventionWithParams({ correct, name, birthday }) {
    // 在聊天中显示一条“专家操作”消息概览
    const summary = correct ? '✅ 确认信息正确 (correct=y)' : `📝 提交修改：${name ? 'name='+name : ''} ${birthday ? 'birthday='+birthday : ''}`.trim();
    this.addMessage('user', summary || '📝 提交人工确认');

    this.resetInterventionState();
    this.updateStatus('processing', '处理专家回复中...');
    this.isProcessing = true;
    this.sendButton.disabled = true;

    const params = new URLSearchParams({ thread_id: this.threadId });
    if (correct) params.set('correct', correct);
    if (!correct) {
      if (name) params.set('name', name);
      if (birthday) params.set('birthday', birthday);
    }
    const url = `/customize-state/respond/stream?${params.toString()}`;
    const es = new EventSource(encodeURI(url));

    let assistantMsg = this.addMessage('assistant', '');
    const contentDiv = assistantMsg.querySelector('.content');
    this.aiResponseContainer = null;
    this.renderMarkdown(contentDiv, '');

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('respond/stream:', data.type, data);
        switch (data.type) {
          case 'start':
            break;
          case 'content': {
            let target = this.aiResponseContainer;
            if (!target) {
              const hasToolInfo = contentDiv.querySelector('.ai-decision-info, .tool-call-info, .tool-result-info');
              if (hasToolInfo) {
                const sec = document.createElement('div');
                sec.className = 'ai-response-section';
                sec.innerHTML = '<div class="ai-response-header">🤖 AI回复:</div><div class="ai-response-content"></div>';
                contentDiv.appendChild(sec);
                target = sec.querySelector('.ai-response-content');
                this.aiResponseContainer = target;
              } else {
                target = contentDiv;
              }
            }
            this.currentContent = (this.currentContent || '') + data.content;
            this.renderMarkdown(target, this.currentContent);
            break; }
          case 'ai_decision':
            this.addAIDecisionInfo(assistantMsg, data);
            break;
          case 'tool_running':
            this.addToolRunningInfo(assistantMsg, data);
            break;
          case 'tool_call':
            this.addToolCallInfo(assistantMsg, data);
            break;
          case 'tool_result':
            this.addToolResultInfo(assistantMsg, data);
            break;
          case 'end':
            es.close();
            this.updateStatus('ready', '就绪');
            this.isProcessing = false;
            this.sendButton.disabled = false;
            break;
          case 'error':
            es.close();
            contentDiv.innerHTML = `<p class="error-message">错误: ${data.error}</p>`;
            this.updateStatus('error', '错误');
            this.isProcessing = false;
            this.sendButton.disabled = false;
            break;
        }
        this.scrollToBottom();
      } catch (e) {
        console.error('解析SSE失败:', e, event.data);
      }
    };

    es.onerror = (err) => {
      console.error('SSE错误:', err);
      es.close();
      this.updateStatus('error', '连接错误');
      this.isProcessing = false;
      this.sendButton.disabled = false;
      if (!this.currentAssistantMessage || this.currentContent === '') {
        this.addMessage('assistant', '连接失败，请稍后再试。');
      }
    };
  }

  renderMarkdown(container, content) {
    if (typeof marked !== 'undefined') {
      container.innerHTML = marked.parse(content);
    } else {
      container.innerHTML = content.replace(/\n/g, '<br>');
    }
  }

  addAIDecisionInfo(messageElement, data) {
    const contentDiv = messageElement.querySelector('.content');
    if (!contentDiv) return;
    if (contentDiv.innerHTML.includes('正在思考...')) {
      contentDiv.innerHTML = '';
    }
    const decisionDiv = document.createElement('div');
    decisionDiv.className = 'ai-decision-info';
    decisionDiv.innerHTML = `<div class="decision-header">${data.content || '🤖 AI决定调用工具'}</div>`;
    contentDiv.appendChild(decisionDiv);
  }

  addToolCallInfo(messageElement, toolData) {
    const contentDiv = messageElement.querySelector('.content');
    if (!contentDiv) return;
    const toolDiv = document.createElement('div');
    toolDiv.className = 'tool-call-info';
    const toolName = toolData.tool_name || toolData.name || 'unknown';
    const args = JSON.stringify(toolData.tool_args || toolData.args || {}, null, 2);
    toolDiv.innerHTML = `<div class="tool-header">🔍 调用工具: <strong>${toolName}</strong></div><pre><code>${args}</code></pre>`;
    contentDiv.appendChild(toolDiv);
  }

  addToolResultInfo(messageElement, toolData) {
    const contentDiv = messageElement.querySelector('.content');
    if (!contentDiv) return;
    const resDiv = document.createElement('div');
    resDiv.className = 'tool-result-info';
    resDiv.innerHTML = `<div class="tool-result-header">✅ 工具执行完成</div><div class="tool-result-content">${toolData.result || ''}</div>`;
    contentDiv.appendChild(resDiv);
    const aiSec = document.createElement('div');
    aiSec.className = 'ai-response-section';
    aiSec.innerHTML = '<div class="ai-response-header">🤖 AI回复:</div><div class="ai-response-content"></div>';
    contentDiv.appendChild(aiSec);
    this.aiResponseContainer = aiSec.querySelector('.ai-response-content');
    this.currentContent = '';
  }

  // 在聊天消息中内联展示干预表单（不弹窗、不移除已有消息）
  showInterventionInline(data) {
    this.isWaitingForHumanInput = true;
    const { question, name, birthday } = data || {};
    this.currentIntervention = { question, name, birthday };

    const msg = document.createElement('div');
    msg.className = 'message assistant intervention-message';
    const contentMd = [
      '🤝 **需要人工专家协助**',
      question ? `\n\n**问题：** ${question}` : '',
    ].join('');
    msg.innerHTML = `
      <div class="message-content">
        <div class="message-avatar">🤖</div>
        <div class="content">
          ${typeof marked !== 'undefined' ? marked.parse(contentMd) : contentMd}
          <div class="intervention-inline-form">
            <label style="display:flex;align-items:center;gap:8px;margin:8px 0;">
              <input id="inline-correct" type="checkbox"> 信息正确 (correct=y)
            </label>
            <div style="display:flex;gap:10px;flex-wrap:wrap;margin:8px 0;">
              <input id="inline-name" type="text" placeholder="姓名" value="${name || ''}" style="flex:1;min-width:160px;padding:8px;border:1px solid #e9ecef;border-radius:8px;" />
              <input id="inline-birthday" type="text" placeholder="生日 (YYYY-MM-DD)" value="${birthday || ''}" style="flex:1;min-width:180px;padding:8px;border:1px solid #e9ecef;border-radius:8px;" />
            </div>
            <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:10px;">
              <button id="inline-submit" class="submit-button">提交回复</button>
              <button id="inline-cancel" class="cancel-button">取消</button>
            </div>
          </div>
        </div>
      </div>`;
    this.chatMessages.appendChild(msg);

    // 绑定内联按钮事件
    const correctEl = msg.querySelector('#inline-correct');
    const nameEl = msg.querySelector('#inline-name');
    const birthdayEl = msg.querySelector('#inline-birthday');
    const submitBtn = msg.querySelector('#inline-submit');
    const cancelBtn = msg.querySelector('#inline-cancel');

    submitBtn.addEventListener('click', () => {
      const correct = correctEl && correctEl.checked ? 'y' : undefined;
      const n = nameEl && nameEl.value.trim() || undefined;
      const b = birthdayEl && birthdayEl.value.trim() || undefined;
      this.submitInterventionWithParams({ correct, name: n, birthday: b });
      // 提交后禁用按钮避免重复提交
      submitBtn.disabled = true;
    });
    cancelBtn.addEventListener('click', () => {
      msg.remove();
      this.resetInterventionState();
    });

    this.scrollToBottom();
  }

  resetInterventionState() {
    this.isWaitingForHumanInput = false;
    this.currentIntervention = null;
    this.userInput.placeholder = '请输入您的问题...';
    const sendText = this.sendButton.querySelector('.send-text');
    if (sendText) sendText.textContent = '发送';
  }

  // 打开/关闭干预面板
  openInterventionPanel(data) {
    if (!this.interventionPanel) return;
    const { question, name, birthday } = data || {};
    if (this.interventionQuestion) this.interventionQuestion.textContent = question || 'Is this correct?';
    if (this.interventionName) this.interventionName.value = name || '';
    if (this.interventionBirthday) this.interventionBirthday.value = birthday || '';
    if (this.interventionCorrect) this.interventionCorrect.checked = false;
    this.interventionPanel.style.display = 'flex';
  }

  closeInterventionPanel() {
    if (!this.interventionPanel) return;
    this.interventionPanel.style.display = 'none';
  }

  submitInterventionForm() {
    // 读取表单值
    const correct = this.interventionCorrect && this.interventionCorrect.checked ? 'y' : undefined;
    const name = (this.interventionName && this.interventionName.value.trim()) || undefined;
    const birthday = (this.interventionBirthday && this.interventionBirthday.value.trim()) || undefined;

    // 在聊天中显示一条“专家操作”消息
    const summary = correct ? '✅ 确认信息正确 (correct=y)' : `📝 提交修改：${name ? 'name='+name : ''} ${birthday ? 'birthday='+birthday : ''}`.trim();
    this.addMessage('user', summary || '📝 提交人工确认');

    this.closeInterventionPanel();
    this.resetInterventionState();
    this.updateStatus('processing', '处理专家回复中...');
    this.isProcessing = true;
    this.sendButton.disabled = true;

    // 拼接查询参数
    const params = new URLSearchParams({ thread_id: this.threadId });
    if (correct) params.set('correct', correct);
    if (!correct) {
      if (name) params.set('name', name);
      if (birthday) params.set('birthday', birthday);
    }

    const url = `/customize-state/respond/stream?${params.toString()}`;
    const es = new EventSource(encodeURI(url));

    let assistantMsg = this.addMessage('assistant', '');
    const contentDiv = assistantMsg.querySelector('.content');
    let buf = '';
    this.aiResponseContainer = null;
    this.renderMarkdown(contentDiv, buf);

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('respond/stream:', data.type, data);
        switch (data.type) {
          case 'start':
            break;
          case 'content':
            let target = this.aiResponseContainer;
            if (!target) {
              const hasToolInfo = contentDiv.querySelector('.ai-decision-info, .tool-call-info, .tool-result-info');
              if (hasToolInfo) {
                const sec = document.createElement('div');
                sec.className = 'ai-response-section';
                sec.innerHTML = '<div class="ai-response-header">🤖 AI回复:</div><div class="ai-response-content"></div>';
                contentDiv.appendChild(sec);
                target = sec.querySelector('.ai-response-content');
                this.aiResponseContainer = target;
              } else {
                target = contentDiv;
              }
            }
            buf += data.content;
            this.renderMarkdown(target, buf);
            break;
          case 'ai_decision':
            this.addAIDecisionInfo(assistantMsg, data);
            break;
          case 'tool_running':
            this.addToolRunningInfo(assistantMsg, data);
            break;
          case 'tool_call':
            this.addToolCallInfo(assistantMsg, data);
            break;
          case 'tool_result':
            this.addToolResultInfo(assistantMsg, data);
            break;
          case 'intervention_required':
            es.close();
            this.showInterventionInChat(data);
            this.openInterventionPanel(data);
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
  }
}

// 初始化
window.addEventListener('DOMContentLoaded', () => {
  new CustomizeStateApp();
});
