from __future__ import annotations

import logging
import mimetypes
import os
import re
import threading
import tkinter as tk
from email.message import EmailMessage
from tkinter import messagebox, ttk
from typing import Callable, Optional

import documents as doc
from app_logging import configure_logging
from email_config import (
    EMAIL_PATTERN,
    EmailConfigurationError,
    EmailSettings,
    migrate_and_sanitize_config,
    save_non_secret_email_settings,
)
from smtp_client import SecureSMTPClient, SecureSMTPError


configure_logging(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger("email.ui")


class EmailManagementWindow:
    READY_COLUMNS = ("document", "body", "sender", "recipient", "send")
    REVIEW_COLUMNS = ("document", "department", "confidence", "recipient", "status")

    def __init__(
        self,
        parent,
        config_path: Optional[str] = None,
        on_email_sent: Optional[Callable[[], None]] = None,
    ):
        self.parent = parent
        self.on_email_sent = on_email_sent
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.config_path = config_path or os.path.join(self.base_path, "config.json")
        self.settings = migrate_and_sanitize_config(self.config_path)

        self.window = tk.Toplevel(parent)
        self.window.title("Email Management")
        self.window.geometry("1450x800")
        self.window.minsize(1050, 640)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self._close_window)

        self._sending_ids: set[int] = set()
        self._editor = None
        self._editor_tree = None
        self._editor_item = None
        self._placeholder_state = {}

        self.status_var = tk.StringVar(value="Ready")
        self.sender_email_var = tk.StringVar(value=self.settings.sender_email)
        self.smtp_user_var = tk.StringVar(value=self.settings.smtp_user)
        self.smtp_pass_var = tk.StringVar(value="")
        self.smtp_host_var = tk.StringVar(value=self.settings.smtp_host)
        self.smtp_port_var = tk.StringVar(value=str(self.settings.smtp_port))
        self._show_password_var = tk.BooleanVar(value=False)

        self._apply_style()
        self._build_ui()
        self.refresh()

    def _apply_style(self):
        style = ttk.Style(self.window)
        style.configure("Email.TFrame", background="#F3F4F6")
        style.configure("Email.TLabel", background="#F3F4F6", foreground="#000000")
        style.configure("Email.Security.TLabel", background="#F3F4F6", foreground="#14532D")
        style.configure("Email.TLabelframe", background="#F3F4F6", foreground="#000000")
        style.configure("Email.TLabelframe.Label", foreground="#000000")
        style.configure("Email.TButton", foreground="#000000")
        style.configure("Email.TCheckbutton", background="#F3F4F6", foreground="#000000")
        style.configure("Email.Treeview", foreground="#000000", background="#FFFFFF", fieldbackground="#FFFFFF")
        style.configure("Email.Treeview.Heading", foreground="#000000", background="#E5E7EB")

    def _build_ui(self):
        header = ttk.Frame(self.window, style="Email.TFrame")
        header.pack(fill="x", padx=12, pady=(12, 6))
        ttk.Label(header, style="Email.TLabel", text="Email Document Dispatch", font=("Arial", 16, "bold")).pack(side="left")
        ttk.Label(
            header,
            style="Email.TLabel",
            text=f"Minimum confidence: {self.settings.confidence_threshold:.0%}",
        ).pack(side="left", padx=24)
        ttk.Button(header, style="Email.TButton", text="Refresh", command=self.refresh).pack(side="right")

        settings_group = ttk.LabelFrame(
            self.window,
            style="Email.TLabelframe",
            text="Sender / SMTP Settings",
            padding=8,
        )
        settings_group.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Label(settings_group, text="SMTP Host", style="Email.TLabel").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        self.smtp_host_entry = ttk.Entry(settings_group, textvariable=self.smtp_host_var, width=28)
        self.smtp_host_entry.grid(row=0, column=1, sticky="we", padx=5, pady=3)
        self._add_placeholder(self.smtp_host_entry, self.smtp_host_var, "e.g. smtp.gmail.com")

        ttk.Label(settings_group, text="SMTP Port", style="Email.TLabel").grid(row=0, column=2, sticky="w", padx=5, pady=3)
        self.smtp_port_entry = ttk.Entry(settings_group, textvariable=self.smtp_port_var, width=8)
        self.smtp_port_entry.grid(row=0, column=3, sticky="w", padx=5, pady=3)

        ttk.Label(settings_group, text="Sender Email", style="Email.TLabel").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        self.sender_email_entry = ttk.Entry(settings_group, textvariable=self.sender_email_var, width=36)
        self.sender_email_entry.grid(row=1, column=1, sticky="we", padx=5, pady=3)
        self._add_placeholder(self.sender_email_entry, self.sender_email_var, "e.g. sender@example.com")

        ttk.Label(settings_group, text="SMTP User", style="Email.TLabel").grid(row=1, column=2, sticky="w", padx=5, pady=3)
        self.smtp_user_entry = ttk.Entry(settings_group, textvariable=self.smtp_user_var, width=36)
        self.smtp_user_entry.grid(row=1, column=3, sticky="we", padx=5, pady=3)
        self._add_placeholder(self.smtp_user_entry, self.smtp_user_var, "SMTP account or email")

        ttk.Label(settings_group, text="SMTP Password", style="Email.TLabel").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        self.smtp_pass_entry = ttk.Entry(settings_group, textvariable=self.smtp_pass_var, width=36, show="*")
        self.smtp_pass_entry.grid(row=2, column=1, sticky="we", padx=5, pady=3)
        self._add_placeholder(
            self.smtp_pass_entry,
            self.smtp_pass_var,
            "Enter SMTP password",
            password=True,
        )
        ttk.Checkbutton(
            settings_group,
            text="Show",
            style="Email.TCheckbutton",
            variable=self._show_password_var,
            command=self._toggle_password_visibility,
        ).grid(row=2, column=2, sticky="w", padx=5, pady=3)
        ttk.Button(
            settings_group,
            text="Save Non-secret Settings",
            style="Email.TButton",
            command=self.save_smtp_settings,
        ).grid(row=2, column=3, sticky="e", padx=5, pady=3)

        security_text = (
            "TLS Required — "
            + ("STARTTLS" if self.settings.security_mode == "starttls" else "Implicit TLS")
            + "; certificate validation enabled; password is never stored"
        )
        ttk.Label(settings_group, text="Connection Security", style="Email.TLabel").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        self.security_label = ttk.Label(
            settings_group,
            text=security_text,
            style="Email.Security.TLabel",
            font=("Arial", 10, "bold"),
        )
        self.security_label.grid(row=3, column=1, columnspan=3, sticky="w", padx=5, pady=3)
        settings_group.columnconfigure(1, weight=1)
        settings_group.columnconfigure(3, weight=1)

        ready_group = ttk.LabelFrame(self.window, style="Email.TLabelframe", text="Ready To Send", padding=8)
        ready_group.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self.ready_tree = self._build_tree(
            ready_group,
            columns=self.READY_COLUMNS,
            headings={"document": "Document Name", "body": "Document Body", "sender": "Sender Email", "recipient": "Recipient Email", "send": "Send"},
            widths={"document": 220, "body": 450, "sender": 230, "recipient": 260, "send": 90},
        )
        self.ready_tree.tag_configure("ready", background="#E9F8EE")
        self.ready_tree.tag_configure("sending", background="#E7F0FF")
        self.ready_tree.bind("<Double-1>", self._on_ready_double_click)
        self.ready_tree.bind("<ButtonRelease-1>", self._on_ready_click)

        review_group = ttk.LabelFrame(self.window, style="Email.TLabelframe", text="Manual Review", padding=8)
        review_group.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.review_tree = self._build_tree(
            review_group,
            columns=self.REVIEW_COLUMNS,
            headings={"document": "Document", "department": "Department", "confidence": "Confidence", "recipient": "Recipient", "status": "Status"},
            widths={"document": 260, "department": 220, "confidence": 120, "recipient": 300, "status": 250},
        )
        self.review_tree.tag_configure("review", background="#FFF4D6")
        self.review_tree.tag_configure("missing", background="#FDECEC")
        self.review_tree.bind("<Double-1>", self._on_review_double_click)

        footer = ttk.Frame(self.window, style="Email.TFrame")
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Label(footer, textvariable=self.status_var, style="Email.TLabel").pack(side="left")
        ttk.Label(
            footer,
            style="Email.TLabel",
            text="Double-click Recipient to edit. Only Ready To Send rows can be sent.",
        ).pack(side="left", padx=18)
        ttk.Button(footer, style="Email.TButton", text="Close", command=self._close_window).pack(side="right")

    @staticmethod
    def _build_tree(parent, columns, headings, widths):
        container = ttk.Frame(parent, style="Email.TFrame")
        container.pack(fill="both", expand=True)
        tree = ttk.Treeview(container, style="Email.Treeview", columns=columns, show="headings", selectmode="browse")
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(
                column,
                width=widths[column],
                minwidth=70,
                anchor="center" if column in {"confidence", "status", "send"} else "w",
                stretch=column in {"body", "recipient"},
            )
        y_scroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        return tree

    def _add_placeholder(self, entry, variable, placeholder, password=False):
        """Add a lightweight placeholder without treating it as real input."""
        state = {
            "variable": variable,
            "placeholder": placeholder,
            "password": password,
            "active": False,
        }
        self._placeholder_state[entry] = state

        def show_placeholder():
            if variable.get():
                return
            state["active"] = True
            variable.set(placeholder)
            entry.configure(foreground="#6B7280")
            if password:
                entry.configure(show="")

        def focus_in(_event):
            if not state["active"]:
                return
            state["active"] = False
            variable.set("")
            entry.configure(foreground="#000000")
            if password:
                entry.configure(show="" if self._show_password_var.get() else "*")

        def focus_out(_event):
            if not variable.get():
                show_placeholder()

        entry.bind("<FocusIn>", focus_in)
        entry.bind("<FocusOut>", focus_out)
        show_placeholder()

    def _entry_value(self, entry, strip=True):
        state = self._placeholder_state.get(entry)
        if state and state["active"]:
            return ""
        value = state["variable"].get() if state else entry.get()
        return value.strip() if strip else value

    def _restore_placeholder(self, entry):
        state = self._placeholder_state.get(entry)
        if not state:
            return
        state["variable"].set("")
        state["active"] = True
        state["variable"].set(state["placeholder"])
        entry.configure(foreground="#6B7280")
        if state["password"]:
            entry.configure(show="")

    def _toggle_password_visibility(self):
        state = self._placeholder_state.get(self.smtp_pass_entry)
        if state and state["active"]:
            self.smtp_pass_entry.configure(show="")
            return
        self.smtp_pass_entry.configure(show="" if self._show_password_var.get() else "*")

    def _clear_password(self):
        self._show_password_var.set(False)
        try:
            self._restore_placeholder(self.smtp_pass_entry)
        except tk.TclError:
            self.smtp_pass_var.set("")

    def _close_window(self):
        if self._sending_ids:
            messagebox.showwarning(
                "Email Sending",
                "Wait until the current email attempt finishes before closing this window.",
                parent=self.window,
            )
            return
        self._clear_password()
        self._close_editor(save=False)
        self.window.destroy()

    def save_smtp_settings_without_popup(self):
        try:
            smtp_port = int(self.smtp_port_entry.get().strip())
        except ValueError as exc:
            raise EmailConfigurationError("SMTP Port must be a number.") from exc

        self.settings = save_non_secret_email_settings(
            self.config_path,
            {
                "smtp_host": self._entry_value(self.smtp_host_entry),
                "smtp_port": smtp_port,
                "smtp_user": self._entry_value(self.smtp_user_entry),
                "sender_email": self._entry_value(self.sender_email_entry),
            },
        )

    def save_smtp_settings(self):
        try:
            self.save_smtp_settings_without_popup()
        except Exception as exc:
            messagebox.showerror("SMTP Settings Error", str(exc), parent=self.window)
            return
        self.sender_email_var.set(self.settings.sender_email)
        self.smtp_user_var.set(self.settings.smtp_user)
        self.smtp_host_var.set(self.settings.smtp_host)
        self.smtp_port_var.set(str(self.settings.smtp_port))
        messagebox.showinfo(
            "Saved",
            "SMTP host, port, user, and sender were saved. The SMTP password was not stored.",
            parent=self.window,
        )
        self.refresh()

    def refresh(self):
        if self._sending_ids:
            messagebox.showinfo("Email Sending", "Please wait until the current email has finished sending.", parent=self.window)
            return
        self._close_editor(save=False)
        for tree in (self.ready_tree, self.review_tree):
            for item in tree.get_children():
                tree.delete(item)

        ready_count = 0
        review_count = 0
        for row in doc.get_documents_for_email():
            document_id, di_filename, pdf_filename, _folder_path, instruction, department, confidence, recipient_email, _email_sent = row
            confidence_value = float(confidence or 0.0)
            recipient = (recipient_email or "").strip()
            valid_recipient = self._valid_recipient_list(recipient)
            attachment_name = pdf_filename or di_filename or f"Document {document_id}"

            if confidence_value >= self.settings.confidence_threshold and valid_recipient:
                self.ready_tree.insert(
                    "",
                    "end",
                    iid=str(document_id),
                    values=(attachment_name, self._single_line(instruction or "", 320), self.settings.sender_email, recipient, "Send"),
                    tags=("ready",),
                )
                ready_count += 1
            else:
                if not valid_recipient:
                    status, tag = "Recipient missing or invalid", "missing"
                else:
                    status, tag = "Confidence below threshold; manual review required", "review"
                self.review_tree.insert(
                    "",
                    "end",
                    iid=str(document_id),
                    values=(attachment_name, department or "", f"{confidence_value:.2%}", recipient, status),
                    tags=(tag,),
                )
                review_count += 1
        self.status_var.set(f"Ready: {ready_count}    Manual review: {review_count}")

    @staticmethod
    def _single_line(value: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value)).strip()
        return text if len(text) <= limit else text[: limit - 1] + "…"

    @staticmethod
    def _split_recipients(raw: str):
        return [value.strip() for value in re.split(r"[;,\s、]+", raw or "") if value.strip()]

    def _valid_recipient_list(self, raw: str) -> bool:
        recipients = self._split_recipients(raw)
        return bool(recipients) and all(EMAIL_PATTERN.fullmatch(address) for address in recipients)

    def _on_ready_double_click(self, event):
        self._handle_recipient_edit(self.ready_tree, self.READY_COLUMNS, event)

    def _on_review_double_click(self, event):
        self._handle_recipient_edit(self.review_tree, self.REVIEW_COLUMNS, event)

    def _handle_recipient_edit(self, tree, columns, event):
        if tree.identify_region(event.x, event.y) != "cell":
            return
        item_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not item_id or column_id != f"#{columns.index('recipient') + 1}":
            return
        self._open_recipient_editor(tree, columns, item_id, column_id)

    def _open_recipient_editor(self, tree, columns, item_id, column_id):
        self._close_editor(save=False)
        bbox = tree.bbox(item_id, column_id)
        if not bbox:
            return
        x, y, width, height = bbox
        current_email = tree.item(item_id, "values")[columns.index("recipient")]
        editor = ttk.Entry(tree)
        editor.insert(0, current_email)
        editor.select_range(0, "end")
        editor.focus_set()
        editor.place(x=x, y=y, width=width, height=height)
        self._editor, self._editor_tree, self._editor_item = editor, tree, item_id
        editor.bind("<Return>", lambda _event: self._close_editor(save=True))
        editor.bind("<Escape>", lambda _event: self._close_editor(save=False))
        editor.bind("<FocusOut>", lambda _event: self._close_editor(save=True))

    def _close_editor(self, save):
        if self._editor is None:
            return
        editor, item_id = self._editor, self._editor_item
        self._editor = self._editor_tree = self._editor_item = None
        try:
            new_email = editor.get().strip()
        except tk.TclError:
            new_email = ""
        try:
            editor.destroy()
        except tk.TclError:
            pass
        if not save or not item_id:
            return
        if new_email and not self._valid_recipient_list(new_email):
            messagebox.showerror(
                "Invalid Recipient",
                "Enter valid email addresses separated by commas or semicolons.",
                parent=self.window,
            )
            return
        doc.update_document_email(int(item_id), new_email)
        self.refresh()

    def _on_ready_click(self, event):
        if self._editor is not None:
            return
        if self.ready_tree.identify_region(event.x, event.y) != "cell":
            return
        item_id = self.ready_tree.identify_row(event.y)
        column_id = self.ready_tree.identify_column(event.x)
        if not item_id or column_id != f"#{self.READY_COLUMNS.index('send') + 1}":
            return
        values = self.ready_tree.item(item_id, "values")
        if values[self.READY_COLUMNS.index("send")] == "Send":
            self._start_send(int(item_id))

    def _resolve_attachment(self, row):
        _document_id, di_filename, pdf_filename, folder_path, *_rest = row
        candidates = []
        for filename in (pdf_filename, di_filename):
            if not filename:
                continue
            if os.path.isabs(filename):
                candidates.append(filename)
            if folder_path:
                candidates.append(os.path.join(folder_path, filename))
                candidates.append(os.path.join(self.base_path, folder_path, filename))
            candidates.append(os.path.join(self.base_path, filename))
        for candidate in candidates:
            full_path = os.path.abspath(candidate)
            if os.path.isfile(full_path):
                return full_path
        return None

    def _start_send(self, document_id):
        if document_id in self._sending_ids:
            return
        try:
            self.save_smtp_settings_without_popup()
        except Exception as exc:
            messagebox.showerror("SMTP Settings Error", str(exc), parent=self.window)
            return

        password = self._entry_value(self.smtp_pass_entry, strip=False)
        if not password:
            messagebox.showerror("SMTP Password Required", "Enter the SMTP password before sending.", parent=self.window)
            self.smtp_pass_entry.focus_set()
            return

        row = doc.get_document_for_email(document_id)
        if row is None:
            messagebox.showerror("Document Not Found", "This document no longer exists in the database.", parent=self.window)
            self.refresh()
            return

        _document_id, _di_filename, pdf_filename, _folder_path, instruction, department, confidence, recipient_email, email_sent = row
        if email_sent:
            messagebox.showinfo("Already Sent", "This document has already been emailed.", parent=self.window)
            self.refresh()
            return

        confidence_value = float(confidence or 0.0)
        if confidence_value < self.settings.confidence_threshold:
            messagebox.showwarning(
                "Manual Review Required",
                f"Confidence {confidence_value:.2%} is below {self.settings.confidence_threshold:.2%}.",
                parent=self.window,
            )
            self.refresh()
            return

        recipient = (recipient_email or "").strip()
        if not self._valid_recipient_list(recipient):
            messagebox.showerror("Invalid Recipient", "Enter a valid recipient address first.", parent=self.window)
            self.refresh()
            return

        attachment_path = self._resolve_attachment(row)
        if not attachment_path:
            messagebox.showerror("Attachment Not Found", "Neither the PDF nor DI attachment could be found.", parent=self.window)
            return
        attachment_size = os.path.getsize(attachment_path)
        if attachment_size > self.settings.max_attachment_bytes:
            messagebox.showerror(
                "Attachment Too Large",
                f"Attachment size is {attachment_size / 1024 / 1024:.2f} MB; limit is {self.settings.max_attachment_mb:.2f} MB.",
                parent=self.window,
            )
            return

        display_name = pdf_filename or os.path.basename(attachment_path)
        if not messagebox.askyesno(
            "Confirm Email",
            f"Document: {display_name}\nDepartment: {department or ''}\nConfidence: {confidence_value:.2%}\nFrom: {self.settings.sender_email}\nTo: {recipient}\n\nSend this document now?",
            parent=self.window,
        ):
            return

        self._sending_ids.add(document_id)
        self._set_ready_row_sending(document_id)
        self.status_var.set(f"Sending {display_name}...")
        threading.Thread(
            target=self._send_worker,
            args=(document_id, row, attachment_path, self._split_recipients(recipient), instruction or "", password),
            daemon=True,
            name=f"email-send-{document_id}",
        ).start()

    def _set_ready_row_sending(self, document_id):
        item_id = str(document_id)
        if not self.ready_tree.exists(item_id):
            return
        values = list(self.ready_tree.item(item_id, "values"))
        values[self.READY_COLUMNS.index("send")] = "Sending..."
        self.ready_tree.item(item_id, values=values, tags=("sending",))

    def _send_worker(self, document_id, row, attachment_path, recipients, instruction, password):
        try:
            department = row[5] or ""
            confidence = float(row[6] or 0.0)
            attachment_name = os.path.basename(attachment_path)

            message = EmailMessage()
            message["From"] = self.settings.sender_email
            message["To"] = ", ".join(recipients)
            message["Subject"] = f"{self.settings.subject_prefix} {department} - {attachment_name}".strip()
            message.set_content(
                "This document was classified by the AI document dispatch system.\n\n"
                f"Department: {department}\n"
                f"Confidence: {confidence:.2%}\n"
                f"Document: {attachment_name}\n"
                f"Instruction: {instruction}\n"
            )

            mime_type, _encoding = mimetypes.guess_type(attachment_path)
            maintype, subtype = mime_type.split("/", 1) if mime_type else ("application", "octet-stream")
            with open(attachment_path, "rb") as file:
                message.add_attachment(file.read(), maintype=maintype, subtype=subtype, filename=attachment_name)

            SecureSMTPClient(self.settings).send(message, password)
            if not doc.mark_email_sent(document_id):
                raise RuntimeError("Email was sent, but the database status could not be updated.")

            logger.info(
                "Email sent document_id=%s host=%s recipients=%d",
                document_id,
                self.settings.smtp_host,
                len(recipients),
            )
            self.window.after(0, lambda: self._send_succeeded(document_id, recipients))
        except SecureSMTPError as exc:
            logger.warning("Email send failed document_id=%s reason=%s", document_id, type(exc).__name__)
            self.window.after(0, lambda error=str(exc): self._send_failed(document_id, error))
        except Exception as exc:
            logger.exception("Unexpected email failure document_id=%s", document_id)
            self.window.after(
                0,
                lambda: self._send_failed(
                    document_id,
                    "Email sending failed because of an internal system error. Contact the administrator.",
                ),
            )
        finally:
            password = ""

    def _send_succeeded(self, document_id, recipients):
        self._sending_ids.discard(document_id)
        self._clear_password()
        self.status_var.set("Email sent successfully to " + ", ".join(recipients))
        messagebox.showinfo("Email Sent", "The document was sent successfully.", parent=self.window)
        self.refresh()
        if self.on_email_sent:
            self.on_email_sent()

    def _send_failed(self, document_id, error):
        self._sending_ids.discard(document_id)
        self._clear_password()
        self.status_var.set("Email sending failed.")
        messagebox.showerror("Email Sending Failed", error, parent=self.window)
        self.refresh()


def open_email_window(
    parent,
    config_path: Optional[str] = None,
    on_email_sent: Optional[Callable[[], None]] = None,
):
    try:
        return EmailManagementWindow(
            parent=parent,
            config_path=config_path,
            on_email_sent=on_email_sent,
        )
    except EmailConfigurationError as exc:
        messagebox.showerror("Email Configuration Error", str(exc), parent=parent)
        logger.warning("Email window configuration failure: %s", exc)
        return None
    except Exception:
        logger.exception("Unable to open email management window")
        messagebox.showerror(
            "Email Management Error",
            "The email management window could not be opened. Contact the administrator.",
            parent=parent,
        )
        return None
