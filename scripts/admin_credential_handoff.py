"""Local-only GUI for handing an admin credential to its owner.

The plaintext password is never printed or written to disk. The window remains
open after the Render verifier is copied so the owner can copy the real login
password again after deployment. Secrets are cleared only after login succeeds.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tianwai.security import (  # noqa: E402
    ADMIN_PASSWORD_ENTROPY_BITS,
    generate_admin_password,
    hash_admin_password,
    verify_admin_password,
)


HANDOFF_TTL_MINUTES = 30


class HandoffError(ValueError):
    """Raised when the one-time handoff safety gate is not satisfied."""


@dataclass(repr=False)
class AdminCredentialHandoff:
    password: str = field(repr=False)
    encoded_hash: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    password_copied: bool = False
    hash_copied: bool = False
    completed: bool = False

    def __repr__(self) -> str:
        return (
            "AdminCredentialHandoff("
            f"created_at={self.created_at!r}, expires_at={self.expires_at!r}, "
            f"password_copied={self.password_copied!r}, hash_copied={self.hash_copied!r}, "
            f"completed={self.completed!r})"
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        checked_at = now or datetime.now(timezone.utc)
        return checked_at >= self.expires_at

    def mark_password_copied(self, now: datetime | None = None) -> None:
        if self.is_expired(now):
            raise HandoffError("handoff_expired")
        self.password_copied = True

    def mark_hash_copied(self, owner_confirmed: bool, now: datetime | None = None) -> None:
        if self.is_expired(now):
            raise HandoffError("handoff_expired")
        if not self.password_copied:
            raise HandoffError("password_not_copied")
        if not owner_confirmed:
            raise HandoffError("password_not_saved")
        self.hash_copied = True

    def mark_completed(self) -> None:
        if not self.hash_copied:
            raise HandoffError("render_hash_not_copied")
        self.completed = True

    def public_status(self) -> dict[str, int | str | bool]:
        if self.completed:
            status = "completed"
        elif self.hash_copied:
            status = "ready_for_render"
        else:
            status = "pending_owner_confirmation"
        return {
            "status": status,
            "length": len(self.password),
            "entropy_bits": ADMIN_PASSWORD_ENTROPY_BITS,
            "argon2id": self.encoded_hash.startswith("$argon2id$"),
        }


def create_handoff(now: datetime | None = None) -> AdminCredentialHandoff:
    created_at = now or datetime.now(timezone.utc)
    password = generate_admin_password()
    encoded_hash = hash_admin_password(password)
    if not verify_admin_password(password, encoded_hash):
        raise RuntimeError("generated_credential_verification_failed")
    return AdminCredentialHandoff(
        password=password,
        encoded_hash=encoded_hash,
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=HANDOFF_TTL_MINUTES),
    )


class CredentialHandoffWindow:
    def __init__(self, handoff: AdminCredentialHandoff) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.handoff = handoff
        self.closed = False
        self.root = tk.Tk()
        self.root.title("天外一筆｜管理員密碼安全更新")
        self.root.geometry("820x560")
        self.root.minsize(760, 520)
        self.root.configure(bg="#0d1130")
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)
        self.root.attributes("-topmost", True)
        self.root.after(1200, lambda: self.root.attributes("-topmost", False))

        self.password_var = tk.StringVar(value=handoff.password)
        self.saved_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="請先複製密碼並保存到密碼管理器。")
        self.countdown_var = tk.StringVar()

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Main.TFrame", background="#0d1130")
        style.configure("Card.TFrame", background="#f4eed9")
        style.configure(
            "Title.TLabel",
            background="#0d1130",
            foreground="#f1d58b",
            font=("Microsoft JhengHei UI", 22, "bold"),
        )
        style.configure(
            "Body.TLabel",
            background="#f4eed9",
            foreground="#28223a",
            font=("Microsoft JhengHei UI", 11),
        )
        style.configure(
            "Status.TLabel",
            background="#f4eed9",
            foreground="#8e3f35",
            font=("Microsoft JhengHei UI", 11, "bold"),
        )
        style.configure(
            "Action.TButton",
            font=("Microsoft JhengHei UI", 11, "bold"),
            padding=(16, 10),
        )
        style.configure(
            "Confirm.TCheckbutton",
            background="#f4eed9",
            foreground="#28223a",
            font=("Microsoft JhengHei UI", 11, "bold"),
        )

        outer = ttk.Frame(self.root, style="Main.TFrame", padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="管理員憑證一次性交接", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="新密碼只在這台電腦顯示；不會傳到 LINE、Gmail、Chat 或寫入專案。",
            background="#0d1130",
            foreground="#c7d6d3",
            font=("Microsoft JhengHei UI", 11),
        ).pack(anchor="w", pady=(8, 20))

        card = ttk.Frame(outer, style="Card.TFrame", padding=24)
        card.pack(fill="both", expand=True)
        ttk.Label(
            card,
            text="43 位 Base64url｜256-bit 安全亂數｜正式站只保存 Argon2id 驗證值",
            style="Body.TLabel",
        ).pack(anchor="w")

        password_entry = ttk.Entry(
            card,
            textvariable=self.password_var,
            state="readonly",
            font=("Cascadia Mono", 14, "bold"),
            justify="center",
        )
        password_entry.pack(fill="x", pady=(16, 12), ipady=10)

        buttons = ttk.Frame(card, style="Card.TFrame")
        buttons.pack(fill="x")
        self.copy_button = ttk.Button(
            buttons,
            text="1. 複製新密碼",
            command=self.copy_password,
            style="Action.TButton",
        )
        self.copy_button.pack(side="left")
        ttk.Label(
            buttons,
            textvariable=self.countdown_var,
            style="Status.TLabel",
        ).pack(side="right")

        self.saved_checkbox = ttk.Checkbutton(
            card,
            text="2. 我已將新密碼存入密碼管理器",
            variable=self.saved_var,
            command=self.refresh_confirm_state,
            style="Confirm.TCheckbutton",
        )
        self.saved_checkbox.pack(anchor="w", pady=(22, 12))

        self.confirm_button = ttk.Button(
            card,
            text="3. 複製 Render 驗證值",
            command=self.copy_render_hash,
            state="disabled",
            style="Action.TButton",
        )
        self.confirm_button.pack(anchor="w")

        self.finish_button = ttk.Button(
            card,
            text="4. 新密碼已登入成功，清除並關閉",
            command=self.complete,
            state="disabled",
            style="Action.TButton",
        )
        self.finish_button.pack(anchor="w", pady=(10, 0))

        ttk.Label(card, textvariable=self.status_var, style="Status.TLabel").pack(
            anchor="w", pady=(18, 0)
        )
        ttk.Label(
            card,
            text="視窗會保持開啟；Render 上線後可再按第 1 步複製真正登入密碼。",
            style="Body.TLabel",
        ).pack(anchor="w", pady=(8, 0))

        self.root.after(250, self.refresh_countdown)

    def _replace_clipboard(self, value: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self.root.update()

    def _clear_sensitive_clipboard(self) -> None:
        try:
            current = self.root.clipboard_get()
        except self.tk.TclError:
            return
        if current in {self.handoff.password, self.handoff.encoded_hash}:
            self.root.clipboard_clear()
            self.root.update()

    def copy_password(self) -> None:
        try:
            self.handoff.mark_password_copied()
        except HandoffError:
            self.expire()
            return
        self._replace_clipboard(self.handoff.password)
        if self.handoff.hash_copied:
            self.status_var.set("真正登入密碼已重新複製。請貼到正式登入頁驗收。")
        else:
            self.status_var.set("密碼已複製。請保存後再複製 Render 驗證值。")
        self.refresh_confirm_state()

    def refresh_confirm_state(self) -> None:
        enabled = self.handoff.password_copied and self.saved_var.get()
        self.confirm_button.configure(state="normal" if enabled else "disabled")

    def copy_render_hash(self) -> None:
        try:
            self.handoff.mark_hash_copied(self.saved_var.get())
        except HandoffError as exc:
            self.status_var.set(f"尚未符合安全確認條件：{exc}")
            return
        self._replace_clipboard(self.handoff.encoded_hash)
        self.saved_checkbox.configure(state="disabled")
        self.confirm_button.configure(text="Render 驗證值已複製（可再次複製）")
        self.finish_button.configure(state="normal")
        self.status_var.set("Render 驗證值已複製。視窗不會關閉；部署後請再複製登入密碼。")
        print(json.dumps(self.handoff.public_status(), ensure_ascii=False), flush=True)

    def complete(self) -> None:
        try:
            self.handoff.mark_completed()
        except HandoffError as exc:
            self.status_var.set(f"尚未完成登入驗收：{exc}")
            return
        self._clear_sensitive_clipboard()
        self.password_var.set("")
        print(json.dumps(self.handoff.public_status(), ensure_ascii=False), flush=True)
        self.closed = True
        self.root.after(1200, self.root.destroy)

    def refresh_countdown(self) -> None:
        if self.closed:
            return
        remaining = int((self.handoff.expires_at - datetime.now(timezone.utc)).total_seconds())
        if remaining <= 0:
            if self.handoff.hash_copied:
                self.countdown_var.set("等待正式登入驗收")
                self.status_var.set("已超過 30 分鐘；為避免鎖死，密碼仍保留到你確認登入成功。")
                return
            self.expire()
            return
        minutes, seconds = divmod(remaining, 60)
        self.countdown_var.set(f"有效時間 {minutes:02d}:{seconds:02d}")
        self.root.after(1000, self.refresh_countdown)

    def expire(self) -> None:
        if self.closed:
            return
        self._clear_sensitive_clipboard()
        self.password_var.set("")
        self.closed = True
        print(json.dumps({"status": "expired"}), flush=True)
        self.root.destroy()

    def cancel(self) -> None:
        if self.closed:
            return
        if self.handoff.hash_copied and not self.handoff.completed:
            from tkinter import messagebox

            should_close = messagebox.askyesno(
                "尚未完成登入驗收",
                "Render 驗證值已交付。現在關閉可能失去真正登入密碼並造成鎖定。\n\n"
                "確定仍要關閉嗎？",
                parent=self.root,
            )
            if not should_close:
                return
        self._clear_sensitive_clipboard()
        self.password_var.set("")
        self.closed = True
        print(json.dumps({"status": "cancelled"}), flush=True)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    handoff = create_handoff()
    window = CredentialHandoffWindow(handoff)
    window.run()


if __name__ == "__main__":
    main()
