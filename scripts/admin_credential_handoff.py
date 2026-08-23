"""Local-only GUI for handing an admin credential to its owner.

The plaintext password is never printed or written to disk. After the owner
confirms it has been saved, the Windows clipboard is replaced with the
Argon2id verifier that can be pasted into Render.
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


HANDOFF_TTL_MINUTES = 10


class HandoffError(ValueError):
    """Raised when the one-time handoff safety gate is not satisfied."""


@dataclass(repr=False)
class AdminCredentialHandoff:
    password: str = field(repr=False)
    encoded_hash: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    password_copied: bool = False
    confirmed: bool = False

    def __repr__(self) -> str:
        return (
            "AdminCredentialHandoff("
            f"created_at={self.created_at!r}, expires_at={self.expires_at!r}, "
            f"password_copied={self.password_copied!r}, confirmed={self.confirmed!r})"
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        checked_at = now or datetime.now(timezone.utc)
        return checked_at >= self.expires_at

    def mark_password_copied(self, now: datetime | None = None) -> None:
        if self.is_expired(now):
            raise HandoffError("handoff_expired")
        self.password_copied = True

    def confirm_saved(self, owner_confirmed: bool, now: datetime | None = None) -> None:
        if self.is_expired(now):
            raise HandoffError("handoff_expired")
        if not self.password_copied:
            raise HandoffError("password_not_copied")
        if not owner_confirmed:
            raise HandoffError("password_not_saved")
        self.confirmed = True

    def public_status(self) -> dict[str, int | str | bool]:
        return {
            "status": "ready_for_render" if self.confirmed else "pending_owner_confirmation",
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
        self.root.geometry("780x470")
        self.root.minsize(720, 440)
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
            text="3. 已安全保存，開始正式更新",
            command=self.confirm,
            state="disabled",
            style="Action.TButton",
        )
        self.confirm_button.pack(anchor="w")

        ttk.Label(card, textvariable=self.status_var, style="Status.TLabel").pack(
            anchor="w", pady=(18, 0)
        )
        ttk.Label(
            card,
            text="確認後，畫面與剪貼簿中的明文會被清除，剪貼簿改放 Render 驗證值。",
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
        self.status_var.set("密碼已複製。請先存入密碼管理器，再勾選確認。")
        self.refresh_confirm_state()

    def refresh_confirm_state(self) -> None:
        enabled = self.handoff.password_copied and self.saved_var.get()
        self.confirm_button.configure(state="normal" if enabled else "disabled")

    def confirm(self) -> None:
        try:
            self.handoff.confirm_saved(self.saved_var.get())
        except HandoffError as exc:
            self.status_var.set(f"尚未符合安全確認條件：{exc}")
            return
        self._replace_clipboard(self.handoff.encoded_hash)
        self.password_var.set("")
        self.copy_button.configure(state="disabled")
        self.saved_checkbox.configure(state="disabled")
        self.confirm_button.configure(state="disabled")
        self.status_var.set("本機交接完成；明文已清除，正在接續正式環境更新。")
        print(json.dumps(self.handoff.public_status(), ensure_ascii=False), flush=True)
        self.closed = True
        self.root.after(1200, self.root.destroy)

    def refresh_countdown(self) -> None:
        if self.closed:
            return
        remaining = int((self.handoff.expires_at - datetime.now(timezone.utc)).total_seconds())
        if remaining <= 0:
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

