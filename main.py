# 本次執行快取 App 密碼 fjjm kkgm peth ymms


import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from matplotlib import style
from tkcalendar import DateEntry 
from PIL import Image, ImageTk
import sqlite3
import os
import threading
import queue
import traceback

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
import random

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import re
from collections import OrderedDict


import department as dpt
import documents as doc
import uploads as upl
import utils as utl
import doc_crawler as crawler   
# === BASE Settings ===
base_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_path, "config.json")

config_data = utl.load_config(config_path)
SMTP_HOST = config_data['smtp_host']
SMTP_PORT = config_data['smtp_port']
_SMTP_USER = config_data['smtp_user']
_SMTP_PASS = config_data['smtp_pass']
_SENDER_EMAIL = config_data['sender_email']
db_path = config_data['db_path']
upload_dir = config_data['upload_dir']

MAX_MAIL_BYTES = 15 * 1024 * 1024

DB_PATH = os.path.join(base_path, db_path)
UPLOAD_DIR = os.path.join(base_path, upload_dir)
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)


# === INIT DATABASE ===
dpt.init_db()
doc.init_documents_table()

# === Global Variables ===
email_entries = {}
uploaded_files = []

# Background worker communication
ui_queue = queue.Queue()
classification_running = False

#region UI

# === define colors ===

BG      = "#E0E0E0"
PANEL   = "#1E3A5F"
FG      = "#FFFFFF"
ENTRYBG = "#0F2F47"
SELBG   = "#2A628F"
PRIMARY = "#007ACC"
SUCCESS = "#28a745"
DANGER  = "#d9534f"
WARNING = "#F59E0B"
DARK = "#374151"
BTN_ACTIVE = "#2A628F"
BTN_PRESSED = "#173B57"

# === INIT MAIN WINDOW ===
root = tk.Tk()
root.title("AI 智能助手 - 主頁")
root.geometry("1200x700")
root.configure(bg="#97CBFF")

# === Unify theme and style (only change appearance, not functionality) ===
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
    style.configure('Danger.TButton',  background=DANGER, foreground='white')
    style.configure('Primary.TButton', background=PRIMARY, foreground='white')
    style.configure('Dark.TButton',    background=DARK, foreground='white')
    style.configure('Orange.TButton',  background=WARNING, foreground='white')
    style.map('TButton',
          background=[('active', BTN_ACTIVE), ('pressed', BTN_PRESSED)],
          foreground=[('disabled', '#AAAAAA')])

    root.configure(bg=BG)
    root.tk_setPalette(background=BG, foreground=FG,
                       activeBackground=SELBG, activeForeground=FG,
                       highlightColor=BG)

    style.configure(".", background=BG, foreground=FG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)

    # Buttons（改用 ttk.Button 以確保顏色）
    style.configure("TButton", background=PANEL, foreground=FG, padding=(10,6), borderwidth=0)
    style.map("TButton", background=[("active", BTN_ACTIVE), ("pressed", "#173B57")])
    style.configure("Primary.TButton", background=PRIMARY)
    style.configure("Success.TButton", background=SUCCESS)
    style.configure("Danger.TButton", background=DANGER)

    # Entry（用 ttk.Entry，避免 mac 強制白底）
    style.configure("TEntry", fieldbackground="#FFFFFF", foreground="#0F172A", insertcolor="#0F172A")

    # COmbobox（用 ttk.Combobox，避免 mac 強制白底）
    style.configure("TCombobox", foreground="#0F172A", fieldbackground="white")

    # Treeview（表格）
    style.configure("Treeview", background=FG, foreground=SELBG, fieldbackground=FG)
    style.configure("Treeview.Heading", 
                foreground=SELBG,          
                background=BG,        
                font=('Helvetica', 10, 'bold')) # Optional: Makes text bold
    

# === Left side: Department Email Management ===
frame_left = tk.Frame(root, width=400, bg="#1E3A5F", highlightthickness=0)
frame_left.pack(side="left", fill="y")

label_email = tk.Label(frame_left, text="📬 部門 Email 管理", font=("Arial", 14, "bold"), bg="#1E3A5F", fg="white")
label_email.pack(pady=(10, 0))

# === New department blocks ===
add_dept_frame = tk.Frame(frame_left, bg="#d3d3d3", highlightthickness=0)
add_dept_frame.pack(padx=10, pady=(5, 0), fill="x")

