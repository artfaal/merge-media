#!/usr/bin/env python3

import argparse
import os
import sys
import glob
import subprocess
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

# Настройка логирования
logging.basicConfig(filename='merge_media.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def find_files_with_pattern(directory, pattern):
    """Ищет файлы в директории с учетом специальных символов"""
    files = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if re.match(pattern, filename):
                files.append(os.path.join(root, filename))
    return files

def process_video(video_path, source_dir, dest_dir, audio_groups=None, subtitle_groups=None, check_only=False):
    video_filename = os.path.basename(video_path)
    base_name, video_ext = os.path.splitext(video_filename)
    base_name_escaped = re.escape(base_name)

    print(f"\nВидео: {video_filename}")
    print(f"Базовое имя файла: {base_name}")

    logging.info(f"Обработка файла: {video_filename}")

    # Инициализируем списки для аудио и субтитров
    audio_files = []
    subtitle_files = []

    # Поиск аудиодорожек
    audio_groups_dirs = []
    if audio_groups:
        # Проверяем, что указанные группы существуют
        for group in audio_groups:
            group_dir = os.path.join(source_dir, "RUS Sound", group)
            if os.path.isdir(group_dir):
                audio_groups_dirs.append((group_dir, group))
            else:
                print(f"Предупреждение: Группа аудио '{group}' не найдена.")
    else:
        # Используем все группы
        group_dirs = glob.glob(os.path.join(source_dir, "RUS Sound", "*"))
        audio_groups_dirs = [(group_dir, os.path.basename(group_dir)) for group_dir in group_dirs if os.path.isdir(group_dir)]

    for group_dir, group_name in audio_groups_dirs:
        pattern = f"^{base_name_escaped}.*\\.mka$"
        print(f"Ищем аудио в группе '{group_name}' по шаблону: {pattern}")
        group_audio_files = []
        for filename in os.listdir(group_dir):
            if re.match(pattern, filename):
                group_audio_files.append(os.path.join(group_dir, filename))
        for audio_file in group_audio_files:
            print(f" - Найдена аудиодорожка: {audio_file}")
            audio_files.append((audio_file, group_name))

    # Поиск субтитров
    subtitle_groups_dirs = []
    if subtitle_groups:
        # Проверяем, что указанные группы существуют
        for group in subtitle_groups:
            group_dir = os.path.join(source_dir, "RUS Subs", group)
            if os.path.isdir(group_dir):
                subtitle_groups_dirs.append((group_dir, group))
            else:
                print(f"Предупреждение: Группа субтитров '{group}' не найдена.")
    else:
        # Используем все группы
        group_dirs = glob.glob(os.path.join(source_dir, "RUS Subs", "*"))
        subtitle_groups_dirs = [(group_dir, os.path.basename(group_dir)) for group_dir in group_dirs if os.path.isdir(group_dir)]

    for group_dir, group_name in subtitle_groups_dirs:
        pattern = f"^{base_name_escaped}.*\\.ass$"
        print(f"Ищем субтитры в группе '{group_name}' по шаблону: {pattern}")
        group_subtitle_files = []
        for filename in os.listdir(group_dir):
            if re.match(pattern, filename):
                group_subtitle_files.append(os.path.join(group_dir, filename))
        for subtitle_file in group_subtitle_files:
            print(f" - Найдены субтитры: {subtitle_file}")
            subtitle_files.append((subtitle_file, group_name))

    if check_only:
        print(f"  Аудиодорожки:")
        for audio_file, group_name in audio_files:
            print(f"    - {os.path.basename(audio_file)} (Группа: {group_name})")
        print(f"  Субтитры:")
        for subtitle_file, group_name in subtitle_files:
            print(f"    - {os.path.basename(subtitle_file)} (Группа: {group_name})")
        return

    # Если нет аудио и субтитров, пропускаем обработку
    if not audio_files and not subtitle_files:
        print(f"Предупреждение: Для видео '{video_filename}' не найдено ни аудио, ни субтитров.")
        return

    # Формирование командных параметров для FFmpeg
    inputs = ['-i', video_path]
    maps = ['-map', '0:v', '-map', '0:a']
    codecs = ['-c:v', 'copy', '-c:a', 'copy', '-c:s', 'copy']
    metadata_options = ['-metadata:s:v:0', 'language=jpn', '-metadata:s:a:0', 'language=jpn']
    output_path = os.path.join(dest_dir, video_filename)

    stream_index = 1  # Начальный индекс для дополнительных аудио потоков (первый дополнительный)

    # Добавление аудио
    for idx, (audio_file, group_name) in enumerate(audio_files):
        inputs.extend(['-i', audio_file])
        maps.extend(['-map', f"{len(inputs)//2 - 1}:a"])
        # Добавляем метаданные
        metadata_options.extend([
            f"-metadata:s:a:{stream_index}", "language=rus",
            f"-metadata:s:a:{stream_index}", f"title={group_name}"
        ])
        stream_index += 1

    # Добавление субтитров
    subtitle_stream_index = 0
    for idx, (subtitle_file, group_name) in enumerate(subtitle_files):
        inputs.extend(['-i', subtitle_file])
        maps.extend(['-map', f"{len(inputs)//2 - 1}:s"])
        # Добавляем метаданные
        metadata_options.extend([
            f"-metadata:s:s:{subtitle_stream_index}", "language=rus",
            f"-metadata:s:s:{subtitle_stream_index}", f"title={group_name}"
        ])
        subtitle_stream_index += 1

    # Создание выходной директории, если ее нет
    os.makedirs(dest_dir, exist_ok=True)

    ffmpeg_command = ['ffmpeg', '-y'] + inputs + maps + codecs + metadata_options + [output_path]

    print(f"Команда FFmpeg: {' '.join(ffmpeg_command)}")

    # Запуск FFmpeg
    try:
        subprocess.run(ffmpeg_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info(f"Файл успешно сохранен: {output_path}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Ошибка при обработке файла {video_filename}: {e.stderr.decode('utf-8')}")
        print(f"Ошибка при обработке файла {video_filename}. Подробности в лог-файле.")

def main():
    parser = argparse.ArgumentParser(description="Скрипт для объединения видеофайлов с аудио и субтитрами.")
    parser.add_argument('-s', '--source', help='Исходная директория', default='.')
    parser.add_argument('-d', '--dest', help='Выходная директория', default=None)
    parser.add_argument('-c', '--check', help='Режим проверки', action='store_true')
    parser.add_argument('-a', '--audio-groups', nargs='+', help='Группы аудио для включения', default=None)
    parser.add_argument('-sub', '--subtitle-groups', nargs='+', help='Группы субтитров для включения', default=None)
    parser.add_argument('-t', '--threads', type=int, help='Количество потоков для параллельной обработки', default=1)
    args = parser.parse_args()

    source_dir = args.source
    dest_dir = args.dest or f"{source_dir}_converted"

    # Проверяем существование исходной директории
    if not os.path.isdir(source_dir):
        print(f"Ошибка: Исходная директория '{source_dir}' не найдена.")
        sys.exit(1)

    # Поиск всех видеофайлов
    video_files = []
    for filename in os.listdir(source_dir):
        if filename.endswith('.mkv'):
            video_files.append(os.path.join(source_dir, filename))

    if not video_files:
        print("Не найдено видеофайлов для обработки.")
        sys.exit(1)

    if args.check:
        print("Режим проверки активирован. Будет выведена информация о файлах для обработки.")
        for video_file in video_files:
            process_video(video_file, source_dir, dest_dir, args.audio_groups, args.subtitle_groups, check_only=True)
        sys.exit(0)

    # Обработка видеофайлов с прогресс-баром
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        list(tqdm(executor.map(lambda vf: process_video(vf, source_dir, dest_dir, args.audio_groups, args.subtitle_groups), video_files), total=len(video_files), desc="Обработка файлов"))

    print("Обработка завершена.")

if __name__ == "__main__":
    main()

