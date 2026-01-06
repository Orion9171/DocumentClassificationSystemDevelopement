 # 本次執行快取 App 密碼 fjjm kkgm peth ymms

import shutil
from string import ascii_uppercase
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import ttk
from PIL import Image, ImageTk
import sqlite3
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import random
import speech_recognition as sr
import threading
import pyaudio
import numpy as np
import time
import difflib
import whisper
import torch
import tempfile
import platform
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import re
from collections import OrderedDict
# === 基本設定 ===
base_path = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(base_path, "uploads.db")
UPLOAD_DIR = os.path.join(base_path, "uploaded_files")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# === 初始化資料庫 ===
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
# 確保部門名稱唯一，才能用 INSERT OR IGNORE
cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_departments_name ON departments(name)')
conn.commit()

default_departments = ["人事室", "資訊室", "護理部", "藥學部", "myself"]
for dept in default_departments:
    cursor.execute("INSERT OR IGNORE INTO departments (name, email) VALUES (?, ?)", (dept, ''))
conn.commit()
conn.close()

# === 主視窗 ===
root = tk.Tk()
root.title("AI 智能助手 - 主頁")
root.geometry("1200x700")
root.configure(bg="#97CBFF")

# === 統一主題與樣式（只動外觀，不改你的功能） ===
def apply_theme(root):
    try:
        root.tk.call("tk", "scaling", 1.2)  # mac 視網膜顯示更銳利
    except tk.TclError:
        pass
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar", troughcolor="#FFFFFF")
    except tk.TclError:
        pass
    style.configure('Danger.TButton',  background='#d9534f', foreground='white')
    style.configure('Primary.TButton', background='#007ACC', foreground='white')
    style.configure('Dark.TButton',    background='#374151', foreground='white')
    style.configure('Orange.TButton',  background='#F59E0B', foreground='white')
    style.map('TButton',
          background=[('active', '#2A628F'), ('pressed', '#173B57')],
          foreground=[('disabled', '#AAAAAA')])

    BG      = "#E0E0E0"
    PANEL   = "#1E3A5F"
    FG      = "#FFFFFF"
    ENTRYBG = "#0F2F47"
    SELBG   = "#2A628F"
    PRIMARY = "#007ACC"
    SUCCESS = "#28a745"
    DANGER  = "#d9534f"

    root.configure(bg=BG)
    root.tk_setPalette(background=BG, foreground=FG,
                       activeBackground=SELBG, activeForeground=FG,
                       highlightColor=BG)

    style.configure(".", background=BG, foreground=FG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)

    # Buttons（改用 ttk.Button 以確保顏色）
    style.configure("TButton", background=PANEL, foreground=FG, padding=(10,6), borderwidth=0)
    style.map("TButton", background=[("active", SELBG), ("pressed", "#173B57")])
    style.configure("Primary.TButton", background=PRIMARY)
    style.configure("Success.TButton", background=SUCCESS)
    style.configure("Danger.TButton", background=DANGER)

    # Entry（用 ttk.Entry，避免 mac 強制白底）
    style.configure("TEntry", fieldbackground="#FFFFFF", foreground="#0F172A", insertcolor="#0F172A")

    # Listbox 選取色一致
    root.option_add("*Listbox.selectBackground", SELBG)
    root.option_add("*Listbox.selectForeground", FG)

apply_theme(root)

# === 左側：部門 Email 管理 ===
frame_left = tk.Frame(root, width=400, bg="#1E3A5F", highlightthickness=0)
frame_left.pack(side="left", fill="y")

label_email = tk.Label(frame_left, text="📬 部門 Email 管理", font=("Arial", 14, "bold"), bg="#1E3A5F", fg="white")
label_email.pack(pady=(10, 0))

# === 新增部門區塊 ===
add_dept_frame = tk.Frame(frame_left, bg="#d3d3d3", highlightthickness=0)
add_dept_frame.pack(padx=10, pady=(5, 0), fill="x")

tk.Label(add_dept_frame, text="新增部門名稱：", anchor="w", bg="#d3d3d3", width=15).grid(row=0, column=0, padx=5, pady=2, sticky="w")
new_dept_name_entry = ttk.Entry(add_dept_frame, width=30)
new_dept_name_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")