tk.Label(add_dept_frame, text="新增部門名稱：", anchor="w", bg="#d3d3d3", width=15).grid(row=0, column=0, padx=5, pady=2, sticky="w")
new_dept_name_entry = ttk.Entry(add_dept_frame, width=30, foreground="#0F172A")
new_dept_name_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")

tk.Label(add_dept_frame, text="新增部門 Email：", anchor="w", bg="#d3d3d3", width=15).grid(row=1, column=0, padx=5, pady=2, sticky="w")
new_dept_email_entry = ttk.Entry(add_dept_frame, width=30, foreground="#0F172A")
new_dept_email_entry.grid(row=1, column=1, padx=5, pady=2, sticky="w")


ttk.Button(add_dept_frame, text="➕ 新增部門", command=lambda: add_department(), style="Primary.TButton").grid(row=2, column=0, columnspan=2, pady=8, sticky="we")

# === Email display block (Canvas width synchronized) ===
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


btn_save_emails = ttk.Button(frame_left, text="💾 儲存 Email", style="Success.TButton")
btn_save_emails.pack(pady=5, fill="x")

# === Middle area: logo + upload history ===
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

frame_filters = tk.Frame(frame_center, bg=PRIMARY, highlightthickness=0)
frame_filters.pack(padx=10, pady=5, fill="x", expand=True)

optionStatus = ["All", "Not Classified", "Not Emailed"]
tk.Label(frame_filters, text="Status", anchor="w", bg=PRIMARY, width=15).grid(row=0, column=0, padx=5, pady=2, sticky="w")
status_entry = ttk.Combobox(frame_filters, values=optionStatus, width=28, foreground="#0F172A")
status_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
status_entry.current(0)  # Set the default value


departmentList = dpt.get_departments()
departmentList.insert(0, (0, "All", ""))  # Add "All" option at the beginning
departmentNames = [name for _, name, _ in departmentList]
tk.Label(frame_filters, text="Department", anchor="w", bg=PRIMARY, width=20).grid(row=0, column=3, padx=5, pady=2, sticky="w")
dept_entry = ttk.Combobox(frame_filters, values=departmentNames, width=28, foreground="#0F172A")
dept_entry.grid(row=0, column=4, padx=5, pady=2, sticky="w")
dept_entry.current(0)  # Set the default value


def clear_control(widget):
    """
    A generic function to clear various Tkinter controls.
    Supports: DateEntry, Entry, and Combobox.
    """
    if isinstance(widget, ttk.Combobox):
        widget.set('')  # Clears a dropdown selection completely
    else:
        widget.delete(0, "end")  # Clears DateEntry and standard Entry fields

tk.Label(frame_filters, text="Date Created", anchor="w", bg=PRIMARY, width=15).grid(row=1, column=0, padx=5, pady=2, sticky="w")
created_date_entry = DateEntry(frame_filters, width=22, borderwidth=2, date_pattern='yyyy-mm-dd')
created_date_entry.grid(row=1, column=1, padx=5, pady=2, sticky="w")
created_date_entry.delete(0, tk.END)  # Clear the default date
# Button to clear ONLY the date picker
btn_clear_date = ttk.Button(
    frame_filters, 
    text="X", width=2,
    command=lambda: clear_control(created_date_entry)
)
btn_clear_date.grid(row=1, column=1, padx=5, pady=2, sticky="e")


tk.Label(frame_filters, text="Date Classified", anchor="w", bg=PRIMARY, width=15).grid(row=1, column=3, padx=5, pady=2, sticky="w")
classified_date_entry = DateEntry(frame_filters, width=22, borderwidth=2, date_pattern='yyyy-mm-dd')
classified_date_entry.grid(row=1, column=4, padx=5, pady=2, sticky="w")
classified_date_entry.delete(0, tk.END)  # Clear the default date
btn_clear_classified_date = ttk.Button(
    frame_filters, 
    text="X", width=2,
    command=lambda: clear_control(classified_date_entry)
)
btn_clear_classified_date.grid(row=1, column=4, padx=5, pady=2, sticky="e")

# ttk.Button(frame_filters, text="Search",  style="Success.TButton", command=load_documents).grid(row=2, column=0, padx=10)

record_frame = tk.Frame(frame_center, bg="#FFFFFF", highlightthickness=0)
record_frame.pack(padx=10, pady=5, fill="both", expand=True)


#define the table for displaying documents
# 1. Define columns
columns = ('Id', 'DI Filename', 'PDF Filename', 'Classification Department', "Confidence", "Email", "Email Sent")

