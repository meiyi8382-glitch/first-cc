import ctypes
import datetime
import json
import os
import time
import tkinter as tk
from tkinter import messagebox

try:
    import winsound

    def play_sound():
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
        try:
            winsound.Beep(880, 250)
            winsound.Beep(1108, 350)
        except Exception:
            pass

except ImportError:

    def play_sound():
        print("\a", end="")


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pomodoro_config.json")
STATS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pomodoro_stats.json")
PREFS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pomodoro_prefs.json")

DEFAULT_CONFIG = {
    "work_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "sessions_before_long_break": 4,
}

DEFAULT_PREFS = {
    "always_on_top": False,
}

PHASES = ("work", "short_break", "long_break")

PHASE_META = {
    "work": {"label": "专注", "color": "#e63946"},
    "short_break": {"label": "短休息", "color": "#ff6b6b"},
    "long_break": {"label": "长休息", "color": "#c1121f"},
}

# 红白配色
BG = "#ffffff"
TEXT = "#1f1f1f"
MUTED = "#9aa0a6"
ACCENT = "#e63946"
ACCENT_DARK = "#c62828"
ACCENT_TINT = "#fdecec"
RING_BG = "#f1f3f4"
DOT_BG = "#e3e6e8"
BORDER = "#f0b8b8"


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    saved = load_json(CONFIG_PATH, {})
    if isinstance(saved, dict):
        cfg.update({k: v for k, v in saved.items() if k in DEFAULT_CONFIG})
    return cfg


def save_config(cfg):
    save_json(CONFIG_PATH, cfg)


def load_stats():
    data = load_json(STATS_PATH, None)
    if isinstance(data, dict) and "days" in data:
        return data
    return {"days": {}}


def save_stats(stats):
    save_json(STATS_PATH, stats)


def load_prefs():
    prefs = dict(DEFAULT_PREFS)
    saved = load_json(PREFS_PATH, {})
    if isinstance(saved, dict):
        prefs.update({k: v for k, v in saved.items() if k in DEFAULT_PREFS})
    return prefs


def save_prefs(prefs):
    save_json(PREFS_PATH, prefs)


def record_session(stats, task_name, minutes):
    today = datetime.date.today().isoformat()
    day = stats["days"].setdefault(today, {"count": 0, "minutes": 0, "tasks": []})
    day["count"] += 1
    day["minutes"] += minutes
    day["tasks"].append({"name": task_name or "未命名任务", "minutes": minutes})
    save_stats(stats)


