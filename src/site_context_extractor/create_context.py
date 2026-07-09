import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox


try:
    from bs4 import BeautifulSoup
except ImportError:
    messagebox.showerror(
        "Библиотека не найдена",
        "Для работы этой функции требуется библиотека 'BeautifulSoup'.\n\n"
        "Пожалуйста, установите ее, выполнив команду в терминале:\n"
        "pip install beautifulsoup4"
    )
    sys.exit()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Выбор типов файлов")
        self.root.geometry("350x230")
        self.root.resizable(False, False)
        self.root.eval('tk::PlaceWindow . center')

        self.include_html = tk.BooleanVar(value=True)
        self.include_text = tk.BooleanVar(value=False)
        self.include_css = tk.BooleanVar(value=True)
        self.include_js = tk.BooleanVar(value=True)

        self.create_widgets()

    def create_widgets(self):
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(expand=True, fill=tk.BOTH)

        label = tk.Label(main_frame, text="Выберите, какие файлы включить:", font=("Arial", 12))
        label.pack(pady=(0, 10))

        c_html = tk.Checkbutton(main_frame, text="Исходный код HTML (.html, .htm)", variable=self.include_html, font=("Arial", 10))
        c_html.pack(anchor='w')

        c_text = tk.Checkbutton(main_frame, text="Только текст (извлечь из HTML)", variable=self.include_text, font=("Arial", 10))
        c_text.pack(anchor='w')

        c_css = tk.Checkbutton(main_frame, text="CSS (.css)", variable=self.include_css, font=("Arial", 10))
        c_css.pack(anchor='w')

        c_js = tk.Checkbutton(main_frame, text="JavaScript (.js)", variable=self.include_js, font=("Arial", 10))
        c_js.pack(anchor='w')

        button_frame = tk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))

        btn_ok = tk.Button(button_frame, text="Продолжить", command=self.start_extraction)
        btn_ok.pack(side=tk.LEFT, expand=True, padx=5)

        btn_cancel = tk.Button(button_frame, text="Отмена", command=self.root.destroy)
        btn_cancel.pack(side=tk.RIGHT, expand=True, padx=5)

    def start_extraction(self):
        selected_types = {
            'html': self.include_html.get(),
            'text': self.include_text.get(),
            'css': self.include_css.get(),
            'js': self.include_js.get()
        }

        if not any(selected_types.values()):
            messagebox.showwarning("Ничего не выбрано", "Пожалуйста, выберите хотя бы один тип файлов для продолжения.")
            return


        self.root.withdraw()


        extract_content_from_site(selected_types)


        self.root.destroy()


def extract_content_from_site(selected_types):


    root_dir = filedialog.askdirectory(title="Выберите корневую папку вашего сайта")

    if not root_dir:
        return


    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    output_file = os.path.join(application_path, '_context_all.txt')

    html_contents = []
    text_contents = []
    css_contents = []
    js_contents = []
    saved_types = []

    for subdir, dirs, files in os.walk(root_dir):
        for file in files:
            file_path = os.path.join(subdir, file)
            rel_path = os.path.relpath(file_path, root_dir)

            if file.lower().endswith(('.html', '.htm')):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    if selected_types['html']:
                        separator = f"\n\n--- СТРАНИЦА (HTML): {rel_path} ---\n\n"
                        html_contents.append(separator)
                        html_contents.append(content)

                    if selected_types['text']:
                        soup = BeautifulSoup(content, 'html.parser')
                        extracted_text = soup.get_text(separator=' ', strip=True)
                        separator = f"\n\n--- СТРАНИЦА (ТОЛЬКО ТЕКСТ): {rel_path} ---\n\n"
                        text_contents.append(separator)
                        text_contents.append(extracted_text)
                except Exception:
                    pass

            if selected_types['css'] and file.lower().endswith('.css'):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        css_text = f.read()
                    separator = f"\n\n--- CSS ФАЙЛ: {rel_path} ---\n\n"
                    css_contents.append(separator)
                    css_contents.append(css_text)
                except Exception:
                    pass

            if selected_types['js'] and file.lower().endswith('.js'):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        js_text = f.read()
                    separator = f"\n\n--- JAVASCRIPT ФАЙЛ: {rel_path} ---\n\n"
                    js_contents.append(separator)
                    js_contents.append(js_text)
                except Exception:
                    pass

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            if html_contents:
                f.write("".join(html_contents))
                saved_types.append("HTML")

            if text_contents:
                f.write("\n\n" + "="*20 + " ИЗВЛЕЧЕННЫЙ ТЕКСТ ИЗ HTML " + "="*20 + "\n\n")
                f.write("".join(text_contents))
                if "Только текст" not in saved_types: saved_types.append("Только текст")

            if css_contents:
                f.write("\n\n" + "="*20 + " СОДЕРЖИМОЕ CSS ФАЙЛОВ " + "="*20 + "\n\n")
                f.write("".join(css_contents))
                if "CSS" not in saved_types: saved_types.append("CSS")

            if js_contents:
                f.write("\n\n" + "="*20 + " СОДЕРЖИМОЕ JAVASCRIPT ФАЙЛОВ " + "="*20 + "\n\n")
                f.write("".join(js_contents))
                if "JS" not in saved_types: saved_types.append("JS")

        if not any([html_contents, text_contents, css_contents, js_contents]):
             messagebox.showinfo(
                "Файлы не найдены",
                "Не найдено файлов выбранных типов в указанной папке."
            )
             return

        messagebox.showinfo(
            "Готово!",
            f"Весь контент ({', '.join(saved_types)}) успешно сохранен в файл:\n\n{output_file}"
        )

    except Exception as e:
        messagebox.showerror(
            "Ошибка записи файла",
            f"Не удалось сохранить файл.\n\nОшибка: {e}"
        )

if __name__ == '__main__':
    main_root = tk.Tk()
    app = App(main_root)
    main_root.mainloop()
