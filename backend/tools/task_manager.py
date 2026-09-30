from backend.storage import get_db, utc_now


def add_user_task(user_id: int, title: str) -> dict:
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO tasks (user_id, title, created_at) VALUES (?, ?, ?)",
            (user_id, title.strip(), utc_now()),
        )
        task_id = cursor.lastrowid
        row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row)


def list_user_tasks(user_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM tasks WHERE user_id = ? ORDER BY completed ASC, created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def complete_user_task(user_id: int, task_id: int) -> dict:
    with get_db() as db:
        db.execute("UPDATE tasks SET completed = 1 WHERE user_id = ? AND id = ?", (user_id, task_id))
        row = db.execute("SELECT * FROM tasks WHERE user_id = ? AND id = ?", (user_id, task_id)).fetchone()
    return dict(row) if row else {"error": "Task not found"}


def delete_user_task(user_id: int, task_id: int) -> dict:
    with get_db() as db:
        cursor = db.execute("DELETE FROM tasks WHERE user_id = ? AND id = ?", (user_id, task_id))
    return {"deleted": cursor.rowcount > 0, "task_id": task_id}
