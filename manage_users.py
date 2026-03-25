from datetime import datetime
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

from matplotlib import style
import users as usr

usr.init_db()


def load_users():
    users = usr.get_all_users()
    for user in users:
        tree.insert("", "end", values=user)

def save_user():
    username = entry_username.get()
    password = entry_password.get()
    is_active = var_isActive.get()
    is_admin = var_isAdmin.get()
    if var_state.get() == "NEW":
        if not username or not password:
            messagebox.showerror("錯誤", "請輸入帳號與密碼")
            return
        response = usr.insert_user(username, password, is_active, is_admin)
        if response:
            messagebox.showinfo("成功", "使用者新增成功！")
            clear_inputs()

        else:
            messagebox.showerror("錯誤", "帳號已被註冊")
    else:
        usr.update_user(username, is_active, is_admin)
        messagebox.showinfo("成功", "使用者更新成功！")
        clear_inputs()
    clear_treeview(tree)
    load_users()

def change_password():
    username = entry_username.get()
    new_password = entry_password.get()
    if not username or not new_password:
        messagebox.showerror("錯誤", "請輸入帳號與新密碼")
        return
    usr.update_password(username, new_password)
    messagebox.showinfo("成功", "密碼更新成功！")
    clear_inputs()
    clear_treeview(tree)
    load_users()

def clear_treeview(tree):
    for item in tree.get_children():
        tree.delete(item)

def clear_inputs():
    var_state.set("NEW")
    entry_username.configure(state="normal") 
    entry_username.delete(0, tk.END)
    entry_password.delete(0, tk.END)
    btn_save_password.configure(state="disabled")
    var_isActive.set(0)
    var_isAdmin.set(0)

BG      = "#E0E0E0"
PANEL   = "#1E3A5F"
FG      = "#FFFFFF"
PRIMARY = "#007ACC"
SELBG   = "#2A628F"
SUCCESS = "#28a745"
DANGER  = "#d9534f"
WARNING = "#F59E0B"
DARK = "#374151"
BTN_ACTIVE = "#2A628F"
BTN_PRESSED = "#173B57"



root = tk.Tk()
style = ttk.Style(root)
try:
    style.theme_use("clam")
    style.configure("Vertical.TScrollbar", troughcolor="#FFFFFF")
except tk.TclError:
    pass

root.title("多模態 AI 智能系統 - User Management")
root.geometry("500x400")
root.resizable(False, False)
background_color = "#E6F2FF"
root.configure(bg=background_color)
root.tk_setPalette(background=BG, foreground=FG,
                       activeBackground=SELBG, activeForeground=FG,
                       highlightColor=BG)
style.configure("TLabel", background=BG, foreground=DARK)
style.configure('Danger.TButton',  background=DANGER, foreground='white')
style.configure('Primary.TButton', background=PRIMARY, foreground='white')
style.configure('Dark.TButton',    background=DARK, foreground='white')
style.configure('Orange.TButton',  background=WARNING, foreground='white')
style.map('TButton',
          background=[('active', BTN_ACTIVE), ('pressed', BTN_PRESSED)],
          foreground=[('disabled', '#AAAAAA')])


# === User Add/Edit Area ===
frameAddEditUser = tk.Frame(root, width=400, highlightthickness=0)
frameAddEditUser.pack(side="top", fill="x")

var_state = tk.StringVar(value="NEW")

label_username = ttk.Label(frameAddEditUser, text="Username")
label_username.grid(row=0, column=0, sticky="w", padx=10, pady=5)
entry_username = ttk.Entry(frameAddEditUser, width=40)
entry_username.grid(row=0, column=1, sticky="w", padx=10, pady=5)
label_password = ttk.Label(frameAddEditUser, text="Password")
label_password.grid(row=1, column=0, sticky="w", padx=10, pady=5)
entry_password = ttk.Entry(frameAddEditUser, width=40, show="*")
entry_password.grid(row=1, column=1, sticky="w", padx=10, pady=5)
btn_save_password = ttk.Button(frameAddEditUser, text="Change Password", command=lambda: change_password(), state="disabled")
btn_save_password.grid(row=1, column=2, padx=10, sticky= "w")

var_isActive = tk.IntVar()
var_isAdmin = tk.IntVar()
label_active = ttk.Label(frameAddEditUser, text="Active").grid(row=2, column=0, sticky="w", padx=10, pady=5)
label_admin = ttk.Label(frameAddEditUser, text="Admin").grid(row=3, column=0, sticky="w", padx=10, pady=5)
check_active = ttk.Checkbutton(frameAddEditUser, variable=var_isActive)
check_active.grid(row=2, column=1, sticky="w", padx=10, pady=5)
check_admin = ttk.Checkbutton(frameAddEditUser, variable=var_isAdmin)
check_admin.grid(row=3, column=1, sticky="w", padx=10, pady=5)

btn_add_user = ttk.Button(frameAddEditUser, text="Save", command=lambda: save_user())
btn_add_user.grid(row=4, column=0, padx=10, sticky="w")
btn_cancel = ttk.Button(frameAddEditUser, text="Cancel", command=lambda: clear_inputs())
btn_cancel.grid(row=4, column=1, padx=10, sticky="w")

# === User List Area ===
frameListUsers = tk.Frame(root, width=400, highlightthickness=0)
frameListUsers.pack(side="top", fill="y", pady=20)
vsb = ttk.Scrollbar(frameListUsers, orient="vertical")

columns_info = (
    ('ID', 50),
    ('Username', 150),
    ('Last Login', 120),
    ('Active', 50),
    ('Admin', 50)
)
column_names = [col[0] for col in columns_info]
tree = ttk.Treeview(frameListUsers, columns=column_names, show='headings')

vsb.configure(command=tree.yview)
tree.config(yscrollcommand=vsb.set)
# Configure each column's width and heading
for col_name, width_val in columns_info:
    tree.heading(col_name, text=col_name, anchor=tk.CENTER)
    tree.column(col_name, width=width_val, minwidth=width_val, stretch=False, anchor=tk.CENTER)

tree.grid(row=0, column=0, sticky="nsew")
vsb.grid(row=0, column=1, sticky="ns")
load_users()
clear_inputs()

def on_row_click(event):
    # Get the ID of the selected item
    item_id = tree.focus()
    if item_id:
        # Get the values of the clicked row
        item_values = tree.item(item_id, 'values')
        var_state.set("EDIT")
        btn_save_password.configure(state="normal")
        entry_username.delete(0, tk.END)
        entry_username.insert(0, item_values[1])  
        entry_username.configure(state="readonly")  # 禁止編輯 username
        var_isActive.set(int(item_values[3]))  
        var_isAdmin.set(int(item_values[4]))  
        print(f"Clicked row values: {item_values}")
        # You can perform other actions here

# Bind the left mouse button click event (<Button-1>) to the function
tree.bind("<Button-1>", on_row_click)
root.mainloop()