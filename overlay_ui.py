"""悬浮窗 UI — tkinter always-on-top 窗口，滚动历史记录"""

import tkinter as tk
from tkinter import scrolledtext, font
import threading
import logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)

BG = "#1e1e2e"
FG_TITLE = "#cdd6f4"
FG_ORIGINAL = "#6c7086"
FG_TRANSLATION = "#f5e0dc"
FG_ANSWER = "#a6e3a1"
FG_HINT = "#89b4fa"
FG_STATUS = "#f9e2af"
ACCENT = "#cba6f7"
SEPARATOR = "#45475a"
BG_ENTRY = "#252536"


class OverlayUI:
    """始终置顶的半透明悬浮窗"""

    def __init__(self):
        self._root: tk.Tk | None = None
        self._text_area: scrolledtext.ScrolledText | None = None
        self._status_var: tk.StringVar | None = None
        self._ready = threading.Event()
        self._entry_count = 0

    def start(self):
        self._root = tk.Tk()
        self._root.title("InterviewBridge")
        self._root.geometry(
            f"{config.WINDOW_WIDTH}x{config.WINDOW_HEIGHT}+{self._default_x()}+50"
        )
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", config.WINDOW_OPACITY)
        self._root.configure(bg=BG)
        self._root.minsize(400, 300)
        self._build_ui()
        self._ready.set()
        self._root.mainloop()

    def start_in_thread(self):
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        self._ready.wait(timeout=3.0)
        return thread

    def stop(self):
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 更新 — 支持翻译 ON/OFF
    # ------------------------------------------------------------------

    def update(self, explanation: str, answer_lines: list, original_text: str = ""):
        if self._root is None:
            return
        self._root.after(0, self._do_update, explanation, answer_lines, original_text)

    def _do_update(self, explanation: str, answer_lines: list, original_text: str):
        if self._text_area is None:
            return

        self._entry_count += 1
        ts = datetime.now().strftime("%H:%M:%S")
        ta = self._text_area
        ta.configure(state="normal")

        # --- header ---
        ta.insert(tk.END, f"\n{'─' * 50}\n", "separator")
        ta.insert(tk.END, f"#{self._entry_count}  {ts}\n", "meta")
        ta.insert(tk.END, "\n")

        # --- original ---
        ta.insert(tk.END, f"🎤 面试官: ", "meta")
        ta.insert(tk.END, f"{original_text}\n\n", "original")

        # --- explanation ---
        if config.ENABLE_TRANSLATION:
            ta.insert(tk.END, f"📖 翻译: ", "meta")
        else:
            ta.insert(tk.END, f"📋 要点: ", "meta")
        ta.insert(tk.END, f"{explanation}\n\n", "translation")

        # --- answer lines ---
        ta.insert(tk.END, f"💬 回答思路:\n", "meta")

        if isinstance(answer_lines, list):
            for i, line in enumerate(answer_lines):
                resp = line.get("response", "")
                extra = line.get("extra", "")

                ta.insert(tk.END, f"  {i+1}. {resp}\n", "answer")

                if extra:
                    if config.ENABLE_TRANSLATION:
                        ta.insert(tk.END, f"     {extra}\n", "original")
                    else:
                        ta.insert(tk.END, f"     {extra}\n", "answer_hint")
        else:
            # fallback: plain string
            ta.insert(tk.END, f"  {answer_lines}\n", "answer")

        ta.insert(tk.END, "\n")
        ta.configure(state="disabled")
        ta.see(tk.END)

        if self._status_var:
            self._status_var.set(f"{self._entry_count} 条记录")

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _default_x(self) -> int:
        try:
            return self._root.winfo_screenwidth() - config.WINDOW_WIDTH - 30
        except Exception:
            return 1000

    def _build_ui(self):
        # title
        tf = tk.Frame(self._root, bg=BG)
        tf.pack(fill="x", padx=12, pady=(10, 4))

        mode_tag = "翻译模式" if config.ENABLE_TRANSLATION else "思路模式"
        tk.Label(
            tf, text=f"InterviewBridge [{mode_tag}]",
            fg=ACCENT, bg=BG,
            font=font.Font(family="Microsoft YaHei", size=12, weight="bold"),
        ).pack(side="left")

        self._status_var = tk.StringVar(value="等待语音...")
        tk.Label(
            tf, textvariable=self._status_var,
            fg=FG_STATUS, bg=BG,
            font=font.Font(family="Microsoft YaHei", size=9),
        ).pack(side="right")

        # separator
        tk.Frame(self._root, height=1, bg=SEPARATOR).pack(fill="x", padx=12, pady=2)

        # hint
        hint = f"{config.SOURCE_LANGUAGE} → {config.TARGET_LANGUAGE}"
        tk.Label(
            self._root, text=f"面试官语言: {hint}  |  滚动鼠标查看历史",
            fg=FG_ORIGINAL, bg=BG,
            font=font.Font(family="Microsoft YaHei", size=8),
        ).pack(anchor="w", padx=14, pady=(2, 0))

        # scrollable text
        tf2 = tk.Frame(self._root, bg=BG)
        tf2.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self._text_area = scrolledtext.ScrolledText(
            tf2, wrap="word", bg=BG_ENTRY, fg=FG_TRANSLATION,
            insertbackground=FG_TRANSLATION,
            selectbackground=ACCENT, selectforeground=BG,
            font=font.Font(family="Microsoft YaHei", size=11),
            padx=10, pady=8, borderwidth=0, highlightthickness=0,
            state="disabled",
        )
        self._text_area.pack(fill="both", expand=True)

        # tags
        self._text_area.tag_configure(
            "original", foreground=FG_ORIGINAL,
            font=font.Font(family="Microsoft YaHei", size=10))
        self._text_area.tag_configure(
            "translation", foreground=FG_TRANSLATION,
            font=font.Font(family="Microsoft YaHei", size=11, weight="bold"))
        self._text_area.tag_configure(
            "answer", foreground=FG_ANSWER,
            font=font.Font(family="Microsoft YaHei", size=10))
        self._text_area.tag_configure(
            "answer_hint", foreground=FG_HINT,
            font=font.Font(family="Microsoft YaHei", size=9))
        self._text_area.tag_configure(
            "meta", foreground=SEPARATOR,
            font=font.Font(family="Microsoft YaHei", size=9))
        self._text_area.tag_configure(
            "separator", foreground=SEPARATOR,
            font=font.Font(family="Microsoft YaHei", size=8))

        self._text_area.bind("<MouseWheel>", self._on_mousewheel)

        # welcome
        self._text_area.configure(state="normal")
        self._text_area.insert(tk.END,
            "InterviewBridge 已就绪\n"
            "会议中对方开始说话时，回答思路会自动出现在这里。\n"
            f"当前模式: {'翻译模式' if config.ENABLE_TRANSLATION else '同语言思路模式'}\n"
        )
        self._text_area.configure(state="disabled")

    def _on_mousewheel(self, event):
        if self._text_area:
            self._text_area.yview_scroll(int(-1 * (event.delta / 120)), "units")
