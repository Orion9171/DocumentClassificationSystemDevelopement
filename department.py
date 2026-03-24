import sqlite3
import os
import utils as utl
base_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_path, "config.json")
config_data = utl.load_config(config_path)
db_path = config_data['db_path']


DB_PATH = os.path.join(base_path, db_path)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT
        )
    ''')
    # Ensure that department names are unique in order to use INSERT OR IGNORE
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_departments_name ON departments(name)')
    conn.commit()

    default_departments = ["人事室", "資訊室", "護理部", "藥學部", "myself"]
    for dept in default_departments:
        cursor.execute("INSERT OR IGNORE INTO departments (name, email) VALUES (?, ?)", (dept, ''))
    conn.commit()
    conn.close()

def insert_department(name, email):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO departments (name, email) VALUES (?, ?)", (name, email))
    conn.commit()
    conn.close()

def get_departments():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM departments ORDER BY name")
    departments = cursor.fetchall()
    conn.close()
    return departments

def delete_department(dept_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
    conn.commit()
    conn.close()

def update_department_emails(email_entries):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for dept_id, entry in email_entries.items():
        cursor.execute("UPDATE departments SET email = ? WHERE id = ?", (entry.get().strip(), dept_id))
    conn.commit()
    conn.close()
