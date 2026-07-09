import os
import shutil
import re
from PIL import Image
from bs4 import BeautifulSoup
import pillow_avif
from urllib.parse import quote


SRCSET_WIDTHS = [320, 480, 640, 768, 1024, 1280, 1600, 1920]
JPG_QUALITY = 75
ENABLE_AVIF = True
ENABLE_WEBP = True
DEFAULT_SIZES_ATTR = "(max-width: 768px) 100vw, (max-width: 1280px) 50vw, 1280px"
IGNORE_FILENAMES = ['favicon', 'apple-touch-icon']


def get_source_directory():
    """Запрашивает у пользователя путь к исходной папке сайта."""
    while True:
        path = input("Пожалуйста, введите полный путь к папке с вашим сайтом: ")
        path = path.strip().strip('"')
        if os.path.isdir(path):
            return path
        else:
            print("\n❌ ОШИБКА: Указанный путь не существует или не является папкой.\n")

def create_responsive_images(source_path, output_dir):
    """
    Создает набор адаптивных изображений (сжатый оригинал, WebP, AVIF)
    для указанного исходного файла.
    """
    try:
        with Image.open(source_path) as img:
            original_width, original_height = img.size
            base_name = os.path.splitext(os.path.basename(source_path))[0]

            generated_files = {'original': [], 'webp': [], 'avif': []}
            temp_dir = os.path.join(output_dir, "temp_processing")
            os.makedirs(temp_dir, exist_ok=True)

            widths_to_process = {w for w in SRCSET_WIDTHS if w < original_width}
            widths_to_process.add(original_width)

            print(f"  - Обработка {os.path.basename(source_path)} (размеры: {sorted(list(widths_to_process))})")

            for width in sorted(list(widths_to_process), reverse=True):
                is_largest_version = (width == original_width)
                file_suffix = "" if is_largest_version else f"-{width}w"

                resized_img = img
                if not is_largest_version:
                    ratio = width / original_width
                    height = int(img.height * ratio)
                    resized_img = img.resize((width, height), Image.Resampling.LANCZOS)

                original_ext = os.path.splitext(source_path)[1].lower()
                final_path = os.path.join(output_dir, base_name + file_suffix + original_ext)
                temp_path = os.path.join(temp_dir, os.path.basename(final_path))


                if original_ext == '.png':
                    resized_img.save(temp_path, optimize=True)
                else:
                    rgb_img = resized_img.convert("RGB")
                    rgb_img.save(temp_path, quality=JPG_QUALITY, optimize=True, progressive=True)


                if is_largest_version:
                    source_size = os.path.getsize(source_path)
                    compressed_size = os.path.getsize(temp_path)

                    if compressed_size >= source_size:
                        print(f"    - 🟡 Наше сжатие не улучшило файл. Копируется оригинал: {os.path.basename(final_path)}")
                        shutil.copy2(source_path, final_path)
                    else:
                        print(f"    - ✨ Сжато: {os.path.basename(final_path)} (было {source_size} B, стало {compressed_size} B)")
                        shutil.move(temp_path, final_path)
                else:
                    shutil.move(temp_path, final_path)
                    print(f"    - ✨ Сжато: {os.path.basename(final_path)}")

                generated_files['original'].append((os.path.basename(final_path), width))


                if resized_img.mode != "RGBA":
                    save_img = resized_img.convert("RGBA")
                else:
                    save_img = resized_img

                if ENABLE_WEBP:
                    webp_path = os.path.join(output_dir, base_name + file_suffix + ".webp")
                    save_img.save(webp_path, format="WEBP", quality=JPG_QUALITY)
                    generated_files['webp'].append((os.path.basename(webp_path), width))
                if ENABLE_AVIF:
                    avif_path = os.path.join(output_dir, base_name + file_suffix + ".avif")
                    save_img.save(avif_path, format="AVIF", quality=JPG_QUALITY)
                    generated_files['avif'].append((os.path.basename(avif_path), width))

            shutil.rmtree(temp_dir)
            return generated_files, original_width, original_height

    except Exception as e:
        print(f"  - 🔴 ОШИБКА при создании адаптивных версий для {source_path}: {e}")
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return None, None, None