# 2. Create the Treeview widget
table = ttk.Treeview(record_frame, columns=columns, show='headings')

# 3. Define headings and column widths
table.heading('Id', text='ID')
table.column('Id', width=10, anchor=tk.CENTER)

table.heading('DI Filename', text='DI Filename')
table.column('DI Filename', width=150, anchor=tk.W)

table.heading('PDF Filename', text='PDF Filename')
table.column('PDF Filename', width=150, anchor=tk.W)

table.heading('Classification Department', text='Classification Department')
table.column('Classification Department', width=150, anchor=tk.W)

table.heading('Confidence', text='Confidence')
table.column('Confidence', width=100, anchor=tk.CENTER)

table.heading('Email', text='Email')
table.column('Email', width=150, anchor=tk.W)

table.heading('Email Sent', text='Email Sent')
table.column('Email Sent', width=100, anchor=tk.CENTER)

# 4. Add a scrollbar (highly recommended for tables)
scrollbar = ttk.Scrollbar(record_frame, orient=tk.VERTICAL, command=table.yview)
table.configure(yscroll=scrollbar.set)

# Pack everything onto the screen
table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

# region Progress Bar Area
progress_frame = tk.Frame(frame_center, bg="#00CACA", highlightthickness=0)
progress_frame.pack(padx=10, pady=(0, 8), fill="x")
progress_text_var = tk.StringVar(value="Current Status：Waiting for action")
progress_value_var = tk.DoubleVar(value=0)
progress_label = tk.Label(
    progress_frame,
    textvariable=progress_text_var,
    bg="#00CACA",
    fg="white",
    anchor="w"
)
progress_label.pack(fill="x", padx=5, pady=(2, 2))
progress_bar = ttk.Progressbar(
    progress_frame,
    variable=progress_value_var,
    maximum=100,
    mode="determinate"
)
progress_bar.pack(fill="x", padx=5, pady=(2, 2))

def update_progress(current, total, message="Processing"):
    if total <= 0:
        percent = 0
        progress_text_var.set(f"{message}：0/0")
    else:
        percent = (current / total) * 100
        progress_text_var.set(
            f"{message}：{current}/{total}（{percent:.1f}%）"
        )

    progress_value_var.set(percent)
    root.update_idletasks()

def reset_progress(message="Current Status：Waiting for action"):
    progress_value_var.set(0)
    progress_text_var.set(message)
    root.update_idletasks()

def finish_progress(message="Completed"):
    progress_value_var.set(100)
    progress_text_var.set(message)
    root.update_idletasks()
    
def set_progress_percent(percent, message="Processing"):
    percent = max(0, min(100, float(percent)))
    progress_value_var.set(percent)
    progress_text_var.set(f"{message}（{percent:.1f}%）")
    root.update_idletasks()
    
# endregion
#---- APPLY THEME ----
apply_theme(root)

#endregion

#region Departments

def add_department():
    name = new_dept_name_entry.get().strip()
    email = new_dept_email_entry.get().strip()
    if not name or not email:
        messagebox.showwarning("欄位錯誤", "請輸入完整部門名稱與 Email")
        return
    dpt.insert_department(name, email)

    new_dept_name_entry.delete(0, tk.END)
    new_dept_email_entry.delete(0, tk.END)
    load_departments()

def load_departments():
    for widget in scrollable_frame.winfo_children():
        widget.destroy()
    email_entries.clear()

    departments = dpt.get_departments()

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
                    dpt.delete_department(dept_id)
                    load_departments()
            return delete_department

        ttk.Button(scrollable_frame, text="🗑", width=4,
                   command=make_delete_callback(dept_id, name),
                   style="Danger.TButton").grid(row=i, column=2, padx=5, pady=2, sticky="e")

    scrollable_frame.grid_columnconfigure(1, weight=1)

def save_department_emails():
    dpt.update_department_emails(email_entries)
    messagebox.showinfo("成功", "部門 Email 已儲存")

#endregion

