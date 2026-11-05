import imaplib
import email
from email.header import decode_header
from groq import Groq
import json
import os
import time
import logging
import psycopg2
import re
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_db_connection():
    return psycopg2.connect(os.getenv("NEON_DB_URL"))

def get_events_from_db():
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
        logger.error(f"Database read error: {str(e)}")
        return {"events": [], "total_events": 0}

def extract_first_link(text):
    urls = re.findall(r'(https?://[^\s]+)', text)
    for url in urls:
        url = url.rstrip(')>].')
        if "uni-koblenz.de" in url or "moodle" in url or "klips" in url or "velebit" in url:
            return url
    return urls[0] if urls else None

def sync_emails_to_db():
    logger.info("Starting background email sync...")
    processed_count = 0
    skipped_count = 0
    try:
        mail = imaplib.IMAP4_SSL(os.getenv("IMAP_SERVER"), 993)
        mail.login(os.getenv("IMAP_USERNAME"), os.getenv("IMAP_PASSWORD"))
        
        ignored_uids = set()
        mail.list()
        for folder_candidate in ['"[Gmail]/Trash"', '"Trash"', '"Done"', '"Archive"']:
            try:
                res, _ = mail.select(folder_candidate)
                if res == 'OK':
                    _, data = mail.uid("search", None, "ALL")
                    if data[0]:
                        ignored_uids.update([uid.decode('utf-8') for uid in data[0].split()])
                    logger.info(f"Collected {len(ignored_uids)} UIDs to ignore from folder {folder_candidate}")
            except Exception:
                continue

        mail.select("inbox")
        status, messages = mail.uid("search", None, "ALL")
        email_uids = messages[0].split()

        if not email_uids:
            mail.logout()
            return

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT email_uid FROM university_events WHERE email_uid IS NOT NULL")
        existing_uids = {row[0] for row in cursor.fetchall()}

        available_models = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]

        for uid_bytes in email_uids:
            uid_str = uid_bytes.decode('utf-8')
            
            if uid_str in existing_uids or uid_str in ignored_uids:
                skipped_count += 1
                continue

            status, msg_data = mail.uid("fetch", uid_str, "(BODY.PEEK[HEADER] BODY.PEEK[1])")
            email_subject, email_body, email_date = "No Subject", "", ""

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    if msg["Date"]:
                        email_date = msg["Date"]
                    if msg["Subject"]:
                        subject, encoding = decode_header(msg["Subject"])[0]
                        email_subject = subject.decode(encoding if encoding else "utf-8", errors="ignore") if isinstance(subject, bytes) else subject
                    
                    payload = msg.get_payload(decode=True)
                    if payload:
                        email_body += payload.decode(errors="ignore")

            extracted_link = extract_first_link(email_body)

            prompt = f"""
            Analyze this university email. Extract academic events, exam dates, deadlines, or administrative appointments.
            Categorize into: "Exam", "Lecture", "Administrative", "Event", "Job/Internship", "Deadline", or "Other".
            
            EMAIL METADATA:
            - Email Date Header: {email_date}
            
            CRITICAL DATE INSTRUCTION: 
            - All extracted event dates or deadlines must align with the year found in the Email Date Header above (which is in 2026). Do not output years like 2024 or 2025 unless explicitly written in the text.
            - All dates and deadlines must strictly use the format "DD.MM.YYYY" (e.g., 16.11.2026). 
            - If a time is included, format as "DD.MM.YYYY HH:MM". 
            - If it is a date range, format as "DD.MM.YYYY - DD.MM.YYYY".
            
            Return ONLY a JSON object: {{"event_title": "","category": "","date": "","deadline": "","organizer": "","action_required": true/false,"summary": ""}}
            Subject: {email_subject}
            Body: {email_body[:4000]}
            """

            success = False
            for model_id in available_models:
                try:
                    completion = client.chat.completions.create(
                        model=model_id,
                        messages=[
                            {"role": "system", "content": "You are a data extraction assistant. Always output strictly valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0,
                        response_format={"type": "json_object"}
                    )
                    extracted_json = json.loads(completion.choices[0].message.content)
                    
                    insert_query = """
                    INSERT INTO university_events (event_title, category, date, deadline, organizer, action_required, summary, email_uid, email_date, email_link)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (email_uid) DO NOTHING
                    """
                    cursor.execute(insert_query, (
                        extracted_json.get("event_title", ""),
                        extracted_json.get("category", "Other"),
                        extracted_json.get("date", ""),
                        extracted_json.get("deadline", ""),
                        extracted_json.get("organizer", ""),
                        extracted_json.get("action_required", False),
                        extracted_json.get("summary", ""),
                        uid_str,
                        email_date,
                        extracted_link
                    ))
                    conn.commit()
                    processed_count += 1
                    logger.info(f"Processed and saved: {email_subject}")
                    success = True
                    break 
                except Exception as e:
                    logger.warning(f"Model {model_id} failed: {str(e)}. Trying next...")
                    continue
            
            if success:
                time.sleep(3)

        cursor.close()
        conn.close()
        mail.logout()
        logger.info(f"Background sync complete. Processed: {processed_count}, Skipped: {skipped_count}")

    except Exception as e:
        logger.error(f"System error during sync: {str(e)}")