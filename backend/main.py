import os
import secrets
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from backend.agent import run_agent
from backend.storage import (
    UPLOAD_DIR,
    google_token_path,
    create_session,
    create_user,
    delete_session,
    get_connections,
    get_user_by_email,
    get_user_for_token,
    init_db,
    set_connection,
    verify_password,
)
from backend.tools.RAG import add_document, list_documents, remove_document, retrieve_for_user
from backend.tools.google_tools import build_flow, credentials_available, remove_credentials, save_credentials
from backend.tools.task_manager import delete_user_task, list_user_tasks
import os

# Allow insecure HTTP connections for local testing
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
#this line should be removed before deploying the project to the server 

load_dotenv()
init_db()

app = FastAPI(title="LifeOS")
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = (BASE_DIR / ".." / "frontend").resolve()
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

SESSION_MESSAGES: dict[str, list[dict]] = {}



class AuthRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1)


class SearchRequest(BaseModel):
    query: str
    k: int = 5


class ConnectionRequest(BaseModel):
    gmail_enabled: bool | None = None
    calendar_enabled: bool | None = None


def public_user(user):
    return {"id": user["id"], "email": user["email"]}


def auth_context(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    user = get_user_for_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return {"user": user, "token": token}


@app.get("/")
def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.post("/api/auth/register")
def register(payload: AuthRequest):
    if get_user_by_email(payload.email):
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = create_user(payload.email, payload.password)
    token = create_session(user["id"])
    return {"token": token, "user": public_user(user)}


@app.post("/api/auth/login")
def login(payload: AuthRequest):
    user = get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_session(user["id"])
    return {"token": token, "user": public_user(user)}


@app.get("/api/auth/me")
def me(ctx=Depends(auth_context)):
    return {"user": public_user(ctx["user"])}


@app.post("/api/auth/logout")
def logout(ctx=Depends(auth_context)):
    delete_session(ctx["token"])
    SESSION_MESSAGES.pop(ctx["token"], None)
    return {"ok": True}


@app.get("/api/status")
def status(ctx=Depends(auth_context)):
    user_id = ctx["user"]["id"]
    connections = get_connections(user_id)
    google_connected = google_token_path(user_id).exists()
    return {
        "gmail_connected": bool(connections["gmail_enabled"]) and google_connected,
        "calendar_connected": bool(connections["calendar_enabled"]) and google_connected,
        "google_credentials_available": credentials_available(),
        "google_connected": google_connected,
        "documents": len(list_documents(user_id)),
        "tasks": len(list_user_tasks(user_id)),
    }


@app.post("/api/ask")
def ask_question(payload: QuestionRequest, ctx=Depends(auth_context)):
    history = SESSION_MESSAGES.setdefault(ctx["token"], [])
    history.append({"role": "user", "content": payload.question})
    compact_history = history[-12:]
    try:
        answer = run_agent(ctx["user"]["id"], compact_history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    history.append({"role": "assistant", "content": answer})
    SESSION_MESSAGES[ctx["token"]] = history[-12:]
    return {"answer": answer}


@app.get("/api/tasks")
def tasks(ctx=Depends(auth_context)):
    return {"tasks": list_user_tasks(ctx["user"]["id"])}


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, ctx=Depends(auth_context)):
    return delete_user_task(ctx["user"]["id"], task_id)


@app.get("/api/documents")
def documents(ctx=Depends(auth_context)):
    return {"documents": list_documents(ctx["user"]["id"])}


@app.post("/api/documents/search")
def search_documents(payload: SearchRequest, ctx=Depends(auth_context)):
    return retrieve_for_user(ctx["user"]["id"], payload.query, payload.k)


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...), ctx=Depends(auth_context)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")
    filename = Path(file.filename).name
    if Path(filename).suffix.lower() not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    stored_name = f"user_{ctx['user']['id']}_{secrets.token_hex(8)}_{filename}"
    file_path = UPLOAD_DIR / stored_name
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        result = add_document(ctx["user"]["id"], str(file_path), filename, file.content_type or "")
        return {"message": "Document uploaded and indexed", **result}
    except Exception as exc:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await file.close()


@app.delete("/api/documents/{filename}")
def delete_document(filename: str, ctx=Depends(auth_context)):
    return remove_document(ctx["user"]["id"], Path(filename).name)




OAUTH_STATES: dict[str, dict] = {}


@app.get("/api/google/connect")
def google_connect(request: Request, ctx=Depends(auth_context)):
    redirect_uri = str(request.url_for("google_callback"))

    flow = build_flow(redirect_uri)

    state = secrets.token_urlsafe(24)

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )

    OAUTH_STATES[state] = {
        "user_id": ctx["user"]["id"],
        "code_verifier": flow.code_verifier,
    }

    return {"url": auth_url}


@app.get("/api/google/callback")
def google_callback(request: Request):
    state = request.query_params.get("state", "")

    oauth_data = OAUTH_STATES.pop(state, None)

    if not oauth_data:
        return RedirectResponse("/?oauth=failed")

    user_id = oauth_data["user_id"]
    code_verifier = oauth_data["code_verifier"]

    redirect_uri = str(request.url_for("google_callback"))

    flow = build_flow(
        redirect_uri,
        code_verifier=code_verifier,
    )

    flow.fetch_token(
        authorization_response=str(request.url)
    )

    save_credentials(
        user_id,
        flow.credentials
    )

    set_connection(
        user_id,
        gmail=True,
        calendar=True,
    )

    return RedirectResponse("/?oauth=connected")


@app.post("/api/connections")
def update_connections(payload: ConnectionRequest, ctx=Depends(auth_context)):
    user_id = ctx["user"]["id"]
    wants_google_tool = payload.gmail_enabled is True or payload.calendar_enabled is True
    if wants_google_tool and not google_token_path(user_id).exists():
        raise HTTPException(status_code=400, detail="Connect Google OAuth before enabling Gmail or Calendar tools")
    set_connection(user_id, payload.gmail_enabled, payload.calendar_enabled)
    connections = get_connections(user_id)
    google_connected = google_token_path(user_id).exists()
    return {
        "gmail_connected": bool(connections["gmail_enabled"]) and google_connected,
        "calendar_connected": bool(connections["calendar_enabled"]) and google_connected,
    }


@app.delete("/api/google")
def disconnect_google(ctx=Depends(auth_context)):
    remove_credentials(ctx["user"]["id"])
    return {"gmail_connected": False, "calendar_connected": False}
