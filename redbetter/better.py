# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import argparse
import multiprocessing
import os
import sys

from redbetter.transcode import Job
from redbetter.transcode import Defaults
from redbetter.compat import mutagen

# noinspection PyBroadException



# The version number
__version__ = '0.7'
__description__ = ''' redbetter (version {})
Transcode albums and create torrents in one command. Default behavior can be
changed by editing the code with a text editor and changing variables, or by
passing different command line flags.'''.format(__version__)


def parse_args():
    description = __description__

    postfixes = {
        'a': ' (Usable URL set)' if len(Defaults.announce) > 0 else '',
        't': ' (default)' if Defaults.do_transcode else '',
        'T': ' (default)' if not Defaults.do_transcode else '',
        'm': ' (default)' if Defaults.make_torrent else '',
        'M': ' (default)' if not Defaults.make_torrent else ''
    }

    parser = argparse.ArgumentParser(description=description)
    transcode_group = parser.add_mutually_exclusive_group()
    torrent_group = parser.add_mutually_exclusive_group()

    parser.add_argument('album', help='The album to process', nargs='+')
    parser.add_argument(
            '-v',
            '--version',
            action='version',
            version='%(prog)s ' + __version__)

    parser.add_argument(
            '-a',
            '--announce',
            action='store',
            default=Defaults.announce,
            help='The torrent announce URL to use' + postfixes['a'])

    transcode_group.add_argument(
            '-t',
            '--transcode',
            action='store_true',
            help='Transcode the given album into other formats' + postfixes['t'])
    transcode_group.add_argument(
            '-T',
            '--no-transcode',
            action='store_true',
            help='Ensures the given album is NOT transcoded' + postfixes['T'])

    torrent_group.add_argument(
            '-m',
            '--make-torrent',
            action='count',
            default=Defaults.make_torrent,
            help='Creates a torrent of any transcoded albums. Specify more '
            'than once to also create a torrent of the source album '
            '(e.g. -mm).' + postfixes['m'])
    torrent_group.add_argument(
            '-M',
            '--no-torrent',
            action='store_true',
            help='Ensures no .torrent files are created' + postfixes['M'])

    parser.add_argument(
            '-f',
            '--formats',
            action='store',
            default=Defaults.formats,
            help='The comma-separated formats to transcode to (can be of '
            '16-48,16-44,alac,320,v0,v1,v2) (default: %(default)s)')
    parser.add_argument(
            '-p',
            '--prefix',
            action='store',
            default=Defaults.prefix,
            help='A space-separated list of prefixes to add to transcode '
            'directories and all .torrent files (empty by default)')
    parser.add_argument(
            '-x',
            '--snip-prefixes',
            dest='snip_prefixes',
            nargs='*',
            default=Defaults.snip_prefixes,
            help='A prefix to remove from the beginning of any transcoded '
            'directories and .torrent files, performed before any specified '
            'prefixes are added')
    parser.add_argument(
            '-s',
            '--source',
            action='store',
            dest='source',
            default=Defaults.source,
            help='A source to embed in the torrent, such as "red", to avoid '
            'having to re-download the torrent from the website after '
            'uploading it. (default: %(default)s)')
    parser.add_argument(
            '-c',
            '--cores',
            action='store',
            type=int, default=Defaults.max_threads,
            help='The number of cores/threads to transcode at once. Any number '
            'below 1 means to use the number of CPU cores in the system '
            '(default: %(default)s)')
    parser.add_argument(
            '-o',
            '--torrent-output',
            action='store',
            default=Defaults.torrent_output,
            help='The directory to store any created .torrent files '
            '(default: %(default)s)')
    parser.add_argument(
            '-O',
            '--transcode-output',
            action='store',
            default=Defaults.transcode_output,
            help='The directory to store any transcoded albums in '
            '(default: %(default)s)')

    return parser.parse_args()


def main():
    args = parse_args()

    # Transcoding
    do_transcode = ((args.transcode or Defaults.do_transcode) and
                    not args.no_transcode)
    explicit_transcode = args.transcode or args.no_transcode

    # Formats
    # TODO: use arg parsing instead of split on ,
    formats = args.formats.split(',')

    # TODO: two separate arguments, for transcode and original
    do_torrent = (not args.no_torrent and
                  (args.make_torrent or Defaults.make_torrent))
    explicit_torrent = args.make_torrent
    original_torrent = args.make_torrent == 2

    job = Job(
        albums = args.album,

        announce = args.announce,
        do_torrent = do_torrent,
        do_transcode = do_transcode,
        formats = formats,
        max_threads = args.cores,
        prefix = args.prefix,
        snip_prefixes = args.snip_prefixes,
        source = args.source,
        torrent_output = args.torrent_output,
        transcode_output = args.transcode_output,

        explicit_torrent = explicit_torrent,
        explicit_transcode = explicit_transcode,
        original_torrent = original_torrent,
    )
    job.start()
