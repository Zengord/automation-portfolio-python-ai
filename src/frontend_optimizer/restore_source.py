import os
import shutil
import re
from bs4 import BeautifulSoup
from PIL import Image

def get_optimized_directory():
    """Запрашивает у пользователя путь к оптимизированной папке сайта."""
    while True:
        path = input("Пожалуйста, введите полный путь к папке с ОПТИМИЗИРОВАННЫМ сайтом (папка _optimized): ")
        path = path.strip().strip('"')
        if os.path.isdir(path):
            return path
        else:
            print("\n❌ ОШИБКА: Указанный путь не существует или не является папкой.\n")

def find_original_image(img_dir, base_name):
    """
    Находит оригинальный файл изображения наилучшего качества.
    Ищет файлы с расширениями jpg, png, svg, gif.
    """
    candidates = []
    pattern = re.compile(rf"^{re.escape(base_name)}(?:-(\d+)w)?\.(jpe?g|png|svg|gif)$", re.IGNORECASE)

    if not os.path.isdir(img_dir):
        return None, None

    for filename in os.listdir(img_dir):
        match = pattern.match(filename)
        if match:
            ext = match.group(2).lower()
            if ext in ['svg', 'gif']:
                candidates.append((99999, filename, ext))
                continue

            try:
                with Image.open(os.path.join(img_dir, filename)) as img:
                    real_width = img.width
                candidates.append((real_width, filename, ext))
            except Exception:
                continue

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_filename = candidates[0][1]
        original_ext = candidates[0][2]
        return os.path.join(img_dir, best_filename), original_ext

    return None, None

def _resolve_path(base_file_path, url, root_dir):
    """Вспомогательная функция для корректного определения абсолютного пути."""
    if url.startswith('/'):
        return os.path.normpath(os.path.join(root_dir, url.lstrip('/\\')))
    else:
        return os.path.normpath(os.path.join(os.path.dirname(base_file_path), url))

def restore_html(source_html_path, output_html_path, optimized_dir, restored_dir, restored_images):
    """Восстанавливает HTML-файл, заменяя <picture> на <img> и удаляя лишние атрибуты."""
    print(f"  - Восстановление HTML: {os.path.basename(source_html_path)}")
    with open(source_html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')


    for picture in soup.find_all('picture'):
        img_tag = picture.find('img')
        if not img_tag:
            picture.unwrap()
            continue

        src_for_name = img_tag.get('src', '')
        if not src_for_name:
            picture.replace_with(img_tag)
            continue

        base_name_with_suffix = os.path.splitext(os.path.basename(src_for_name))[0]
        base_name = re.sub(r'-\d+w$', '', base_name_with_suffix)

        optimized_img_dir = os.path.dirname(_resolve_path(source_html_path, src_for_name, optimized_dir))
        source_image_path, original_ext = find_original_image(optimized_img_dir, base_name)

        if not source_image_path:
            print(f"    - ⚠️ ПРЕДУПРЕЖДЕНИЕ (img): Не удалось найти исходный файл для '{base_name}'")
            picture.replace_with(img_tag)
            continue

        restored_img_filename = f"{base_name}.{original_ext}"
        relative_img_path = os.path.relpath(os.path.join(optimized_img_dir, restored_img_filename), os.path.dirname(source_html_path))
        new_src = relative_img_path.replace('\\', '/')

        restored_img_path_abs = os.path.join(os.path.dirname(_resolve_path(output_html_path, new_src, restored_dir)), restored_img_filename)

        if restored_img_path_abs not in restored_images:
            os.makedirs(os.path.dirname(restored_img_path_abs), exist_ok=True)
            shutil.copy2(source_image_path, restored_img_path_abs)
            restored_images.add(restored_img_path_abs)
            print(f"    - ✨ Восстановлено изображение: {os.path.relpath(restored_img_path_abs, restored_dir)}")

        new_img = soup.new_tag('img')
        new_img['src'] = new_src
        safe_attrs = ['alt', 'class', 'id', 'style', 'title']
        for attr in safe_attrs:
            if img_tag.has_attr(attr):
                new_img[attr] = img_tag[attr]

        picture.replace_with(new_img)


    for script in soup.find_all('script', defer=True):
        del script['defer']

    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))


