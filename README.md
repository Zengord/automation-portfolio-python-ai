# Python Automation Portfolio

Набор Python-утилит, которые я делал для автоматизации рабочих задач: сбор контекста проекта для ИИ, проверка локальных сайтов, оптимизация фронтенда, обработка изображений и запуск собственных скриптов из единого интерфейса.

Главная идея репозитория: показать практический подход к автоматизации рутины. Я беру повторяющуюся ручную задачу, раскладываю ее на понятные шаги, добавляю проверки и собираю инструмент, которым можно пользоваться повторно.

## Projects

### Site Context Extractor

Файлы:

- `src/site_context_extractor/create_context.py`
- `src/site_context_extractor/collect_project.py`

Утилиты для подготовки контекста проекта перед работой с ИИ-инструментами. Скрипты обходят папку проекта, собирают нужные HTML/CSS/JS/JSON/Markdown-файлы и формируют единый текстовый файл.

Что автоматизирует:

- ручной сбор файлов из разных папок;
- подготовку структурированного контекста для ChatGPT, Claude или другой LLM;
- исключение служебных директорий, зависимостей и локальных секретов.

### Website Auditor

Файл:

- `src/website_auditor/check_links.py`

CLI-утилита для проверки локального сайта перед сдачей или публикацией.

Проверяет:

- битые локальные ссылки;
- битые якоря;
- отсутствующие изображения;
- favicon;
- базовую HTML-структуру;
- inline styles;
- текстовые placeholder-ы;
- неиспользуемые страницы и изображения.

### Frontend Optimizer

Файлы:

- `src/frontend_optimizer/optimizer_frontend.py`
- `src/frontend_optimizer/restore_source.py`

Инструменты для оптимизации фронтенд-проекта и обратного восстановления исходной структуры.

Что умеют:

- создавать адаптивные версии изображений;
- генерировать WebP/AVIF;
- обновлять HTML/CSS под оптимизированные ассеты;
- откатывать оптимизированную версию обратно к исходной структуре.

### Image Automation

Файл:

- `src/image_automation/app.py`

GUI-инструмент для подбора, просмотра и замены изображений в локальном сайте.

Использует:

- Selenium для поиска изображений;
- BeautifulSoup для анализа HTML;
- Pillow для обработки превью;
- очереди и фоновые потоки для работы интерфейса;
- локальное логирование и резервные копии перед изменениями.

### Script Manager

Файл:

- `src/script_manager/script_manager.py`

GUI-менеджер локальных Python-скриптов. Помогает находить `.py`-файлы в выбранной папке, хранить описания и запускать нужные утилиты из одного окна.

## Tech Stack

- Python
- BeautifulSoup
- Pillow
- Selenium
- requests
- pandas
- tkinter / customtkinter / PyQt6
- HTML/CSS processing
- file automation
- image processing

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage Examples

```bash
python src/site_context_extractor/collect_project.py
python src/website_auditor/check_links.py
python src/frontend_optimizer/optimizer_frontend.py
```

Некоторые инструменты имеют GUI и открывают окно выбора папки.

## Notes

Это портфолио рабочих автоматизаций, поэтому часть скриптов ориентирована на Windows и локальные проекты. Следующие улучшения, которые я бы добавил:

- единый CLI-интерфейс через `argparse`;
- тестовые HTML/CSS fixtures;
- GitHub Actions для smoke-тестов;
- конфигурацию через `.env.example` и YAML/JSON;
- возможность запускать проверки через внешний workflow-инструмент, webhook или расписание.
