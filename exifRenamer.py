# coding=utf-8
from argparse import ArgumentParser
from collections import OrderedDict
from datetime import datetime, timedelta
from ntpath import basename, dirname, split
from os import getcwd, listdir, rename, stat
from os.path import getctime, isfile, join, splitext
from platform import system

from colorama import Fore, Style, init
from exifread import process_file
from progressbar import Bar, ETA, FormatLabel, Percentage, ProgressBar
from qprompt import ask_yesno

init()

EXIF_DATE_TIME_ORIGINAL = 'EXIF DateTimeOriginal'

image_extensions = [
    '.jpg',
    '.jpeg'
]

video_extensions = [
    '.mp4',
    '.mov',
    '.avi'
]


def has_extension(file, extensions):
    """
    Checks whether file name ends with any of the passed extensions.
    Matching is case-insensitive
    :param file: string that represents path to the file
    :param extensions: iterable of strings
    :return: Boolean
    """
    return any((file.lower().endswith(ext) for ext in extensions))


def is_image(file):
    """
    Checks whether file name ends with any of image extensions.
    :param file: string that represents path to the file
    :return: Boolean
    """
    return has_extension(file, image_extensions)


def is_video(file):
    """
        Checks whether file name ends with any of video extensions.
    :param file: string that represents path to the file
    :return: Boolean
    """
    return has_extension(file, video_extensions)


def creation_time(file):
    """
    Returns datetime when file was created,
    falls back to last modified if that isn't possible
    :param file: string that represents path to the file
    :return: datetime
    """
    if system() == 'Windows':
        return datetime.fromtimestamp(getctime(file))
    else:
        stats = stat(file)
        try:
            return datetime.fromtimestamp(stats.st_birthtime)
        except AttributeError:
            return datetime.fromtimestamp(stats.st_mtime)


def exif_creation_time(file):
    """
    Returns creation time of image using EXIF info
    :param file: string that represents path to the file
    :return: datetime if EXIF tag is present, None otherwise
    """
    with open(file, 'rb') as image:
        tags = process_file(image)

        if EXIF_DATE_TIME_ORIGINAL not in tags:
            return None

        date_time = tags[EXIF_DATE_TIME_ORIGINAL].printable
        return datetime.strptime(date_time, '%Y:%m:%d %H:%M:%S')


def renamed_file_name(file, target_datetime):
    """
    Returns renamed file name based on the specified datetime object
    :param file: string that represents path to the file
    :param target_datetime: datetime to rename the specified file
    :return: string that represents path to the renamed file
    """
    head, tail = split(file)
    dir_name = head if tail else dirname(head)
    file_name = tail or basename(head)
    extension = splitext(file_name)[1]
    return join(dir_name, target_datetime.strftime('%Y-%m-%d %H:%M:%S')
                + extension)


def calculate_renamings(file_to_time_map):
    """
    Calculates map of original file name to file name based on date
    present in the specified map. If there are collisions between
    target names, the '+1 second' strategy is applied multiple times
    until collision is resolved
    :param file_to_time_map: dictionary of string to datetime that 
    represents file path to its creation time
    :return: dictionary of string to tuple of string and boolean
    that represents original file path to its renamed file path and
    flag whether '+1 second' strategy has been applied to this file
    """
    sorted_info = sorted(file_to_time_map.items(), key=lambda p: p[1])
    renamings = {}

    for entry in sorted_info:
        file, original_time = entry
        time = original_time
        collision_resolved = False
        while not collision_resolved:
            if time in renamings:
                time += timedelta(seconds=1)
            else:
                renamings[time] = (file, time != original_time)
                collision_resolved = True

    result = {}

    for entry in renamings.items():
        target_datetime = entry[0]
        file = entry[1][0]
        renamed_file = renamed_file_name(file, target_datetime)
        strategy_applied = entry[1][1]
        result[file] = renamed_file, strategy_applied

    return result


def exif_time_else_creation_time(file):
    """
    Returns creation time of image using EXIF info or creation time
    based on file info if EXIF is absent
    :param file: string that represents path to the file
    :return: datetime
    """
    exif_info = exif_creation_time(file)
    return creation_time(file) if exif_info is None else exif_info


def dump_renamings(renamings_map):
    """
    Prints information about renamings
    :param renamings_map: map of string to tuple of string and boolean
    :return: OrderedDict of original filename to renamed filename
    """
    result = OrderedDict()

    for original, (renamed, collision) in sorted(renamings_map.items(),
                                                 key=lambda p: p[1][0]):
        result[original] = renamed
        style = Style.BRIGHT if collision else Style.DIM
        color = Fore.YELLOW if collision else Fore.GREEN
        print('{}{}{} -> {}{}'.format(
            style, color, original, renamed, Style.RESET_ALL))

    return result


def rename_files(renamings_map, label='Renaming_files'):
    """
    Applies renamings on file system
    :param label: string represents label on progressbar
    :param renamings_map: map of original file name to the renamed one
    """
    widgets = [FormatLabel(label), ' ',
               Percentage(), ' ',
               Bar(), ' ',
               ETA()]

    progress_bar = ProgressBar(maxval=len(renamings_map),
                               redirect_stdout=True,
                               widgets=widgets)
    progress_bar.init()
    file_counter = 0

    for original, renamed in renamings_map.items():
        file_counter += 1
        progress_bar.update(file_counter)
        rename(original, renamed)

    progress_bar.finish()


def main():
    """
    Entry point
    """
    working_directory = getcwd()

    parser = ArgumentParser(
        description='')
    parser.add_argument('-i', '--input_folder',
                        dest='input',
                        metavar='INPUT_DIRECTORY',
                        required=False,
                        default=working_directory,
                        help='Source directory for files renaming. '
                             'Current directory by default')
    args = parser.parse_args()

    files = [join(args.input, file) for file in listdir(args.input)
             if isfile(join(args.input, file))]
    images_files = [file for file in files if is_image(file)]
    video_files = [file for file in files if is_video(file)]

    total_files = len(images_files) + len(video_files)

    widgets = [FormatLabel('Extracting info'), ' ',
               Percentage(), ' ',
               Bar(), ' ',
               ETA()]

    progress_bar = ProgressBar(maxval=total_files,
                               redirect_stdout=True,
                               widgets=widgets)
    progress_bar.start()

    images_info_map = {}
    file_counter = 0

    for file in images_files:
        file_counter += 1
        progress_bar.update(file_counter)
        images_info_map[file] = exif_time_else_creation_time(file)

    video_files_map = {}

    for file in video_files:
        file_counter += 1
        progress_bar.update(file_counter)
        video_files_map[file] = creation_time(file)

    progress_bar.finish()

    image_renamings = calculate_renamings(images_info_map)
    video_renamings = calculate_renamings(video_files_map)

    image_renamings = dump_renamings(image_renamings)
    video_renamings = dump_renamings(video_renamings)

    if ask_yesno(msg='Confirm renaming', dft='y'):
        rename_files(image_renamings, label='Renaming image files')
        rename_files(video_renamings, label='Renaming video files')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
