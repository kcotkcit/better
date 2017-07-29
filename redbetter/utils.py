# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import json
import os
import shlex
import shutil
import subprocess

from redbetter.compat import mutagen
from redbetter.compat import quote
from redbetter.compat import to_unicode
from redbetter.compat import which


# The list of lossless file extensions. While m4a can be lossy, it's up to you,
# the user, to ensure you're only transcoding from a lossless source material.
LOSSLESS_EXT = {'flac', 'wav', 'm4a'}

# The list of lossy file extensions
LOSSY_EXT = {'mp3', 'aac', 'opus', 'ogg', 'vorbis'}


def format_command(command, *args):
    safe_args = [quote(arg) for arg in args]
    return command.format(*safe_args)


def base_command(command_with_arguments):
    return shlex.split(command_with_arguments)[0]


def command_exists(command_with_arguments):
    return which(base_command(command_with_arguments)) is not None


def find_torrent_command(commands):
    for command in commands:
        if command_exists(command):
            return command
    return None


def copy_contents(src, dst, dirs, files):
    # from distutils import dir_util
    # dir_util.copy_tree("./src", "./dst")
    os.mkdir(dst)

    for subdir in dirs:
        os.mkdir(dst + '/' + subdir)

    for file in files:
        shutil.copy(src + '/' + file, dst + '/' + file)


def remove_prefixes(prefixes, name):
    for prefix in prefixes:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def get_tags(filename):
    command = 'ffprobe -v 0 -print_format json -show_format'.split(' ') + [filename]
    info = json.loads(to_unicode(subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0]))

    if 'format' not in info or 'tags' not in info['format']:
        return '', '', '', '', ''

    tags = info['format']['tags']
    tags = {key.lower(): tags[key] for key in tags}
    parsed = {'title': '', 'artist': '', 'album': '', 'date': '', 'track': ''}

    for key in tags:
        if key in parsed:
            parsed[key] = tags[key]

    if len(parsed['track']) > 0 and 'tracktotal' in tags and len(tags['tracktotal']) > 0:
        parsed['track'] += '/' + tags['tracktotal']

    return parsed['title'], parsed['artist'], parsed['album'], parsed['date'], parsed['track']


def copy_album_art(source, dest):
    if mutagen is None:
        return

    flac = mutagen.File(source)

    if len(flac.pictures) > 0:
        # noinspection PyUnresolvedReferences
        apic = mutagen.id3.APIC(mime=flac.pictures[0].mime, data=flac.pictures[0].data)

        mp3 = mutagen.File(dest)
        mp3.tags.add(apic)
        mp3.save()


def enumerate_contents(directory):
    has_lossy = False
    lossless_files = []
    data_files = []
    directories = []

    for root, _, files in os.walk(directory):
        root = root[len(directory):].lstrip('/')

        if len(root) > 0:
            directories.append(root)

        for file in files:
            file = to_unicode(file)
            extension = file[file.rfind('.') + 1:]
            if len(root) > 0:
                file = root + '/' + file

            if extension in LOSSLESS_EXT:
                lossless_files.append(file)
            else:
                if extension in LOSSY_EXT:
                    has_lossy = True
                data_files.append(file)

    return directories, data_files, has_lossy, lossless_files

def normalize_directory_path(path):
    return os.path.abspath(os.path.expanduser(path)).rstrip('/')