def restore_css(source_css_path, output_css_path, optimized_dir, restored_dir, restored_images):
    """Восстанавливает CSS, заменяя .webp на оригинальные .jpg/.png."""
    print(f"  - Восстановление CSS: {os.path.basename(source_css_path)}")
    with open(source_css_path, 'r', encoding='utf-8') as f:
        content = f.read()

    urls = re.findall(r'url\((["\']?)(.*?)\1\)', content)

    for quote, url in set(urls):
        if not url.lower().endswith('.webp'):
            continue

        base_name = os.path.splitext(url)[0]
        webp_path = _resolve_path(source_css_path, url, optimized_dir)

        original_found = False
        for ext in ['.png', '.jpg', '.jpeg']:
            original_path = os.path.splitext(webp_path)[0] + ext
            if os.path.exists(original_path):
                new_url = base_name + ext

                restored_img_path = _resolve_path(output_css_path, new_url, restored_dir)
                if restored_img_path not in restored_images:
                    os.makedirs(os.path.dirname(restored_img_path), exist_ok=True)
                    shutil.copy2(original_path, restored_img_path)
                    restored_images.add(restored_img_path)
                    print(f"    - ✨ Восстановлен фон из оригинала: {os.path.relpath(restored_img_path, restored_dir)}")

                content = content.replace(url, new_url)
                original_found = True
                break

        if not original_found:
            print(f"    - ⚠️ Оригинал для {os.path.basename(url)} не найден, конвертируем из WebP...")
            if not os.path.exists(webp_path):
                print(f"    - ❌ Файл {webp_path} не найден. Пропускаем.")
                continue

            new_url = base_name + '.png'
            restored_img_path = _resolve_path(output_css_path, new_url, restored_dir)
            if restored_img_path not in restored_images:
                try:
                    os.makedirs(os.path.dirname(restored_img_path), exist_ok=True)
                    with Image.open(webp_path) as img:
                        img.save(restored_img_path, 'PNG')
                    restored_images.add(restored_img_path)
                    content = content.replace(url, new_url)
                except Exception as e:
                    print(f"    - ❌ ОШИБКА конвертации {os.path.basename(webp_path)}: {e}")

    with open(output_css_path, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    optimized_dir = get_optimized_directory()
    restored_dir = os.path.join(os.path.dirname(optimized_dir), os.path.basename(optimized_dir).replace("_optimized", "") + "_restored")

    if os.path.exists(restored_dir):
        choice = input(f"Папка для результата '{restored_dir}' уже существует. Удалить её и продолжить? (y/n): ").lower()
        if choice == 'y':
            shutil.rmtree(restored_dir)
        else:
            print("Отмена операции.")
            return

    os.makedirs(restored_dir)

    print(f"\nНачало восстановления. Результат будет в: {restored_dir}\n")

    restored_images = set()
    generated_file_pattern = re.compile(r'-\d+w\.(jpe?g|png|webp|avif)$', re.IGNORECASE)

    print("--- Сканирование и восстановление файлов ---")
    for root, dirs, files in os.walk(optimized_dir, topdown=True):
        dirs[:] = [d for d in dirs if d != 'temp_processing']

        rel_root = os.path.relpath(root, optimized_dir)
        output_root = os.path.join(restored_dir, rel_root) if rel_root != '.' else restored_dir
        if not os.path.exists(output_root):
             os.makedirs(output_root)

        for file in files:
            source_path = os.path.join(root, file)
            output_path = os.path.join(output_root, file)
            ext = os.path.splitext(file)[1].lower()


            if ext == '.html':
                restore_html(source_path, output_path, optimized_dir, restored_dir, restored_images)
            elif ext == '.css':
                restore_css(source_path, output_path, optimized_dir, restored_dir, restored_images)
            else:


                if generated_file_pattern.search(file):
                    continue


                if ext in ['.webp', '.avif']:
                    base_name = os.path.splitext(file)[0]

                    if (os.path.exists(os.path.join(root, base_name + '.jpg')) or
                        os.path.exists(os.path.join(root, base_name + '.jpeg')) or
                        os.path.exists(os.path.join(root, base_name + '.png'))):

                        continue


                if not os.path.exists(output_path):
                     shutil.copy2(source_path, output_path)

    print(f"\n✅ Восстановление завершено! Ваши чистые исходники находятся в папке: {restored_dir}")

if __name__ == "__main__":
    main()
