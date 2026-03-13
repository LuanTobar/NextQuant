'use client';

import { useState, useRef, useEffect } from 'react';
import type { ChatMessage } from '@/types';

const WELCOME_MSG: ChatMessage = {
  id: '0',
  role: 'assistant',
  content:
    "Hi! I'm your NexQuant Copilot. Ask me anything about your portfolio, market conditions, or predictions. Try: \"What's the outlook for AAPL?\"",
  timestamp: new Date().toISOString(),
};

export function ChatInterface() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MSG]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });

      const data = await res.json();

      const assistantMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.response || 'Sorry, I could not process that request.',
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: 'Connection error. Please try again.',
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-nq-card rounded-xl border border-nq-border flex flex-col h-[600px] overflow-hidden">
      {/* Header — gradient accent */}
      <div className="px-4 py-3.5 border-b border-nq-border relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #6366f115 0%, #111827 70%)' }}
      >
        <div className="absolute -top-6 -right-6 w-24 h-24 rounded-full blur-2xl opacity-20 pointer-events-none bg-nq-accent" />
        <div className="flex items-center gap-2 relative">
          <span className="text-lg">🧠</span>
          <div>
            <p className="text-sm font-semibold">Causal Copilot</p>
            <p className="text-[10px] text-nq-muted">Ask why things happen, not just what happened</p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-nq-accent text-white shadow-lg shadow-nq-accent/20'
                  : 'bg-nq-bg border border-nq-border'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-nq-bg border border-nq-border rounded-xl px-4 py-3 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-nq-accent animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-nq-accent animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-nq-accent animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={messagesEnd} />
      </div>

      {/* Input */}
      <div className="p-3.5 border-t border-nq-border">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Ask about your portfolio..."
            className="flex-1 bg-nq-bg border border-nq-border rounded-lg px-4 py-2.5 text-sm outline-none focus:border-nq-accent focus:ring-1 focus:ring-nq-accent/30 transition"
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            className="bg-nq-accent hover:bg-nq-accent/80 disabled:opacity-40 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition shadow-md shadow-nq-accent/20"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
