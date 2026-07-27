import os
import sqlite3

import utils as utl


base_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_path, "config.json")
config_data = utl.load_config(config_path)
db_path = config_data["db_path"]
DB_PATH = os.path.join(base_path, db_path)


DOCUMENT_COLUMNS = (
    "id, di_filename, pdf_filename, folder_path, instruction, "
    "created_at, processed_at, department, confidence, email, email_sent"
)


def _connect():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_documents_table():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                di_filename TEXT NOT NULL,
                pdf_filename TEXT NOT NULL,
                folder_path TEXT NOT NULL,
                instruction TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                department TEXT,
                confidence REAL,
                email TEXT,
                email_sent BOOLEAN DEFAULT 0
            )
            """
        )


def get_documents():
    with _connect() as conn:
        return conn.execute(
            f"SELECT {DOCUMENT_COLUMNS} FROM documents ORDER BY id DESC"
        ).fetchall()


def get_document_by_filter(
    status="All",
    department=None,
    created_date=None,
    classified_date=None,
):
    query = f"SELECT {DOCUMENT_COLUMNS} FROM documents WHERE 1=1"
    params = []

    if status == "Not Classified":
        query += " AND department IS NULL"
    elif status == "Not Emailed":
        query += (
            " AND email_sent = 0"
            " AND department IS NOT NULL"
            " AND TRIM(COALESCE(email, '')) <> ''"
        )

    if department:
        query += " AND department = ?"
        params.append(department)

    if created_date:
        query += " AND DATE(created_at) = ?"
        params.append(created_date)

    if classified_date:
        query += " AND DATE(processed_at) = ?"
        params.append(classified_date)

    query += " ORDER BY id DESC"

    with _connect() as conn:
        return conn.execute(query, params).fetchall()


def insert_document(di_filename, pdf_filename, folder_path, instruction):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO documents
                (di_filename, pdf_filename, folder_path, instruction, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (di_filename, pdf_filename, folder_path, instruction),
        )


def process_document(document_id, department, confidence):
    with _connect() as conn:
        conn.execute(
            """
            UPDATE documents
            SET processed_at = CURRENT_TIMESTAMP,
                department = ?,
                confidence = ?
            WHERE id = ?
            """,
            (department, confidence, document_id),
        )


def delete_document(document_id):
    with _connect() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def get_documents_for_classification():
    with _connect() as conn:
        return conn.execute(
            """
            SELECT id, di_filename, pdf_filename, folder_path, instruction
            FROM documents
            WHERE department IS NULL
            ORDER BY id DESC
            """
        ).fetchall()


def update_classification(document_id, department, confidence, email):
    with _connect() as conn:
        conn.execute(
            """
            UPDATE documents
            SET department = ?,
                confidence = ?,
                processed_at = CURRENT_TIMESTAMP,
                email = ?,
                email_sent = 0
            WHERE id = ?
            """,
            (department, confidence, email, document_id),
        )


def get_documents_for_email():
    """
    Return classified documents that have not yet been emailed.

    Tuple order:
    id, di_filename, pdf_filename, folder_path, instruction,
    department, confidence, email, email_sent
    """
    with _connect() as conn:
        return conn.execute(
            """
            SELECT
                id,
                di_filename,
                pdf_filename,
                folder_path,
                instruction,
                department,
                confidence,
                email,
                email_sent
            FROM documents
            WHERE email_sent = 0
              AND department IS NOT NULL
            ORDER BY id DESC
            """
        ).fetchall()


def get_document_for_email(document_id):
    with _connect() as conn:
        return conn.execute(
            """
            SELECT
                id,
                di_filename,
                pdf_filename,
                folder_path,
                instruction,
                department,
                confidence,
                email,
                email_sent
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()


def update_document_email(document_id, email):
    normalized_email = (email or "").strip()
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE documents SET email = ? WHERE id = ?",
            (normalized_email, document_id),
        )
        return cursor.rowcount > 0


def mark_email_sent(document_id):
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE documents SET email_sent = 1 WHERE id = ?",
            (document_id,),
        )
        return cursor.rowcount > 0


def mark_email_not_sent(document_id):
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE documents SET email_sent = 0 WHERE id = ?",
            (document_id,),
        )
        return cursor.rowcount > 0
