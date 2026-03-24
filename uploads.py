import sqlite3
import os
import utils as utl
base_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_path, "config.json")
config_data = utl.load_config(config_path)
db_path = config_data['db_path']
DB_PATH = os.path.join(base_path, db_path)

def get_uploads():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, filename, filepath FROM uploads ORDER BY id DESC")
    uploads = cursor.fetchall()
    conn.close()
    return uploads

def insert_upload(filename, filepath):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO uploads (filename, filepath) VALUES (?, ?)", (filename, filepath))
    conn.commit()
    conn.close()

def delete_upload(upload_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
    conn.commit()
    conn.close()