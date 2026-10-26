export type Route = 'overview' | 'sessions' | 'analysis' | 'patterns' | 'recommendations' | 'settings' | 'chat' | 'auth'
export type Message = { id: string; role: 'user' | 'assistant'; content: string; createdAt: string }
export type Session = { id: string; title: string; topic: string; date: string; status: 'completed' | 'in_progress'; duration: string; messages: Message[] }
export type User = { id: string; name: string; email: string }
export type Pattern = { id: string; title: string; description: string; confidence?: number; evidence: string[]; sessions: number }
export type Analysis = { summary: string; traces: { type: string; content: string; evidence: string }[]; reflection: string }
