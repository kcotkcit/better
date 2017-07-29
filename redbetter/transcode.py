# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from redbetter.compat import quote
from redbetter.compat import mutagen
from redbetter.compat import to_unicode
from redbetter.compat import print_bytes as printb
from redbetter.compat import which
from redbetter.errors import ARG_NOT_DIRECTORY
from redbetter.errors import FILE_NOT_FOUND
from redbetter.errors import NO_ANNOUNCE_URL
from redbetter.errors import NO_TORRENT_CLIENT
from redbetter.errors import NO_TRANSCODER
from redbetter.errors import TORRENT_ERROR
from redbetter.errors import TRANSCODE_AGAINST_RULES
from redbetter.errors import TRANSCODE_DIR_EXISTS
from redbetter.errors import TRANSCODE_ERROR
from redbetter.errors import UNKNOWN_TRANSCODE

class Job(object):
    class Defaults(object):
        # Your unique announce URL
        announce = ''
        # Where to output .torrent files
        torrent_output = '.'
        # Where to save transcoded albums
        transcode_output = '.'
        # The default formats to transcode to
        default_formats = '320,v0'
        # Whether or not to transcode by default
        do_transcode = True
        # Whether or not to make .torrent files by default. 0 for none, 1 for
        # transcodes, 2 for transcodes and the original.
        make_torrent = 1
        # The maximum number of threads to maintain. Any number less than 1
        # means the script will use the number of CPU cores in the system. This
        # is the default value for the -c (--cores) option.
        max_threads = 0
        # I prefix torrents I download as FL for Freeleech, UL for Upload, etc.
        # Any prefix in this set will be removed from any transcoded albums and
        # from the resulting torrent files created.
        ignored_prefixes = set([
            'FL',
            #'UL',
        ])

    def __init__(self, announce, torrent_output, transcode_output, max_threads, explicit_transcode, formats, do_transcode, do_torrent, explicit_torrent, original_torrent, albums=None, ignored_prefixes=None):
        self.announce = announce
        self.torrent_output = torrent_output
        self.transcode_output = transcode_output
        self.max_threads = max_threads
        self.explicit_transcode = explicit_transcode
        self.formats = formats
        self.do_transcode = do_transcode
        self.do_torrent = do_torrent
        self.explicit_torrent = explicit_torrent
        self.original_torrent = original_torrent
        self.exit_code = 0
        self.torrent_command = None
        if albums == None:
            albums = []
        self.albums = albums
        if ignored_prefixes is None:
            ignored_prefixes = Job.Defaults.ignored_prefixes
        self.ignored_prefixes = ignored_prefixes

    def start(self):
        global job
        job = self
        # Check directories
        if not os.path.isdir(self.torrent_output):
            printb('The given torrent output dir ({}) is not a directory'.format(self.torrent_output))
            self.exit_code |= ARG_NOT_DIRECTORY
        elif not os.path.isdir(self.transcode_output):
            printb('The given transcode output dir ({}) is not a directory'.format(self.transcode_output))
            self.exit_code |= ARG_NOT_DIRECTORY
        self.exit_if_error()

        first_print = True
        for album in self.albums:
            if not first_print:
                printb('\n\n')
            first_print = False

            album = to_unicode(album)
            printb('Processing', album)

            process_album(album, job.do_transcode, job.explicit_transcode, job.formats, job.do_torrent, job.explicit_torrent, job.original_torrent)
        self.exit()

    def exit_if_error(self):
        if self.exit_code != 0:
            self.exit()

    def exit(self):
        if (self.exit_code != 0):
            printb('An error occurred, exiting with code {0}'.format(self.exit_code))
        sys.exit(self.exit_code)

job = None

# transcode_commands is the map of how to transcode into each format. The
# replacements are as follows:
# {0}: The input file (*.flac)
# {1}: The output file (*.mp3 or *.m4a)
# {2}: Song title
# {3}: Artist
# {4}: Album
# {5}: date
# {6}: track number
ffmpeg = 'ffmpeg -threads 1 '
transcode_commands = {
    '16-48': ffmpeg + '-i {0} -acodec flac -sample_fmt s16 -ar 48000 {1}',
    '16-44': ffmpeg + '-i {0} -acodec flac -sample_fmt s16 -ar 44100 {1}',
    'alac': ffmpeg + '-i {0} -acodec alac {1}',
    '320': ffmpeg + '-i {0} -acodec libmp3lame -ab 320k {1}',
    'v0': 'flac --decode --stdout {0} | lame -V 0 -q 0 --add-id3v2 --tt {2} --ta {3} --tl {4} --ty {5} --tn {6} - {1}',
    'v1': 'flac --decode --stdout {0} | lame -V 1 -q 0 --add-id3v2 --tt {2} --ta {3} --tl {4} --ty {5} --tn {6} - {1}',
    'v2': 'flac --decode --stdout {0} | lame -V 2 -q 0 --add-id3v2 --tt {2} --ta {3} --tl {4} --ty {5} --tn {6} - {1}'
}

