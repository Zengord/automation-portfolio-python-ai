import os


OUTPUT_FILENAME = 'full_project_code.txt'


IGNORED_DIRS = {
    'node_modules',
    '.git',
    '.next',
    '.vscode',
    '.idea',
    'dist',
    'build',
    'coverage'
}


IGNORED_FILES = {
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    '.DS_Store',
    '.env',
    '.env.local',
    OUTPUT_FILENAME
}


INCLUDED_EXTENSIONS = {

    '.jsx', '.js',
    '.tsx', '.ts',

    '.css', '.scss', '.sass', '.less', '.module.css',

    '.html',
    '.json',
    '.md'
}

def get_project_path():
    """Запрашивает путь у пользователя и очищает его от кавычек."""
    path = input("Введите (или вставьте) путь к папке проекта: ").strip()

    path = path.strip('"').strip("'")
    return path

def collect_code(root_dir):
    output_path = os.path.join(root_dir, OUTPUT_FILENAME)

    print(f"\nНачинаю сканирование папки: {root_dir}...")

    count = 0

    try:
        with open(output_path, 'w', encoding='utf-8') as outfile:


            for dirpath, dirnames, filenames in os.walk(root_dir):


                dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS]

                for filename in filenames:

                    if filename in IGNORED_FILES:
                        continue


                    _, ext = os.path.splitext(filename)
                    if ext.lower() in INCLUDED_EXTENSIONS:

                        full_path = os.path.join(dirpath, filename)

                        rel_path = os.path.relpath(full_path, root_dir)

                        try:
                            with open(full_path, 'r', encoding='utf-8') as infile:
                                content = infile.read()


                                outfile.write(f"{'='*60}\n")
                                outfile.write(f"FILE: {rel_path}\n")
                                outfile.write(f"{'='*60}\n")
                                outfile.write(content)
                                outfile.write("\n\n")

                                print(f"Обработан: {rel_path}")
                                count += 1

                        except Exception as e:
                            print(f"⚠️ Ошибка при чтении {rel_path}: {e}")

        print(f"\n--- ГОТОВО ---")
        print(f"Всего собрано файлов: {count}")
        print(f"Результат сохранен в: {output_path}")

    except OSError as e:
        print(f"Ошибка доступа или записи файла: {e}")

if __name__ == '__main__':
    target_path = get_project_path()

    if os.path.isdir(target_path):
        collect_code(target_path)
    else:
        print("❌ Ошибка: Указанный путь не существует или это не папка.")
