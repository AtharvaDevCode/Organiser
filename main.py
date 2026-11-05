from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import FileResponse
from extractor import get_events_from_db, sync_emails_to_db
import psycopg2
import os

app = FastAPI(title="Uni Koblenz Dashboard API")

def get_db_connection():
    return psycopg2.connect(os.getenv("NEON_DB_URL"))

@app.get("/", response_class=FileResponse)
def serve_dashboard():
    return FileResponse("index.html")

@app.get("/events")
def get_events():
    data = get_events_from_db()
    return {
        "events": data["events"],
        "total_events": data["total_events"]
    }

@app.post("/sync")
def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_emails_to_db)
    return {"message": "Sync started in the background."}

@app.patch("/events/{event_id}/done")
async def toggle_done(event_id: int, request: Request):
    body = await request.json()
    is_done = body.get("is_done", False)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE university_events SET is_done = %s WHERE id = %s", (is_done, event_id))
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "Status updated"}
    except Exception as e:
        return {"error": str(e)}

@app.patch("/events/{event_id}/tags")
async def update_tags(event_id: int, request: Request):
    body = await request.json()
    tags = body.get("tags", [])
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE university_events SET tags = %s WHERE id = %s", (str(tags), event_id))
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "Tags updated"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/events/batch-delete")
async def batch_delete(request: Request):
    body = await request.json()
    ids = body.get("ids", [])
    if not ids:
        return {"message": "No IDs provided"}
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM university_events WHERE id = ANY(%s)", (ids,))
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "Batch deleted successfully"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/events/{event_id}")
def delete_event(event_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM university_events WHERE id = %s", (event_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "Event deleted successfully"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/events")
def clear_all_events():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE university_events RESTART IDENTITY")
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "All events cleared"}
    except Exception as e:
        return {"error": str(e)}
@app.patch("/events/{event_id}/pin")
async def toggle_pin(event_id: int, request: Request):
    body = await request.json()
    is_pinned = body.get("is_pinned", False)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE university_events SET is_pinned = %s WHERE id = %s", (is_pinned, event_id))
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "Pin status updated"}
    except Exception as e:
        return {"error": str(e)}