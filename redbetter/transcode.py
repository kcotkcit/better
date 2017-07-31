# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import multiprocessing
import os
import re
import subprocess
import sys
import time

from redbetter.bencode import Bencode
from redbetter.compat import print_bytes as printb
from redbetter.compat import to_unicode
from redbetter.compat import mutagen
from redbetter.errors import ARG_NOT_DIRECTORY
from redbetter.errors import FILE_NOT_FOUND
from redbetter.errors import NO_ANNOUNCE_URL
from redbetter.errors import NO_TORRENT_CLIENT
from redbetter.errors import NO_TRANSCODER
from redbetter.errors import SOURCE_EMBED_ERROR
from redbetter.errors import TORRENT_ERROR
from redbetter.errors import TRANSCODE_AGAINST_RULES
from redbetter.errors import TRANSCODE_DIR_EXISTS
from redbetter.errors import TRANSCODE_ERROR
from redbetter.errors import UNKNOWN_TRANSCODE
from redbetter.utils import base_command
from redbetter.utils import command_exists
from redbetter.utils import copy_contents
from redbetter.utils import find_torrent_command
from redbetter.utils import get_tags
from redbetter.utils import format_command
from redbetter.utils import adjust_prefixes
from redbetter.utils import enumerate_contents
from redbetter.utils import normalize_directory_path

class Defaults(object):
    # Your unique announce URL
    announce = ''
    # Where to output .torrent files
    torrent_output = '.'
    # Where to save transcoded albums
    transcode_output = '.'
    # The default formats to transcode to
    formats = '320,v0'
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
    snip_prefixes = set()
    # A prefix to add to the front of any transcoded albums and any resulting
    # torrent files created.
    prefix = ''
    # A source to embed in the generated torrent files.
    source = ''


