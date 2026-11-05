from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from mangum import Mangum
from extractor import sync_emails_to_db

load_dotenv()

app = FastAPI()

def get_db_connection():
    return psycopg2.connect(os.getenv("NEON_DB_URL"))

@app.get("/", response_class=HTMLResponse)
async def read_root():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "index.html not found in root directory."

@app.get("/events")
async def get_events():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM university_events ORDER BY id DESC")
        events = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) as total FROM university_events")
        total_events = cursor.fetchone()["total"]
        
        cursor.close()
        conn.close()
        return {"events": events, "total_events": total_events}
    except Exception as e:
        return {"events": [], "total_events": 0, "error": str(e)}

@app.post("/sync")
async def trigger_sync():
    try:
        sync_emails_to_db()
        return {"message": "Sync completed successfully."}
    except Exception as e:
        return {"error": str(e)}

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
        return {"message": "Done status updated"}
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

@app.patch("/events/{event_id}/tags")
async def update_tags(event_id: int, request: Request):
    body = await request.json()
    tags = body.get("tags", [])
    is_done = body.get("is_done", None)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if is_done is not None:
            cursor.execute("UPDATE university_events SET tags = %s, is_done = %s WHERE id = %s", (str(tags), is_done, event_id))
        else:
            cursor.execute("UPDATE university_events SET tags = %s WHERE id = %s", (str(tags), event_id))
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "Tags updated"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/events/{event_id}")
async def delete_event(event_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM university_events WHERE id = %s", (event_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "Event deleted"}
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
        return {"message": f"Deleted {len(ids)} events"}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/events")
async def clear_all_events():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM university_events")
        conn.commit()
        cursor.close()
        conn.close()
        return {"message": "All events purged"}
    except Exception as e:
        return {"error": str(e)}

# Vercel Serverless Handler Adapter
handler = Mangum(app)