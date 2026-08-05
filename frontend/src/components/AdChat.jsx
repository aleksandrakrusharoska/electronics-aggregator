import { useEffect, useRef, useState } from 'react'
import { chatAboutAd } from '../api/client'

const SUGGESTED_QUESTIONS = [
  'Дали е ова добра цена?',
  'На што да внимавам пред купување?',
  'Дали вреди да преговарам за цената?',
]

export default function AdChat({ ad }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  const send = async (text) => {
    const content = (text ?? input).trim()
    if (!content || loading) return
    const nextMessages = [...messages, { role: 'user', content }]
    setMessages(nextMessages)
    setInput('')
    setLoading(true)
    setError(null)
    try {
      const { reply } = await chatAboutAd(ad, nextMessages)
      setMessages(m => [...m, { role: 'assistant', content: reply }])
    } catch {
      setError('Асистентот не е достапен во моментов. Обидете се повторно.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-2 p-4 min-h-[240px] max-h-[360px]">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-xs text-slate-400 dark:text-slate-500">Прашај нешто за овој оглас:</p>
            {SUGGESTED_QUESTIONS.map(q => (
              <button
                key={q}
                onClick={() => send(q)}
                className="block w-full text-left text-sm px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-violet-100 dark:hover:bg-violet-900/30 text-slate-600 dark:text-slate-300 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap ${
              m.role === 'user'
                ? 'bg-violet-600 text-white'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200'
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-xl px-3 py-2 text-sm bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 italic">
              Пишува...
            </div>
          </div>
        )}
        {error && <p className="text-xs text-red-500">{error}</p>}
      </div>
      <form
        onSubmit={e => { e.preventDefault(); send() }}
        className="shrink-0 flex items-center gap-2 p-3 border-t border-slate-100 dark:border-slate-800"
      >
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Прашај нешто..."
          maxLength={500}
          className="flex-1 text-sm bg-slate-100 dark:bg-slate-800 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-violet-400 text-slate-900 dark:text-slate-100"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="shrink-0 bg-violet-600 hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg p-2 transition-colors"
          aria-label="Испрати"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-6 6m6-6l6 6" />
          </svg>
        </button>
      </form>
    </div>
  )
}