class Job(object):
    def __init__(
            self,
            albums,
            announce=Defaults.announce,
            do_torrent=Defaults.make_torrent,
            do_transcode=Defaults.do_transcode,
            formats=Defaults.formats,
            max_threads=Defaults.max_threads,
            prefix=Defaults.prefix,
            snip_prefixes=Defaults.snip_prefixes,
            source=Defaults.source,
            torrent_output=Defaults.torrent_output,
            transcode_output=Defaults.transcode_output,
            # Currently calculated and passed by better.py. This interface
            # should be updated to take the same main arguments and calculate
            # these itself.
            explicit_torrent=False,
            explicit_transcode=False,
            original_torrent=False):
        self.albums = albums

        self.announce = announce
        self.do_torrent = do_torrent
        self.do_transcode = do_transcode
        self.formats = formats
        self.max_threads = max_threads
        self.prefix = prefix
        self.snip_prefixes = set(snip_prefixes)
        self.source = source
        self.torrent_output = torrent_output
        self.transcode_output = transcode_output

        self.explicit_torrent = explicit_torrent
        self.explicit_transcode = explicit_transcode
        self.original_torrent = original_torrent

        self.exit_code = 0
        self.torrent_command = None

    def validate_arguments(self):
        # Default to transcoding on one thread per core.
        if self.max_threads < 1:
            self.max_threads = multiprocessing.cpu_count()
            printb('Defaulting to transcoding using %d cores/threads' % (
                self.max_threads))

        # Check mutagen status.
        if mutagen is None and ('v0' in formats or 'v2' in formats):
            printb('Mutagen is not installed; album art cannot be copied to '
                   'VBR transcodes.')
            printb('To keep album art, install mutagen using pip or apt-get')


        # Torrent output directory
        self.torrent_output = normalize_directory_path(self.torrent_output)
        if not os.path.isdir(self.torrent_output):
            self.exit_code |= FILE_NOT_FOUND
            printb('There is no torrent output directory: %s' % (
                self.torrent_output))

        # Transcode output directory
        self.transcode_output = normalize_directory_path(self.transcode_output)
        if not os.path.isdir(self.transcode_output):
            self.exit_code |= FILE_NOT_FOUND
            printb('There is no transcode output directory : %s' % (
                self.transcode_output))

        # Album paths
        bad_albums = []
        valid_albums = []
        for album in self.albums:
            album = normalize_directory_path(to_unicode(album))
            if not os.path.isdir(album):
                bad_albums.append(album)
            else:
                valid_albums.append(album)
        if bad_albums:
            self.exit_code |= FILE_NOT_FOUND
            printb('The following albums are not directories:')
            for bad_album in bad_albums:
                printb('\t%s' % (bad_album))
        self.albums = valid_albums

        # Transcode formats
        bad_formats = []
        valid_formats = []
        for i, transcode_format in enumerate(self.formats):
            f = transcode_format.lower()
            if transcode_format not in transcode_commands:
                bad_formats.append(transcode_format)
            else:
                valid_formats.append(transcode_format)
        if bad_formats:
            self.exit_code |= UNKNOWN_TRANSCODE
            printb('Cannot transcode to the following formats:')
            for bad_format in bad_formats:
                printb('\t%s' % (bad_format))
        self.formats = valid_formats

        if not self.announce:
            # Cannot create .torrent files without an announce url.
            if self.explicit_torrent:
                printb('You cannot create torrents without first setting your announce URL')
                self.exit_code |= NO_ANNOUNCE_URL
            else:
                self.do_torrent = False


        self.exit_if_error()


    def start(self):
        self.validate_arguments()

        first_print = True
        for album in self.albums:
            if not first_print:
                printb('\n\n')
            first_print = False

            album = to_unicode(album)
            printb('Processing', album)

            self.process_album(album, self.do_transcode, self.explicit_transcode, self.formats, self.do_torrent, self.explicit_torrent, self.original_torrent)
        self.exit()

    # noinspection PyUnresolvedReferences
    def transcode_files(self, src, dst, files, command, extension):
        remaining = files[:]
        transcoded = []
        # TODO: use multiprocessing.ThreadPool instead
        threads = [None] * self.max_threads
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
                self.exit_code |= TRANSCODE_ERROR
            elif os.path.getsize(file) == 0:
                printb('An error occurred and {} is empty'.format(file))
                self.exit_code |= TRANSCODE_ERROR

        try:
            for pair in filenames:
                copy_album_art(*pair)
        except:
            pass

    def is_transcode_allowed(self, has_lossy, lossless_files, explicit_transcode):
        if has_lossy > 0:
            if len(lossless_files) == 0:
                printb('Cannot transcode lossy formats, exiting')
                self.exit_code |= TRANSCODE_AGAINST_RULES
                return False
            elif not explicit_transcode:
                printb('Found mixed lossy and lossless, you must explicitly enable transcoding')
                self.exit_code |= TRANSCODE_AGAINST_RULES
                return False

        if len(lossless_files) == 0:
            printb('Nothing to transcode!')
            self.exit_code |= TRANSCODE_AGAINST_RULES
            return False

        return True

    def make_torrent(self, directory, output, announce_url):
        printb('Making torrent for ' + directory)

        if self.torrent_command is None:
            self.torrent_command = find_torrent_command(torrent_commands)
            if self.torrent_command is None:
                printb('No torrent client found, can\'t create a torrent')
                self.exit_code |= NO_TORRENT_CLIENT
                return None

        new_torrent_path = os.path.join(self.torrent_output, output)
        command = format_command(self.torrent_command, directory, new_torrent_path, announce_url)
        torrent_status = subprocess.call(command, shell=True)
        if torrent_status != 0:
            printb('Making torrent file exited with status {}!'.format(torrent_status))
            self.exit_code |= TORRENT_ERROR
            return None
        return new_torrent_path


    def process_album(self, album_path, do_transcode, explicit_transcode, transcode_formats, do_torrent, explicit_torrent,
                      original_torrent):

        torrent_path = None
        if original_torrent:
            _, directory_name = os.path.split(album_path)
            torrent_filename = '%s.torrent' % (directory_name)
            torrent_path = self.make_torrent(album_path, torrent_filename, self.announce)

        if torrent_path and self.source:
            self.embed_source(torrent_path)

        if not do_transcode:
            return

        (directories,
         data_files,
         has_lossy,
         lossless_files) = enumerate_contents(album_path)

        if not self.is_transcode_allowed(has_lossy, lossless_files, explicit_transcode):
            return

        self.transcode_album(album_path,
                        directories,
                        data_files,
                        lossless_files,
                        transcode_formats,
                        explicit_transcode,
                        do_torrent)

    def transcode_album(self, source, directories, files, lossless_files, formats, explicit_transcode, mktorrent):
        codec_regex = r'\[(' + '|'.join([codec for codec in codecs]) + r')\](?!.*\/.*)'
        dir_has_codec = re.search(codec_regex, source, flags=re.IGNORECASE) is not None

        for transcode_format in formats:
            command = transcode_commands[transcode_format]
            if not command_exists(command):
                printb('Cannot transcode to %s: "%s" not found' % (
                    transcode_format, base_command(command)))
                self.exit_code |= NO_TRANSCODER
                continue

            printb('\nTranscoding to %s' % (transcode_format))

            if dir_has_codec:
                transcoded = re.sub(
                        codec_regex,
                        '[%s]' % (transcode_format.upper()),
                        source,
                        flags=re.IGNORECASE)
            else:
                transcoded = '%s [%s]' % (source.rstrip(), transcode_format.upper())

            transcoded = transcoded[transcoded.rfind('/') + 1:]
            transcoded = adjust_prefixes(transcoded,
                                         self.prefix,
                                         self.snip_prefixes)
            transcoded = self.transcode_output + '/' + transcoded

            if os.path.exists(transcoded):
                printb('Directory already exists: ', transcoded)
                if not explicit_transcode:
                    self.exit_code |= TRANSCODE_DIR_EXISTS
                    continue
            else:
                copy_contents(source, transcoded, directories, files)
                self.transcode_files(source,
                                    transcoded,
                                    lossless_files,
                                    transcode_commands[transcode_format],
                                    extensions[transcode_format])

            torrent_path = None
            if mktorrent:
                _, filename = os.path.split(transcoded)
                filename = filename + '.torrent'
                torrent_path = self.make_torrent(transcoded, filename, self.announce)
            if torrent_path and self.source:
                self.embed_source(torrent_path)

    def embed_source(self, torrent_path):
        printb('embedding source = "%s" into %s' % (self.source, torrent_path))
        try:
            torrent = Bencode(torrent_path)
            torrent.read()
            torrent['info']['source'] = self.source
            torrent.write()
        except Exception as e:
            printb('Could not embed source "%s" in %s' % (
                self.source, torrent_path))
            print(e)
            self.exit_code |= SOURCE_EMBED_ERROR


    def exit_if_error(self):
        if self.exit_code != 0:
            self.exit()

    def exit(self):
        if (self.exit_code != 0):
            printb('An error occurred, exiting with code {0}'.format(self.exit_code))
        sys.exit(self.exit_code)


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
