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
    "work": {"label": "专注", "stamp": "WORK"},
    "short_break": {"label": "短休息", "stamp": "REST"},
    "long_break": {"label": "长休息", "stamp": "LONG REST"},
}

# 复古文具配色：纸张底色 + 钢笔墨色
BG = "#f2e8d5"
PAPER = "#ece0c7"
TEXT = "#3a2e1f"
MUTED = "#9c8b6f"
ACCENT = "#8b2e2e"
ACCENT_DARK = "#6e2222"
ACCENT_TINT = "#e6d4c3"
BORDER = "#c4a572"
CELL_EMPTY = "#ddd0b4"


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

        header = tk.Frame(self.root, bg=BG, highlightthickness=2, highlightbackground=TEXT)
        header.pack(fill="x", padx=28, pady=(24, 0))
        tk.Label(
            header, text="POMODORO LOG", bg=BG, fg=TEXT,
            font=("Georgia", 13, "bold"),
        ).pack(side="left", padx=14, pady=8)
        self.date_label = tk.Label(
            header, text=datetime.date.today().strftime("%Y.%m.%d"),
            bg=BG, fg=MUTED, font=("Consolas", 11),
        )
        self.date_label.pack(side="right", padx=14, pady=8)

        self.phase_stamp = tk.Label(
            self.root, text="", bg=BG, fg=ACCENT,
            font=("Georgia", 15, "bold"), highlightthickness=2,
            highlightbackground=ACCENT,
        )
        self.phase_stamp.pack(pady=(22, 4), ipadx=16, ipady=4)

        self.cycle_label = tk.Label(self.root, text="", bg=BG, fg=MUTED, font=("Georgia", 11, "italic"))
        self.cycle_label.pack(pady=(2, 14))

        task_frame = tk.Frame(self.root, bg=BG)
        task_frame.pack(pady=(0, 10))
        self.task_var = tk.StringVar(value="")
        tk.Label(task_frame, text="task —", bg=BG, fg=MUTED, font=("Georgia", 11, "italic")).pack(side="left")
        self.task_entry = tk.Entry(
            task_frame, textvariable=self.task_var, width=26, justify="left",
            bg=BG, fg=TEXT, insertbackground=ACCENT,
            relief="flat", highlightthickness=0,
            bd=0, font=("Georgia", 11),
        )
        self.task_entry.pack(side="left", padx=(6, 0))
        tk.Frame(task_frame, bg=TEXT, height=1, width=170).place(in_=self.task_entry, relx=0, rely=1.0, y=2)

        time_frame = tk.Frame(self.root, bg=PAPER, highlightthickness=2, highlightbackground=BORDER)
        time_frame.pack(pady=10, padx=60, fill="x")
        self.time_label = tk.Label(
            time_frame, text="", bg=PAPER, fg=TEXT, font=("Consolas", 64, "bold"),
        )
        self.time_label.pack(pady=18)

        self.progress_canvas = tk.Canvas(self.root, height=28, bg=BG, highlightthickness=0)
        self.progress_canvas.pack(pady=(14, 4), padx=60, fill="x")
        self.progress_canvas.bind("<Configure>", lambda e: self._render())

        self.dots_frame = tk.Frame(self.root, bg=BG)
        self.dots_frame.pack(pady=(4, 6))
        self.dots = []

        buttons = tk.Frame(self.root, bg=BG)
        buttons.pack(pady=24)

        self.start_btn = tk.Button(
            buttons, text="START", command=self.toggle, width=10,
            bg=ACCENT, fg=BG, activebackground=ACCENT_DARK, activeforeground=BG,
            relief="flat", bd=0, cursor="hand2", font=("Georgia", 13, "bold"), padx=10, pady=10,
            highlightthickness=2, highlightbackground=TEXT,
        )
        self.start_btn.grid(row=0, column=0, padx=6)

        self.skip_btn = tk.Button(
            buttons, text="skip", command=self.skip, width=7,
            bg=BG, fg=TEXT, activebackground=ACCENT_TINT, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2", highlightthickness=2,
            highlightbackground=TEXT,
            font=("Georgia", 12), padx=10, pady=10,
        )
        self.skip_btn.grid(row=0, column=1, padx=6)

        self.reset_btn = tk.Button(
            buttons, text="reset", command=self.reset, width=7,
            bg=BG, fg=TEXT, activebackground=ACCENT_TINT, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2", highlightthickness=2,
            highlightbackground=TEXT,
            font=("Georgia", 12), padx=10, pady=10,
        )
        self.reset_btn.grid(row=0, column=2, padx=6)

        bottom_frame = tk.Frame(self.root, bg=BG)
        bottom_frame.pack(pady=(0, 24))

        self.settings_btn = tk.Button(
            bottom_frame, text="settings", command=self.open_settings,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", font=("Georgia", 10, "italic"),
        )
        self.settings_btn.pack(side="left", padx=10)

        self.stats_btn = tk.Button(
            bottom_frame, text="log book", command=self.open_stats,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=ACCENT,
            relief="flat", bd=0, cursor="hand2", font=("Georgia", 10, "italic"),
        )
        self.stats_btn.pack(side="left", padx=10)

        self.topmost_var = tk.BooleanVar(value=self.prefs["always_on_top"])
        self.topmost_check = tk.Checkbutton(
            bottom_frame, text="pin on top", variable=self.topmost_var, command=self.toggle_topmost,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=ACCENT,
            selectcolor=BG, relief="flat", bd=0, cursor="hand2", font=("Georgia", 10, "italic"),
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

        self.phase_stamp.config(text=f"[ {meta['stamp']} ]")

        sessions = int(self.cfg["sessions_before_long_break"])
        self.cycle_label.config(text=f"cycle {self.completed_in_cycle} / {sessions}")

        self.start_btn.config(text="PAUSE" if self.running else "START")

        self._render_progress()
        self._render_cells()
        self._render_time()

    def _render_progress(self):
        c = self.progress_canvas
        c.delete("bar")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1:
            w, h = 440, 28
        c.create_rectangle(0, 0, w, h, outline=TEXT, width=2, tags="bar")

        frac = 1 - (self.remaining / self.total_seconds() if self.total_seconds() else 0)
        notch_count = 20
        notch_w = w / notch_count
        filled_notches = int(round(frac * notch_count))
        for i in range(filled_notches):
            x0 = i * notch_w + 2
            x1 = (i + 1) * notch_w - 2
            c.create_rectangle(x0, 2, x1, h - 2, fill=ACCENT, outline="", tags="bar")

    def _render_time(self):
        total = int(round(self.remaining))
        mm, ss = divmod(total, 60)
        self.time_label.config(text=f"{mm:02d}:{ss:02d}")

    def _render_cells(self):
        for dot in self.dots:
            dot.destroy()
        self.dots = []
        sessions = int(self.cfg["sessions_before_long_break"])
        for i in range(sessions):
            if self.phase == "work":
                filled = i < self.completed_in_cycle
            else:
                filled = i < (self.completed_in_cycle % sessions)
            cell = tk.Label(
                self.dots_frame, text=" ", width=2, height=1,
                bg=ACCENT if filled else CELL_EMPTY,
                highlightthickness=1, highlightbackground=TEXT,
            )
            cell.pack(side="left", padx=3)
            self.dots.append(cell)

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
            parent, text="close", command=win.destroy,
            bg=BG, fg=MUTED, activebackground=BG, activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2", highlightthickness=2,
            highlightbackground=TEXT, font=("Georgia", 11, "italic"), padx=16, pady=7,
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
            tk.Label(win, text=label, bg=BG, fg=TEXT, font=("Georgia", 11)).grid(
                row=i, column=0, sticky="w", padx=16, pady=9
            )
            var = tk.StringVar(value=str(self.cfg[key]))
            e = tk.Entry(win, textvariable=var, width=8, justify="center",
                         bg=PAPER, fg=TEXT, insertbackground=ACCENT,
                         relief="flat", highlightthickness=2,
                         highlightbackground=BORDER, highlightcolor=ACCENT,
                         font=("Consolas", 11))
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
        tk.Button(btn_frame, text="save", command=save,
                  bg=ACCENT, fg=BG, activebackground=ACCENT_DARK, activeforeground=BG,
                  relief="flat", bd=0, cursor="hand2", highlightthickness=2, highlightbackground=TEXT,
                  font=("Georgia", 11, "bold"), padx=16, pady=7).pack(side="left", padx=8)

    def open_stats(self):
        win = self._make_dialog("统计")

        today = datetime.date.today().isoformat()
        today_data = self.stats["days"].get(today, {"count": 0, "minutes": 0, "tasks": []})

        tk.Label(
            win, text=f"今日完成番茄数：{today_data['count']}",
            bg=BG, fg=TEXT, font=("Georgia", 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 4))
        tk.Label(
            win, text=f"今日累计专注：{today_data['minutes']} 分钟",
            bg=BG, fg=TEXT, font=("Georgia", 12, "bold"),
        ).pack(anchor="w", padx=16, pady=(0, 10))

        total_count = total_minutes = 0
        for d in self.stats["days"].values():
            total_count += d["count"]
            total_minutes += d["minutes"]
        tk.Label(
            win, text=f"历史总计：{total_count} 个番茄 / {total_minutes} 分钟",
            bg=BG, fg=MUTED, font=("Georgia", 10, "italic"),
        ).pack(anchor="w", padx=16, pady=(0, 10))

        list_frame = tk.Frame(win, bg=BG)
        list_frame.pack(padx=16, pady=(0, 16), fill="both")
        tk.Label(list_frame, text="今日任务记录", bg=BG, fg=MUTED, font=("Georgia", 10, "italic")).pack(anchor="w")

        tasks = today_data.get("tasks", [])
        if not tasks:
            tk.Label(list_frame, text="（暂无记录）", bg=BG, fg=MUTED, font=("Georgia", 10, "italic")).pack(anchor="w", pady=4)
        else:
            for t in tasks:
                tk.Label(
                    list_frame, text=f"· {t['name']}  —  {t['minutes']} 分钟",
                    bg=BG, fg=TEXT, font=("Georgia", 10),
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