# torrent_commands is the set of all ways to create a torrent using various
# torrent clients. These are the following replacements:
# {0}: Source directory to create a torrent from
# {1}: Output .torrent file
# {2}: Your announce URL
torrent_commands = {
    'transmission-create -p -o {1} -t {2} {0}',
    'mktorrent -p -o {1} -a {2} {0}'
}

# extensions maps each codec type to the extension it should use
extensions = {
    '16-48': 'flac',
    '16-44': 'flac',
    'alac': 'm4a',
    '320': 'mp3',
    'v0': 'mp3',
    'v2': 'mp3'
}

# codecs is use in string matching. If, in naming an album's folder name, you
# would use [FLAC] or [ALAC] or [320], then the lowercase contents of the
# brackets belongs in codecs so it can be matched and replaced with the
# transcode codec type.
codecs = {
    'wav',
    'flac', 'flac 24bit', 'flac 16-44', 'flac 16-48', 'flac 24-44', 'flac 24-48', 'flac 24-96', 'flac 24-196',
    '16-44', '16-48', '24-44', '24-48', '24-96', '24-196',
    'alac',
    '320', '256', '224', '192',
    'v0', 'apx', '256 vbr', 'v1', '224 vbr', 'v2', 'aps', '192 vbr'
}

# The list of lossless file extensions. While m4a can be lossy, it's up to you,
# the user, to ensure you're only transcoding from a lossless source material.
LOSSLESS_EXT = {'flac', 'wav', 'm4a'}

# The list of lossy file extensions
LOSSY_EXT = {'mp3', 'aac', 'opus', 'ogg', 'vorbis'}


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


def process_album(directory, do_transcode, explicit_transcode, transcode_formats, do_torrent, explicit_torrent,
                  original_torrent):
    global job
    directory = os.path.abspath(directory)

    if not (check_main_args(directory, transcode_formats, explicit_torrent)):
        return

    if original_torrent:
        printb("making the original torrent")
        _, filename = os.path.split(directory)
        filename = filename + '.torrent'
        printb('filename:', filename)
        printb('directory:', directory)
        make_torrent(directory, filename, job.announce)

    if do_transcode:
        directories, data_files, has_lossy, lossless_files = enumerate_contents(directory)

        if is_transcode_allowed(has_lossy, lossless_files, explicit_transcode):
            transcode_album(directory,
                            directories,
                            data_files,
                            lossless_files,
                            transcode_formats,
                            explicit_transcode,
                            do_torrent)


def transcode_album(source, directories, files, lossless_files, formats, explicit_transcode, mktorrent):
    global job

    codec_regex = r'\[(' + '|'.join([codec for codec in codecs]) + r')\](?!.*\/.*)'
    dir_has_codec = re.search(codec_regex, source, flags=re.IGNORECASE) is not None

    for transcode_format in formats:
        if not command_exists(transcode_commands[transcode_format]):
            command = shlex.split(transcode_commands[transcode_format])[0]
            printb('Cannot transcode to ' + transcode_format + ', "' + command + '" not found')
            job.exit_code |= NO_TRANSCODER
            continue

        printb('\nTranscoding to ' + transcode_format)

        if dir_has_codec:
            transcoded = re.sub(codec_regex, '[{}]'.format(transcode_format.upper()), source, flags=re.IGNORECASE)
        else:
            transcoded = source.rstrip() + ' [{}]'.format(transcode_format.upper())

        transcoded = transcoded[transcoded.rfind('/') + 1:]

        transcoded = remove_prefixes(job.ignored_prefixes, transcoded)

        transcoded = job.transcode_output + '/' + transcoded

        if os.path.exists(transcoded):
            printb('Directory already exists: ' + transcoded)
            if not explicit_transcode:
                job.exit_code |= TRANSCODE_DIR_EXISTS
                continue
        else:
            copy_contents(source, transcoded, directories, files)
            transcode_files(source, transcoded, lossless_files, transcode_commands[transcode_format],
                            extensions[transcode_format])

        if mktorrent:
            _, filename = os.path.split(transcoded)
            filename = filename + '.torrent'
            make_torrent(transcoded, filename, job.announce)


