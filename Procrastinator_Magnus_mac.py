import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Menu
from tkinter.colorchooser import askcolor
import datetime
import threading
import time
import json
import os
import sys
import webbrowser
import re
import platform
import subprocess
from PIL import Image, ImageDraw

# ОПРЕДЕЛЕНИЕ СИСТЕМЫ
CURRENT_OS = platform.system() # 'Windows' или 'Darwin' (macOS)

if CURRENT_OS == 'Windows':
    import winsound
    import winreg
    import ctypes
    from ctypes import windll, byref, sizeof, c_int

# --- КОНФИГУРАЦИЯ ---
APP_TITLE = "PROCRASTINATOR MAGNUS"
APP_SIZE = "600x850"

# Цвета (Dark Mode)
C_BG = "#1E1E1E"        
C_PANEL = "#252526"     
C_FG = "#D4D4D4"        
C_BORDER = "#3E3E42"    
C_ACCENT_1 = "#FF5F00"  
C_ACCENT_2 = "#9D50FF"  
C_BTN_GREEN = "#2E7D32" 
C_BTN_RED = "#C62828"
C_BTN_YELLOW = "#F9A825"
C_TRANSPARENT = "#000001"

DEFAULT_PRESETS = [
    ("#000000", "#FFFFFF"), ("#FFFFFF", "#000000"), ("#1e1e1e", "#d4d4d4"), ("#002b36", "#839496"),
    ("#440000", "#FFCCCC"), ("#003300", "#CCFFCC"), ("#000044", "#CCCCFF"), ("#330033", "#FFCCFF"),
    ("#008080", "#afeeee"), ("#282a36", "#f8f8f2"), ("#5D0016", "#FF9999"), ("#000080", "#00FF00"),
    ("#2E003E", "#E0B0FF"), ("#3C3C3C", "#CCCCCC"), ("#121212", "#00FF41"), ("#FFB6C1", "#4B0082")
]

DATA_FILE = "reminders_data_v9.json"

try:
    import pystray
    from pystray import MenuItem as item
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

def generate_time_scale():
    steps = [(0, "Сейчас / Сразу")]
    for i in range(1, 11): steps.append((i, f"{i} мин"))
    for i in range(15, 31, 5): steps.append((i, f"{i} мин"))
    for i in range(60, 1441, 30):
        h = i / 60
        steps.append((i, f"{int(h) if h.is_integer() else h} ч"))
    for d in range(2, 8): steps.append((d*1440, f"{d} дн"))
    for w in range(2, 5): steps.append((w*10080, f"{w} нед"))
    for m in range(2, 13): steps.append((m*43200, f"{m} мес"))
    for y in range(2, 11): steps.append((y*525600, f"{y} лет"))
    for y in range(20, 101, 10): steps.append((y*525600, f"{y} лет"))
    return steps

TIME_SCALE = generate_time_scale()

class ReminderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(APP_SIZE)
        self.root.configure(bg=C_BG)
        self.root.configure(highlightthickness=0, borderwidth=0)
        
        self.apply_windows_dark_mode()
        self.icon_image = self.create_icon_image()
        
        self.tasks = []
        self.archive = []
        self.user_presets = []
        self.sound_file = None
        self.tray_icon = None
        
        self.load_data()

        self.create_widgets()
        
        # Биндинг горячих клавиш
        if CURRENT_OS == 'Darwin':
            self.root.bind_all("<Command-Key>", self.handle_ctrl_key_low_level)
        else:
            self.root.bind_all("<Control-Key>", self.handle_ctrl_key_low_level)

        self.stop_threads = False
        self.check_thread = threading.Thread(target=self.checker_loop, daemon=True)
        self.check_thread.start()

        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)
        self.root.bind("<Unmap>", self.on_window_state_change)

    def apply_windows_dark_mode(self):
        if CURRENT_OS != 'Windows': return
        try:
            self.root.update()
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), 4)
            color = 0x001E1E1E
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(color)), 4)
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, byref(c_int(color)), 4)
        except: pass

    def on_window_state_change(self, event):
        if self.root.state() == 'iconic':
            self.minimize_to_tray()

    def create_icon_image(self):
        image = Image.new('RGBA', (64, 64), (0,0,0,0))
        d = ImageDraw.Draw(image)
        d.ellipse([4, 4, 60, 60], fill="#8A2BE2", outline=None)
        d.ellipse([24, 24, 40, 40], fill="white", outline=None)
        return image

    def play_sound_cross_platform(self, sound_path):
        if sound_path and os.path.exists(sound_path):
            if CURRENT_OS == 'Windows':
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif CURRENT_OS == 'Darwin':
                subprocess.Popen(['afplay', sound_path])
            else:
                try: subprocess.Popen(['aplay', sound_path])
                except: pass
        else:
            if CURRENT_OS == 'Windows':
                winsound.MessageBeep()
            else:
                print('\a') 

    def create_widgets(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background=C_BG, borderwidth=0)
        style.configure("TLabel", background=C_BG, foreground=C_FG, borderwidth=0)
        style.configure("TButton", background=C_PANEL, foreground=C_FG, borderwidth=1, focuscolor=C_BG, lightcolor=C_BORDER, darkcolor=C_BORDER, bordercolor=C_BORDER)
        style.configure("TNotebook", background=C_BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure("TNotebook.Tab", background=C_PANEL, foreground=C_FG, padding=[15, 8], borderwidth=0, focuscolor=C_BG)
        style.map("TNotebook.Tab", background=[("selected", "#333333")], foreground=[("selected", "#FFFFFF")])
        style.configure("Vertical.TScrollbar", gripcount=0, background="#333", darkcolor="#1E1E1E", lightcolor="#333", troughcolor="#1E1E1E", bordercolor="#1E1E1E", arrowcolor="#AAA")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both")

        self.tab_create = tk.Frame(self.notebook, bg=C_BG)
        self.notebook.add(self.tab_create, text="Создать / Редактировать")
        
        self.tab_list = tk.Frame(self.notebook, bg=C_BG)
        self.notebook.add(self.tab_list, text="Список")

        self.build_create_tab()
        self.build_task_list_tab()

    def build_create_tab(self):
        tk.Label(self.tab_create, text="Сообщение:", fg="#888", bg=C_BG, font=("Segoe UI", 10)).pack(anchor="w", padx=15, pady=(10,0))
        self.text_area = tk.Text(self.tab_create, height=6, bg=C_PANEL, fg=C_FG, 
                                 font=("Consolas", 11), insertbackground="white", 
                                 relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=C_BORDER)
        self.text_area.pack(padx=15, pady=5, fill="x")
        self.add_context_menu(self.text_area)

        presets_container = tk.Frame(self.tab_create, bg=C_BG)
        presets_container.pack(padx=15, pady=5, fill="x")
        self.preset_grid = tk.Frame(presets_container, bg=C_BG)
        self.preset_grid.pack(fill="x", pady=2)
        self.refresh_presets_ui()

        fmt_frame = tk.Frame(self.tab_create, bg=C_BG)
        fmt_frame.pack(padx=15, pady=5, fill="x")
        tk.Button(fmt_frame, text="Фон", bg=C_PANEL, fg=C_FG, relief="flat", command=self.pick_bg_color).pack(side="left", padx=2)
        tk.Button(fmt_frame, text="Текст", bg=C_PANEL, fg=C_FG, relief="flat", command=self.pick_fg_color).pack(side="left", padx=2)
        tk.Button(fmt_frame, text="[+] Стиль", bg="#333", fg=C_FG, relief="flat", command=self.save_user_preset).pack(side="left", padx=10)

        self.chk_bold = tk.BooleanVar()
        self.chk_italic = tk.BooleanVar()
        self.chk_underline = tk.BooleanVar()
        for txt, var, f in [("B", self.chk_bold, "bold"), ("I", self.chk_italic, "italic"), ("U", self.chk_underline, "underline")]:
            tk.Checkbutton(fmt_frame, text=txt, variable=var, bg=C_BG, fg=C_FG, selectcolor=C_PANEL, activebackground=C_BG, font=("Arial",9,f), command=self.update_font_preview).pack(side="left", padx=2)

        s1_frame = tk.Frame(self.tab_create, bg=C_BG)
        s1_frame.pack(padx=15, pady=(15, 5), fill="x")
        self.lbl_start_time = tk.Label(s1_frame, text="Запустить через: 30 минут", fg=C_ACCENT_1, bg=C_BG, font=("Segoe UI", 10, "bold"))
        self.lbl_start_time.pack(anchor="w")
        
        self.slider_start = tk.Scale(s1_frame, from_=0, to=len(TIME_SCALE)-1, orient="horizontal", 
                                     bg=C_BG, fg=C_ACCENT_1, troughcolor=C_PANEL, activebackground=C_ACCENT_1, 
                                     highlightthickness=0, showvalue=0, bd=0, command=self.update_start_label)
        self.slider_start.set(13)
        self.slider_start.pack(fill="x", pady=5)

        manual_frame = tk.Frame(s1_frame, bg=C_BG)
        manual_frame.pack(fill="x")
        now = datetime.datetime.now()
        style_entry = {"bg": C_PANEL, "fg": "white", "relief": "flat", "insertbackground": "white", "highlightthickness": 1, "highlightbackground": C_BORDER}
        self.entry_date = tk.Entry(manual_frame, width=12, justify="center", **style_entry)
        self.entry_date.insert(0, now.strftime("%d.%m.%Y"))
        self.entry_date.pack(side="left", padx=(0, 5))
        self.entry_time = tk.Entry(manual_frame, width=6, justify="center", **style_entry)
        self.entry_time.config(fg=C_ACCENT_1)
        self.entry_time.insert(0, (now + datetime.timedelta(minutes=30)).strftime("%H:%M"))
        self.entry_time.pack(side="left")

        s2_frame = tk.Frame(self.tab_create, bg=C_BG)
        s2_frame.pack(padx=15, pady=(15, 5), fill="x")
        self.var_repeat = tk.BooleanVar(value=True)
        self.chk_repeat = tk.Checkbutton(s2_frame, text="Повторять каждые: 1 час", variable=self.var_repeat,
                                         fg=C_ACCENT_2, bg=C_BG, selectcolor=C_PANEL, activebackground=C_BG,
                                         font=("Segoe UI", 10, "bold"), command=self.toggle_repeat_ui)
        self.chk_repeat.pack(anchor="w")
        
        self.repeat_ui_frame = tk.Frame(s2_frame, bg=C_BG)
        self.repeat_ui_frame.pack(fill="x")
        self.slider_repeat = tk.Scale(self.repeat_ui_frame, from_=0, to=len(TIME_SCALE)-1, orient="horizontal",
                                      bg=C_BG, fg=C_ACCENT_2, troughcolor=C_PANEL, activebackground=C_ACCENT_2, 
                                      highlightthickness=0, showvalue=0, bd=0, command=self.update_repeat_label)
        self.slider_repeat.set(17)
        self.slider_repeat.pack(fill="x", pady=5)

        manual_rep_frame = tk.Frame(self.repeat_ui_frame, bg=C_BG)
        manual_rep_frame.pack(fill="x")
        tk.Label(manual_rep_frame, text="Свой интервал:", fg="#777", bg=C_BG).pack(side="left")
        self.entry_rep_manual = tk.Entry(manual_rep_frame, width=6, **style_entry)
        self.entry_rep_manual.pack(side="left", padx=5)
        self.combo_rep_unit = ttk.Combobox(manual_rep_frame, values=["мин", "час", "дн", "мес", "лет"], width=5, state="readonly")
        self.combo_rep_unit.set("мин")
        self.combo_rep_unit.pack(side="left")

        opts_frame = tk.Frame(self.tab_create, bg=C_BG)
        opts_frame.pack(padx=15, pady=10, fill="x")
        
        self.var_autoclose = tk.BooleanVar(value=True)
        tk.Checkbutton(opts_frame, text="Автозакрытие", variable=self.var_autoclose, 
                       bg=C_BG, fg=C_FG, selectcolor=C_PANEL, activebackground=C_BG).pack(side="left")
        self.combo_autoclose = ttk.Combobox(opts_frame, values=["10 сек", "30 сек", "1 минута", "Никогда"], width=10, state="readonly")
        self.combo_autoclose.set("10 сек")
        self.combo_autoclose.pack(side="left", padx=5)

        self.btn_sound = tk.Button(opts_frame, text="🎵 Звук", bg=C_PANEL, fg=C_FG, relief="flat", command=self.select_sound)
        self.btn_sound.pack(side="right")

        startup_frame = tk.Frame(self.tab_create, bg=C_BG)
        startup_frame.pack(padx=15, fill="x")
        
        if CURRENT_OS == 'Windows':
            self.var_startup = tk.BooleanVar(value=self.check_startup_status())
            tk.Checkbutton(startup_frame, text="Запускать вместе с Windows", variable=self.var_startup,
                           bg=C_BG, fg="#888", selectcolor=C_PANEL, activebackground=C_BG,
                           command=self.toggle_startup).pack(side="left")
        else:
            tk.Label(startup_frame, text="(Автозагрузка доступна в настройках системы)", bg=C_BG, fg="#555").pack(side="left")

        self.btn_create = tk.Button(self.tab_create, text="СОЗДАТЬ ПРОКРАСТИНАЦИЮ!", bg=C_BTN_GREEN, fg="white", 
                                    font=("Arial", 11, "bold"), height=2, relief="flat", command=self.create_task)
        self.btn_create.pack(side="bottom", fill="x", padx=20, pady=20)

    def build_task_list_tab(self):
        container = tk.Frame(self.tab_list, bg=C_BG)
        container.pack(fill="both", expand=True)
        
        canvas = tk.Canvas(container, bg=C_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview, style="Vertical.TScrollbar")
        self.scrollable_frame = tk.Frame(canvas, bg=C_BG)
        self.scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=580)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.task_canvas = canvas
        
        bottom_panel = tk.Frame(self.tab_list, bg=C_BG)
        bottom_panel.pack(fill="x", pady=5, padx=5)
        
        tk.Button(bottom_panel, text="Обновить", bg=C_PANEL, fg=C_FG, relief="flat", 
                  command=self.redraw_task_list).pack(side="left", fill="x", expand=True, padx=2)
        
        tk.Button(bottom_panel, text="🗄️ Открыть Архив", bg="#333", fg="white", relief="flat",
                  command=self.open_archive_window).pack(side="right", padx=2)

    def check_startup_status(self):
        if CURRENT_OS != 'Windows': return False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "ProcrastinatorMagnus")
            winreg.CloseKey(key)
            return True
        except WindowsError:
            return False

    def toggle_startup(self):
        if CURRENT_OS != 'Windows': return
        app_path = sys.executable
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if self.var_startup.get():
                winreg.SetValueEx(key, "ProcrastinatorMagnus", 0, winreg.REG_SZ, app_path)
            else:
                try: winreg.DeleteValue(key, "ProcrastinatorMagnus")
                except: pass
            winreg.CloseKey(key)
        except Exception as e:
            messagebox.showerror("Ошибка реестра", str(e))

    def open_archive_window(self):
        arch_win = tk.Toplevel(self.root)
        arch_win.title("Архив задач")
        arch_win.geometry("500x600")
        arch_win.configure(bg=C_BG)
        if CURRENT_OS == 'Windows':
            try:
                arch_win.update()
                hwnd = windll.user32.GetParent(arch_win.winfo_id())
                windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), 4)
                color = 0x001E1E1E
                windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, byref(c_int(color)), 4)
                windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, byref(c_int(color)), 4)
            except: pass

        container = tk.Frame(arch_win, bg=C_BG)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, bg=C_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview, style="Vertical.TScrollbar")
        frame = tk.Frame(canvas, bg=C_BG)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=frame, anchor="nw", width=480)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        if not self.archive:
            tk.Label(frame, text="Архив пуст", bg=C_BG, fg="#555").pack(pady=20)
        
        for task in self.archive:
            row = tk.Frame(frame, bg=C_PANEL, pady=5, padx=5)
            row.pack(fill="x", pady=2, padx=5)
            msg = task['msg'].replace("\n", " ")[:40] + "..."
            tk.Label(row, text=msg, bg=C_PANEL, fg="white", anchor="w").pack(side="left", fill="x", expand=True)
            
            tk.Button(row, text="Восстановить", bg=C_BTN_GREEN, fg="white", relief="flat", font=("Arial", 8),
                      command=lambda t=task, w=arch_win: [self.restore_from_archive(t), w.destroy(), self.open_archive_window()]).pack(side="right", padx=2)
            tk.Button(row, text="X", bg=C_BTN_RED, fg="white", relief="flat", font=("Arial", 8),
                      command=lambda t=task, w=arch_win: [self.archive.remove(t), self.save_data(), w.destroy(), self.open_archive_window()]).pack(side="right", padx=2)

    def restore_from_archive(self, task):
        self.archive.remove(task)
        task['time'] = datetime.datetime.now().timestamp() + 300
        self.tasks.append(task)
        self.save_data()
        self.redraw_task_list()

    def move_to_archive(self, task):
        if task in self.tasks:
            self.tasks.remove(task)
            self.archive.append(task)
            self.save_data()
            self.redraw_task_list()

    def toggle_pause(self, task):
        task['paused'] = not task.get('paused', False)
        self.save_data()
        self.redraw_task_list()

    def redraw_task_list(self):
        for w in self.scrollable_frame.winfo_children(): w.destroy()
        
        if not self.tasks:
            tk.Label(self.scrollable_frame, text="Нет активных задач", bg=C_BG, fg="#555").pack(pady=20)
            return

        for task in self.tasks:
            bg_color = task['bg'] if not task.get('paused', False) else "#333"
            row = tk.Frame(self.scrollable_frame, bg=bg_color, pady=10, padx=5)
            row.pack(fill="x", pady=2, padx=5)
            
            dt = datetime.datetime.fromtimestamp(task['time']).strftime("%d.%m %H:%M")
            status = " [PAUSED]" if task.get('paused') else ""
            
            tk.Label(row, text=f"[{dt}]{status}", bg=bg_color, fg="white", font=("Consolas",9)).pack(side="left")
            prev = task['msg'].replace("\n"," ")[:20] + "..."
            tk.Label(row, text=prev, bg=bg_color, fg=task['fg']).pack(side="left", padx=5)
            
            tk.Button(row, text="Удалить", bg=C_BTN_RED, fg="white", relief="flat", 
                      command=lambda t=task: self.move_to_archive(t)).pack(side="right", padx=2)
            
            tk.Button(row, text="Редактировать", bg=C_PANEL, fg="white", relief="flat", 
                      command=lambda t=task: self.edit_from_list(t)).pack(side="right", padx=2)
            
            pause_text = "▶" if task.get('paused') else "||"
            pause_bg = C_BTN_GREEN if task.get('paused') else C_BTN_YELLOW
            tk.Button(row, text=pause_text, bg=pause_bg, fg="white", relief="flat", width=3,
                      command=lambda t=task: self.toggle_pause(t)).pack(side="right", padx=2)

    def update_start_label(self, val):
        idx = int(val)
        mins, text = TIME_SCALE[idx]
        self.lbl_start_time.config(text=f"Запустить через: {text}")
        target = datetime.datetime.now() + datetime.timedelta(minutes=mins)
        self.entry_date.delete(0, tk.END)
        self.entry_date.insert(0, target.strftime("%d.%m.%Y"))
        self.entry_time.delete(0, tk.END)
        self.entry_time.insert(0, target.strftime("%H:%M"))

    def update_repeat_label(self, val):
        idx = int(val)
        _, text = TIME_SCALE[idx]
        self.chk_repeat.config(text=f"Повторять каждые: {text}")

    def toggle_repeat_ui(self):
        if self.var_repeat.get():
            self.repeat_ui_frame.pack(fill="x")
            self.chk_repeat.config(fg=C_ACCENT_2)
        else:
            self.repeat_ui_frame.pack_forget()
            self.chk_repeat.config(fg="#777", text="Повтор отключен")

    def refresh_presets_ui(self):
        for widget in self.preset_grid.winfo_children(): widget.destroy()
        cols = 8
        for i, (bg_c, fg_c) in enumerate(DEFAULT_PRESETS):
            btn = tk.Button(self.preset_grid, bg=bg_c, fg=fg_c, text="Aa", relief="flat", bd=0, command=lambda b=bg_c, f=fg_c: self.apply_preset(b, f))
            self.preset_grid.columnconfigure(i % cols, weight=1)
            btn.grid(row=i // cols, column=i % cols, padx=1, pady=1, sticky="ew")
        for i in range(16):
            r = 2 + (i // cols); c = i % cols
            if i < len(self.user_presets):
                bg_c, fg_c = self.user_presets[i]
                btn = tk.Button(self.preset_grid, bg=bg_c, fg=fg_c, text="Aa", relief="flat", bd=0, command=lambda b=bg_c, f=fg_c: self.apply_preset(b, f))
            else:
                btn = tk.Button(self.preset_grid, bg=C_PANEL, fg="#555", text="+", relief="flat", bd=0, state="disabled")
            self.preset_grid.columnconfigure(c, weight=1)
            btn.grid(row=r, column=c, padx=1, pady=1, sticky="ew")

    def save_user_preset(self):
        bg = self.text_area.cget("bg"); fg = self.text_area.cget("fg")
        if len(self.user_presets) >= 16: return messagebox.showinfo("Лимит", "16 ячеек занято")
        self.user_presets.append([bg, fg]); self.save_data(); self.refresh_presets_ui()

    def apply_preset(self, bg, fg): self.text_area.config(bg=bg, fg=fg, insertbackground=fg)
    def pick_bg_color(self): 
        c = askcolor(color=self.text_area.cget("bg"))[1]
        if c: self.text_area.config(bg=c)
    def pick_fg_color(self):
        c = askcolor(color=self.text_area.cget("fg"))[1]
        if c: self.text_area.config(fg=c, insertbackground=c)
    def update_font_preview(self):
        ft = ["Consolas", 11]
        if self.chk_bold.get(): ft.append("bold")
        if self.chk_italic.get(): ft.append("italic")
        if self.chk_underline.get(): ft.append("underline")
        self.text_area.configure(font=tuple(ft))
    def select_sound(self):
        f = filedialog.askopenfilename(filetypes=[("WAV", "*.wav")])
        if f: self.sound_file = f

    def create_task(self):
        msg = self.text_area.get("1.0", tk.END).strip()
        if not msg: return messagebox.showerror("Ошибка", "Пусто")
        try: dt = datetime.datetime.strptime(f"{self.entry_date.get()} {self.entry_time.get()}", "%d.%m.%Y %H:%M")
        except: return messagebox.showerror("Ошибка", "Дата")
        rep = 0
        if self.var_repeat.get():
            man = self.entry_rep_manual.get().strip()
            if man:
                try: v = int(man); u = self.combo_rep_unit.get(); m = {"мин":1, "час":60, "дн":1440, "мес":43200, "лет":525600}; rep = v * m.get(u,1)
                except: return
            else: idx = int(self.slider_repeat.get()); rep = TIME_SCALE[idx][0]
        ft = []
        if self.chk_bold.get(): ft.append("bold")
        if self.chk_italic.get(): ft.append("italic")
        if self.chk_underline.get(): ft.append("underline")
        ac_map = {"10 сек": 10, "30 сек": 30, "1 минута": 60, "Никогда": 0}
        task = { "id": int(time.time()*1000), "msg": msg, "time": dt.timestamp(), "bg": self.text_area.cget("bg"), "fg": self.text_area.cget("fg"),
                 "sound": self.sound_file, "auto_close": ac_map.get(self.combo_autoclose.get(), 10), "repeat_min": rep, "font_style": ft, "paused": False }
        self.tasks.append(task); self.save_data(); self.redraw_task_list()
        self.btn_create.config(text="ГОТОВО!", bg="white", fg="green")
        self.root.after(1000, lambda: self.btn_create.config(text="СОЗДАТЬ ПРОКРАСТИНАЦИЮ!", bg=C_BTN_GREEN, fg="white"))

    def snooze(self, task):
        task["time"] = datetime.datetime.now().timestamp() + 600
        self.save_data(); self.redraw_task_list()

    def edit_from_list(self, task):
        self.notebook.select(self.tab_create)
        self.text_area.delete("1.0", tk.END); self.text_area.insert("1.0", task["msg"])
        self.apply_preset(task["bg"], task["fg"])

    def create_popup(self, task):
        self.play_sound_cross_platform(task["sound"])
        
        pop = tk.Toplevel(self.root); pop.overrideredirect(True); pop.attributes('-topmost', True)
        if CURRENT_OS == 'Windows':
            try: pop.wm_attributes('-transparentcolor', C_TRANSPARENT)
            except: pass
        
        pop.config(bg=C_TRANSPARENT)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = 420, 320; pop.geometry(f"{w}x{h}+{sw-w-20}+{sh-h-60}")
        canvas = tk.Canvas(pop, width=w, height=h, bg=C_TRANSPARENT, highlightthickness=0); canvas.pack(fill="both", expand=True)
        cut = 30; poly = [cut, 0, w, 0, w, h, 0, h, 0, cut]; canvas.create_polygon(poly, fill=task['bg'], outline="#333", width=1)
        main = tk.Frame(canvas, bg=task['bg']); main.place(x=2, y=cut, width=w-4, height=h-cut-2)
        close_bg_x, close_bg_y = w-30, 5
        canvas.create_rectangle(close_bg_x, close_bg_y, close_bg_x+25, close_bg_y+20, fill="#111", outline="#333")
        canvas.create_text(close_bg_x+12, close_bg_y+10, text="X", fill="#DDD", font=("Arial", 9, "bold"))
        canvas.tag_bind(canvas.create_rectangle(close_bg_x, close_bg_y, close_bg_x+25, close_bg_y+20, fill="", outline=""), "<Button-1>", lambda e: pop.destroy())
        btn_bar = tk.Frame(main, bg=task["bg"]); btn_bar.pack(side="bottom", fill="x", pady=5)
        tk.Button(btn_bar, text="Прокастинировать! (10 мин)", bg=C_BTN_GREEN, fg="white", relief="flat", command=lambda: [pop.destroy(), self.snooze(task)]).pack(side="left", padx=5)
        edit_btn = tk.Button(btn_bar, text="Редактировать", bg=C_BTN_RED, fg="white", relief="flat"); edit_btn.pack(side="right", padx=5)
        ft = ["Consolas", 11]; 
        if "bold" in task.get("font_style", []): ft.append("bold")
        if "italic" in task.get("font_style", []): ft.append("italic")
        txt = tk.Text(main, bg=task["bg"], fg=task["fg"], font=tuple(ft), wrap="word", relief="flat")
        txt.insert("1.0", task["msg"]); txt.pack(fill="both", expand=True, padx=5, pady=5)
        
        if CURRENT_OS == 'Darwin': txt.bind("<Command-Key>", self.handle_ctrl_key_low_level)
        else: txt.bind("<Control-Key>", self.handle_ctrl_key_low_level)
        
        self.add_context_menu(txt); self.highlight_links(txt)
        def on_key(e):
            if (e.state & 4) or (e.state & 0x20000) or e.keysym in ['Left', 'Right', 'Up', 'Down']: return
            return "break"
        txt.bind("<Key>", on_key)
        self.is_editing = False
        def toggle_edit():
            self.is_editing = not self.is_editing
            if self.is_editing: txt.unbind("<Key>"); txt.focus(); edit_btn.config(text="СОХРАНИТЬ", bg="green")
            else: task["msg"] = txt.get("1.0", "end-1c"); self.save_data(); txt.bind("<Key>", on_key); edit_btn.config(text="Редактировать", bg=C_BTN_RED); self.highlight_links(txt)
        edit_btn.config(command=toggle_edit)
        pop.timer_cancelled = False
        def stop_timer(e): pop.timer_cancelled = True
        pop.bind("<Enter>", stop_timer); main.bind("<Enter>", stop_timer); txt.bind("<Enter>", stop_timer)
        if task["auto_close"] > 0:
            def check():
                if not pop.winfo_exists(): return
                if not pop.timer_cancelled and not self.is_editing: pop.destroy()
            self.root.after(task["auto_close"] * 1000, check)

    def handle_ctrl_key_low_level(self, event):
        is_ctrl = (event.state & 4) or (event.state & 0x20000)
        if CURRENT_OS == 'Darwin': is_ctrl = True
        
        if not is_ctrl: return
        kc = event.keycode
        
        action = None
        if kc == 67 or event.keysym == 'c': action = 'copy'
        elif kc == 86 or event.keysym == 'v': action = 'paste'
        elif kc == 88 or event.keysym == 'x': action = 'cut'
        elif kc == 65 or event.keysym == 'a': action = 'select_all'
        
        if action: return self.perform_clipboard_action(action, event.widget)

    def perform_clipboard_action(self, action, widget):
        try:
            if not isinstance(widget, (tk.Text, tk.Entry)): widget = self.root.focus_get()
            
            if action == 'copy':
                t = widget.get("sel.first", "sel.last") if isinstance(widget, tk.Text) else widget.selection_get()
                self.root.clipboard_clear()
                self.root.clipboard_append(t)
            elif action == 'paste': 
                try: 
                    if isinstance(widget, tk.Text): widget.delete("sel.first", "sel.last")
                    elif isinstance(widget, tk.Entry): widget.delete("sel.first", "sel.last")
                except: pass
                widget.insert("insert", self.root.clipboard_get())
                return "break"
            elif action == 'cut': 
                self.perform_clipboard_action('copy', widget)
                try:
                    if isinstance(widget, tk.Text): widget.delete("sel.first", "sel.last")
                    elif isinstance(widget, tk.Entry): widget.delete("sel.first", "sel.last")
                except: pass
            elif action == 'select_all': 
                if isinstance(widget, tk.Text): widget.tag_add("sel", "1.0", "end")
                elif isinstance(widget, tk.Entry): widget.select_range(0, 'end')
                return "break"
        except: pass

    def highlight_links(self, txt):
        txt.tag_remove("link", "1.0", "end"); text = txt.get("1.0", "end")
        for m in re.finditer(r"https?://\S+", text): txt.tag_add("link", f"1.0+{m.start()}c", f"1.0+{m.end()}c")
        txt.tag_config("link", foreground="#4da6ff", underline=True)
        txt.tag_bind("link", "<Button-1>", lambda e: self.open_link(e, txt))
        txt.tag_bind("link", "<Enter>", lambda e: txt.config(cursor="hand2")); txt.tag_bind("link", "<Leave>", lambda e: txt.config(cursor="arrow"))
    def open_link(self, event, widget):
        try:
            idx = widget.index(f"@{event.x},{event.y}"); ranges = widget.tag_ranges("link")
            for i in range(0, len(ranges), 2):
                if widget.compare(ranges[i], "<=", idx) and widget.compare(ranges[i+1], ">=", idx): webbrowser.open(widget.get(ranges[i], ranges[i+1]))
        except: pass
    def add_context_menu(self, widget):
        menu = Menu(self.root, tearoff=0, bg=C_PANEL, fg=C_FG, activebackground="#444", activeforeground="white")
        menu.add_command(label="Копировать", command=lambda: self.perform_clipboard_action('copy', widget))
        menu.add_command(label="Вставить", command=lambda: self.perform_clipboard_action('paste', widget))
        menu.add_command(label="Вырезать", command=lambda: self.perform_clipboard_action('cut', widget))
        widget.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
    def minimize_to_tray(self):
        if not TRAY_AVAILABLE: self.root.iconify(); return
        self.root.withdraw()
        menu = (item('Редактор', self.show_window, default=True), item('Выход', self.quit_app))
        self.tray_icon = pystray.Icon("PM", self.icon_image, "Procrastinator Magnus", menu)
        self.tray_icon.run_detached()
    def show_window(self, icon=None, item=None):
        if self.tray_icon: self.tray_icon.stop()
        self.root.after(0, self.root.deiconify)
    def quit_app(self, icon=None, item=None):
        if self.tray_icon: self.tray_icon.stop()
        os._exit(0)
    def save_data(self):
        data = {"tasks": self.tasks, "archive": self.archive, "user_presets": self.user_presets, "sound_file": self.sound_file}
        try: 
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except: pass
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list): self.tasks = data
                    else:
                        self.tasks = data.get("tasks", [])
                        self.archive = data.get("archive", [])
                        self.user_presets = data.get("user_presets", [])
                        self.sound_file = data.get("sound_file", None)
            except: self.tasks = []
    
    def play_sound_cross_platform(self, sound_path):
        if sound_path and os.path.exists(sound_path):
            if CURRENT_OS == 'Windows':
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            elif CURRENT_OS == 'Darwin':
                subprocess.Popen(['afplay', sound_path])
            else:
                try: subprocess.Popen(['aplay', sound_path])
                except: pass
        else:
            if CURRENT_OS == 'Windows':
                winsound.MessageBeep()
            else:
                print('\a') 

    def checker_loop(self):
        while not self.stop_threads:
            now = datetime.datetime.now().timestamp()
            proc = [t for t in self.tasks if t["time"] <= now and not t.get('paused')]
            if proc:
                for t in proc:
                    self.root.after(0, lambda task=t: self.create_popup(task))
                    if t["repeat_min"] > 0: t["time"] = now + (t["repeat_min"]*60)
                    else: self.tasks.remove(t)
                self.save_data(); self.root.after(0, self.redraw_task_list)
            time.sleep(1)

if __name__ == "__main__":
    root = tk.Tk()
    app = ReminderApp(root)
    root.mainloop()