def convert_to_webp(source_image_path, output_image_path):
    """Конвертирует одно изображение в WebP для использования в CSS."""
    try:
        with Image.open(source_image_path) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(output_image_path, format="WEBP", quality=JPG_QUALITY)
            print(f"  - 🖼️  Конвертировано в WebP: {os.path.basename(output_image_path)}")
            return True
    except Exception as e:
        print(f"  - 🔴 ОШИБКА при конвертации в WebP для {source_image_path}: {e}")
        return False

def optimize_html(source_path, output_path, source_dir, output_dir, image_cache):
    """Находит все теги <img> в HTML, заменяет их на <picture> с адаптивными версиями."""
    with open(source_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    to_html_path = lambda p: p.replace('\\', '/')

    for img in soup.find_all('img'):
        original_src = img.get('src')
        if not original_src or original_src.startswith('data:'): continue
        if any(ignored_name in original_src.lower() for ignored_name in IGNORE_FILENAMES): continue

        src_lower = original_src.lower()
        if src_lower.endswith(('.svg', '.webp', '.avif', '.gif')):
            if not img.has_attr('loading'): img['loading'] = 'lazy'
            continue

        if original_src.startswith('/'):
            img_path = os.path.join(source_dir, original_src.lstrip('/\\'))
        else:
            img_path = os.path.join(os.path.dirname(source_path), original_src)
        img_path = os.path.normpath(img_path)

        if not os.path.exists(img_path):
            print(f"  - 🔴 ВНИМАНИЕ: Файл изображения не найден по пути: {img_path}")
            continue

        if img_path in image_cache:
            generated_files, width, height = image_cache[img_path]
            print(f"  - 🔵 Используются кешированные версии для {os.path.basename(img_path)}")
        else:
            img_output_dir = os.path.dirname(os.path.join(output_dir, os.path.relpath(img_path, source_dir)))
            os.makedirs(img_output_dir, exist_ok=True)
            generated_files, width, height = create_responsive_images(img_path, img_output_dir)
            if generated_files:
                image_cache[img_path] = (generated_files, width, height)

        if not generated_files: continue

        if width and height:
            if not img.has_attr('width'): img['width'] = str(width)
            if not img.has_attr('height'): img['height'] = str(height)

        picture_tag = soup.new_tag('picture')

        for key in generated_files:
            generated_files[key].sort(key=lambda x: x[1], reverse=True)

        if generated_files['original']:
             smallest_original = generated_files['original'][-1][0]

             img['src'] = quote(to_html_path(os.path.join(os.path.dirname(original_src), smallest_original)))

        if ENABLE_AVIF and generated_files.get('avif'):

            avif_srcset = ", ".join([f"{quote(to_html_path(os.path.join(os.path.dirname(original_src), f)))} {w}w" for f, w in generated_files['avif']])
            picture_tag.append(soup.new_tag('source', type='image/avif', srcset=avif_srcset, sizes=DEFAULT_SIZES_ATTR))

        if ENABLE_WEBP and generated_files.get('webp'):

            webp_srcset = ", ".join([f"{quote(to_html_path(os.path.join(os.path.dirname(original_src), f)))} {w}w" for f, w in generated_files['webp']])
            picture_tag.append(soup.new_tag('source', type='image/webp', srcset=webp_srcset, sizes=DEFAULT_SIZES_ATTR))

        if generated_files.get('original'):

            original_srcset = ", ".join([f"{quote(to_html_path(os.path.join(os.path.dirname(original_src), f)))} {w}w" for f, w in generated_files['original']])
            img['srcset'] = original_srcset
            img['sizes'] = DEFAULT_SIZES_ATTR

        img['loading'] = 'lazy'
        img['decoding'] = 'async'
        img.wrap(picture_tag)

    for iframe in soup.find_all('iframe'): iframe['loading'] = 'lazy'
    for script in soup.find_all('script'):
        if script.get('src') and not script.has_attr('async') and not script.has_attr('defer'):
            script['defer'] = True

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))

