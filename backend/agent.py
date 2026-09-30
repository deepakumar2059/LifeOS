from langchain.agents import create_agent
from langchain_core.tools import StructuredTool

from backend.storage import get_connections
from backend.tools.RAG import retrieve_for_user
from backend.tools.config import GEMINI_MODEL
from backend.tools.google_tools import (
    create_calendar_event,
    delete_calendar_event,
    delete_email_for_user,
    draft_email,
    get_email_for_user,
    list_calendar_events,
    list_recent_emails,
    search_emails_for_user,
    send_email_for_user,
)
from backend.tools.task_manager import add_user_task, complete_user_task, list_user_tasks

SYSTEM_PROMPT = """
You are LifeOS, a practical productivity agent for the logged-in user.

You can manage pending tasks, search uploaded documents, and, when connected by the user, use Gmail and Google Calendar tools. Use tools when they can improve accuracy or complete an action. Do not claim Gmail or Calendar access unless the matching tool is available.

For email or calendar destructive actions, be careful: only delete or send when the user's request is explicit. You may draft email content without sending. Use the knowledge base when the user asks to search documents or when uploaded documents are likely to contain needed context.

Keep answers concise, useful, and grounded in tool results. The system has only short-term memory for the current session; do not say that you stored long-term memory.
"""


def build_tools(user_id: int):
    tools = [
        StructuredTool.from_function(
            name="add_task",
            description="Add a pending task for the user.",
            func=lambda title: add_user_task(user_id, title),
        ),
        StructuredTool.from_function(
            name="list_tasks",
            description="List the user's pending and completed tasks.",
            func=lambda: list_user_tasks(user_id),
        ),
        StructuredTool.from_function(
            name="complete_task",
            description="Mark a task complete by numeric task id.",
            func=lambda task_id: complete_user_task(user_id, int(task_id)),
        ),
        StructuredTool.from_function(
            name="search_knowledge_base",
            description="Search the user's uploaded PDF and DOCX documents for relevant context.",
            func=lambda query, k=5: retrieve_for_user(user_id, query, int(k)),
        ),
    ]

    connections = get_connections(user_id)
    if connections["gmail_enabled"]:
        tools.extend(
            [
                StructuredTool.from_function(
                    name="read_recent_emails",
                    description="Read the user's latest Gmail messages. max_results controls top k emails.",
                    func=lambda max_results=10: list_recent_emails(user_id, int(max_results)),
                ),
                StructuredTool.from_function(
                    name="search_emails",
                    description="Search Gmail using Gmail search syntax such as from:, subject:, is:unread.",
                    func=lambda query, max_results=10: search_emails_for_user(user_id, query, int(max_results)),
                ),
                StructuredTool.from_function(
                    name="read_email",
                    description="Read a specific Gmail message by message id.",
                    func=lambda message_id: get_email_for_user(user_id, message_id),
                ),
                StructuredTool.from_function(
                    name="write_email",
                    description="Draft an email body without sending it.",
                    func=draft_email,
                ),
                StructuredTool.from_function(
                    name="send_email",
                    description="Send an email. Only use after the user clearly asks to send.",
                    func=lambda to, subject, body: send_email_for_user(user_id, to, subject, body),
                ),
                StructuredTool.from_function(
                    name="delete_email",
                    description="Move a Gmail message to trash by id. Only use after explicit user request.",
                    func=lambda message_id: delete_email_for_user(user_id, message_id),
                ),
            ]
        )

    if connections["calendar_enabled"]:
        tools.extend(
            [
                StructuredTool.from_function(
                    name="read_calendar_events",
                    description="Read upcoming Google Calendar events.",
                    func=lambda days=14, max_results=20: list_calendar_events(user_id, int(days), int(max_results)),
                ),
                StructuredTool.from_function(
                    name="create_calendar_event",
                    description="Create a calendar event using ISO datetime strings for start and end.",
                    func=lambda summary, start_iso, end_iso, description="", location="": create_calendar_event(
                        user_id, summary, start_iso, end_iso, description, location
                    ),
                ),
                StructuredTool.from_function(
                    name="delete_calendar_event",
                    description="Delete a calendar event by event id. Only use after explicit user request.",
                    func=lambda event_id: delete_calendar_event(user_id, event_id),
                ),
            ]
        )

    return tools


def run_agent(user_id: int, messages: list[dict]) -> str:
    agent = create_agent(model=GEMINI_MODEL, tools=build_tools(user_id), system_prompt=SYSTEM_PROMPT)
    result = agent.invoke({"messages": messages})
    final_message = result["messages"][-1]
    if hasattr(final_message, "content") and isinstance(final_message.content, str):
        return final_message.content
    if hasattr(final_message, "content_blocks") and final_message.content_blocks:
        return "\n".join(block.get("text", "") for block in final_message.content_blocks if block.get("type") == "text")
    return str(final_message)
