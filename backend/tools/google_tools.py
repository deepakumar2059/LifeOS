import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from backend.storage import google_token_path, set_connection

BASE_DIR = Path(__file__).resolve().parents[2]
CLIENT_SECRET_FILE = BASE_DIR / "client_secrets.json"
if not CLIENT_SECRET_FILE.exists():
    CLIENT_SECRET_FILE = Path(__file__).resolve().parent / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]


def credentials_available() -> bool:
    return CLIENT_SECRET_FILE.exists()


def build_flow(redirect_uri: str, code_verifier: str | None = None) -> Flow:
    if not credentials_available():
        raise RuntimeError(
            "Google OAuth credentials were not found. "
            "Add client_secrets.json to the project root."
        )

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    if code_verifier:
        flow.code_verifier = code_verifier

    return flow




def save_credentials(user_id: int, credentials: Credentials):
    path = google_token_path(user_id)
    path.write_text(credentials.to_json(), encoding="utf-8")


def remove_credentials(user_id: int):
    path = google_token_path(user_id)
    if path.exists():
        path.unlink()
    set_connection(user_id, gmail=False, calendar=False)


def get_credentials(user_id: int) -> Credentials:
    path = google_token_path(user_id)
    if not path.exists():
        raise RuntimeError("Google account is not connected")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(user_id, creds)
    if not creds.valid:
        raise RuntimeError("Google account needs to be reconnected")
    return creds


def gmail_service(user_id: int):
    return build("gmail", "v1", credentials=get_credentials(user_id), cache_discovery=False)


def calendar_service(user_id: int):
    return build("calendar", "v3", credentials=get_credentials(user_id), cache_discovery=False)


def _headers(payload: dict) -> dict:
    return {item.get("name", ""): item.get("value", "") for item in payload.get("headers", [])}


def _decode_body(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    body_data = payload.get("body", {}).get("data")
    if body_data:
        return _decode_body(body_data)
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode_body(part["body"]["data"])
    for part in payload.get("parts", []):
        nested = _extract_body(part)
        if nested:
            return nested
    return ""


def list_recent_emails(user_id: int, max_results: int = 10) -> list[dict]:
    service = gmail_service(user_id)
    response = service.users().messages().list(userId="me", maxResults=max_results).execute()
    messages = response.get("messages", [])
    results = []
    for item in messages:
        email = service.users().messages().get(
            userId="me",
            id=item["id"],
            format="metadata",
            metadataHeaders=["From", "To", "Subject", "Date"],
        ).execute()
        headers = _headers(email.get("payload", {}))
        results.append(
            {
                "id": item["id"],
                "thread_id": email.get("threadId"),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "snippet": email.get("snippet", ""),
            }
        )
    return results


def search_emails_for_user(user_id: int, query: str, max_results: int = 10) -> list[dict]:
    service = gmail_service(user_id)
    response = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = response.get("messages", [])
    return [get_email_for_user(user_id, item["id"], include_body=False) for item in messages]


def get_email_for_user(user_id: int, message_id: str, include_body: bool = True) -> dict:
    email = gmail_service(user_id).users().messages().get(userId="me", id=message_id, format="full").execute()
    payload = email.get("payload", {})
    headers = _headers(payload)
    result = {
        "id": message_id,
        "thread_id": email.get("threadId"),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "snippet": email.get("snippet", ""),
    }
    if include_body:
        result["body"] = _extract_body(payload)
    return result


def send_email_for_user(user_id: int, to: str, subject: str, body: str) -> dict:
    message = EmailMessage()
    message.set_content(body)
    message["To"] = to
    message["Subject"] = subject
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    sent = gmail_service(user_id).users().messages().send(userId="me", body={"raw": encoded}).execute()
    return {"sent": True, "id": sent.get("id"), "thread_id": sent.get("threadId")}


def delete_email_for_user(user_id: int, message_id: str) -> dict:
    gmail_service(user_id).users().messages().trash(userId="me", id=message_id).execute()
    return {"deleted": True, "id": message_id}


def draft_email(to: str, subject: str, intent: str) -> dict:
    return {
        "to": to,
        "subject": subject,
        "body": f"Hi,\n\n{intent}\n\nBest,",
    }


def list_calendar_events(user_id: int, days: int = 14, max_results: int = 20) -> list[dict]:
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days)
    events = calendar_service(user_id).events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=time_max.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])
    return [
        {
            "id": event.get("id"),
            "summary": event.get("summary", ""),
            "start": event.get("start", {}),
            "end": event.get("end", {}),
            "location": event.get("location", ""),
            "description": event.get("description", ""),
        }
        for event in events
    ]


def create_calendar_event(user_id: int, summary: str, start_iso: str, end_iso: str, description: str = "", location: str = "") -> dict:
    event = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    created = calendar_service(user_id).events().insert(calendarId="primary", body=event).execute()
    return {"created": True, "id": created.get("id"), "html_link": created.get("htmlLink")}


def delete_calendar_event(user_id: int, event_id: str) -> dict:
    calendar_service(user_id).events().delete(calendarId="primary", eventId=event_id).execute()
    return {"deleted": True, "id": event_id}
