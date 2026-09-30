# LifeOS

LifeOS is a personal productivity web app that combines a local knowledge base, task management, and optional Google Gmail/Calendar integrations into a single AI-powered assistant.

The app is built with FastAPI on the backend, a lightweight vanilla JavaScript frontend, and a Gemini-powered agent using LangChain. Users can sign in, ask questions, manage tasks, upload PDFs/DOCX documents, and search their own knowledge base.

## Features

- User authentication with email/password
- Persistent task tracking per user
- AI chat assistant for productivity workflows
- Upload and index PDF/DOCX documents using ChromaDB + embeddings
- Semantic search across uploaded knowledge base
- Optional Google Gmail integration
- Optional Google Calendar integration
- Short-term session memory for the current login session

## Architecture

### Backend

The backend is in `backend/` and uses FastAPI.

- `backend/main.py` — API routes, authentication, document uploads, Google OAuth flow, and app entry point
- `backend/agent.py` — builds the LangChain agent and exposes productivity tools
- `backend/storage.py` — SQLite database setup, session/token management, and user data storage
- `backend/tools/` — supporting tools for:
  - task management
  - document indexing and retrieval (RAG)
  - Google Gmail/Calendar integration
  - configuration values for the LLM and embeddings

### Frontend

The frontend is served from `frontend/` and is a simple static app:

- `frontend/index.html` — dashboard, auth UI, task view, knowledge base interface, and tools configuration page
- `frontend/style.css` — UI styling
- `frontend/script.js` — frontend logic for authentication, chat, document upload/search, tasks, and Google connection toggles

## Tech Stack

- Python
- FastAPI
- SQLite
- LangChain
- LangChain Chroma + embeddings
- Google API client libraries
- Gemini model via `langchain-google-genai`
- JavaScript + HTML + CSS

## Project Workflow

The application basically works like this:

1. A user registers or logs in.
2. The user can ask LifeOS questions via the chat interface.
3. The agent can:
   - create or list tasks
   - search uploaded documents using RAG
   - read Gmail messages if connected
   - search Gmail if connected
   - create or delete calendar events if connected
4. Documents are uploaded as PDF or DOCX, split into chunks, embedded, and stored in ChromaDB.
5. The user can search their uploaded knowledge base for contextual answers.

## Repository Structure

```text
LifeOS/
├── backend/
│   ├── data/
│   ├── tools/
│   ├── __init__.py
│   ├── agent.py
│   ├── main.py
│   └── storage.py
├── frontend/
│   ├── index.html
│   ├── script.js
│   └── style.css
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/deepakumar2059/LifeOS.git
cd LifeOS
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root if you want to customize environment settings:

```env
# Optional project configuration
# Add any required app secrets or API settings here
```

The app also expects a Google OAuth credentials file named `client_secrets.json` at the project root if you want Gmail or Calendar features enabled.

## Running the Application

Start the backend server:

```bash
uvicorn backend.main:app --reload
```

Then open the app in your browser at:

```text
http://127.0.0.1:8000/
```

The app serves the frontend from the `frontend/` directory and exposes the REST API through FastAPI.

## Google Integration

Google OAuth is supported for Gmail and Calendar.

To enable it:

1. Add a valid `client_secrets.json` file at the project root.
2. Log in to the app.
3. Use the Google connection flow in the Tools page.
4. Toggle Gmail and/or Calendar access in the UI.

The project expects OAuth credentials with scopes for:

- Gmail access
- Calendar access

## Knowledge Base

Users can upload:

- PDF files
- DOCX files

These are:

- parsed
- split into chunks
- embedded using `sentence-transformers/all-MiniLM-L6-v2`
- stored in ChromaDB for semantic retrieval

## Notes

- The system keeps short-term conversation context only for the current session.
- Long-term memory is intentionally not implemented in this version.
- The app stores local data under `backend/data/` and creates required directories automatically.

## License

This project does not appear to include a license file in the current repository snapshot. If needed, add one before publishing or redistributing the code.

## Summary

LifeOS is a practical personal productivity assistant that brings together task management, document knowledge retrieval, and optional Google productivity tools into one user-facing app. It is especially useful for users who want an AI assistant that can operate over their own documents and calendar/email workflows without needing a complex multi-service setup.
