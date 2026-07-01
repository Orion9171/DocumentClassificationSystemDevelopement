import sqlite3
import os
import utils as utl
base_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_path, "config.json")
config_data = utl.load_config(config_path)
db_path = config_data['db_path']
DB_PATH = os.path.join(base_path, db_path)


def init_documents_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
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
    ''')
    conn.commit()
    conn.close()

def get_documents():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, di_filename, pdf_filename, folder_path, instruction, created_at, processed_at, department, confidence, email, email_sent FROM documents ORDER BY id DESC")
    documents = cursor.fetchall()
    conn.close()
    return documents

def get_document_by_filter(status = "All", department=None, created_date=None, classified_date=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = "SELECT id, di_filename, pdf_filename, folder_path, instruction, created_at, processed_at, department, confidence, email, email_sent FROM documents WHERE 1=1"
    params = []

    if status == "Not Classified":
        query += " AND department IS NULL"
    elif status == "Not Emailed":
        query += " AND email_sent = 0 AND email IS NOT NULL"
    
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
    
    cursor.execute(query, params)
    documents = cursor.fetchall()
    conn.close()
    return documents

def insert_document(di_filename, pdf_filename, folder_path, instruction):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO documents (di_filename, pdf_filename, folder_path, instruction, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)", (di_filename, pdf_filename, folder_path, instruction))
    conn.commit()
    conn.close()

def process_document(document_id, department, confidence):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET processed_at = CURRENT_TIMESTAMP, department = ?, confidence = ? WHERE id = ?", (department, confidence, document_id))
    conn.commit()
    conn.close()

def delete_document(document_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))
    conn.commit()
    conn.close()


def get_documents_for_classification():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, di_filename, pdf_filename, folder_path, instruction FROM documents where department IS NULL ORDER BY id DESC")
    documents = cursor.fetchall()
    conn.close()
    return documents

def update_classification(document_id, department, confidence, email):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET department = ?, confidence = ?, processed_at = CURRENT_TIMESTAMP, email = ?, email_sent = 0  WHERE id = ?", (department, confidence, email, document_id))
    conn.commit()
    conn.close()

def get_documents_for_email():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, di_filename, pdf_filename, folder_path, instruction, department, confidence, email FROM documents where email_sent = 0 AND email IS NOT NULL ORDER BY id DESC")
    documents = cursor.fetchall()
    conn.close()
    return documents

def mark_email_sent(document_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET email_sent = 1 WHERE id = ?", (document_id,))
    conn.commit()
    conn.close()