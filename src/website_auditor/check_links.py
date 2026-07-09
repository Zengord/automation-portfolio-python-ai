import os
import re
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote


try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    COLOR_SUPPORT = True
except ImportError:

    class DummyColor:
        def __getattr__(self, name):
            return ""
    Fore = DummyColor()
    Style = DummyColor()
    COLOR_SUPPORT = False


IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico']
CSS_EXTENSIONS = ['.css']
HTML_EXTENSIONS = ['.html']
JS_EXTENSIONS = ['.js']

def find_files(root_dir, extensions):
    """Находит все файлы с указанными расширениями."""
    found_files = []
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if any(filename.lower().endswith(ext) for ext in extensions):
                found_files.append(os.path.join(dirpath, filename))
    return found_files

def resolve_path(base_path, href, root_dir):
    """Преобразует относительный путь в абсолютный."""
    if href.startswith('/'):
        target_path = os.path.join(root_dir, href.lstrip('/\\'))
    else:
        current_dir = os.path.dirname(base_path)
        target_path = os.path.join(current_dir, href)
    return os.path.normpath(target_path)

def analyze_website(root_dir):
    """Комплексно анализирует сайт."""
    html_files = find_files(root_dir, HTML_EXTENSIONS)
    css_files = find_files(root_dir, CSS_EXTENSIONS)
    js_files = find_files(root_dir, JS_EXTENSIONS)
    all_image_files = set(find_files(root_dir, IMAGE_EXTENSIONS))

    reports = {
        "broken_links": {}, "broken_anchors": {}, "broken_images": {}, "orphan_pages": set(), "orphan_images": set(),
        "html_structure": {'no_title': [], 'no_description': [], 'no_main': [], 'no_h1': [], 'no_favicon': []},
        "inline_styles": {}, "placeholders": {}
    }
    linked_pages = set()
    referenced_images = set()
    anchor_targets = {}


    print(f"🔍 Начинаю анализ. Найдено: {len(html_files)} HTML, {len(css_files)} CSS, {len(js_files)} JS, {len(all_image_files)} изображений.")


    print("...предварительный анализ: ищу все якоря (ID)...")
    for html_path in html_files:
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
                soup = BeautifulSoup(content, 'lxml')

                ids = {tag['id'] for tag in soup.find_all(id=True)}
                names = {tag['name'] for tag in soup.find_all('a', attrs={'name': True})}
                anchor_targets[html_path] = ids.union(names)
        except Exception as e:
            print(f"{Fore.RED}❌ Не удалось прочитать файл на этапе сбора якорей: {html_path}. Ошибка: {e}")


    print("...анализирую HTML файлы...")
    placeholder_pattern = re.compile(r'\[[^\]]+\]')
    for html_path in html_files:
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
                soup = BeautifulSoup(content, 'lxml')
        except Exception as e:
            print(f"{Fore.RED}❌ Не удалось прочитать файл: {html_path}. Ошибка: {e}"); continue


        if not soup.title or not soup.title.string.strip(): reports['html_structure']['no_title'].append(html_path)
        if not soup.find('meta', attrs={'name': 'description'}): reports['html_structure']['no_description'].append(html_path)
        if not soup.find('main'): reports['html_structure']['no_main'].append(html_path)
        if not soup.h1 or not soup.h1.get_text(strip=True): reports['html_structure']['no_h1'].append(html_path)


        favicon_link = soup.find('link', rel=lambda r: r and 'icon' in r)
        if not favicon_link or not favicon_link.get('href'):
            reports['html_structure']['no_favicon'].append(html_path)
        else:
            favicon_path = resolve_path(html_path, favicon_link['href'].strip(), root_dir)
            if not os.path.exists(favicon_path):
                reports['broken_images'].setdefault(html_path, []).append(f"{favicon_link['href'].strip()} (favicon)")
            else:
                referenced_images.add(favicon_path)


        styled_tags = soup.find_all(style=True)
        if styled_tags:
            reports['inline_styles'][html_path] = [str(tag.name) for tag in styled_tags]


        found_placeholders = placeholder_pattern.findall(content)
        if found_placeholders:
            reports['placeholders'][html_path] = found_placeholders


        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            if not href or href.startswith(('mailto:', 'tel:', 'javascript:')) or urlparse(href).scheme:
                continue

            path_part, _, anchor_part = href.partition('#')
            path_part = unquote(path_part) if path_part else ''

            target_file_path = None


            if path_part:
                resolved = resolve_path(html_path, path_part, root_dir)
                if os.path.isdir(resolved) and os.path.exists(os.path.join(resolved, 'index.html')):
                    target_file_path = os.path.join(resolved, 'index.html')
                else:
                    target_file_path = resolved
            else:
                target_file_path = html_path


            if path_part:
                if not os.path.exists(target_file_path):
                    reports['broken_links'].setdefault(html_path, []).append(href)
                    continue


                if target_file_path.lower().endswith(tuple(HTML_EXTENSIONS)):
                    linked_pages.add(target_file_path)


            if anchor_part:

                if not target_file_path.lower().endswith(tuple(HTML_EXTENSIONS)):
                    reports['broken_anchors'].setdefault(html_path, []).append(f"{href} (ссылка на якорь в не-HTML файле)")
                    continue

                available_anchors = anchor_targets.get(target_file_path)
                if not available_anchors or anchor_part not in available_anchors:
                    reports['broken_anchors'].setdefault(html_path, []).append(href)


        for img_tag in soup.find_all(['img', 'source']):
            src = img_tag.get('src', '').strip() or img_tag.get('srcset', '').strip().split(' ')[0]
            if src and not src.startswith(('http', 'data:')):
                img_path = resolve_path(html_path, src, root_dir)
                if not os.path.exists(img_path):
                    reports['broken_images'].setdefault(html_path, []).append(src)
                else:
                    referenced_images.add(img_path)


    print("...анализирую CSS файлы...")
    url_pattern = re.compile(r'url\s*\(([^)]+)\)')
    for css_path in css_files:
        try:
            with open(css_path, 'r', encoding='utf-8') as f: content = f.read()
        except Exception as e: print(f"{Fore.RED}❌ Не удалось прочитать файл: {css_path}. Ошибка: {e}"); continue

        for match in url_pattern.finditer(content):
            url_value = match.group(1).strip('\'"')
            if not url_value or url_value.startswith(('#', 'data:')) or urlparse(url_value).scheme: continue


            if any(url_value.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                img_path = resolve_path(css_path, url_value, root_dir)
                if not os.path.exists(img_path):
                    reports['broken_images'].setdefault(css_path, []).append(url_value)
                else:
                    referenced_images.add(img_path)


    print("...анализирую JS файлы...")


    extensions_pattern = '|'.join([ext.lstrip('.') for ext in IMAGE_EXTENSIONS])
    js_image_pattern = re.compile(r'[\'"`]([^\'"`]+\.(?:' + extensions_pattern + '))[\'"`]')

    for js_path in js_files:
        try:
            with open(js_path, 'r', encoding='utf-8') as f: content = f.read()
        except Exception as e: print(f"{Fore.RED}❌ Не удалось прочитать файл: {js_path}. Ошибка: {e}"); continue

        for match in js_image_pattern.finditer(content):
            img_src = match.group(1)
            if not img_src or img_src.startswith(('http', 'data:')): continue

            img_path = resolve_path(js_path, img_src, root_dir)
            if not os.path.exists(img_path):
                reports['broken_images'].setdefault(js_path, []).append(img_src)
            else:
                referenced_images.add(img_path)


    main_index_path = os.path.join(root_dir, 'index.html')
    reports['orphan_pages'] = set(html_files) - linked_pages

    if main_index_path in html_files:
        reports['orphan_pages'].discard(main_index_path)

    reports['orphan_images'] = all_image_files - referenced_images

    return reports


def print_report_section(title, report_data, root_dir, color, icon, item_color=None):
    """Универсальная функция для печати секции отчета."""
    header = f" {title} "
    width = (60 - len(header)) // 2
    print("\n" + "="*width + header + "="*width)

    if not report_data:
        msg = f"🎉 Проблем не найдено."
        print(color + msg)
        return [f"\n--- {title} ---", msg]

    count = sum(len(v) for v in report_data.values()) if isinstance(report_data, dict) else len(report_data)
    msg = f"🚨 Найдено проблем: {count}"
    print(item_color or color, Style.BRIGHT, msg, "\n")
    lines = [f"\n--- {title} ---", msg]

    if isinstance(report_data, dict):
        for file, items in sorted(report_data.items()):
            rel_path = os.path.relpath(file, root_dir)

            file_icon = "📜" if file.endswith(".js") else "📄"
            print(f"В файле: {file_icon} {Fore.CYAN}{rel_path}")
            lines.append(f"\nВ файле: {rel_path}")
            for item in sorted(items):
                print(f"  -> {icon} {item_color or color}{item}")
                lines.append(f"  -> {icon} {item}")
    elif isinstance(report_data, set):
        for item in sorted(list(report_data)):
            rel_path = os.path.relpath(item, root_dir)
            print(f"  -> {icon} {item_color or color}{rel_path}")
            lines.append(f"  -> {icon} {rel_path}")

    return lines


def main():
    if not COLOR_SUPPORT: print("💡 Совет: установите 'colorama' (`pip install colorama`) для цветного вывода.")

    path_input = input(f"➡️  Введите путь к корневой папке сайта:\n{Style.DIM}(оставьте пустым для текущей папки): {Style.RESET_ALL}")
    root_dir = os.path.abspath(path_input or '.')

    if not os.path.isdir(root_dir):
        print(f"{Fore.RED}❌ Ошибка: Путь '{root_dir}' не является папкой."); return

    print(f"\n{Fore.GREEN}✅ Принято! Проверяю папку: {Style.BRIGHT}{root_dir}\n")

    results = analyze_website(root_dir)
    report_lines = [f"Отчет о проверке сайта: {root_dir}", f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    is_site_perfect = True


    structure_errors = {k: v for k, v in results['html_structure'].items() if v}
    if structure_errors:
        is_site_perfect = False
        issue_map = {
            'no_title': '🚨 Отсутствует/пуст <title>:', 'no_description': '🚨 Отсутствует <meta name="description">:',
            'no_main': '🚨 Отсутствует <main>:', 'no_h1': '🚨 Отсутствует/пуст <h1>:',
            'no_favicon': '🚨 Нет ссылки на favicon:'
        }
        header = " ОТЧЕТ О СТРУКТУРЕ HTML "
        print("\n" + "="*18 + header + "="*18); report_lines.extend(["\n" + "="*50, header.strip(), "="*50])
        for issue_type, files in structure_errors.items():
            print(Fore.YELLOW + Style.BRIGHT + issue_map[issue_type]); report_lines.append("\n" + issue_map[issue_type])
            for file in sorted(files):
                rel_path = os.path.relpath(file, root_dir)
                print(f"  -> 📄 {Fore.YELLOW}{rel_path}"); report_lines.append(f"  -> 📄 {rel_path}")

    sections = [
        ("ОТЧЕТ О БИТЫХ ССЫЛКАХ (файлы не найдены)", results['broken_links'], Fore.RED, "🔗"),
        ("ОТЧЕТ О БИТЫХ ЯКОРЯХ (#...)", results['broken_anchors'], Fore.RED, "⚓"),
        ("ОТЧЕТ О БИТЫХ ИЗОБРАЖЕНИЯХ", results['broken_images'], Fore.RED, "🖼️"),
        ("ОТЧЕТ ОБ ИНЛАЙН-СТИЛЯХ (style=...)", results['inline_styles'], Fore.YELLOW, "🎨"),
        ("ОТЧЕТ О ТЕКСТЕ-ЗАПОЛНИТЕЛЕ ([...])", results['placeholders'], Fore.YELLOW, "✏️"),
        ("ОТЧЕТ О СТРАНИЦАХ-СИРОТАХ", results['orphan_pages'], Fore.YELLOW, "📄"),
        ("ОТЧЕТ ОБ ИЗОБРАЖЕНИЯХ-СИРОТАХ", results['orphan_images'], Fore.YELLOW, "🖼️"),
    ]

    for title, data, color, icon in sections:
        if data: is_site_perfect = False
        report_lines.extend(print_report_section(title, data, root_dir, color, icon))


    if is_site_perfect:
        print("\n" + "="*24 + " РЕЗУЛЬТАТ " + "="*25)
        msg = "🎉 Поздравляю! Все проверки пройдены успешно. Проблем не найдено."
        print(f"{Fore.GREEN}{Style.BRIGHT}{msg}")
        report_lines.append("\n" + "="*50 + "\nРЕЗУЛЬТАТ: Все проверки пройдены успешно.")
    else:
        print(f"\n{Fore.RED}{Style.BRIGHT}❌ Проверка завершена с ошибками. Пожалуйста, исправьте найденные проблемы.")
        report_lines.append("\n" + "="*50 + "\nРЕЗУЛЬТАТ: Проверка завершена с ошибками.")


        if results['orphan_images']:
            print("\n" + "-"*50)
            print(f"{Fore.RED}{Style.BRIGHT}ВНИМАНИЕ! Следующее действие необратимо.{Style.RESET_ALL}")
            if input(f"Хотите удалить {len(results['orphan_images'])} изображений-сирот? (введите 'yes'): ").lower() == 'yes':
                print("\nНачинаю удаление..."); deleted_count = 0
                log = ["\n--- Лог удаления изображений-сирот ---"]
                for img_path in sorted(list(results['orphan_images'])):
                    try:
                        os.remove(img_path); deleted_count += 1
                        msg = f"🗑️  Удален файл: {os.path.relpath(img_path, root_dir)}"
                        print(Style.DIM + msg); log.append(msg)
                    except Exception as e:
                        msg = f"❌ Не удалось удалить {img_path}. Ошибка: {e}"
                        print(Fore.RED + msg); log.append(msg)

                final_msg = f"\nУдаление завершено. Успешно удалено файлов: {deleted_count} из {len(results['orphan_images'])}."
                print(f"{Fore.GREEN}✅ {final_msg.strip()}"); log.append(final_msg)
                report_lines.extend(log)
            else:
                msg = "\nℹ️ Удаление отменено пользователем."
                print(Fore.CYAN + msg.strip()); report_lines.append(msg)


    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"site_checker_report_{timestamp}.txt"
    filepath = os.path.join(root_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f: f.write("\n".join(report_lines))
        print(f"\n{Fore.GREEN}✅ Отчет сохранен в файл:{Style.BRIGHT}\n   {filepath}")
    except Exception as e:
        print(f"\n{Fore.RED}❌ Не удалось сохранить отчет. Ошибка: {e}")

if __name__ == "__main__":
    main()