#region Document crawler
def load_documents():
    for row in table.get_children():
        table.delete(row)

    status = status_entry.get()
    department = dept_entry.get() if dept_entry.get() != "All" else None
    created_date = created_date_entry.get()
    classified_date = classified_date_entry.get()

    documents = doc.get_document_by_filter(
        status=status,
        department=department,
        created_date=created_date,
        classified_date=classified_date
    )

    for (
        doc_id,
        di_filename,
        pdf_filename,
        folder_path,
        instruction,
        created_at,
        processed_at,
        department,
        confidence,
        email,
        email_sent
    ) in documents:

        table.insert(
            "",
            tk.END,
            iid=str(doc_id),
            values=(
                doc_id,
                di_filename,
                pdf_filename,
                department or "",
                f"{confidence:.2%}" if confidence is not None else "",
                email or "",
                "" if not email else "Yes" if email_sent else "No"
            )
        )
def update_document_row(
    doc_id,
    di_filename,
    pdf_filename,
    department,
    confidence,
    email,
    email_sent=False
):
    """
    只更新完成分類的那一列，不重新載入整張表格。
    必須由 Tkinter 主執行緒呼叫。
    """
    row_id = str(doc_id)

    values = (
        doc_id,
        di_filename,
        pdf_filename,
        department or "",
        f"{confidence:.2%}" if confidence is not None else "",
        email or "",
        "" if not email else "Yes" if email_sent else "No"
    )

    if table.exists(row_id):
        table.item(row_id, values=values)

        # 讓剛完成的那一列自動出現在可視範圍
        table.see(row_id)
        table.selection_set(row_id)

    else:
        # 若該列目前不存在，例如表格剛被篩選或尚未載入
        table.insert(
            "",
            tk.END,
            iid=row_id,
            values=values
        )
        table.see(row_id)
        table.selection_set(row_id)
def process_new_documents():
    crawler.process_and_move_files()
    load_documents()

def upload_document_folder():
    selected_dir = filedialog.askdirectory(title="Choose Document Folder to Upload")
    if not selected_dir:
        return
    try:
        reset_progress("Starting document folder import...")
        crawler.process_and_move_files(
            selected_dir=selected_dir,
            progress_callback=update_progress
        )
        load_documents()
        finish_progress("Document folder import completed")
        messagebox.showinfo(
            "Import Completed",
            "Document folder import, instruction extraction, and database writing completed."
        )
    except Exception as e:
        reset_progress("Import Failed")
        messagebox.showerror("Import Failed", str(e))
#endregion

#region Document Classification & Email Sending

def start_classification():
    """Start model loading and document classification in a background thread."""
    global classification_running

    if classification_running:
        messagebox.showinfo("Reminder", "Classification is already running.")
        return

    documents = doc.get_documents_for_classification()
    if not documents:
        reset_progress("No documents to classify")
        messagebox.showinfo(
            "Reminder",
            "There are currently no documents to classify.\n\n"
            "Possible reasons:\n"
            "1. No documents have been imported\n"
            "2. All documents have already been classified"
        )
        return

    classification_running = True
    btn_process_documents.configure(state="disabled")

    progress_bar.configure(mode="indeterminate")
    progress_value_var.set(0)
    progress_text_var.set("Starting classification worker...")
    progress_bar.start(12)

    worker = threading.Thread(
        target=classification_worker,
        args=(documents,),
        daemon=True,
        name="document-classification-worker"
    )
    worker.start()