# noinspection PyUnresolvedReferences
def transcode_files(src, dst, files, command, extension):
    global job
    remaining = files[:]
    transcoded = []
    # TODO: use multiprocessing.ThreadPool instead
    threads = [None] * job.max_threads
    filenames = []

    transcoding = True

    while transcoding:
        transcoding = False

        for i in range(len(threads)):
            if threads[i] is None or threads[i].poll() is not None:
                if threads[i] is not None:
                    if threads[i].poll() != 0:
                        printb('Error transcoding, process exited with code {}'.format(threads[i].poll()))
                        printb('stderr output...')
                        printb(to_unicode(threads[i].communicate()[1]))
                    # noinspection PyBroadException
                    try:
                        threads[i].kill()
                    except Exception as _:
                        pass

                threads[i] = None

                if len(remaining) > 0:
                    transcoding = True
                    file = remaining.pop()
                    transcoded.append(dst + '/' + file[:file.rfind('.') + 1] + extension)
                    threads[i] = subprocess.Popen(
                        format_command(command, src + '/' + file, transcoded[-1], *get_tags(src + '/' + file)),
                        stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True,
                        universal_newlines=True
                    )
                    filenames.append((src + '/' + file, transcoded[-1]))
                    printb('Transcoding {} ({} remaining)'.format(to_unicode(file), len(remaining)))
            else:
                transcoding = True

        time.sleep(0.05)

    for file in transcoded:
        if not os.path.isfile(file):
            printb('An error occurred and {} was not created'.format(file))
            job.exit_code |= TRANSCODE_ERROR
        elif os.path.getsize(file) == 0:
            printb('An error occurred and {} is empty'.format(file))
            job.exit_code |= TRANSCODE_ERROR

    try:
        for pair in filenames:
            copy_album_art(*pair)
    except:
        pass


def check_main_args(directory, transcode_formats, explicit_torrent):
    global job
    code = 0

    if not os.path.exists(directory):
        printb('The directory "{}" doesn\'t exist'.format(directory))
        code |= FILE_NOT_FOUND
    elif os.path.isfile(directory):
        printb('The file "{}" is not a directory'.format(directory))
        code |= ARG_NOT_DIRECTORY

    for i in range(len(transcode_formats)):
        transcode_formats[i] = transcode_formats[i].lower()

        if transcode_formats[i] not in transcode_commands.keys():
            printb('No way of transcoding to ' + transcode_formats[i])
            code |= UNKNOWN_TRANSCODE

    if explicit_torrent and (job.announce is None or len(job.announce) == 0):
        printb('You cannot create torrents without first setting your announce URL')
        code |= NO_ANNOUNCE_URL

    job.exit_code |= code

    return code == 0


# --- Utils?

def is_transcode_allowed(has_lossy, lossless_files, explicit_transcode):
    global job

    if has_lossy > 0:
        if len(lossless_files) == 0:
            printb('Cannot transcode lossy formats, exiting')
            job.exit_code |= TRANSCODE_AGAINST_RULES
            return False
        elif not explicit_transcode:
            printb('Found mixed lossy and lossless, you must explicitly enable transcoding')
            job.exit_code |= TRANSCODE_AGAINST_RULES
            return False

    if len(lossless_files) == 0:
        printb('Nothing to transcode!')
        job.exit_code |= TRANSCODE_AGAINST_RULES
        return False

    return True


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


def make_torrent(directory, output, announce_url):
    global job
    printb('Making torrent for ' + directory)

    if job.torrent_command is None:
        job.torrent_command = find_torrent_command(torrent_commands)
        if job.torrent_command is None:
            printb('No torrent client found, can\'t create a torrent')
            job.exit_code |= NO_TORRENT_CLIENT
            return

    command = format_command(job.torrent_command, directory, os.path.join(job.torrent_output, output), announce_url)
    torrent_status = subprocess.call(command, shell=True)
    if torrent_status != 0:
        printb('Making torrent file exited with status {}!'.format(torrent_status))
        job.exit_code |= TORRENT_ERROR


def format_command(command, *args):
    safe_args = [quote(arg) for arg in args]
    return command.format(*safe_args)


def command_exists(command):
    return which(shlex.split(command)[0]) is not None


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
