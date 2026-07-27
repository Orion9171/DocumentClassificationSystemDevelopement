import json
import mimetypes
import os
import re
import smtplib
import ssl
import threading
import tkinter as tk
from dataclasses import dataclass
from email.message import EmailMessage
from tkinter import messagebox, ttk
from typing import Callable, Optional

import documents as doc
import utils as utl


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmailSettings:
    enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    sender_email: str
    use_starttls: bool
    confidence_threshold: float
    max_attachment_mb: float
    subject_prefix: str

    @classmethod
    def from_config(cls, config: dict) -> "EmailSettings":
        section = config.get("email_config", {})

        def value(key, default=None):
            if key in section:
                return section.get(key)
            return config.get(key, default)

        settings = cls(
            enabled=bool(value("enabled", True)),
            smtp_host=str(value("smtp_host", "") or "").strip(),
            smtp_port=int(value("smtp_port", 587)),
            smtp_user=str(value("smtp_user", "") or "").strip(),
            smtp_pass=str(value("smtp_pass", "") or "").replace(" ", ""),
            sender_email=str(
                value("sender_email", value("smtp_user", "")) or ""
            ).strip(),
            use_starttls=bool(value("use_starttls", True)),
            confidence_threshold=float(value("confidence_threshold", 0.8)),
            max_attachment_mb=float(value("max_attachment_mb", 15)),
            subject_prefix=str(
                value("subject_prefix", "[AI 公文分發]") or ""
            ).strip(),
        )
        settings.validate()
        return settings

    @property
    def max_attachment_bytes(self) -> int:
        return int(self.max_attachment_mb * 1024 * 1024)

    def validate(self):
        if not self.enabled:
            raise EmailConfigurationError("Email function is disabled in config.json.")

        missing = []
        if not self.smtp_host:
            missing.append("smtp_host")
        if not self.smtp_user:
            missing.append("smtp_user")
        if not self.smtp_pass:
            missing.append("smtp_pass")
        if not self.sender_email:
            missing.append("sender_email")

        if missing:
            raise EmailConfigurationError(
                "Missing email configuration: " + ", ".join(missing)
            )

        if not 1 <= self.smtp_port <= 65535:
            raise EmailConfigurationError("smtp_port must be between 1 and 65535.")

        if not EMAIL_PATTERN.match(self.sender_email):
            raise EmailConfigurationError(
                f"Invalid sender_email: {self.sender_email}"
            )

        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise EmailConfigurationError(
                "confidence_threshold must be between 0 and 1."
            )

        if self.max_attachment_mb <= 0:
            raise EmailConfigurationError("max_attachment_mb must be greater than 0.")


def _load_json_config(config_path: str) -> dict:
    return utl.load_config(config_path)


def _save_json_config(config_path: str, config: dict):
    with open(config_path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=4)


def _ensure_email_config(config: dict) -> dict:
    section = config.setdefault("email_config", {})

    # Preserve compatibility with the original top-level SMTP fields.
    for key in ("smtp_host", "smtp_port", "smtp_user", "smtp_pass", "sender_email"):
        if key not in section and key in config:
            section[key] = config[key]

    section.setdefault("enabled", True)
    section.setdefault("smtp_host", "smtp.gmail.com")
    section.setdefault("smtp_port", 587)
    section.setdefault("smtp_user", "")
    section.setdefault("smtp_pass", "")
    section.setdefault("sender_email", section.get("smtp_user", ""))
    section.setdefault("use_starttls", True)
    section.setdefault("confidence_threshold", 0.8)
    section.setdefault("max_attachment_mb", 15)
    section.setdefault("subject_prefix", "[AI 公文分發]")
    return section


def _write_runtime_email_config(config_path: str, section_values: dict):
    config = _load_json_config(config_path)
    section = _ensure_email_config(config)

    for key, value in section_values.items():
        section[key] = value

    # Mirror these values to top-level fields because the uploaded project
    # originally kept SMTP settings there.
    for key in ("smtp_host", "smtp_port", "smtp_user", "smtp_pass", "sender_email"):
        config[key] = section[key]

    _save_json_config(config_path, config)
    return EmailSettings.from_config(config)



