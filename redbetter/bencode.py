# coding: utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import six

class Bencode(dict):
    def __init__(self, filename):
        super(Bencode, self).__init__()
        self.filename = filename

    def read(self):
        self.clear()
        with open(self.filename, 'rb') as torrent:
            contents = bytelist(torrent.read())
            self.update(Bencode._decode_dict(contents)[0])

        return self

    def write(self, filename=None):
        with open(filename or self.filename, 'wb') as output:
            output.write(Bencode._encode_dict(self))

    @staticmethod
    def _encode_text(text):
        return '{}:{}'.format(len(text), text).encode('utf-8')

    @staticmethod
    def _encode_bytes(btext):
        return '{}:'.format(len(btext)).encode('utf-8') + btext

    @staticmethod
    def _decode_item(file):
        for test, getter in decoders.items():
            if test(file[0]):
                return getter(file)

        raise Exception('Unknown bencoding object starting with "{}"'.format(file[0]))

    @staticmethod
    def _encode_item(item):
        for t, encoder in encoders.items():
            if isinstance(item, t):
                return encoder(item)

    @staticmethod
    def _decode_int(file):
        end = file.index(six.byte2int(b'e'))
        return int(bytelist_to_text(file[1: end])), file[end + 1:]

    @staticmethod
    def _decode_string(file):
        colon = file.index(six.byte2int(b':'))
        length = int(bytelist_to_text(file[: colon]))
        return bytelist_to_text(file[colon + 1: colon + 1 + length]), file[colon + 1 + length:]

    @staticmethod
    def _decode_list(file):
        file = file[1:]
        lst = []
        while file[0] != six.byte2int(b'e'):
            item, file = Bencode._decode_item(file)
            lst.append(item)
        return lst, file[1:]

    @staticmethod
    def _encode_list(lst):
        data = b'l'

        for item in lst:
            data += Bencode._encode_item(item)

        return data + b'e'

    @staticmethod
    def _decode_dict(file):
        file = file[1:]
        dct = {}
        while file[0] != six.byte2int(b'e'):
            key, file = Bencode._decode_string(file)
            item, file = Bencode._decode_item(file)
            dct[key.decode('utf-8')] = item
        return dct, file[1:]

    @staticmethod
    def _encode_dict(dct):
        data = b'd'
        for key, value in sorted(dct.items()):
            data += Bencode._encode_item(key) + Bencode._encode_item(value)
        return data + b'e'

    @staticmethod
    def _encode_int(i):
        return 'i{}e'.format(i).encode('utf-8')

decoders = {
    lambda x: x == ord('i'): lambda f: Bencode._decode_int(f),
    lambda x: ord('0') <= x <= ord('9'): lambda f: Bencode._decode_string(f),
    lambda x: x == ord('l'): lambda f: Bencode._decode_list(f),
    lambda x: x == ord('d'): lambda f: Bencode._decode_dict(f)
}
encoders = {
    six.text_type: Bencode._encode_text,
    six.binary_type: Bencode._encode_bytes,
    int: Bencode._encode_int,
    #str: lambda x: Bencode._encode_string(x),
    list: Bencode._encode_list,
    dict: Bencode._encode_dict,
}

def bytelist(stream):
    out = list(stream)
    if not out:
        return out
    if isinstance(out[0], int):
        return out
    return [ord(c) for c in out]

def bytelist_to_text(bytelist):
    return b''.join(map(six.int2byte, bytelist))
