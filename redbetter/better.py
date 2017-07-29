#!/usr/bin/env python
# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from redbetter.transcode import Job
import argparse
import multiprocessing
import os
import sys

# noinspection PyBroadException
try:
    import mutagen
except:
    mutagen = None



# The version number
__version__ = '0.7'


def parse_args():
    description = '(Version {}) Transcode albums and create torrents in one command. Default behavior can be changed ' \
                  'by opening %(prog)s with a text editor and changing the variables at the top of the file.' \
        .format(__version__)

    parser = argparse.ArgumentParser(description=description)
    transcode_group = parser.add_mutually_exclusive_group()
    torrent_group = parser.add_mutually_exclusive_group()

    parser.add_argument('album', help='The album to process', nargs='+')

    parser.add_argument('-v', '--version', action='version', version='%(prog)s ' + __version__)

    announce_postfix = ' (Usable URL set)' if len(Job.Defaults.announce) > 0 else ''
    parser.add_argument('-a', '--announce', action='store', default=Job.Defaults.announce,
                        help='The torrent announce URL to use' + announce_postfix)

    postfixes = {
        't': ' (default)' if Job.Defaults.do_transcode else '',
        'T': ' (default)' if not Job.Defaults.do_transcode else '',
        'm': ' (default)' if Job.Defaults.make_torrent else '',
        'M': ' (default)' if not Job.Defaults.make_torrent else ''
    }
    transcode_group.add_argument('-t', '--transcode', action='store_true',
                                 help='Transcode the given album into other formats' + postfixes['t'])
    transcode_group.add_argument('-T', '--no-transcode', action='store_true',
                                 help='Ensures the given album is NOT transcoded' + postfixes['T'])

    torrent_group.add_argument('-m', '--make-torrent', action='count', default=Job.Defaults.make_torrent,
                               help='Creates a torrent of any transcoded albums. Specify more than once to also create '
                                    'a torrent of the source album (e.g. -mm).' + postfixes['m'])
    torrent_group.add_argument('-M', '--no-torrent', action='store_true',
                               help='Ensures no .torrent files are created' + postfixes['M'])

    parser.add_argument('-f', '--formats', action='store', default=Job.Defaults.default_formats,
                        help='The comma-separated formats to transcode to (can be of 16-48,16-44,alac,320,v0,v1,v2) '
                             '(default: %(default)s)')
    parser.add_argument('-c', '--cores', action='store', type=int, default=Job.Defaults.max_threads,
                        help='The number of cores to transcode on. Any number below 1 means to use the '
                             'number of CPU cores in the system (default: %(default)s)')

    parser.add_argument('-o', '--torrent-output', action='store', default=Job.Defaults.torrent_output,
                        help='The directory to store any created .torrent files (default: %(default)s)')
    parser.add_argument('-O', '--transcode-output', action='store', default=Job.Defaults.transcode_output,
                        help='The directory to store any transcoded albums in (default: %(default)s)')

    return parser.parse_args()


def run(args):
    do_transcode = Job.Defaults.do_transcode and not args.no_transcode
    explicit_transcode = args.transcode
    formats = args.formats.split(',')

    do_torrent = Job.Defaults.make_torrent and not args.no_torrent
    explicit_torrent = args.make_torrent
    original_torrent = args.make_torrent == 2

    if not explicit_torrent and len(args.announce) == 0:
        do_torrent = False
    if mutagen is None and 'v0' in formats:
        print('Mutagen is not installed; album art won\'t be copied to VBR transcodes')
        print('To keep album art, install mutagen (try "sudo python3 -m pip install mutagen")')
        if sys.version_info[1] < 4:
            print('Your python version is <3.4, you must install pip yourself before mutagen.')

    torrent_output = args.torrent_output
    torrent_output = os.path.expanduser(torrent_output)
    torrent_output = os.path.abspath(torrent_output)
    torrent_output = torrent_output.rstrip('/')

    transcode_output = args.transcode_output
    transcode_output = os.path.expanduser(transcode_output)
    transcode_output = os.path.abspath(transcode_output)
    transcode_output = transcode_output.rstrip('/')

    max_threads = args.cores
    if max_threads < 1:
        max_threads = multiprocessing.cpu_count()

    job = Job(
            announce=args.announce,
            torrent_output=torrent_output,
            transcode_output=transcode_output,
            max_threads=max_threads,
            explicit_transcode=explicit_transcode,
            formats=formats,
            do_transcode=do_transcode,
            do_torrent=do_torrent,
            explicit_torrent=explicit_torrent,
            original_torrent=original_torrent,
            albums=args.album)
    job.start()


def main():
    run(parse_args())