class PomodoroApp:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.stats = load_stats()
        self.prefs = load_prefs()

        self.completed_in_cycle = 0
        self.phase = "work"

        self.remaining = self.phase_duration()
        self.running = False
        self._start_time = 0.0
        self._remaining_at_start = 0.0
        self._after_id = None

        self._build_ui()
        self.root.attributes("-topmost", self.prefs["always_on_top"])
        self._render()

    # ---- config / phase helpers ----
    def phase_duration(self):
        key = {
            "work": "work_minutes",
            "short_break": "short_break_minutes",
            "long_break": "long_break_minutes",
        }[self.phase]
        return int(self.cfg[key]) * 60

    def total_seconds(self):
        return self.phase_duration()

    def next_phase(self):
        if self.phase == "work":
            self.completed_in_cycle += 1
            if self.completed_in_cycle % int(self.cfg["sessions_before_long_break"]) == 0:
                return "long_break"
            return "short_break"
        return "work"

    # ---- ui ----
    def _build_ui(self):
        self.root.title("番茄钟")
        self.root.configure(bg=BG)
        self.root.minsize(500, 720)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        tk.Frame(self.root, bg=ACCENT, height=4).pack(fill="x", side="top")

        self.phase_label = tk.Label(self.root, text="", bg=BG, fg=ACCENT, font=("Segoe UI", 22, "bold"))
        self.phase_label.pack(pady=(28, 0))

        self.cycle_label = tk.Label(self.root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 12))
        self.cycle_label.pack(pady=(6, 10))

        task_frame = tk.Frame(self.root, bg=BG)
        task_frame.pack(pady=(0, 6))
        self.task_var = tk.StringVar(value="")
        tk.Label(task_frame, text="任务：", bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(side="left")
        self.task_entry = tk.Entry(
            task_frame, textvariable=self.task_var, width=24, justify="center",
            bg="#fafafa", fg=TEXT, insertbackground=ACCENT,
            relief="flat", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            font=("Segoe UI", 11),
        )
        self.task_entry.pack(side="left")

        self.canvas = tk.Canvas(self.root, width=460, height=460, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=8)
        self.canvas.bind("<Configure>", lambda e: self._render())

        self.time_text = self.canvas.create_text(230, 230, text="", fill=TEXT, font=("Consolas", -88, "bold"))

        self.dots_frame = tk.Frame(self.root, bg=BG)
        self.dots_frame.pack(pady=6)
        self.dots = []

        buttons = tk.Frame(self.root, bg=BG)
        buttons.pack(pady=22)

        self.start_btn = tk.Button(
            buttons, text="开始", command=self.toggle, width=10,
            bg=ACCENT, fg="white", activebackground=ACCENT_DARK, activeforeground="white",
            relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 13, "bold"), padx=10, pady=10,
        )
        self.start_btn.grid(row=0, column=0, padx=6)

        self.skip_btn = tk.Button(
            buttons, text="跳过", command=self.skip, width=7,
            bg=BG, fg=ACCENT, activebackground=ACCENT_TINT, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            font=("Segoe UI", 12), padx=10, pady=10,
        )
        self.skip_btn.grid(row=0, column=1, padx=6)

        self.reset_btn = tk.Button(
            buttons, text="重置", command=self.reset, width=7,
            bg=BG, fg=ACCENT, activebackground=ACCENT_TINT, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            font=("Segoe UI", 12), padx=10, pady=10,
        )
        self.reset_btn.grid(row=0, column=2, padx=6)

        bottom_frame = tk.Frame(self.root, bg=BG)
        bottom_frame.pack(pady=(0, 22))

        self.settings_btn = tk.Button(
            bottom_frame, text="设置", command=self.open_settings,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 10),
        )
        self.settings_btn.pack(side="left", padx=10)

        self.stats_btn = tk.Button(
            bottom_frame, text="统计", command=self.open_stats,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 10),
        )
        self.stats_btn.pack(side="left", padx=10)

        self.topmost_var = tk.BooleanVar(value=self.prefs["always_on_top"])
        self.topmost_check = tk.Checkbutton(
            bottom_frame, text="窗口置顶", variable=self.topmost_var, command=self.toggle_topmost,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=ACCENT,
            selectcolor=BG, relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 10),
        )
        self.topmost_check.pack(side="left", padx=10)

    def toggle_topmost(self):
        value = bool(self.topmost_var.get())
        self.prefs["always_on_top"] = value
        self.root.attributes("-topmost", value)
        save_prefs(self.prefs)

    # ---- timer ----
    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def start(self):
        if self.running or self.remaining <= 0:
            self.remaining = self.total_seconds()
        self.running = True
        self._start_time = time.monotonic()
        self._remaining_at_start = self.remaining
        self._tick()
        self._render()

    def pause(self):
        if not self.running:
            return
        self.remaining = self._time_left()
        self.running = False
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._render()

    def reset(self):
        self.running = False
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.remaining = self.total_seconds()
        self._render()

    def skip(self):
        self._advance()

    def _time_left(self):
        return max(0.0, self._remaining_at_start - (time.monotonic() - self._start_time))

    def _tick(self):
        left = self._time_left()
        if left <= 0:
            self.remaining = 0
            self._finish()
            return
        self.remaining = left
        self._render()
        self._after_id = self.root.after(200, self._tick)

    def _finish(self):
        self.running = False
        self._after_id = None
        play_sound()
        self._flash()
        finished = self.phase
        if finished == "work":
            minutes = int(self.cfg["work_minutes"])
            record_session(self.stats, self.task_var.get().strip(), minutes)
        self.phase = self.next_phase()
        self.remaining = self.total_seconds()
        self._render()
        self._notify(finished)

    def _advance(self):
        self.running = False
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.phase = self.next_phase()
        self.remaining = self.total_seconds()
        self._render()

    def _flash(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(1500, lambda: self.root.attributes("-topmost", False))

    def _notify(self, finished_phase):
        finished_label = PHASE_META[finished_phase]["label"]
        next_label = PHASE_META[self.phase]["label"]
        messagebox.showinfo("番茄钟", f"{finished_label}结束，接下来是：{next_label}")

    # ---- rendering ----
    def _render(self):
        meta = PHASE_META[self.phase]
        color = meta["color"]

        self.phase_label.config(text=meta["label"], fg=color)

        sessions = int(self.cfg["sessions_before_long_break"])
        self.cycle_label.config(text=f"本轮已完成 {self.completed_in_cycle} / {sessions} 个番茄")

        self.start_btn.config(text="暂停" if self.running else "开始")

        self._render_ring(color)
        self._render_dots(color)
        self._render_time()

    def _render_ring(self, color):
        c = self.canvas
        c.delete("ring")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            w, h = 460, 460
        size = min(w, h)
        pad = 26
        box = (pad, pad, size - pad, size - pad)
        cx, cy = size / 2, size / 2
        c.coords(self.time_text, cx, cy - 16)

        c.create_oval(*box, outline=RING_BG, width=18, tags="ring")

        frac = self.remaining / self.total_seconds() if self.total_seconds() else 0
        if frac > 0:
            c.create_arc(
                *box, start=90, extent=-360 * frac,
                style="arc", outline=color, width=18, tags="ring",
            )

    def _render_time(self):
        total = int(round(self.remaining))
        mm, ss = divmod(total, 60)
        self.canvas.itemconfig(self.time_text, text=f"{mm:02d}:{ss:02d}")

    def _render_dots(self, color):
        for dot in self.dots:
            dot.destroy()
        self.dots = []
        sessions = int(self.cfg["sessions_before_long_break"])
        for i in range(sessions):
            if self.phase == "work":
                filled = i < self.completed_in_cycle
            else:
                filled = i < (self.completed_in_cycle % sessions)
            dot = tk.Label(
                self.dots_frame, text="●", bg=BG,
                fg=color if filled else DOT_BG, font=("Segoe UI", 14),
            )
            dot.pack(side="left", padx=4)
            self.dots.append(dot)

    # ---- dialogs ----
    def _make_dialog(self, title):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        return win

    def _close_button(self, parent, win):
        return tk.Button(
            parent, text="关闭", command=win.destroy,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2", highlightthickness=1,
            highlightbackground=BORDER, font=("Segoe UI", 11), padx=16, pady=7,
        )

    # ---- settings ----
    def open_settings(self):
        win = self._make_dialog("设置")

        fields = [
            ("专注时长（分钟）", "work_minutes"),
            ("短休息（分钟）", "short_break_minutes"),
            ("长休息（分钟）", "long_break_minutes"),
            ("长休息前的番茄数", "sessions_before_long_break"),
        ]
        entries = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(win, text=label, bg=BG, fg=TEXT, font=("Segoe UI", 11)).grid(
                row=i, column=0, sticky="w", padx=16, pady=9
            )
            var = tk.StringVar(value=str(self.cfg[key]))
            e = tk.Entry(win, textvariable=var, width=8, justify="center",
                         bg="#fafafa", fg=TEXT, insertbackground=ACCENT,
                         relief="flat", highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT,
                         font=("Segoe UI", 11))
            e.grid(row=i, column=1, padx=16, pady=9)
            entries[key] = var

        def save():
            new_cfg = {}
            for key in ("work_minutes", "short_break_minutes", "long_break_minutes", "sessions_before_long_break"):
                try:
                    val = int(entries[key].get())
                except ValueError:
                    messagebox.showerror("错误", "请输入整数", parent=win)
                    return
                if val <= 0:
                    messagebox.showerror("错误", "数值必须大于 0", parent=win)
                    return
                new_cfg[key] = val
            self.cfg.update(new_cfg)
            save_config(self.cfg)
            self.reset()
            win.destroy()

        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=16)
        self._close_button(btn_frame, win).pack(side="left", padx=8)
        tk.Button(btn_frame, text="保存", command=save,
                  bg=ACCENT, fg="white", activebackground=ACCENT_DARK, activeforeground="white",
                  relief="flat", bd=0, cursor="hand2", font=("Segoe UI", 11, "bold"), padx=16, pady=7).pack(side="left", padx=8)

    def open_stats(self):
        win = self._make_dialog("统计")

        today = datetime.date.today().isoformat()
        today_data = self.stats["days"].get(today, {"count": 0, "minutes": 0, "tasks": []})

        tk.Label(
            win, text=f"今日完成番茄数：{today_data['count']}",
            bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(
            win, text=f"今日累计专注：{today_data['minutes']} 分钟",
            bg=BG, fg=TEXT, font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(0, 10))

        total_count = total_minutes = 0
        for d in self.stats["days"].values():
            total_count += d["count"]
            total_minutes += d["minutes"]
        tk.Label(
            win, text=f"历史总计：{total_count} 个番茄 / {total_minutes} 分钟",
            bg=BG, fg=MUTED, font=("Segoe UI", 10),
        ).pack(anchor="w", padx=16, pady=(0, 10))

        list_frame = tk.Frame(win, bg=BG)
        list_frame.pack(padx=16, pady=(0, 16), fill="both")
        tk.Label(list_frame, text="今日任务记录", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")

        tasks = today_data.get("tasks", [])
        if not tasks:
            tk.Label(list_frame, text="（暂无记录）", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=4)
        else:
            for t in tasks:
                tk.Label(
                    list_frame, text=f"· {t['name']}  —  {t['minutes']} 分钟",
                    bg=BG, fg=TEXT, font=("Segoe UI", 10),
                ).pack(anchor="w", pady=2)

        self._close_button(win, win).pack(pady=(0, 16))

    def _on_close(self):
        save_config(self.cfg)
        self.root.destroy()


def main():
    enable_dpi_awareness()
    root = tk.Tk()

    app = PomodoroApp(root)
    root.update_idletasks()
    w = 560
    h = 800
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.mainloop()


if __name__ == "__main__":
    main()
