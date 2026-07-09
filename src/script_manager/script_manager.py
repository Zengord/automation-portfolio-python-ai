import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import subprocess
import threading
import tempfile
import json


DESCRIPTIONS_FILE = "script_descriptions.json"

CONFIG_FILE = "script_manager_config.json"

EXCLUDE_DIRS = {'venv', '.venv', '__pycache__', 'node_modules', '.git', '$RECYCLE.BIN'}

class ScriptManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Менеджер Python Скриптов v2.1")
        self.geometry("1000x700")


        self.descriptions = self._load_descriptions()
        self.scripts = {}
        self.current_selected_path = None

        self._create_widgets()


        initial_path = self.search_path_var.get()
        if os.path.isdir(initial_path):
            self.after(100, self.start_search_thread)


    def _load_initial_path(self):
        """Загружает последний сохраненный путь или возвращает путь к текущему скрипту."""
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                last_path = config.get("last_search_path")

                if last_path and os.path.isdir(last_path):
                    return last_path
        except (FileNotFoundError, json.JSONDecodeError):

            pass


        return os.path.dirname(os.path.abspath(__file__))

    def _save_path(self, path):
        """Сохраняет указанный путь в файл конфигурации."""
        config = {"last_search_path": path}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)


    def _load_descriptions(self):
        """Загружает описания из JSON-файла."""
        try:
            with open(DESCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_descriptions(self):
        """Сохраняет описания в JSON-файл."""
        with open(DESCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.descriptions, f, indent=4, ensure_ascii=False)

    def _create_widgets(self):
        """Создает все элементы интерфейса."""

        top_frame = ttk.Frame(self, padding="10")
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="Папка для поиска:").pack(side=tk.LEFT, padx=(0, 5))


        initial_path = self._load_initial_path()
        self.search_path_var = tk.StringVar(value=initial_path)

        path_entry = ttk.Entry(top_frame, textvariable=self.search_path_var, state='readonly')
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Button(top_frame, text="Выбрать...", command=self.select_directory).pack(side=tk.LEFT, padx=5)
        self.find_button = ttk.Button(top_frame, text="Найти/Обновить", command=self.start_search_thread)
        self.find_button.pack(side=tk.LEFT)


        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        list_frame = ttk.Frame(main_pane, padding=5)
        self.script_listbox = tk.Listbox(list_frame, exportselection=False)
        self.script_listbox.pack(fill=tk.BOTH, expand=True)
        self.script_listbox.bind("<<ListboxSelect>>", self.on_script_select)

        main_pane.add(list_frame, weight=1)

        details_frame = ttk.Frame(main_pane, padding=10)

        self.script_title_label = ttk.Label(details_frame, text="Выберите скрипт или нажмите 'Найти'", font=("Segoe UI", 14, "bold"))
        self.script_title_label.pack(anchor=tk.W)
        self.script_path_label = ttk.Label(details_frame, text="", wraplength=400, foreground="gray")
        self.script_path_label.pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(details_frame, text="Описание:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(10, 2))
        self.desc_text = tk.Text(details_frame, height=10, state=tk.DISABLED, wrap=tk.WORD, font=("Segoe UI", 10))
        self.desc_text.pack(fill=tk.BOTH, expand=True)

        action_buttons_frame = ttk.Frame(details_frame)
        action_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        self.launch_button = ttk.Button(action_buttons_frame, text="Запустить скрипт", state=tk.DISABLED, command=self.launch_script)
        self.launch_button.pack(side=tk.RIGHT, padx=5)
        self.edit_button = ttk.Button(action_buttons_frame, text="Редактировать", state=tk.DISABLED, command=self.toggle_edit_mode)
        self.edit_button.pack(side=tk.RIGHT)

        main_pane.add(details_frame, weight=2)

        self.status_label = ttk.Label(self, text="Готов к работе.", padding=5, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)


    def on_script_select(self, event=None):
        selected_indices = self.script_listbox.curselection()
        if not selected_indices:
            return

        display_name = self.script_listbox.get(selected_indices[0])
        self.current_selected_path = self.scripts.get(display_name)

        if not self.current_selected_path: return

        self.script_title_label.config(text=os.path.basename(self.current_selected_path))
        self.script_path_label.config(text=self.current_selected_path)

        self.launch_button.config(state=tk.NORMAL)
        self.edit_button.config(state=tk.NORMAL, text="Редактировать")

        description = self.descriptions.get(self.current_selected_path, "Нет описания. Нажмите 'Редактировать', чтобы добавить.")
        self.desc_text.config(state=tk.NORMAL)
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", description)
        self.desc_text.config(state=tk.DISABLED)

    def toggle_edit_mode(self):
        if self.desc_text.cget('state') == tk.DISABLED:
            self.desc_text.config(state=tk.NORMAL, background="white")
            self.edit_button.config(text="Сохранить")
            self.desc_text.focus_set()
        else:
            new_description = self.desc_text.get("1.0", tk.END).strip()
            self.descriptions[self.current_selected_path] = new_description
            self._save_descriptions()

            self.desc_text.config(state=tk.DISABLED, background="#f0f0f0")
            self.edit_button.config(text="Редактировать")
            self.status_label.config(text=f"Описание для '{os.path.basename(self.current_selected_path)}' сохранено.")

    def clear_details_pane(self):
        self.script_title_label.config(text="Выберите скрипт из списка")
        self.script_path_label.config(text="")
        self.desc_text.config(state=tk.NORMAL)
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.config(state=tk.DISABLED)
        self.launch_button.config(state=tk.DISABLED)
        self.edit_button.config(state=tk.DISABLED)
        self.current_selected_path = None


    def select_directory(self):

        initial_dir = self.search_path_var.get()
        path = filedialog.askdirectory(
            title="Выберите папку для поиска",
            initialdir=initial_dir if os.path.isdir(initial_dir) else None
        )
        if path:
            self.search_path_var.set(path)
            self._save_path(path)
            self.status_label.config(text=f"Папка выбрана: {path}. Нажмите 'Найти/Обновить'.")
            self.clear_details_pane()

    def start_search_thread(self):
        search_path = self.search_path_var.get()
        if not os.path.isdir(search_path):
            messagebox.showwarning("Папка не найдена", f"Указанная папка не существует:\n{search_path}")
            return

        self.find_button.config(state=tk.DISABLED)
        self.script_listbox.delete(0, tk.END)
        self.clear_details_pane()
        self.status_label.config(text="Начинаю поиск...")

        threading.Thread(target=self.find_scripts, args=(search_path,), daemon=True).start()

    def find_scripts(self, search_path):
        temp_scripts = {}
        for root, dirs, files in os.walk(search_path, topdown=True):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                if file.endswith(".py") and file != os.path.basename(__file__):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(root, search_path)
                    display_name = f"{file}  ({relative_path})" if relative_path != "." else file
                    temp_scripts[display_name] = full_path

        self.scripts = temp_scripts
        self.after(0, self.populate_listbox)

    def populate_listbox(self):
        self.script_listbox.delete(0, tk.END)
        if not self.scripts:
            self.status_label.config(text="Скрипты не найдены.")
        else:
            sorted_scripts = sorted(self.scripts.keys())
            for display_name in sorted_scripts:
                self.script_listbox.insert(tk.END, display_name)
            self.status_label.config(text=f"Поиск завершен. Найдено скриптов: {len(self.scripts)}")
        self.find_button.config(state=tk.NORMAL)

    def launch_script(self):
        if not self.current_selected_path:
            messagebox.showwarning("Ошибка", "Скрипт не выбран.")
            return

        script_dir = os.path.dirname(self.current_selected_path)
        script_name = os.path.basename(self.current_selected_path)

        bat_content = f"""@echo off\nchcp 65001 > nul\ncd /d "{script_dir}"\npython "{script_name}"\necho.\necho.\necho Скрипт завершил работу. Нажмите любую клавишу...\npause > nul"""

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.bat', encoding='utf-8') as bat:
            bat.write(bat_content)
            bat_filepath = bat.name

        subprocess.Popen(f'cmd.exe /c start "{script_name}" "{bat_filepath}"', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)


if __name__ == "__main__":
    app = ScriptManager()
    app.mainloop()