tk.Label(add_dept_frame, text="新增部門 Email：", anchor="w", bg="#d3d3d3", width=15).grid(row=1, column=0, padx=5, pady=2, sticky="w")
new_dept_email_entry = ttk.Entry(add_dept_frame, width=30)
new_dept_email_entry.grid(row=1, column=1, padx=5, pady=2, sticky="w")

def add_department():
    name = new_dept_name_entry.get().strip()
    email = new_dept_email_entry.get().strip()
    if not name or not email:
        messagebox.showwarning("欄位錯誤", "請輸入完整部門名稱與 Email")
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO departments (name, email) VALUES (?, ?)", (name, email))
    conn.commit()
    conn.close()
    new_dept_name_entry.delete(0, tk.END)
    new_dept_email_entry.delete(0, tk.END)
    load_departments()

ttk.Button(add_dept_frame, text="➕ 新增部門", command=add_department, style="Primary.TButton").grid(row=2, column=0, columnspan=2, pady=8, sticky="we")

# === Email 顯示區塊（Canvas 寬度同步） ===
email_section_frame = tk.Frame(frame_left, bg="#d3d3d3", highlightthickness=0)
email_section_frame.pack(padx=10, pady=10, fill="both", expand=True)

canvas = tk.Canvas(email_section_frame, bg="#d3d3d3", highlightthickness=0)
scrollbar = ttk.Scrollbar(email_section_frame, orient="vertical", command=canvas.yview)
scrollable_frame = tk.Frame(canvas, bg="#D0D0D0", highlightthickness=0)
scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)
canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

def _resize_inner(event):
    try:
        canvas.itemconfig(window_id, width=event.width - scrollbar.winfo_width())
    except tk.TclError:
        canvas.itemconfig(window_id, width=event.width - 12)
canvas.bind("<Configure>", _resize_inner)

email_entries = {}
btn_save_emails = ttk.Button(frame_left, text="💾 儲存 Email", style="Success.TButton")
btn_save_emails.pack(pady=5, fill="x")

