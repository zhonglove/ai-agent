import { useState, useRef, useEffect } from 'react'

const API_BASE = 'http://localhost:8000'

const MODELS = ['qwen-turbo', 'qwen-plus', 'qwen-max', 'gpt-3.5-turbo', 'deepseek-chat']

function ChatMessage({ role, content }) {
  const isUser = role === 'user'
  return (
    <div className={`message ${isUser ? 'message-user' : 'message-assistant'}`}>
      <div className="message-avatar">{isUser ? 'U' : 'A'}</div>
      <div className="message-content">{content}</div>
    </div>
  )
}

function App() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: '你好！我是 AI 助手，有什么可以帮你的？' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [model, setModel] = useState('qwen-turbo')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(2048)
  const [showSettings, setShowSettings] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    if (!input.trim() || loading) return

    const userMsg = { role: 'user', content: input }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setLoading(true)

    const assistantMsg = { role: 'assistant', content: '' }
    setMessages((prev) => [...prev, assistantMsg])

    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: newMessages,
          model,
          temperature,
          max_tokens: maxTokens,
        }),
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = JSON.parse(line.slice(6))
          if (data.error) {
            setMessages((prev) => {
              const copy = [...prev]
              copy[copy.length - 1] = { role: 'assistant', content: `错误: ${data.error}` }
              return copy
            })
            break
          }
          if (data.content === '[DONE]') continue
          setMessages((prev) => {
            const copy = [...prev]
            const last = { ...copy[copy.length - 1] }
            last.content += data.content
            copy[copy.length - 1] = last
            return copy
          })
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const copy = [...prev]
        copy[copy.length - 1] = { role: 'assistant', content: `请求失败: ${err.message}` }
        return copy
      })
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function clearHistory() {
    setMessages([{ role: 'assistant', content: '你好！我是 AI 助手，有什么可以帮你的？' }])
  }

  return (
    <div className="app">
      <header className="header">
        <h1>AI Chat</h1>
        <div className="header-actions">
          <button onClick={clearHistory} className="btn btn-sm">清空</button>
          <button onClick={() => setShowSettings(!showSettings)} className="btn btn-sm">
            {showSettings ? '收起' : '设置'}
          </button>
        </div>
      </header>

      {showSettings && (
        <div className="settings">
          <div className="setting-row">
            <label>模型</label>
            <select value={model} onChange={(e) => setModel(e.target.value)}>
              {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="setting-row">
            <label>温度 {temperature}</label>
            <input type="range" min="0" max="2" step="0.1" value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))} />
          </div>
          <div className="setting-row">
            <label>最大 Token {maxTokens}</label>
            <input type="range" min="256" max="8192" step="256" value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))} />
          </div>
        </div>
      )}

      <div className="messages">
        {messages.map((msg, i) => (
          <ChatMessage key={i} role={msg.role} content={msg.content} />
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="input-area">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
          rows={2}
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading || !input.trim()} className="btn btn-send">
          {loading ? '...' : '发送'}
        </button>
      </div>
    </div>
  )
}

export default App