def classification_worker(documents):
    """
    Runs outside the Tkinter main thread.
    Never updates Tkinter widgets directly; all UI messages go through ui_queue.
    """
    from classifier_service import get_classifier_service

    total_docs = len(documents)
    success_count = 0
    failed_count = 0
    failed_messages = []

    MODEL_LOAD_WEIGHT = 30.0
    INFERENCE_WEIGHT = 70.0

    def model_loading_progress(current, total, message):
        # Model loading has long blocking steps, so the UI uses an animated bar.
        stage_percent = 0.0 if total <= 0 else (current / total) * MODEL_LOAD_WEIGHT
        ui_queue.put(("model_status", stage_percent, f"Model loading: {message}"))

    try:
        ui_queue.put(("mode", "indeterminate"))
        ui_queue.put(("status", "Preparing model loading..."))

        service = get_classifier_service(
            progress_callback=model_loading_progress
        )

        # Model is ready. From here onward the progress is measurable.
        ui_queue.put(("mode", "determinate"))
        ui_queue.put(("progress", MODEL_LOAD_WEIGHT, "Model ready. Starting inference..."))

        for doc_index, (doc_id, di_filename, pdf_filename, folder_path, instruction) in enumerate(documents, start=1):
            display_name = di_filename or pdf_filename or f"Document ID {doc_id}"

            try:
                if not instruction or not instruction.strip():
                    failed_count += 1
                    failed_messages.append(f"Document ID {doc_id}: instruction is empty")
                    percent = MODEL_LOAD_WEIGHT + (doc_index / total_docs) * INFERENCE_WEIGHT
                    ui_queue.put(("progress", percent, f"Skipped empty instruction: {display_name}"))
                    continue

                def inference_progress(current, total, message):
                    inner_ratio = 0.0 if total <= 0 else current / total
                    completed_docs = doc_index - 1
                    percent = MODEL_LOAD_WEIGHT + (
                        (completed_docs + inner_ratio) / total_docs
                    ) * INFERENCE_WEIGHT
                    ui_queue.put((
                        "progress",
                        percent,
                        f"Inference {doc_index}/{total_docs}: {display_name} | {message}"
                    ))

                pred_name, confidence = service.predict_text(
                    instruction,
                    progress_callback=inference_progress
                )

                if not pred_name:
                    pred_name = "無法辨識"
                    confidence = 0.0

                dept_email = get_dept_email(pred_name) or "未設定"
                doc.update_classification(
                    doc_id,
                    pred_name,
                    confidence,
                    dept_email
                )
                success_count += 1
                # Every time a document is classified, send a message to the UI thread to update the table.
                ui_queue.put((
                    "document_result",
                    doc_id,
                    di_filename,
                    pdf_filename,
                    pred_name,
                    confidence,
                    dept_email,
                    False
                ))

                percent = MODEL_LOAD_WEIGHT + (
                    doc_index / total_docs
                ) * INFERENCE_WEIGHT

                ui_queue.put((
                    "progress",
                    percent,
                    f"Document classified {doc_index}/{total_docs}: {display_name}"
                ))

            except Exception as e:
                failed_count += 1
                error_msg = f"Document ID {doc_id} classification failed: {e}"
                failed_messages.append(error_msg)
                print(error_msg)
                traceback.print_exc()

                percent = MODEL_LOAD_WEIGHT + (doc_index / total_docs) * INFERENCE_WEIGHT
                ui_queue.put((
                    "progress",
                    percent,
                    f"Classification failed {doc_index}/{total_docs}: {display_name}"
                ))

        ui_queue.put((
            "done",
            success_count,
            failed_count,
            failed_messages
        ))

    except Exception as e:
        traceback.print_exc()
        ui_queue.put(("fatal_error", str(e)))


def poll_background_events():
    """Process worker messages on the Tkinter main thread."""
    global classification_running

    try:
        while True:
            event = ui_queue.get_nowait()
            event_type = event[0]

            if event_type == "mode":
                mode = event[1]
                progress_bar.stop()
                progress_bar.configure(mode=mode)
                if mode == "indeterminate":
                    progress_bar.start(12)
                else:
                    progress_value_var.set(0)

            elif event_type == "status":
                progress_text_var.set(event[1])

            elif event_type == "model_status":
                _stage_percent, message = event[1], event[2]
                # Keep the bar animated while showing the exact loading stage.
                progress_text_var.set(message)

            elif event_type == "progress":
                percent, message = event[1], event[2]

                progress_bar.stop()
                progress_bar.configure(mode="determinate")

                progress_value_var.set(
                    max(0.0, min(100.0, float(percent)))
                )

                progress_text_var.set(
                    f"{message} ({percent:.1f}%)"
                )

            elif event_type == "document_result":
                (
                    doc_id,
                    di_filename,
                    pdf_filename,
                    department,
                    confidence,
                    email,
                    email_sent
                ) = event[1:]

                update_document_row(
                    doc_id=doc_id,
                    di_filename=di_filename,
                    pdf_filename=pdf_filename,
                    department=department,
                    confidence=confidence,
                    email=email,
                    email_sent=email_sent
                )

            elif event_type == "done":
                success_count, failed_count, failed_messages = (
                    event[1],
                    event[2],
                    event[3]
                )

                classification_running = False
                progress_bar.stop()
                progress_bar.configure(mode="determinate")
                progress_value_var.set(100)

                progress_text_var.set(
                    f"Classification completed: "
                    f"Success {success_count}, Failed {failed_count}"
                )

                btn_process_documents.configure(state="normal")

                # 可保留，作為最後一次資料庫與 UI 同步
                load_documents()

                msg = (
                    f"Classification completed.\n"
                    f"Success: {success_count}\n"
                    f"Failed: {failed_count}"
                )

                if failed_messages:
                    msg += (
                        "\n\nTop 5 failure reasons:\n"
                        + "\n".join(failed_messages[:5])
                    )

                messagebox.showinfo("Classification Results", msg)

            elif event_type == "fatal_error":
                classification_running = False
                progress_bar.stop()
                progress_bar.configure(mode="determinate")
                progress_value_var.set(0)
                progress_text_var.set("Classification failed")
                btn_process_documents.configure(state="normal")
                messagebox.showerror("Classification Failed", event[1])

    except queue.Empty:
        pass

    root.after(100, poll_background_events)