# === 語音上傳 ===
def start_voice_upload_interface():
    voice_window = tk.Toplevel()
    voice_window.title("🎙 語音上傳檔案")
    voice_window.geometry("400x300")
    voice_window.configure(bg="#1E3A5F")

    tk.Label(voice_window, text="請說出檔案名稱（中或英皆可），系統將自動搜尋本機檔案", font=("Arial", 11),
             bg="#1E3A5F", fg="white", wraplength=380).pack(pady=10)

    vu = tk.Canvas(voice_window, width=300, height=100, bg="#FFFFFF", highlightthickness=0)
    vu.pack(pady=20)
    bars = [vu.create_rectangle(i * 10, 100, i * 10 + 8, 100, fill="#80BEF5") for i in range(30)]

    def animate_bars(volume):
        for i, bar in enumerate(bars):
            height = max(100 - volume * (i % 5), 60)
            vu.coords(bar, i * 10, height, i * 10 + 8, 100)

    def normalize_extension(text):
        ext_map = {
            "點P D F": ".pdf", "點PDF": ".pdf", "PDF": ".pdf",
            "點D O C X": ".docx", "DOCX": ".docx",
            "點T X T": ".txt", "TXT": ".txt",
            "點P P T X": ".pptx", "PPTX": ".pptx"
        }
        for key, val in ext_map.items():
            if key.lower().replace(" ", "") in text.lower().replace(" ", ""):
                return val
        return ""

    def convert_chinese_numerals(text):
        cn_nums = {'零':'0','一':'1','二':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','〇':'0','壹':'1','貳':'2','參':'3'}
        for cn, num in cn_nums.items():
            text = text.replace(cn, num)
        return text

    def process_voice():
        model = whisper.load_model("base")
        recognizer = sr.Recognizer()
        mic = sr.Microphone()
        stop_flag = threading.Event()

        def visualize_volume():
            stream = mic.stream
            while not stop_flag.is_set():
                try:
                    data = stream.read(1024, exception_on_overflow=False)
                    audio_data = np.frombuffer(data, np.int16)
                    volume = min(int(np.linalg.norm(audio_data) / 100), 30)
                    animate_bars(volume)
                    vu.update()
                except:
                    pass

        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            volume_thread = threading.Thread(target=visualize_volume)
            volume_thread.start()

            try:
                audio = recognizer.listen(source, timeout=6)
                stop_flag.set()
                volume_thread.join()

                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                    wav_path = f.name
                    with open(wav_path, "wb") as wav_file:
                        wav_file.write(audio.get_wav_data())

                result = model.transcribe(wav_path, fp16=torch.cuda.is_available())
                os.remove(wav_path)

                keyword_raw = result["text"].strip()
                print(f"[Whisper辨識結果]：{keyword_raw}")

                cleaned = keyword_raw.replace("點", ".").replace("dot", ".").replace(" ", "").strip()
                cleaned = convert_chinese_numerals(cleaned.lower())

                ext = normalize_extension(cleaned)
                if ext:
                    keyword = cleaned.replace(ext, "")
                    possible_exts = [ext]
                elif '.' in cleaned:
                    keyword, ext = os.path.splitext(cleaned)
                    possible_exts = [ext]
                else:
                    keyword = cleaned
                    possible_exts = [".pdf", ".docx", ".txt", ".pptx"]

                print(f"[搜尋關鍵字]：{keyword}, 副檔名：{possible_exts}")

                # 跨平台搜尋目錄
                search_dirs = []
                system = platform.system().lower()
                home = os.path.expanduser("~")
                for sub in ("Desktop", "Documents"):
                    p = os.path.join(home, sub)
                    if os.path.exists(p):
                        search_dirs.append(p)
                if system == "windows":
                    search_dirs.extend([f"{d}:/" for d in ascii_uppercase if os.path.exists(f"{d}:/")])
                    user_profile = os.environ.get("USERPROFILE", "")
                    if user_profile:
                        desktop_path = os.path.join(user_profile, "Desktop")
                        documents_path = os.path.join(user_profile, "Documents")
                        search_dirs.extend([desktop_path, documents_path])
                else:
                    volumes = "/Volumes"
                    if os.path.isdir(volumes):
                        for name in os.listdir(volumes):
                            vp = os.path.join(volumes, name)
                            if os.path.isdir(vp):
                                search_dirs.append(vp)

                if os.path.exists(UPLOAD_DIR):
                    search_dirs.insert(0, UPLOAD_DIR)

                def find_file_recursive(keyword, base_dirs, exts):
                    for base in base_dirs:
                        try:
                            for root_, dirs_, files_ in os.walk(base):
                                for f in files_:
                                    fname_no_ext, fext = os.path.splitext(f)
                                    if fext.lower() in [e.lower() for e in exts] and keyword in fname_no_ext.lower():
                                        return os.path.join(root_, f)
                        except Exception:
                            continue
                    return None

                found_path = find_file_recursive(keyword, search_dirs, possible_exts)

                if found_path:
                    os.makedirs(UPLOAD_DIR, exist_ok=True)
                    filename = os.path.basename(found_path)
                    dest_path = os.path.join(UPLOAD_DIR, filename)
                    shutil.copy2(found_path, dest_path)

                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO uploads (filename, filepath) VALUES (?, ?)", (filename, dest_path))
                    conn.commit()
                    conn.close()

                    load_records()
                    messagebox.showinfo("上傳成功", f"已找到並上傳檔案：{filename}")
                else:
                    messagebox.showwarning("找不到檔案", f"辨識為「{keyword_raw}」，但找不到符合檔案")

            except sr.UnknownValueError:
                messagebox.showerror("辨識失敗", "無法辨識您說的話")
            except sr.WaitTimeoutError:
                messagebox.showerror("逾時", "請更快開始說話")
            except Exception as e:
                messagebox.showerror("錯誤", f"發生錯誤：{e}")
            finally:
                voice_window.destroy()

    threading.Thread(target=process_voice, daemon=True).start()

# === 中間區域：logo + 上傳紀錄 ===
frame_center = tk.Frame(root, bg="#00CACA", highlightthickness=0)
frame_center.pack(side="right", expand=True, fill="both")

try:
    logo_path = os.path.join(base_path, "img", "logo.png")
    logo_img = Image.open(logo_path).resize((120, 120))
    logo_photo = ImageTk.PhotoImage(logo_img)
    label_logo = tk.Label(frame_center, image=logo_photo, bg="#00CACA")
    label_logo.image = logo_photo
    label_logo.pack()
except:
    print("Logo 載入失敗")

label_text = tk.Label(
    frame_center,
    text="您好，我是您的 AI 智能助理\n請選擇您要上傳的檔案並由我分發給不同科室...",
    font=("Arial", 12), bg="#00CACA", fg="white"
)
label_text.pack(pady=10)

label_history = tk.Label(frame_center, text="📄 上傳紀錄", font=("Arial", 14, "bold"), bg="#103545", fg="white")
label_history.pack(pady=(10, 0))

record_frame = tk.Frame(frame_center, bg="#FFFFFF", highlightthickness=0)
record_frame.pack(padx=10, pady=5, fill="both", expand=True)

listbox_records = tk.Listbox(record_frame, width=50, height=10,
    bg="#FFFFFF", fg="#0F172A",
    selectbackground="#2A628F",
    selectforeground="#FFFFFF",
    highlightthickness=0, relief=tk.FLAT)
listbox_records.pack(side="left", fill="both", expand=True)
record_scroll = ttk.Scrollbar(record_frame, orient="vertical", command=listbox_records.yview)
record_scroll.pack(side="right", fill="y")
listbox_records.configure(yscrollcommand=record_scroll.set)

def load_records():
    listbox_records.delete(0, tk.END)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM uploads ORDER BY id DESC")
    records = cursor.fetchall()
    conn.close()
    for record in records:
        listbox_records.insert(tk.END, record[0])
load_records()

def delete_selected():
    selected_index = listbox_records.curselection()
    if not selected_index:
        messagebox.showwarning("提醒", "請選擇要刪除的檔案")
        return
    # 支援多選刪除
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    deleted = []
    for idx in selected_index:
        selected_filename = listbox_records.get(idx)
        cursor.execute("SELECT filepath FROM uploads WHERE filename = ?", (selected_filename,))
        record = cursor.fetchone()
        if record:
            try:
                os.remove(record[0])
            except Exception:
                pass
            cursor.execute("DELETE FROM uploads WHERE filename = ?", (selected_filename,))
            deleted.append(selected_filename)
    conn.commit()
    conn.close()
    load_records()
    if deleted:
        messagebox.showinfo("成功", f"已刪除：\n" + "\n".join(deleted))

def upload_file():
    path = filedialog.askopenfilename(title="選擇檔案")
    if not path:
        return
    name = os.path.basename(path)
    dest = os.path.join(UPLOAD_DIR, name)
    with open(path, "rb") as src, open(dest, "wb") as d:
        d.write(src.read())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO uploads (filename, filepath) VALUES (?, ?)", (name, dest))
    conn.commit()
    conn.close()
    load_records()
    messagebox.showinfo("成功", f"{name} 上傳成功！")
    
# ==== 自訂「寄件人憑證」對話框（含 OK/取消） ====
class CredentialsDialog(tk.Toplevel):
    def __init__(self, parent, default_user=""):
        super().__init__(parent)
        self.title("寄件人憑證")
        self.configure(bg="#1E3A5F")
        self.resizable(False, False)
        self.result = None
        self.grab_set()   # 變成 modal
        self.transient(parent)

        tk.Label(self, text="寄件人 Gmail：", bg="#1E3A5F", fg="white").grid(row=0, column=0, padx=12, pady=(12,6), sticky="e")
        tk.Label(self, text="應用程式密碼：", bg="#1E3A5F", fg="white").grid(row=1, column=0, padx=12, pady=6, sticky="e")

        self.var_email = tk.StringVar(value=default_user)
        self.var_app   = tk.StringVar()

        e1 = ttk.Entry(self, width=32, textvariable=self.var_email)
        e2 = ttk.Entry(self, width=32, textvariable=self.var_app, show="*")
        e1.grid(row=0, column=1, padx=12, pady=(12,6))
        e2.grid(row=1, column=1, padx=12, pady=6)

        btns = tk.Frame(self, bg="#1E3A5F")
        btns.grid(row=2, column=0, columnspan=2, pady=12)
        ttk.Button(btns, text="取消", style="Danger.TButton", command=self.on_cancel).pack(side="left", padx=6)
        ttk.Button(btns, text="OK",   style="Success.TButton", command=self.on_ok).pack(side="left", padx=6)

        self.bind("<Return>", lambda _: self.on_ok())
        self.bind("<Escape>", lambda _: self.on_cancel())

        # 置中
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        e1.focus_set()

    def on_ok(self):
        email = self.var_email.get().strip()
        app   = (self.var_app.get() or "").replace(" ", "")
        if not email or not app:
            messagebox.showwarning("欄位不完整", "請輸入寄件人 Gmail 與應用程式密碼。", parent=self)
            return
        self.result = (email, app)
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()

def ask_credentials(default_user=""):
    dlg = CredentialsDialog(root, default_user=default_user)
    root.wait_window(dlg)
    return dlg.result  # (email, app_password) 或 None（取消）

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
_SMTP_USER = None   # 本次執行快取寄件 Gmail（不落地）
_SMTP_PASS = None   # 本次執行快取 App 密碼（不落地）

def open_smtp(default_user=""):
    global _SMTP_USER, _SMTP_PASS
    if not _SMTP_USER or not _SMTP_PASS:
        creds = ask_credentials(default_user)
        if not creds:     # 使用者按了取消
            return None
        _SMTP_USER, _SMTP_PASS = creds

    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
    server.ehlo()
    server.starttls()
    server.login(_SMTP_USER, _SMTP_PASS)
    return server

def send_one(server, to_email, subject, body, attachment_path=None):
    msg = MIMEMultipart()
    msg["From"] = _SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
        msg.attach(part)
    server.send_message(msg)

def get_dept_email(name: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email FROM departments WHERE name=?", (name,))
    row = c.fetchone()
    conn.close()
    return (row[0] or "").strip() if row else ""
        
MAX_MAIL_BYTES = 15 * 1024 * 1024

def parse_recipients(raw: str):
    """支援逗號、分號、空白、換行、頓號分隔；自動過濾空字串。"""
    if not raw:
        return []
    parts = re.split(r'[;,\s、]+', str(raw))
    return [p.strip() for p in parts if p.strip() and '@' in p]

def group_by_department(classified_rows):
    """
    classified_rows: [(fname, dept_name, dept_email, score), ...]
    回傳 OrderedDict key=(dept_name, dept_email) -> [(fname, score), ...]
    """
    groups = OrderedDict()
    for fname, dname, email, score in classified_rows:
        groups.setdefault((dname, email), []).append((fname, score))
    return groups

def split_by_total_size(file_list, path_map, max_bytes=MAX_MAIL_BYTES):
    """
    同一部門的多附件依總大小切批。
    file_list: [(fname, score), ...]
    path_map:  {fname: filepath}
    回傳: [[(fname, score), ...], ...]
    """
    batches, cur, cur_size = [], [], 0
    for fname, score in file_list:
        fpath = path_map.get(fname)
        if not fpath or not os.path.exists(fpath):
            continue
        size = os.path.getsize(fpath)
        if size > max_bytes:
            # 太大的單檔獨立一封（照樣寄）
            batches.append([(fname, score)])
            continue
        if cur_size + size > max_bytes and cur:
            batches.append(cur)
            cur, cur_size = [], 0
        cur.append((fname, score))
        cur_size += size
    if cur:
        batches.append(cur)
    return batches

def send_multi(server, recipients, dept_name, files_chunk, path_map):
    """
    recipients: ["a@x", "b@y"]
    files_chunk: [(fname, score), ...]
    """
    subject = f"[AI 公文分發] {dept_name}（{len(files_chunk)} 檔）"
    lines = [f"部門：{dept_name}", "附件："]
    lines += [f"• {fname}" for fname, _ in files_chunk]
    body = "\n".join(lines)

    msg = MIMEMultipart()
    msg["From"] = _SMTP_USER
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for fname, _ in files_chunk:
        fpath = path_map.get(fname)
        if not fpath or not os.path.exists(fpath):
            continue
        with open(fpath, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(fpath)}")
        msg.attach(part)

    server.send_message(msg)
    
def classify_and_send():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT filename, filepath FROM uploads ORDER BY id DESC")
    files = cursor.fetchall()
    cursor.execute("SELECT id, name, email FROM departments")
    departments = cursor.fetchall()
    path_map = {fn: fp for fn, fp in files}
    conn.close()
    
    if not files:
        messagebox.showwarning("提醒", "目前無上傳紀錄可分類")
        return

    classified = []
    for fname, path in files:
        dept = random.choice(departments)
        confidence = round(random.uniform(0.5, 0.99), 2)
        classified.append((fname, dept[1], dept[2] or "未設定", confidence))

    win = tk.Toplevel(root)
    win.title("分類結果確認")
    win.configure(bg="#103545")

    tk.Label(win, text="檔名", font=("Arial", 10, "bold"), width=30, bg="#103545", fg="white").grid(row=0, column=0)
    tk.Label(win, text="部門名稱", font=("Arial", 10, "bold"), width=20, bg="#103545", fg="white").grid(row=0, column=1)
    tk.Label(win, text="部門 Email", font=("Arial", 10, "bold"), width=30, bg="#103545", fg="white").grid(row=0, column=2)
    tk.Label(win, text="信任分數", font=("Arial", 10, "bold"), width=15, bg="#103545", fg="white").grid(row=0, column=3)

    for i, (fname, dname, email, score) in enumerate(classified, 1):
        tk.Label(win, text=fname, width=30, anchor="w", bg="#103545", fg="white").grid(row=i, column=0, sticky="w")
        tk.Label(win, text=dname, width=20, anchor="w", bg="#103545", fg="white").grid(row=i, column=1, sticky="w")
        tk.Label(win, text=email, width=30, anchor="w", bg="#103545", fg="white").grid(row=i, column=2, sticky="w")
        tk.Label(win, text=f"{score*100:.1f}%", width=15, anchor="w", bg="#103545", fg="white").grid(row=i, column=3, sticky="w")
        
    def confirm():
        # 依部門把檔案分組（用你前面提供的工具函式）
        groups = group_by_department(classified)

        # 啟 SMTP（會跳出一次寄件人 Gmail 與 App 密碼；之後本次快取）
        try:
            server = open_smtp()  # ← 不再預填 myself
            if server is None:
                messagebox.showinfo("已取消", "你已取消寄送。")
                return
        except Exception as e:
            messagebox.showerror("SMTP 連線失敗", str(e))
            return
        sent = 0
        failed = []
        missing = []   # 沒填 email 的部門

        for (dept_name, dept_email), file_list in groups.items():
            # 解析多收件人；沒填就略過
            recipients = parse_recipients(dept_email)
            if not recipients:
                missing.append(dept_name)
                continue
            # 多附件依總大小切批（避免超過郵件大小限制）
            batches = split_by_total_size(file_list, path_map)
            if not batches:
                failed.append(f"{dept_name}（無可用附件）")
                continue

            for chunk in batches:
                try:
                    send_multi(server, recipients, dept_name, chunk, path_map)
                    sent += 1
                except Exception as e:
                    names = [f for f, _ in chunk]
                    failed.append(f"{dept_name}：{names}（{e}）")
        try:
            server.quit()
        except:
            pass
        # 回饋結果
        lines = [f"✅ 成功寄出 {sent} 封"]
        if missing:
            lines.append("❗ 未設定 Email（已略過）： " + "、".join(missing))
        if failed:
            lines.append("⚠️ 失敗：")
            lines += [f"• {x}" for x in failed]
        messagebox.showinfo("寄送結果", "\n".join(lines))
        win.destroy()
    ttk.Button(win, text="✅ 確認並發送", command=confirm, style="Success.TButton").grid(row=i+1, column=0, columnspan=4, pady=10, sticky="we")

# === 右側按鈕列（背景與右半一致 #00CACA） ===
button_frame = tk.Frame(frame_center, bg="#00CACA", highlightthickness=0)
button_frame.pack(pady=10)

ttk.Button(button_frame, text="🗑 刪除選擇", command=delete_selected, style="Danger.TButton").grid(row=0, column=0, padx=10)
ttk.Button(button_frame, text="🤖 分類並發送", command=classify_and_send, style="Primary.TButton").grid(row=0, column=1, padx=10)
ttk.Button(button_frame, text="📂 選擇文件上傳", command=upload_file, style="Dark.TButton").grid(row=0, column=2, padx=10)
ttk.Button(button_frame, text="🎤 語音上傳", command=start_voice_upload_interface, style="Orange.TButton").grid(row=0, column=3, padx=10)

# === Email 函數區（載入/儲存/刪除部門） ===
def load_departments():
    for widget in scrollable_frame.winfo_children():
        widget.destroy()
    email_entries.clear()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM departments ORDER BY name")
    departments = cursor.fetchall()
    conn.close()

    for i, (dept_id, name, email) in enumerate(departments):
        tk.Label(scrollable_frame, text=name, bg="#1E3A5F", fg="white",
                 width=18, anchor="w").grid(row=i, column=0, padx=5, pady=2, sticky="w")

        entry = ttk.Entry(scrollable_frame, width=30)
        entry.insert(0, email)
        entry.grid(row=i, column=1, padx=5, pady=2, sticky="we")
        email_entries[dept_id] = entry

        def make_delete_callback(dept_id, dept_name):
            def delete_department():
                if dept_name == "myself":
                    messagebox.showwarning("禁止刪除", "測試用『myself』不可刪除。")
                    return
                if messagebox.askyesno("確認刪除", f"是否刪除部門「{dept_name}」？"):
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
                    conn.commit()
                    conn.close()
                    load_departments()
            return delete_department

        ttk.Button(scrollable_frame, text="🗑", width=4,
                   command=make_delete_callback(dept_id, name),
                   style="Danger.TButton").grid(row=i, column=2, padx=5, pady=2, sticky="e")

    scrollable_frame.grid_columnconfigure(1, weight=1)

def save_department_emails():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for dept_id, entry in email_entries.items():
        cursor.execute("UPDATE departments SET email = ? WHERE id = ?", (entry.get().strip(), dept_id))
    conn.commit()
    conn.close()
    messagebox.showinfo("成功", "部門 Email 已儲存")

btn_save_emails.configure(command=save_department_emails)


# === Email 寄送（只寄給自己：收件人讀左側 myself；寄件人當場詢問一次） ===
def send_all_to_self():
    # 收件人 = 左側 departments 中的 "myself"
    my_email = get_dept_email("myself")
    if not my_email or "@" not in my_email:
        messagebox.showerror("錯誤", "找不到『myself』部門的 Email，請先在左側設定並按「💾 儲存 Email」。")
        return

    # 要寄的檔案：若有選取只寄選取；否則寄全部
    files = []
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    sel = listbox_records.curselection()
    if sel:
        for idx in sel:
            fname = listbox_records.get(idx)
            cursor.execute("SELECT filepath FROM uploads WHERE filename=?", (fname,))
            row = cursor.fetchone()
            if row and os.path.exists(row[0]):
                files.append((fname, row[0]))
    else:
        cursor.execute("SELECT filename, filepath FROM uploads ORDER BY id DESC")
        for fname, fpath in cursor.fetchall():
            if os.path.exists(fpath):
                files.append((fname, fpath))
    conn.close()

    if not files:
        messagebox.showwarning("提醒", "目前沒有可寄送的檔案。")
        return

    try:
        server = open_smtp(default_user=my_email)
        if server is None:
            messagebox.showinfo("已取消", "你已取消寄送。")
            return
    except Exception as e:
        messagebox.showerror("SMTP 連線失敗", str(e))
        return

    sent, failed = 0, []
    for fname, fpath in files:
        subject = f"[測試寄送] {fname}"
        body = f"這是測試寄送（收件人使用左側『myself』Email）。\n附件：{fname}\n（系統自動寄出）"
        try:
            send_one(server, my_email, subject, body, fpath)
            sent += 1
        except Exception as e:
            failed.append(f"{fname}（{e}）")

    try:
        server.quit()
    except:
        pass

    summary = [f"✅ 已寄到『myself』：{sent} 封"]
    if failed:
        summary.append("⚠️ 失敗：")
        summary += [f"• {x}" for x in failed]
    messagebox.showinfo("測試寄信結果", "\n".join(summary))
ttk.Button(button_frame, text="📧 寄給自己（測試）", command=send_all_to_self, style="Success.TButton").grid(row=0, column=4, padx=10)

# 啟動
load_departments()
root.mainloop()
