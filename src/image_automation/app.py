import os
import sys
import time
import threading
import queue
import random
import subprocess
import json
import logging
from pathlib import Path
from collections import OrderedDict
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk, ImageDraw
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager


class Config:
    """Константы приложения"""
    MIN_SEARCH_INTERVAL = 2.0
    MAX_WORKERS = 3
    CACHE_SIZE = 50
    MAX_PREVIEW_WINDOWS = 3
    REQUEST_TIMEOUT = 15
    CHROME_WINDOW_SIZE = "1200,900"
    BACKUP_DIR_NAME = "_backup_image_replacer"

@dataclass
class Task:
    """Структура задачи замены изображения"""
    html_file: str
    original_src: str
    search_query: str
    orientation: str
    found_images: Optional[List[Dict]] = None
    selected: Optional[Dict] = None

class LRUCache:
    """Кэш изображений с ограничением размера (Least Recently Used)"""
    def __init__(self, maxsize: int = Config.CACHE_SIZE):
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[ImageTk.PhotoImage]:
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        return None

    def put(self, key: str, value: ImageTk.PhotoImage):
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

class Logger:
    """Потокобезопасный логгер в UI и файл"""
    def __init__(self, ui_callback):
        self.ui_callback = ui_callback
        self._lock = threading.Lock()
        self.setup_file_logger()

    def setup_file_logger(self):
        log_file = Path("image_replacer.log")
        log_file.unlink(missing_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def log(self, message: str, level: str = "INFO"):
        with self._lock:
            timestamp = time.strftime('%H:%M:%S')
            formatted = f"[{timestamp}] {message}"
            self.ui_callback(formatted)
            logging.log(getattr(logging, level), message)


class WebDriverManager:
    """Контекстный менеджер для Selenium WebDriver"""
    def __init__(self, logger: Logger):
        self.logger = logger
        self.driver = None

    def __enter__(self):
        try:
            self.logger.log("🚀 Запуск Chrome...")
            options = webdriver.ChromeOptions()
            options.add_argument(f'--window-size={Config.CHROME_WINDOW_SIZE}')
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-web-security")
            options.add_argument("--allow-running-insecure-content")
            options.add_argument("--log-level=3")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            prefs = {"profile.default_content_setting_values.notifications": 2}
            options.add_experimental_option("prefs", prefs)

            service = Service(ChromeDriverManager().install(), log_output=subprocess.DEVNULL)
            self.driver = webdriver.Chrome(service=service, options=options)

            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => false});
                window.navigator.chrome = { runtime: {}, app: {} };
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                """
            })
            self.logger.log("✅ Браузер успешно запущен")
            return self.driver
        except Exception as e:
            self.logger.log(f"❌ Ошибка запуска Chrome: {e}", "ERROR")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            try:
                self.logger.log("Закрытие браузера...")
                self.driver.quit()
            except Exception as e:
                self.logger.log(f"Ошибка при закрытии браузера: {e}", "ERROR")


class ImageSearcher:
    """Ядро поиска изображений в Яндексе"""
    def __init__(self, logger: Logger):
        self.logger = logger
        self.last_search_time = 0

    def ensure_images_section(self, driver) -> bool:
        """Переход в раздел изображений Яндекса"""
        try:
            if "yandex.ru/images" in driver.current_url:
                return True

            self.logger.log("🔄 Переход в раздел изображений...")
            driver.get("https://yandex.ru/images/")
            time.sleep(3)

            if "yandex.ru/images" in driver.current_url:
                return True


            driver.get("https://yandex.ru/")
            time.sleep(2)

            for text in ['Картинки', 'Images']:
                try:
                    link = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, f"//a[contains(@href, '/images/') and contains(text(), '{text}')]"))
                    )
                    link.click()
                    time.sleep(3)
                    return True
                except:
                    continue

            return False
        except Exception as e:
            self.logger.log(f"❌ Ошибка перехода в раздел изображений: {e}", "ERROR")
            return False

    def handle_captcha(self, driver, root_window) -> bool:
        """Обработка капчи с помощью диалогового окна"""
        try:
            current_url = driver.current_url.lower()
            if "captcha" in current_url or "check" in current_url:
                self.logger.log("⚠️ Обнаружена капча!")

                root_window.attributes('-topmost', True)
                response = messagebox.askyesno(
                    "Капча обнаружена",
                    "Пройдите капчу в окне браузера.\n"
                    "Нажмите 'Да', когда будете готовы продолжить.\n"
                    "Нажмите 'Нет' для пропуска текущей задачи.",
                    parent=root_window
                )
                root_window.attributes('-topmost', False)

                if not response:
                    return False

                self.logger.log("⏳ Ожидание прохождения капчи...")
                start_time = time.time()
                while time.time() - start_time < 30:
                    if "captcha" not in driver.current_url.lower():
                        self.logger.log("✅ Капча пройдена")
                        return True
                    time.sleep(1)

                self.logger.log("❌ Таймаут капчи")
                return False
        except Exception as e:
            self.logger.log(f"⚠️ Ошибка проверки капчи: {e}", "WARNING")
        return True

    def search(self, driver, task: Task, root_window) -> List[Dict]:
        """Основной метод поиска изображений"""

        current_time = time.time()
        if current_time - self.last_search_time < Config.MIN_SEARCH_INTERVAL:
            time.sleep(Config.MIN_SEARCH_INTERVAL - (current_time - self.last_search_time))
        self.last_search_time = time.time()

        self.logger.log(f"🔍 Поиск: '{task.search_query}' ({task.orientation})")

        if not self.ensure_images_section(driver):
            return []

        if not self.handle_captcha(driver, root_window):
            return []


        query = task.search_query.replace(' ', '+')
        url = f"https://yandex.ru/images/search?text={query}&isize=large"
        if task.orientation == 'square':
            url += "&iorient=square"
        elif task.orientation == 'horizontal':
            url += "&iorient=horizontal"

        self.logger.log(f"🌐 URL: {url}")
        driver.get(url)
        time.sleep(2)

        if not self.handle_captcha(driver, root_window):
            return []


        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//img[contains(@src, 'yandex.net') or contains(@src, 'avatars.mds.yandex.net')]"))
            )
        except:
            self.logger.log("⚠️ Изображения не загрузились", "WARNING")
            return []


        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(0.8, 1.5))


        imgs = driver.find_elements(By.XPATH, "//img[contains(@src, 'yandex.net') or contains(@src, 'avatars.mds.yandex.net')]")
        imgs = [img for img in imgs if "logo" not in img.get_attribute("src").lower()]

        results = []
        processed_urls = set()

        for i, el in enumerate(imgs[:12]):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", el)
                time.sleep(random.uniform(0.3, 0.7))

                src = el.get_attribute("src")
                if not src or src in processed_urls:
                    continue
                processed_urls.add(src)


                actions = ActionChains(driver)
                actions.move_to_element(el).pause(0.2).click().perform()

                full_img = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//img[contains(@class, 'MMImage-Origin') or contains(@class, 'MMImage-Preview') or contains(@class, 'image')]"))
                )
                url = full_img.get_attribute("src")
                if not url or not url.startswith("http"):
                    continue


                try:
                    resp = requests.get(url, headers=self._get_headers(driver), timeout=Config.REQUEST_TIMEOUT)
                    resp.raise_for_status()
                    img_pil = Image.open(io.BytesIO(resp.content))
                    width, height = img_pil.size
                    results.append({"url": url, "width": width, "height": height})
                except:
                    results.append({"url": url, "width": "?", "height": "?"})


                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(random.uniform(0.4, 0.8))

            except Exception as e:
                self.logger.log(f"❌ Ошибка обработки изображения #{i+1}: {str(e)[:100]}", "ERROR")
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                except:
                    pass

        self.logger.log(f"✅ Найдено: {len(results)} изображений")
        return results

    def _get_headers(self, driver):
        """Формирование заголовков запросов"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://yandex.ru/',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        }
        if driver:
            try:
                cookies = driver.get_cookies()
                headers['Cookie'] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            except:
                pass
        return headers