#endregion


#---- load data on start ----
load_departments()
# load_records()
load_documents()
    
# ==== Customize the "Sender's Credentials" dialog box (including OK/Cancel) ====
class CredentialsDialog(tk.Toplevel):
    def __init__(self, parent, default_user=""):
        super().__init__(parent)
        self.title("Sender's Credentials")
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


def open_smtp(default_user=""):
    global _SMTP_USER, _SMTP_PASS

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
    
# === 右側按鈕列（背景與右半一致 #00CACA） ===
button_frame = tk.Frame(frame_center, bg="#00CACA", highlightthickness=0)
button_frame.pack(pady=10)

ttk.Button(button_frame, text="Search New Documents", command=process_new_documents, style="Primary.TButton").grid(row=0, column=2, padx=10)
btn_process_documents = ttk.Button(
    button_frame,
    text="Process Documents",
    command=start_classification,
    style="Primary.TButton"
)
btn_process_documents.grid(row=0, column=3, padx=10)
ttk.Button(button_frame, text="📂 選擇文件上傳", command=upload_document_folder, style="Dark.TButton").grid(row=0, column=1, padx=10)


ttk.Button(frame_filters, text="Search",  style="Success.TButton", command=load_documents).grid(row=2, column=0, padx=10)

# === Email Function Area (Load/Save/Delete Department)） ===


btn_save_emails.configure(command=save_department_emails)


# === Email sent to oneself (recipient reads "myself" on the left; sender asks once on the spot). ===
# def send_all_to_self():
#     # 收件人 = 左側 departments 中的 "myself"
#     my_email = get_dept_email("myself")
#     if not my_email or "@" not in my_email:
#         messagebox.showerror("錯誤", "找不到『myself』部門的 Email，請先在左側設定並按「💾 儲存 Email」。")
#         return

#     # Files to be sent: If there is a selection, send only the selected files; otherwise, send all files.
#     files = []
#     conn = sqlite3.connect(DB_PATH)
#     cursor = conn.cursor()
#     sel = listbox_records.curselection()
#     if sel:
#         for idx in sel:
#             fname = listbox_records.get(idx)
#             cursor.execute("SELECT filepath FROM uploads WHERE filename=?", (fname,))
#             row = cursor.fetchone()
#             if row and os.path.exists(row[0]):
#                 files.append((fname, row[0]))
#     else:
#         cursor.execute("SELECT filename, filepath FROM uploads ORDER BY id DESC")
#         for fname, fpath in cursor.fetchall():
#             if os.path.exists(fpath):
#                 files.append((fname, fpath))
#     conn.close()

#     if not files:
#         messagebox.showwarning("提醒", "目前沒有可寄送的檔案。")
#         return

#     try:
#         server = open_smtp(default_user=my_email)
#         if server is None:
#             messagebox.showinfo("已取消", "你已取消寄送。")
#             return
#     except Exception as e:
#         messagebox.showerror("SMTP 連線失敗", str(e))
#         return

#     sent, failed = 0, []
#     for fname, fpath in files:
#         subject = f"[測試寄送] {fname}"
#         body = f"這是測試寄送（收件人使用左側『myself』Email）。\n附件：{fname}\n（系統自動寄出）"
#         try:
#             send_one(server, my_email, subject, body, fpath)
#             sent += 1
#         except Exception as e:
#             failed.append(f"{fname}（{e}）")

#     try:
#         server.quit()
#     except:
#         pass

#     summary = [f"✅ 已寄到『myself』：{sent} 封"]
#     if failed:
#         summary.append("⚠️ 失敗：")
#         summary += [f"• {x}" for x in failed]
#     messagebox.showinfo("測試寄信結果", "\n".join(summary))
# ttk.Button(button_frame, text="📧 寄給自己（測試）", command=send_all_to_self, style="Success.TButton").grid(row=0, column=4, padx=10)

# 啟動背景事件輪詢
root.after(100, poll_background_events)

# 啟動
root.mainloop()