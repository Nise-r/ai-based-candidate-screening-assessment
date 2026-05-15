// App.jsx
import { useState, useRef, useEffect } from "react";

const API_BASE = "http://localhost:8000";

const ROLES = [
  "Frontend Engineer", "Backend Engineer", "Full Stack Engineer",
  "Data Scientist", "ML Engineer", "DevOps Engineer",
  "Product Manager", "System Design", "Mobile Engineer", "Other"
];

function generateLocalId() {
  return "chat_" + Math.random().toString(36).slice(2, 10);
}

// Helper functions for localStorage persistence
const STORAGE_KEY = "interview_sessions";

function loadSessionsFromStorage() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    try {
      return JSON.parse(stored);
    } catch (e) {
      console.error("Failed to parse stored sessions", e);
      return [];
    }
  }
  return [];
}

function saveSessionsToStorage(sessions) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function Spinner() {
  return (
    <div className="spinner">
      <span /><span /><span />
    </div>
  );
}

function UploadScreen({ onComplete }) {
  const [file, setFile] = useState(null);
  const [role, setRole] = useState("");
  const [customRole, setCustomRole] = useState("");
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef();

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && f.type === "application/pdf") setFile(f);
    else setError("Only PDF files are accepted.");
  };

  const handleSubmit = async () => {
    const finalRole = role === "Other" ? customRole : role;
    if (!file || !finalRole.trim()) {
      setError("Please upload a resume and select/enter a role.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("role", finalRole);
      const res = await fetch(`${API_BASE}/parse-resume`, { method: "POST", body: fd });
      if (!res.ok) throw new Error("Server error: " + res.status);
      const data = await res.json();
      onComplete({ 
        chat_id: data.chat_id, 
        role: finalRole, 
        filename: file.name,  // Use the actual filename from the file object
        createdAt: new Date().toISOString()
      });
    } catch (e) {
      setError(e.message || "Upload failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-screen">
      <div className="upload-card">
        <div className="upload-header">
          <div className="logo-mark">AI</div>
          <h2>New Interview Session</h2>
          <p className="muted">Upload your resume and select the role you're applying for.</p>
        </div>

        <div
          className={`drop-zone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current.click()}
        >
          <input ref={inputRef} type="file" accept=".pdf" style={{ display: "none" }} onChange={e => setFile(e.target.files[0])} />
          {file ? (
            <>
              <div className="file-icon">📄</div>
              <p className="file-name">{file.name}</p>
              <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
            </>
          ) : (
            <>
              <div className="upload-icon">↑</div>
              <p>Drop your PDF here or <span className="link">browse</span></p>
              <span className="muted small">PDF only, max 10MB</span>
            </>
          )}
        </div>

        <div className="role-section">
          <label>Role Applying For</label>
          <div className="role-chips">
            {ROLES.map(r => (
              <button
                key={r}
                className={`chip ${role === r ? "active" : ""}`}
                onClick={() => setRole(r)}
              >{r}</button>
            ))}
          </div>
          {role === "Other" && (
            <input
              className="custom-role"
              placeholder="Enter role title..."
              value={customRole}
              onChange={e => setCustomRole(e.target.value)}
            />
          )}
        </div>

        {error && <p className="error-msg">{error}</p>}

        <button className="start-btn" onClick={handleSubmit} disabled={loading}>
          {loading ? <><Spinner /> Analyzing Resume…</> : "Start Interview →"}
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`bubble-row ${isUser ? "user" : "ai"}`}>
      {!isUser && <div className="avatar ai-avatar">AI</div>}
      <div className={`bubble ${isUser ? "user-bubble" : "ai-bubble"}`}>
        {msg.content}
      </div>
      {isUser && <div className="avatar user-avatar">You</div>}
    </div>
  );
}

function ChatView({ session, onHistoryLoaded, onMessagesUpdate }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const endRef = useRef();
  const textareaRef = useRef();

  // Load chat history when component mounts or session changes
  useEffect(() => {
    let isMounted = true;
    
    const loadHistory = async () => {
      if (!session?.chat_id) return;
      
      setIsLoadingHistory(true);
      try {
        const res = await fetch(`${API_BASE}/session/${session.chat_id}`);
        if (!res.ok) throw new Error("Failed to load session history");
        
        const data = await res.json();
        
        if (isMounted) {
          // Use the history from the backend, or fallback to default welcome message
          if (data.history && data.history.length > 0) {
            setMessages(data.history);
          } else {
            // No history yet - show welcome message
            const welcomeMsg = { 
              role: "assistant", 
              content: "Welcome! I'll be your interviewer today. Let's get started.\n\nTell me about yourself — your background, key experiences, and what brings you to this role." 
            };
            setMessages([welcomeMsg]);
          }
          
          if (onHistoryLoaded) {
            onHistoryLoaded(session.chat_id);
          }
        }
      } catch (err) {
        console.error("Failed to load history:", err);
        if (isMounted) {
          const welcomeMsg = { 
            role: "assistant", 
            content: "Welcome! I'll be your interviewer today. Let's get started.\n\nTell me about yourself — your background, key experiences, and what brings you to this role." 
          };
          setMessages([welcomeMsg]);
        }
      } finally {
        if (isMounted) {
          setIsLoadingHistory(false);
        }
      }
    };
    
    loadHistory();
    
    return () => {
      isMounted = false;
    };
  }, [session.chat_id, onHistoryLoaded]);

  // Notify parent when messages change (to update session preview)
  useEffect(() => {
    if (onMessagesUpdate && messages.length > 0) {
      onMessagesUpdate(session.chat_id, messages);
    }
  }, [messages, session.chat_id, onMessagesUpdate]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading || isLoadingHistory) return;
    setInput("");
    setError("");
    const newMessages = [...messages, { role: "user", content: q }];
    setMessages(newMessages);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: session.chat_id, query: q })
      });
      if (!res.ok) throw new Error("Server error");
      const data = await res.json();
      setMessages(prev => [...prev, { role: "assistant", content: data.response }]);
    } catch (e) {
      setError("Failed to get a response. Check if the backend is running.");
      setMessages(prev => prev.slice(0, -1));
      setInput(q);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  if (isLoadingHistory) {
    return (
      <div className="chat-view loading-state">
        <div className="loading-container">
          <Spinner />
          <p>Loading conversation history...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-view">
      <div className="chat-topbar">
        <div className="chat-meta">
          <span className="role-badge">{session.role}</span>
          <span className="filename muted">{session.filename || session.chat_id.slice(0, 12) + "…"}</span>
        </div>
        <div className="session-id muted">ID: {session.chat_id.slice(0, 8)}…</div>
      </div>

      <div className="messages-area">
        {messages.map((m, i) => <ChatBubble key={i} msg={m} />)}
        {loading && (
          <div className="bubble-row ai">
            <div className="avatar ai-avatar">AI</div>
            <div className="bubble ai-bubble typing-bubble"><Spinner /></div>
          </div>
        )}
        {error && <p className="error-inline">{error}</p>}
        <div ref={endRef} />
      </div>

      <div className="input-bar">
        <textarea
          ref={textareaRef}
          rows={1}
          placeholder="Type your answer… (Enter to send, Shift+Enter for newline)"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          disabled={loading || isLoadingHistory}
        />
        <button className="send-btn" onClick={send} disabled={loading || isLoadingHistory || !input.trim()}>
          ↑
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [showUpload, setShowUpload] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Load sessions from localStorage on mount
  useEffect(() => {
    const storedSessions = loadSessionsFromStorage();
    console.log("Loaded sessions from storage:", storedSessions);
    
    if (storedSessions.length > 0) {
      setSessions(storedSessions);
      
      // Restore the last active session from localStorage
      const lastActiveId = localStorage.getItem("last_active_session");
      const sessionExists = storedSessions.some(s => s.chat_id === lastActiveId);
      
      if (lastActiveId && sessionExists) {
        setActiveId(lastActiveId);
        setShowUpload(false);
      } else {
        setActiveId(storedSessions[0].chat_id);
        setShowUpload(false);
      }
    } else {
      // No sessions, show upload screen
      setShowUpload(true);
    }
  }, []);

  // Save sessions to localStorage whenever they change
  useEffect(() => {
    if (sessions.length > 0) {
      saveSessionsToStorage(sessions);
      console.log("Saved sessions to storage:", sessions);
    } else {
      // Clear storage if no sessions
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [sessions]);

  // Save last active session to localStorage
  useEffect(() => {
    if (activeId) {
      localStorage.setItem("last_active_session", activeId);
    }
  }, [activeId]);

  const activeSession = sessions.find(s => s.chat_id === activeId);

  const handleNewSession = (sessionData) => {
    const newSession = {
      ...sessionData,
      label: sessionData.role + " · " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      createdAt: new Date().toISOString(),
      lastMessage: "New interview session"
    };
    setSessions(prev => [newSession, ...prev]);
    setActiveId(newSession.chat_id);
    setShowUpload(false);
  };

  const startNew = () => {
    setActiveId(null);
    setShowUpload(true);
  };

  const handleSessionSelect = (chatId) => {
    setActiveId(chatId);
    setShowUpload(false);
  };

  const deleteSession = (chatId, e) => {
    e.stopPropagation();
    setSessions(prev => prev.filter(s => s.chat_id !== chatId));
    if (activeId === chatId) {
      const remainingSessions = sessions.filter(s => s.chat_id !== chatId);
      if (remainingSessions.length > 0) {
        setActiveId(remainingSessions[0].chat_id);
      } else {
        setActiveId(null);
        setShowUpload(true);
      }
    }
  };

  const updateSessionMessages = (chatId, messages) => {
    // Update the last message preview for the session
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.role === "user") {
      setSessions(prev => prev.map(session => 
        session.chat_id === chatId 
          ? { ...session, lastMessage: lastMessage.content.substring(0, 50) + (lastMessage.content.length > 50 ? "..." : "") }
          : session
      ));
    }
  };

  return (
    <div className={`app ${sidebarOpen ? "sidebar-open" : "sidebar-closed"}`}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <span className="brand-icon">◈</span>
            <span className="brand-name">InterviewAI</span>
          </div>
          <button className="toggle-btn" onClick={() => setSidebarOpen(v => !v)} title="Toggle sidebar">
            {sidebarOpen ? "←" : "→"}
          </button>
        </div>

        <button className="new-chat-btn" onClick={startNew}>
          <span>+</span> New Interview
        </button>

        <div className="sessions-list">
          {sessions.length === 0 && (
            <p className="empty-hint">No interviews yet.<br />Start one above.</p>
          )}
          {sessions.map(s => (
            <div key={s.chat_id} className={`session-item-wrapper ${activeId === s.chat_id ? "active" : ""}`}>
              <button
                className="session-item"
                onClick={() => handleSessionSelect(s.chat_id)}
              >
                <span className="session-role">{s.role}</span>
                <span className="session-file muted">{s.filename ? s.filename.slice(0, 20) : s.chat_id.slice(0, 10)}</span>
                {s.lastMessage && (
                  <span className="session-preview muted">{s.lastMessage}</span>
                )}
                <span className="session-time muted">{s.label?.split("·")[1] || ""}</span>
              </button>
              <button 
                className="delete-session-btn" 
                onClick={(e) => deleteSession(s.chat_id, e)}
                title="Delete session"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <p className="muted small">Powered by Groq · LlamaParse</p>
        </div>
      </aside>

      <main className="main">
        {showUpload ? (
          <UploadScreen onComplete={handleNewSession} />
        ) : activeSession ? (
          <ChatView 
            key={activeSession.chat_id} 
            session={activeSession} 
            onMessagesUpdate={updateSessionMessages}
          />
        ) : sessions.length === 0 ? (
          <UploadScreen onComplete={handleNewSession} />
        ) : (
          <div className="empty-state">
            <div className="empty-icon">◈</div>
            <h2>Select an interview</h2>
            <p className="muted">Pick a session from the sidebar or start a new one.</p>
            <button className="start-btn" onClick={startNew}>Start New Interview</button>
          </div>
        )}
      </main>
    </div>
  );
}