class HTMLProcessor:
    """Обработка HTML файлов и сохранение изменений"""
    def __init__(self, project_path: Path, logger: Logger):
        self.project_path = project_path
        self.logger = logger
        self.backup_path = project_path / Config.BACKUP_DIR_NAME

    def analyze_html_files(self) -> List[Task]:
        """Анализ HTML файлов и создание задач"""
        self.logger.log("🔍 Анализ HTML-файлов...")

        html_files = list(self.project_path.rglob("*.html")) + list(self.project_path.rglob("*.htm"))
        if not html_files:
            self.logger.log("❌ HTML-файлы не найдены", "ERROR")
            return []

        tasks = []
        for html_file in html_files:
            try:
                with open(html_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                soup = BeautifulSoup(content, 'html.parser')

                for img in soup.find_all('img'):
                    alt = img.get('alt', '').strip()
                    src = img.get('src', '').strip()

                    if not alt or not src or src.startswith(('http://', 'https://', '//')):
                        continue

                    orientation = 'square' if 'icon' in alt.lower() or 'icon' in src.lower() else 'horizontal'
                    tasks.append(Task(
                        html_file=html_file.relative_to(self.project_path).as_posix(),
                        original_src=src,
                        search_query=alt,
                        orientation=orientation
                    ))
            except Exception as e:
                self.logger.log(f"⚠️ Ошибка чтения {html_file}: {e}", "WARNING")

        return tasks

    def create_backup(self):
        """Создание резервной копии исходных файлов"""
        if self.backup_path.exists():
            self.logger.log("✅ Резервная копия уже существует")
            return

        try:
            self.logger.log("💾 Создание резервной копии...")
            shutil.copytree(self.project_path, self.backup_path,
                          ignore=shutil.ignore_patterns(Config.BACKUP_DIR_NAME, '.*'))
            self.logger.log(f"✅ Резервная копия создана: {self.backup_path}")
        except Exception as e:
            self.logger.log(f"❌ Ошибка создания резервной копии: {e}", "ERROR")
            raise

    def apply_changes(self, tasks: List[Task], driver) -> tuple:
        """Применение изменений к HTML и сохранение изображений"""
        img_dir = self.project_path / "img" / "main"
        img_dir.mkdir(parents=True, exist_ok=True)

        replaced = 0
        skipped = 0

        for task in tasks:
            if not task.selected:
                skipped += 1
                continue

            try:
                html_path = self.project_path / task.html_file
                if not html_path.exists():
                    self.logger.log(f"⚠️ HTML не найден: {html_path}", "WARNING")
                    continue


                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                        'Referer': 'https://yandex.ru/',
                        'Accept': 'image/*'
                    }
                    if driver:
                        try:
                            cookies = driver.get_cookies()
                            headers['Cookie'] = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                        except:
                            pass

                    resp = requests.get(task.selected['url'], headers=headers, timeout=Config.REQUEST_TIMEOUT)
                    resp.raise_for_status()


                    original_ext = Path(task.original_src).suffix.lower()
                    new_ext = '.webp' if original_ext != '.webp' else '.webp'
                    img_filename = Path(task.original_src).stem + new_ext
                    new_img_path = img_dir / img_filename

                    with open(new_img_path, 'wb') as f:
                        f.write(resp.content)

                except Exception as e:
                    self.logger.log(f"⚠️ Ошибка загрузки изображения: {e}", "WARNING")
                    continue


                try:
                    with open(html_path, 'r', encoding='utf-8') as f:
                        soup = BeautifulSoup(f.read(), 'html.parser')

                    img_tag = soup.find('img', src=task.original_src)
                    if not img_tag:
                        img_tag = soup.find('img', src=task.original_src.lstrip('/'))

                    if img_tag:
                        new_src = f"../img/main/{img_filename}"
                        img_tag['src'] = new_src

                        with open(html_path, 'w', encoding='utf-8') as f:
                            f.write(str(soup))

                        replaced += 1
                        self.logger.log(f"✅ Заменено: {task.original_src} -> {new_src}")
                    else:
                        self.logger.log(f"⚠️ Тег img не найден в {html_path}", "WARNING")
                except Exception as e:
                    self.logger.log(f"⚠️ Ошибка обновления HTML: {e}", "WARNING")

            except Exception as e:
                self.logger.log(f"🔥 Ошибка обработки задачи: {e}", "ERROR")

        return replaced, skipped


class ImageReplacerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Замена изображений — Яндекс (Непрерывный поиск)")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 700)


        self.project_path: Optional[Path] = None
        self.tasks: List[Task] = []
        self.current_task_index = 0
        self.driver: Optional[webdriver.Chrome] = None
        self.selected_image: Optional[Dict] = None
        self.search_complete = False
        self.is_running = False
        self.is_paused = False


        self.logger = Logger(self._log_to_ui)
        self.image_cache = LRUCache()
        self.searcher = ImageSearcher(self.logger)
        self.processor: Optional[HTMLProcessor] = None


        self.ui_queue = queue.Queue()
        self.log_queue = queue.Queue()


        self.preview_windows: List[tk.Toplevel] = []

        self.setup_ui()
        self.setup_bindings()
        self.start_queue_processors()

        self.logger.log("Готов к работе. Выберите папку с HTML.")

    def setup_ui(self):

        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(top_frame, text="📁 Выбрать папку с HTML", command=self.select_folder).pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(top_frame, text="Папка не выбрана", font=("Arial", 10, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        self.progress = ttk.Progressbar(top_frame, mode='determinate', maximum=100)
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)
        self.progress.pack_forget()


        task_frame = ttk.LabelFrame(self.root, text="Текущая задача")
        task_frame.pack(fill=tk.X, padx=10, pady=5)

        self.task_info = ttk.Label(task_frame, text="Нет задач", font=("Arial", 11))
        self.task_info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.pause_btn = ttk.Button(task_frame, text="⏸ Пауза", command=self.toggle_pause, width=10)
        self.pause_btn.pack(side=tk.RIGHT, padx=5)


        img_frame = ttk.LabelFrame(self.root, text="Найденные изображения")
        img_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(img_frame)
        scrollbar = ttk.Scrollbar(img_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for i in range(2):
            self.scrollable_frame.columnconfigure(i, weight=1)


        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self.retry_btn = ttk.Button(btn_frame, text="🔄 Повторить поиск", command=self.retry_search)
        self.retry_btn.pack(side=tk.LEFT, padx=5)
        self.retry_btn.pack_forget()

        self.auto_btn = ttk.Button(btn_frame, text="✅ Авто-выбор и продолжить", command=self.auto_select_and_continue)
        self.auto_btn.pack(side=tk.RIGHT, padx=5)

        self.skip_btn = ttk.Button(btn_frame, text="⏭ Пропустить текущую", command=self.skip_task)
        self.skip_btn.pack(side=tk.RIGHT, padx=5)


        log_frame = ttk.LabelFrame(self.root, text="Лог")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state='disabled', font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)


        hint_frame = ttk.Frame(self.root)
        hint_frame.pack(fill=tk.X, padx=10, pady=2)
        ttk.Label(hint_frame, text="Enter: продолжить | Esc: пропустить | Space: пауза | Ctrl+R: повторить",
                 font=("Arial", 8), foreground="gray").pack(side=tk.LEFT)

    def setup_bindings(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind('<Return>', lambda e: self.auto_select_and_continue())
        self.root.bind('<Escape>', lambda e: self.skip_task())
        self.root.bind('<space>', lambda e: self.toggle_pause())
        self.root.bind('<Control-r>', lambda e: self.retry_search())

    def start_queue_processors(self):
        def process_log_queue():
            try:
                while True:
                    message = self.log_queue.get_nowait()
                    self._log_to_ui(message)
            except queue.Empty:
                pass
            self.root.after(100, process_log_queue)

        def process_ui_queue():
            try:
                while True:
                    task = self.ui_queue.get_nowait()
                    task()
            except queue.Empty:
                pass
            self.root.after(50, process_ui_queue)

        self.root.after(100, process_log_queue)
        self.root.after(50, process_ui_queue)

    def _log_to_ui(self, message: str):
        """Вывод лога в UI (только из главного потока)"""
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, message + '\n')
        self.log_text.configure(state='disabled')
        self.log_text.see(tk.END)

    def select_folder(self):
        """Выбор папки проекта"""
        if self.is_running:
            messagebox.showwarning("Внимание", "Операция выполняется. Сначала остановите процесс.")
            return

        folder = filedialog.askdirectory()
        if not folder:
            return

        self.project_path = Path(folder)
        if not os.access(self.project_path, os.W_OK):
            messagebox.showerror("Ошибка", "Нет прав на запись в эту папку!")
            return

        self.status_label.config(text=f"Папка: {self.project_path.name}")
        self.logger.log(f"Выбрана папка: {self.project_path}")


        self.tasks = []
        self.current_task_index = 0
        self.search_complete = False
        self.processor = HTMLProcessor(self.project_path, self.logger)


        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)
        self.progress['value'] = 0


        self.is_running = True
        threading.Thread(target=self._analyze_project_thread, daemon=True).start()

    def _analyze_project_thread(self):
        """Фоновый поток анализа HTML"""
        try:
            tasks = self.processor.analyze_html_files()
            self.ui_queue.put(lambda: self._finish_analysis(tasks))
        except Exception as e:
            self.logger.log(f"🔥 Ошибка анализа: {e}", "ERROR")
            self.ui_queue.put(lambda: self._finish_analysis([]))

    def _finish_analysis(self, tasks: List[Task]):
        """Завершение анализа в UI потоке"""
        self.progress.pack_forget()
        self.is_running = False

        if not tasks:
            self.logger.log("❌ Не найдено подходящих изображений")
            return

        self.tasks = tasks
        self.current_task_index = 0

        square_count = sum(1 for t in tasks if t.orientation == 'square')
        horizontal_count = len(tasks) - square_count

        self.logger.log(f"✅ Найдено задач: {len(tasks)}")
        self.logger.log(f"📊 Ориентации: квадратных={square_count}, горизонтальных={horizontal_count}")

        self.task_info.config(text="1/{} — поиск в процессе...".format(len(tasks)))
        self.show_images([])


        self.is_running = True
        self.search_complete = False
        threading.Thread(target=self._search_all_images_thread, daemon=True).start()

    def _search_all_images_thread(self):
        """Фоновый поток поиска всех изображений"""
        try:
            with WebDriverManager(self.logger) as driver:
                self.driver = driver

                if not self.searcher.ensure_images_section(driver):
                    self.logger.log("❌ Не удалось перейти в раздел изображений", "ERROR")
                    return

                for i, task in enumerate(self.tasks):
                    if not self.is_running:
                        break

                    while self.is_paused and self.is_running:
                        time.sleep(0.5)

                    results = self.searcher.search(driver, task, self.root)
                    task.found_images = results

                    if i == self.current_task_index:
                        self.ui_queue.put(lambda r=results: self.show_images(r))

                    time.sleep(random.uniform(1.0, 2.5))

                self.search_complete = True
                self.logger.log("✅ Поиск завершён")
                self.ui_queue.put(self.check_if_all_done)

        except Exception as e:
            self.logger.log(f"🔥 Критическая ошибка поиска: {e}", "ERROR")
        finally:
            self.driver = None

    def show_images(self, images: List[Dict]):
        """Отображение изображений в UI"""

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        if not images:
            ttk.Label(self.scrollable_frame, text="Изображения не найдены или поиск не завершён",
                     foreground="red", font=("Arial", 10)).pack(pady=20)
            self.selected_image = None
            return


        images.sort(key=lambda x: int(x.get('width', 0)) if str(x.get('width', 0)).isdigit() else 0, reverse=True)


        row = col = 0
        for img_data in images:
            frame = ttk.Frame(self.scrollable_frame, relief="raised", padding=5)
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

            img_label = ttk.Label(frame)
            img_label.pack()


            cached = self.image_cache.get(img_data['url'])
            if cached:
                img_label.configure(image=cached)
                img_label.image = cached
            else:
                placeholder = ImageTk.PhotoImage(Image.new('RGB', (150, 150), '#e0e0e0'))
                img_label.configure(image=placeholder)
                img_label.image = placeholder

                threading.Thread(
                    target=self._load_image_cache,
                    args=(img_data, img_label),
                    daemon=True
                ).start()

            img_label.bind("<Button-1>", lambda e, d=img_data: self.show_preview(d))

            size_text = f"{img_data['width']} × {img_data['height']}" if img_data.get('width') else "размер неизвестен"
            ttk.Label(frame, text=size_text, font=("Arial", 8)).pack(pady=(2, 0))

            btn = ttk.Button(frame, text="Выбрать", width=10, command=lambda d=img_data: self.manual_select(d))
            btn.pack(pady=(2, 0))

            col += 1
            if col > 1:
                col = 0
                row += 1

        self.auto_select_best_image(images)
        self.root.after(100, lambda: self.auto_btn.focus_set())

    def _load_image_cache(self, img_data: Dict, label: ttk.Label):
        """Фоновая загрузка изображения в кэш"""
        try:
            headers = self.searcher._get_headers(self.driver)
            resp = requests.get(img_data['url'], headers=headers, timeout=Config.REQUEST_TIMEOUT)
            resp.raise_for_status()

            img = Image.open(io.BytesIO(resp.content))
            img.thumbnail((150, 150))
            photo = ImageTk.PhotoImage(img)

            self.image_cache.put(img_data['url'], photo)

            self.ui_queue.put(lambda: self._update_image_label(label, photo))
        except Exception as e:
            self.logger.log(f"⚠️ Ошибка кэширования: {e}", "WARNING")

    def _update_image_label(self, label: ttk.Label, photo: ImageTk.PhotoImage):
        """Обновление изображения в UI"""
        label.configure(image=photo)
        label.image = photo

    def auto_select_best_image(self, images: List[Dict]):
        """Автоматический выбор лучшего изображения"""
        best = next((img for img in images if str(img.get('width', 0)).isdigit() and int(img['width']) > 1000), None)
        if not best and images:
            best = images[0]

        self.selected_image = best
        if best:
            self.logger.log(f"🤖 Авто-выбрано: {best.get('width', '?')}×{best.get('height', '?')}")

    def show_preview(self, img_data: Dict):
        """Показ окна предпросмотра"""
        if len(self.preview_windows) >= Config.MAX_PREVIEW_WINDOWS:
            messagebox.showwarning("Лимит окон", f"Закройте предыдущие окна (макс. {Config.MAX_PREVIEW_WINDOWS})")
            return

        self.ui_queue.put(lambda: self._create_preview_window(img_data))

    def _create_preview_window(self, img_data: Dict):
        """Создание окна предпросмотра"""
        preview = tk.Toplevel(self.root)
        preview.title(f"Превью: {img_data['width']}×{img_data['height']}")
        preview.geometry("800x600")
        preview.transient(self.root)

        self.preview_windows.append(preview)
        preview.protocol("WM_DELETE_WINDOW", lambda w=preview: self._close_preview(w))

        status_label = ttk.Label(preview, text="Загрузка...", font=("Arial", 10))
        status_label.pack(pady=10)

        try:
            headers = self.searcher._get_headers(self.driver)
            resp = requests.get(img_data['url'], headers=headers, timeout=Config.REQUEST_TIMEOUT)
            img = Image.open(io.BytesIO(resp.content))


            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            max_w = min(1200, screen_w - 100)
            max_h = min(800, screen_h - 100)

            ratio = min(max_w / img.width, max_h / img.height, 1.0)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

            status_label.pack_forget()

            photo = ImageTk.PhotoImage(img)
            canvas = tk.Canvas(preview, width=new_size[0], height=new_size[1], bg="black")
            canvas.pack(expand=True, fill=tk.BOTH)
            canvas.create_image(new_size[0] // 2, new_size[1] // 2, anchor=tk.CENTER, image=photo)
            canvas.image = photo

            info_frame = ttk.Frame(preview)
            info_frame.pack(fill=tk.X, padx=10, pady=5)
            ttk.Label(info_frame, text=f"Размер: {img_data['width']}×{img_data['height']} пикс.",
                     font=("Arial", 9)).pack(side=tk.LEFT)
            ttk.Label(info_frame, text=f"URL: {img_data['url'][:60]}...",
                     font=("Arial", 9)).pack(side=tk.RIGHT)

        except Exception as e:
            status_label.config(text=f"Ошибка: {e}", foreground="red")

        preview.bind("<Escape>", lambda e: preview.destroy())

    def _close_preview(self, window: tk.Toplevel):
        """Закрытие окна предпросмотра"""
        if window in self.preview_windows:
            self.preview_windows.remove(window)
        window.destroy()

    def manual_select(self, img_data: Dict):
        """Ручной выбор изображения"""
        self.selected_image = img_data
        self.logger.log(f"🖼️ Вручную выбрано: {img_data.get('width', '?')}×{img_data.get('height', '?')}")
        self.tasks[self.current_task_index].selected = img_data
        self.process_next_task()

    def auto_select_and_continue(self):
        """Авто-выбор и переход к следующей задаче"""
        if not self.selected_image:
            messagebox.showwarning("Внимание", "Нет выбранных изображений!")
            return

        self.tasks[self.current_task_index].selected = self.selected_image
        self.process_next_task()

    def skip_task(self):
        """Пропуск текущей задачи"""
        self.tasks[self.current_task_index].selected = None
        self.logger.log(f"⏭️ Пропущено: {self.tasks[self.current_task_index].search_query}")
        self.process_next_task()

    def retry_search(self):
        """Повторный поиск для текущей задачи"""
        if not self.driver:
            messagebox.showwarning("Внимание", "Браузер не запущен")
            return

        if self.current_task_index >= len(self.tasks):
            return

        task = self.tasks[self.current_task_index]
        self.logger.log(f"🔄 Повторный поиск: '{task.search_query}'")
        task.found_images = None

        self.retry_btn.pack_forget()
        threading.Thread(target=self._retry_search_task, args=(task,), daemon=True).start()

    def _retry_search_task(self, task: Task):
        """Фоновый повторный поиск"""
        try:
            results = self.searcher.search(self.driver, task, self.root)
            task.found_images = results
            self.ui_queue.put(lambda r=results: self.show_images(r))
        except Exception as e:
            self.logger.log(f"🔥 Ошибка повторного поиска: {e}", "ERROR")

    def toggle_pause(self):
        """Переключение паузы"""
        self.is_paused = not self.is_paused
        self.is_running = not self.is_paused

        if self.is_paused:
            self.pause_btn.config(text="▶️ Продолжить")
            self.logger.log("⏸ Работа приостановлена")
            if self.current_task_index < len(self.tasks):
                self.retry_btn.pack(side=tk.LEFT, padx=5)
        else:
            self.pause_btn.config(text="⏸ Пауза")
            self.logger.log("▶️ Возобновление работы")
            self.retry_btn.pack_forget()

    def process_next_task(self):
        """Переход к следующей задаче"""
        self.current_task_index += 1

        if self.current_task_index >= len(self.tasks):
            if self.search_complete:
                self.logger.log("🎉 Все задачи завершены!")
                self.apply_all_changes()
            else:
                self.task_info.config(text="⏳ Ожидание завершения поиска...")
        else:
            self.update_ui_for_current_task()

    def update_ui_for_current_task(self):
        """Обновление UI для текущей задачи"""
        if self.current_task_index >= len(self.tasks):
            return

        task = self.tasks[self.current_task_index]
        status = f"{self.current_task_index+1}/{len(self.tasks)} — '{task.search_query}' ({task.orientation})"

        if task.found_images is None:
            status += " — поиск в процессе..."
            self.task_info.config(text=status)
            self.show_images([])
        else:
            self.task_info.config(text=status)
            self.show_images(task.found_images)

    def check_if_all_done(self):
        """Проверка завершения всех задач"""
        if self.current_task_index >= len(self.tasks) and self.search_complete:
            self.apply_all_changes()

    def apply_all_changes(self):
        """Применение всех изменений в исходной папке"""
        if not self.project_path or not self.processor:
            return


        confirm = messagebox.askyesno(
            "Подтверждение",
            "Все изменения будут внесены в исходную папку!\n"
            f"Резервная копия создана в '{Config.BACKUP_DIR_NAME}'\n\n"
            "Продолжить?",
            parent=self.root
        )
        if not confirm:
            self.logger.log("❌ Действие отменено")
            return


        try:
            self.processor.create_backup()
        except:
            return


        self.logger.log("💾 Применение изменений в исходной папке...")
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)
        self.progress['value'] = 0
        self.progress['maximum'] = len(self.tasks)

        try:
            replaced, skipped = self.processor.apply_changes(self.tasks, self.driver)

            self.progress.pack_forget()
            self.logger.log(f"✅ Готово! Заменено: {replaced}, Пропущено: {skipped}")

            messagebox.showinfo(
                "Готово!",
                f"Замена завершена!\n\nЗаменено: {replaced}\nПропущено: {skipped}",
                parent=self.root
            )


            if sys.platform == 'win32':
                os.startfile(self.project_path)
            elif sys.platform == 'darwin':
                os.system(f'open "{self.project_path}"')
            else:
                os.system(f'xdg-open "{self.project_path}"')

        except Exception as e:
            self.logger.log(f"🔥 Ошибка применения изменений: {e}", "ERROR")
            messagebox.showerror("Ошибка", f"Не удалось применить изменения:\n{e}", parent=self.root)
        finally:
            self.progress.pack_forget()
            self.is_running = False

    def on_closing(self):
        """Обработка закрытия приложения"""
        self.is_running = False
        self.is_paused = False

        for window in self.preview_windows[:]:
            try:
                window.destroy()
            except:
                pass

        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

        self.root.destroy()


def main():

    if sys.platform == 'win32':
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

    root = tk.Tk()
    app = ImageReplacerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