class EmailManagementWindow:
    READY_COLUMNS = ("document", "body", "sender", "recipient", "send")
    REVIEW_COLUMNS = (
        "document",
        "department",
        "confidence",
        "recipient",
        "status",
    )

    def __init__(
        self,
        parent,
        config_path: Optional[str] = None,
        on_email_sent: Optional[Callable[[], None]] = None,
    ):
        self.parent = parent
        self.on_email_sent = on_email_sent
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.config_path = config_path or os.path.join(
            self.base_path, "config.json"
        )
        self.settings = EmailSettings.from_config(
            utl.load_config(self.config_path)
        )

        self.window = tk.Toplevel(parent)
        self.window.title("Email Management")
        self.window.geometry("1450x780")
        self.window.minsize(1050, 620)
        self.window.transient(parent)

        self._apply_black_font_style()

        self._sending_ids = set()
        self._editor = None
        self._editor_tree = None
        self._editor_item = None

        self.status_var = tk.StringVar(value="Ready")

        self.sender_email_var = tk.StringVar(value=self.settings.sender_email)
        self.smtp_user_var = tk.StringVar(value=self.settings.smtp_user)
        self.smtp_pass_var = tk.StringVar(value=self.settings.smtp_pass)
        self.smtp_host_var = tk.StringVar(value=self.settings.smtp_host)
        self.smtp_port_var = tk.StringVar(value=str(self.settings.smtp_port))
        self._show_password_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.refresh()

    def _apply_black_font_style(self):
        """
        Keep this Email Management page readable even if main.py globally sets
        ttk foreground colors to white.
        """
        style = ttk.Style(self.window)

        style.configure("Email.TFrame", background="#F3F4F6")
        style.configure("Email.TLabel", background="#F3F4F6", foreground="#000000")
        style.configure("Email.TLabelframe", background="#F3F4F6", foreground="#000000")
        style.configure("Email.TLabelframe.Label", foreground="#000000")
        style.configure("Email.TButton", foreground="#000000")
        style.configure("Email.TCheckbutton", background="#F3F4F6", foreground="#000000")
        style.configure("Email.Treeview", foreground="#000000", background="#FFFFFF", fieldbackground="#FFFFFF")
        style.configure("Email.Treeview.Heading", foreground="#000000", background="#E5E7EB")

    def _build_ui(self):
        header = ttk.Frame(self.window, style="Email.TFrame")
        header.pack(fill="x", padx=12, pady=(12, 6))

        ttk.Label(
            header,
            style="Email.TLabel",
            text="Email Document Dispatch",
            font=("Arial", 16, "bold"),
        ).pack(side="left")

        ttk.Label(
            header,
            style="Email.TLabel",
            text=f"Minimum confidence: {self.settings.confidence_threshold:.0%}",
        ).pack(side="left", padx=24)

        ttk.Button(
            header,
            style="Email.TButton",
            text="Refresh",
            command=self.refresh,
        ).pack(side="right")

        settings_group = ttk.LabelFrame(
            self.window,
            style="Email.TLabelframe",
            text="Sender / SMTP Settings",
            padding=8,
        )
        settings_group.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Label(settings_group, text="SMTP Host", style="Email.TLabel").grid(
            row=0, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(
            settings_group,
            textvariable=self.smtp_host_var,
            width=28,
        ).grid(row=0, column=1, sticky="we", padx=5, pady=3)

        ttk.Label(settings_group, text="SMTP Port", style="Email.TLabel").grid(
            row=0, column=2, sticky="w", padx=5, pady=3
        )
        ttk.Entry(
            settings_group,
            textvariable=self.smtp_port_var,
            width=8,
        ).grid(row=0, column=3, sticky="w", padx=5, pady=3)

        ttk.Label(settings_group, text="Sender Email", style="Email.TLabel").grid(
            row=1, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(
            settings_group,
            textvariable=self.sender_email_var,
            width=36,
        ).grid(row=1, column=1, sticky="we", padx=5, pady=3)

        ttk.Label(settings_group, text="SMTP User", style="Email.TLabel").grid(
            row=1, column=2, sticky="w", padx=5, pady=3
        )
        ttk.Entry(
            settings_group,
            textvariable=self.smtp_user_var,
            width=36,
        ).grid(row=1, column=3, sticky="we", padx=5, pady=3)

        ttk.Label(settings_group, text="SMTP Pass", style="Email.TLabel").grid(
            row=2, column=0, sticky="w", padx=5, pady=3
        )
        self.smtp_pass_entry = ttk.Entry(
            settings_group,
            textvariable=self.smtp_pass_var,
            width=36,
            show="*",
        )
        self.smtp_pass_entry.grid(row=2, column=1, sticky="we", padx=5, pady=3)

        ttk.Checkbutton(
            settings_group,
            text="Show",
            style="Email.TCheckbutton",
            variable=self._show_password_var,
            command=self._toggle_password_visibility,
        ).grid(row=2, column=2, sticky="w", padx=5, pady=3)

        ttk.Button(
            settings_group,
            text="Save SMTP Settings",
            style="Email.TButton",
            command=self.save_smtp_settings,
        ).grid(row=2, column=3, sticky="e", padx=5, pady=3)

        settings_group.columnconfigure(1, weight=1)
        settings_group.columnconfigure(3, weight=1)

        ready_group = ttk.LabelFrame(
            self.window,
            style="Email.TLabelframe",
            text="Ready To Send",
            padding=8,
        )
        ready_group.pack(fill="both", expand=True, padx=12, pady=(4, 8))

        self.ready_tree = self._build_tree(
            ready_group,
            columns=self.READY_COLUMNS,
            headings={
                "document": "Document Name",
                "body": "Document Body",
                "sender": "Sender Email",
                "recipient": "Recipient Email",
                "send": "Send",
            },
            widths={
                "document": 220,
                "body": 450,
                "sender": 230,
                "recipient": 260,
                "send": 90,
            },
        )
        self.ready_tree.tag_configure("ready", background="#E9F8EE")
        self.ready_tree.tag_configure("sending", background="#E7F0FF")
        self.ready_tree.bind("<Double-1>", self._on_ready_double_click)
        self.ready_tree.bind("<ButtonRelease-1>", self._on_ready_click)

        review_group = ttk.LabelFrame(
            self.window,
            style="Email.TLabelframe",
            text="Manual Review",
            padding=8,
        )
        review_group.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.review_tree = self._build_tree(
            review_group,
            columns=self.REVIEW_COLUMNS,
            headings={
                "document": "Document",
                "department": "Department",
                "confidence": "Confidence",
                "recipient": "Recipient",
                "status": "Status",
            },
            widths={
                "document": 260,
                "department": 220,
                "confidence": 120,
                "recipient": 300,
                "status": 250,
            },
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
            text=(
                "Double-click Recipient Email/Recipient to edit. "
                "Only Ready To Send rows can be sent."
            ),
        ).pack(side="left", padx=18)
        ttk.Button(
            footer,
            style="Email.TButton",
            text="Close",
            command=self.window.destroy,
        ).pack(side="right")

    def _toggle_password_visibility(self):
        self.smtp_pass_entry.configure(
            show="" if self._show_password_var.get() else "*"
        )

    def save_smtp_settings_without_popup(self):
        smtp_host = self.smtp_host_var.get().strip()
        sender_email = self.sender_email_var.get().strip()
        smtp_user = self.smtp_user_var.get().strip()
        smtp_pass = self.smtp_pass_var.get().strip().replace(" ", "")

        try:
            smtp_port = int(self.smtp_port_var.get().strip())
        except ValueError as exc:
            raise EmailConfigurationError("SMTP Port must be a number.") from exc

        self.settings = _write_runtime_email_config(
            self.config_path,
            {
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "smtp_user": smtp_user,
                "smtp_pass": smtp_pass,
                "sender_email": sender_email,
            },
        )

    def save_smtp_settings(self):
        try:
            self.save_smtp_settings_without_popup()
        except Exception as exc:
            messagebox.showerror(
                "SMTP Settings Error",
                str(exc),
                parent=self.window,
            )
            return

        self.sender_email_var.set(self.settings.sender_email)
        self.smtp_user_var.set(self.settings.smtp_user)
        self.smtp_pass_var.set(self.settings.smtp_pass)
        self.smtp_host_var.set(self.settings.smtp_host)
        self.smtp_port_var.set(str(self.settings.smtp_port))

        messagebox.showinfo(
            "Saved",
            "SMTP settings have been saved to config.json.",
            parent=self.window,
        )
        self.refresh()

    @staticmethod
    def _build_tree(parent, columns, headings, widths):
        container = ttk.Frame(parent, style="Email.TFrame")
        container.pack(fill="both", expand=True)

        tree = ttk.Treeview(
            container,
            style="Email.Treeview",
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(
                column,
                width=widths[column],
                minwidth=70,
                anchor="center"
                if column in {"confidence", "status", "send"}
                else "w",
                stretch=column in {"body", "recipient"},
            )

        y_scroll = ttk.Scrollbar(
            container,
            orient="vertical",
            command=tree.yview,
        )
        x_scroll = ttk.Scrollbar(
            container,
            orient="horizontal",
            command=tree.xview,
        )
        tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        return tree

    def refresh(self):
        if self._sending_ids:
            messagebox.showinfo(
                "Email Sending",
                "Please wait until the current email has finished sending.",
                parent=self.window,
            )
            return

        self._close_editor(save=False)

        for tree in (self.ready_tree, self.review_tree):
            for item in tree.get_children():
                tree.delete(item)

        ready_count = 0
        review_count = 0

        for row in doc.get_documents_for_email():
            (
                document_id,
                di_filename,
                pdf_filename,
                folder_path,
                instruction,
                department,
                confidence,
                recipient_email,
                email_sent,
            ) = row

            confidence_value = float(confidence or 0.0)
            recipient = (recipient_email or "").strip()
            valid_recipient = self._valid_recipient_list(recipient)
            attachment_name = (
                pdf_filename
                or di_filename
                or f"Document {document_id}"
            )

            if (
                confidence_value >= self.settings.confidence_threshold
                and valid_recipient
            ):
                self.ready_tree.insert(
                    "",
                    "end",
                    iid=str(document_id),
                    values=(
                        attachment_name,
                        self._single_line(instruction or "", 320),
                        self.settings.sender_email,
                        recipient,
                        "Send",
                    ),
                    tags=("ready",),
                )
                ready_count += 1
            else:
                if not valid_recipient:
                    status = "Recipient missing or invalid"
                    tag = "missing"
                else:
                    status = (
                        "Confidence below threshold; manual review required"
                    )
                    tag = "review"

                self.review_tree.insert(
                    "",
                    "end",
                    iid=str(document_id),
                    values=(
                        attachment_name,
                        department or "",
                        f"{confidence_value:.2%}",
                        recipient,
                        status,
                    ),
                    tags=(tag,),
                )
                review_count += 1

        self.status_var.set(
            f"Ready: {ready_count}    Manual review: {review_count}"
        )

    @staticmethod
    def _single_line(value: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value)).strip()
        if len(text) > limit:
            return text[: limit - 1] + "…"
        return text

    def _on_ready_double_click(self, event):
        self._handle_recipient_edit(
            tree=self.ready_tree,
            columns=self.READY_COLUMNS,
            recipient_column_name="recipient",
            event=event,
        )

    def _on_review_double_click(self, event):
        self._handle_recipient_edit(
            tree=self.review_tree,
            columns=self.REVIEW_COLUMNS,
            recipient_column_name="recipient",
            event=event,
        )

    def _handle_recipient_edit(
        self,
        tree,
        columns,
        recipient_column_name,
        event,
    ):
        region = tree.identify_region(event.x, event.y)
        item_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)

        if region != "cell" or not item_id:
            return

        recipient_column = (
            f"#{columns.index(recipient_column_name) + 1}"
        )
        if column_id != recipient_column:
            return

        self._open_recipient_editor(
            tree=tree,
            columns=columns,
            item_id=item_id,
            column_id=column_id,
        )

    def _open_recipient_editor(
        self,
        tree,
        columns,
        item_id,
        column_id,
    ):
        self._close_editor(save=False)

        bbox = tree.bbox(item_id, column_id)
        if not bbox:
            return

        x, y, width, height = bbox
        current_values = tree.item(item_id, "values")
        current_email = current_values[columns.index("recipient")]

        editor = ttk.Entry(tree)
        editor.insert(0, current_email)
        editor.select_range(0, "end")
        editor.focus_set()
        editor.place(x=x, y=y, width=width, height=height)

        self._editor = editor
        self._editor_tree = tree
        self._editor_item = item_id

        editor.bind("<Return>", lambda _event: self._close_editor(save=True))
        editor.bind("<Escape>", lambda _event: self._close_editor(save=False))
        editor.bind("<FocusOut>", lambda _event: self._close_editor(save=True))

    def _close_editor(self, save):
        if self._editor is None:
            return

        editor = self._editor
        item_id = self._editor_item

        self._editor = None
        self._editor_tree = None
        self._editor_item = None

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
                (
                    "Enter one or more valid email addresses separated "
                    "by commas or semicolons."
                ),
                parent=self.window,
            )
            return

        doc.update_document_email(int(item_id), new_email)
        self.refresh()

    def _on_ready_click(self, event):
        if self._editor is not None:
            return

        region = self.ready_tree.identify_region(event.x, event.y)
        item_id = self.ready_tree.identify_row(event.y)
        column_id = self.ready_tree.identify_column(event.x)

        if region != "cell" or not item_id:
            return

        send_column = f"#{self.READY_COLUMNS.index('send') + 1}"
        if column_id != send_column:
            return

        values = self.ready_tree.item(item_id, "values")
        if values[self.READY_COLUMNS.index("send")] != "Send":
            return

        self._start_send(int(item_id))

    @staticmethod
    def _split_recipients(raw: str):
        return [
            value.strip()
            for value in re.split(r"[;,\s、]+", raw or "")
            if value.strip()
        ]

    def _valid_recipient_list(self, raw: str) -> bool:
        recipients = self._split_recipients(raw)
        return bool(recipients) and all(
            EMAIL_PATTERN.match(address) for address in recipients
        )

    def _resolve_attachment(self, row):
        (
            _document_id,
            di_filename,
            pdf_filename,
            folder_path,
            _instruction,
            _department,
            _confidence,
            _email,
            _email_sent,
        ) = row

        candidates = []
        for filename in (pdf_filename, di_filename):
            if not filename:
                continue

            if os.path.isabs(filename):
                candidates.append(filename)

            if folder_path:
                candidates.append(os.path.join(folder_path, filename))
                candidates.append(
                    os.path.join(self.base_path, folder_path, filename)
                )

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
            messagebox.showerror(
                "SMTP Settings Error",
                str(exc),
                parent=self.window,
            )
            return

        row = doc.get_document_for_email(document_id)
        if row is None:
            messagebox.showerror(
                "Document Not Found",
                "This document no longer exists in the database.",
                parent=self.window,
            )
            self.refresh()
            return

        (
            _document_id,
            _di_filename,
            pdf_filename,
            _folder_path,
            instruction,
            department,
            confidence,
            recipient_email,
            email_sent,
        ) = row

        if email_sent:
            messagebox.showinfo(
                "Already Sent",
                "This document has already been emailed.",
                parent=self.window,
            )
            self.refresh()
            return

        confidence_value = float(confidence or 0.0)
        if confidence_value < self.settings.confidence_threshold:
            messagebox.showwarning(
                "Manual Review Required",
                (
                    f"Confidence {confidence_value:.2%} is below "
                    f"{self.settings.confidence_threshold:.2%}."
                ),
                parent=self.window,
            )
            self.refresh()
            return

        recipient = (recipient_email or "").strip()
        if not self._valid_recipient_list(recipient):
            messagebox.showerror(
                "Invalid Recipient",
                "Enter a valid recipient address first.",
                parent=self.window,
            )
            self.refresh()
            return

        attachment_path = self._resolve_attachment(row)
        if not attachment_path:
            messagebox.showerror(
                "Attachment Not Found",
                (
                    "Neither the PDF nor the DI attachment could be found "
                    "from folder_path."
                ),
                parent=self.window,
            )
            return

        attachment_size = os.path.getsize(attachment_path)
        if attachment_size > self.settings.max_attachment_bytes:
            messagebox.showerror(
                "Attachment Too Large",
                (
                    f"The attachment is "
                    f"{attachment_size / 1024 / 1024:.2f} MB. "
                    f"The configured limit is "
                    f"{self.settings.max_attachment_mb:.2f} MB."
                ),
                parent=self.window,
            )
            return

        display_name = pdf_filename or os.path.basename(attachment_path)
        if not messagebox.askyesno(
            "Confirm Email",
            (
                f"Document: {display_name}\n"
                f"Department: {department or ''}\n"
                f"Confidence: {confidence_value:.2%}\n"
                f"From: {self.settings.sender_email}\n"
                f"To: {recipient}\n\n"
                "Send this document now?"
            ),
            parent=self.window,
        ):
            return

        self._sending_ids.add(document_id)
        self._set_ready_row_sending(document_id)
        self.status_var.set(f"Sending {display_name}...")

        threading.Thread(
            target=self._send_worker,
            args=(
                document_id,
                row,
                attachment_path,
                self._split_recipients(recipient),
                instruction or "",
            ),
            daemon=True,
            name=f"email-send-{document_id}",
        ).start()

    def _set_ready_row_sending(self, document_id):
        item_id = str(document_id)
        if not self.ready_tree.exists(item_id):
            return

        values = list(self.ready_tree.item(item_id, "values"))
        values[self.READY_COLUMNS.index("send")] = "Sending..."
        self.ready_tree.item(
            item_id,
            values=values,
            tags=("sending",),
        )

    def _send_worker(
        self,
        document_id,
        row,
        attachment_path,
        recipients,
        instruction,
    ):
        try:
            department = row[5] or ""
            confidence = float(row[6] or 0.0)
            attachment_name = os.path.basename(attachment_path)

            message = EmailMessage()
            message["From"] = self.settings.sender_email
            message["To"] = ", ".join(recipients)
            message["Subject"] = (
                f"{self.settings.subject_prefix} "
                f"{department} - {attachment_name}"
            ).strip()

            message.set_content(
                "This document was classified by the AI document "
                "dispatch system.\n\n"
                f"Department: {department}\n"
                f"Confidence: {confidence:.2%}\n"
                f"Document: {attachment_name}\n"
                f"Instruction: {instruction}\n"
            )

            mime_type, _encoding = mimetypes.guess_type(attachment_path)
            if mime_type:
                maintype, subtype = mime_type.split("/", 1)
            else:
                maintype, subtype = "application", "octet-stream"

            with open(attachment_path, "rb") as file:
                message.add_attachment(
                    file.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=attachment_name,
                )

            context = ssl.create_default_context()
            with smtplib.SMTP(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=30,
            ) as server:
                server.ehlo()
                if self.settings.use_starttls:
                    server.starttls(context=context)
                    server.ehlo()
                server.login(
                    self.settings.smtp_user,
                    self.settings.smtp_pass,
                )
                server.send_message(message)

            doc.mark_email_sent(document_id)
            self.window.after(
                0,
                lambda: self._send_succeeded(document_id, recipients),
            )
        except Exception as exc:
            self.window.after(
                0,
                lambda error=str(exc): self._send_failed(
                    document_id,
                    error,
                ),
            )

    def _send_succeeded(self, document_id, recipients):
        self._sending_ids.discard(document_id)
        self.status_var.set(
            "Email sent successfully to " + ", ".join(recipients)
        )
        messagebox.showinfo(
            "Email Sent",
            "The document was sent successfully.",
            parent=self.window,
        )
        self.refresh()
        if self.on_email_sent:
            self.on_email_sent()

    def _send_failed(self, document_id, error):
        self._sending_ids.discard(document_id)
        self.status_var.set("Email sending failed.")
        messagebox.showerror(
            "Email Sending Failed",
            error,
            parent=self.window,
        )
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
    except (
        EmailConfigurationError,
        FileNotFoundError,
        ValueError,
        KeyError,
    ) as exc:
        messagebox.showerror(
            "Email Configuration Error",
            str(exc),
            parent=parent,
        )
        return None
