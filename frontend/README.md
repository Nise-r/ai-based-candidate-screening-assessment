# InterviewAI — Frontend

A React + Vite frontend for the AI Interview Chatbot FastAPI backend.

## Prerequisites

- Node.js 18+
- Your FastAPI backend running at `http://localhost:8000`

## Setup

```bash
cd interview-chatbot
npm install
npm run dev
```

App runs at **http://localhost:3000**

## Backend CORS

Your FastAPI backend already allows `http://localhost:3000`. Make sure it's running before using the app.

## Features

- **Sidebar** — browse and switch between multiple interview sessions
- **New Interview** — upload a PDF resume + pick/enter a role to start a session
- **Chat** — streaming-style chat UI; first message is always "Tell me about yourself"
- **Session persistence** — each chat_id maps to a separate conversation thread
- **Collapsible sidebar** — toggle with the ← → button

## File Structure

```
src/
  App.jsx     ← all components (UploadScreen, ChatView, App shell)
  App.css     ← full dark-theme stylesheet
  main.jsx    ← React entry point
index.html
vite.config.js
package.json
```