def optimize_css(source_css_path, output_css_path, source_dir, output_dir, css_image_cache):
    """Находит url() в CSS, конвертирует изображения в WebP и обновляет пути."""
    with open(source_css_path, 'r', encoding='utf-8') as f:
        content = f.read()

    urls = re.findall(r'url\((.*?)\)', content)
    to_html_path = lambda p: p.replace('\\', '/')

    for url_match in set(urls):
        original_url = url_match.strip().strip("'\"")
        if original_url.startswith(('data:', 'http', '#')) or not original_url.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue

        if original_url.startswith('/'):
            source_image_path = os.path.normpath(os.path.join(source_dir, original_url.lstrip('/\\')))
        else:
            source_image_path = os.path.normpath(os.path.join(os.path.dirname(source_css_path), original_url))

        if not os.path.exists(source_image_path):
            print(f"  - 🔴 ВНИМАНИЕ (в CSS): Файл изображения не найден: {source_image_path}")
            continue

        if source_image_path in css_image_cache:
            output_webp_path = css_image_cache[source_image_path]
        else:
            base, _ = os.path.splitext(source_image_path)
            output_webp_path = os.path.join(output_dir, os.path.relpath(base + ".webp", source_dir))
            os.makedirs(os.path.dirname(output_webp_path), exist_ok=True)
            if convert_to_webp(source_image_path, output_webp_path):
                css_image_cache[source_image_path] = output_webp_path
            else:
                continue


        new_url = quote(to_html_path(os.path.splitext(original_url)[0] + ".webp"))
        content = content.replace(original_url, new_url)

    with open(output_css_path, 'w', encoding='utf-8') as f:
        f.write(content)

def main():
    """Главная функция, orchestrator всего процесса оптимизации."""
    source_dir = get_source_directory()
    output_dir = os.path.join(os.path.dirname(source_dir), os.path.basename(source_dir) + "_optimized")

    html_image_cache = {}
    css_image_cache = {}

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    print(f"\nНачало фронтенд-оптимизации. Исходная папка: {source_dir}")
    print(f"Результат будет сохранен в: {output_dir}\n")

    print("--- Шаг 1: Копирование ассетов и оптимизация CSS ---")
    for root, dirs, files in os.walk(source_dir):
        for d in dirs:
            os.makedirs(os.path.join(output_dir, os.path.relpath(os.path.join(root, d), source_dir)), exist_ok=True)

        for file in files:
            source_path = os.path.join(root, file)
            output_path = os.path.join(output_dir, os.path.relpath(source_path, source_dir))
            ext = os.path.splitext(file)[1].lower()

            if ext in ['.html', '.jpg', '.jpeg', '.png']:
                continue

            if ext == '.css':
                print(f"Обработка CSS: {file}")
                optimize_css(source_path, output_path, source_dir, output_dir, css_image_cache)
            else:
                shutil.copy2(source_path, output_path)
                print(f"  - Скопирован файл: {file}")

    print("\n--- Шаг 2: Оптимизация HTML и генерация изображений ---")
    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.lower().endswith('.html'):
                source_path = os.path.join(root, file)
                output_path = os.path.join(output_dir, os.path.relpath(source_path, source_dir))
                print(f"Обработка HTML: {file}")
                optimize_html(source_path, output_path, source_dir, output_dir, html_image_cache)

    print(f"\n✅ Оптимизация завершена! Результаты находятся в папке: {output_dir}")

if __name__ == "__main__":
    main()
