# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals


FILE_NOT_FOUND = 1 << 0
ARG_NOT_DIRECTORY = 1 << 1
NO_TORRENT_CLIENT = 1 << 2
TRANSCODE_AGAINST_RULES = 1 << 3
TRANSCODE_DIR_EXISTS = 1 << 4
UNKNOWN_TRANSCODE = 1 << 5
NO_ANNOUNCE_URL = 1 << 6
NO_TRANSCODER = 1 << 7
TORRENT_ERROR = 1 << 8
TRANSCODE_ERROR = 1 << 9
