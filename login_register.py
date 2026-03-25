import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import sqlite3
import subprocess
import os

import users as usr


# 建立資料庫
usr.init_db()

# 註冊功能
def register():
    username = entry_username.get()
    password = entry_password.get()
    if not username or not password:
        messagebox.showerror("錯誤", "請輸入帳號與密碼")
        return
    response = usr.insert_user(username, password)
    if response:
        messagebox.showinfo("成功", "註冊成功！")
    else:
        messagebox.showerror("錯誤", "帳號已被註冊")


# 開啟主畫面腳本
def open_new_script():
    root.destroy()
    script_path = os.path.join(os.path.dirname(__file__), "main.py")
    try:
        subprocess.Popen(["python", script_path])
        print("成功開啟 main.py")
    except Exception as e:
        print(f"無法開啟主畫面：{e}")

# 登入功能
def login():
    username = entry_username.get()
    password = entry_password.get()
    
    # hashed_password = password  # 這裡可以加入密碼哈希處理
    user = usr.validate_user(username, password)
    if user:
        messagebox.showinfo("成功", "登入成功！")
        open_new_script()
    else:
        messagebox.showerror("錯誤", "帳號或密碼錯誤")

# 建立視窗
root = tk.Tk()
root.title("多模態 AI 智能系統 - 登入")
root.geometry("800x400")
root.resizable(False, False)
background_color = "#E6F2FF"
root.configure(bg=background_color)

# 取得相對圖片路徑
base_path = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(base_path, "img", "login_bg.jpeg")
logo_path = os.path.join(base_path, "img", "logo.png")

# 背景圖處理
try:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"找不到背景圖：{image_path}")
    image = Image.open(image_path)
    image = image.resize((400, 400))
    photo = ImageTk.PhotoImage(image)
    canvas = tk.Canvas(root, width=400, height=400)
    canvas.pack(side="right", fill="both", expand=True)
    canvas.create_image(0, 0, anchor="nw", image=photo)
except Exception as e:
    print(f"無法載入背景圖：{e}")

# 左側登入區塊
frame = tk.Frame(root, bg=background_color)
frame.pack(side="left", padx=50, pady=50)

# Logo 圖片處理
try:
    if not os.path.exists(logo_path):
        raise FileNotFoundError(f"找不到 Logo：{logo_path}")
    logo_image = Image.open(logo_path)
    logo_image = logo_image.resize((80, 80))
    logo_photo = ImageTk.PhotoImage(logo_image)
    label_logo = tk.Label(root, image=logo_photo, bg=background_color)
    label_logo.place(x=150, y=-5)
except Exception as e:
    print(f"無法載入 Logo: {e}")

# 標題與輸入欄位
project_title = tk.Label(frame, text="多模態 AI 智能系統", font=("Arial", 20), bg=background_color)
project_title.pack(pady=10)

label_title = tk.Label(frame, text="Login", font=("Arial", 16), bg=background_color)
label_title.pack(pady=10)

entry_username = tk.Entry(frame, width=30)
entry_username.pack(pady=5)
entry_username.insert(0, "Enter account or email")

entry_password = tk.Entry(frame, width=30, show="*")
entry_password.pack(pady=5)
entry_password.insert(0, "Password")

btn_login = tk.Button(frame, text="Login", command=login, width=15)
btn_login.pack(pady=5)

btn_register = tk.Button(frame, text="Register", command=register, width=15)
btn_register.pack(pady=5)

# 執行主程式
root.mainloop()
