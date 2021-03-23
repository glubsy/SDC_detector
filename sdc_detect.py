#!/bin/env python3

# 1) Get md5 or crc32 or sha1 of each file in a dir
# 2) store results in a data structure (dict?)
# 	- filename
#	- hash
#	- file sizes on disk
#	- mtime
# 2) serialize the result
# 3) do the same for another dir
# 4) compare the results by iteration
#
# TODO: if possible
# * write to file in chunks (buffered, not possible
# with serialization of python objects into json or yaml sadly)
# * don't keep everything in memory, use iterators / generators

import os
import argparse
import logging
from datetime import datetime
import time
import functools
from pathlib import Path

import hashlib
# import zlib
import binascii # crc32 seems a tiny bit faster than zlib?

from yaml import load, dump, parse
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper
import pprint

# import dictdiffer # smaller, faster but cannot traverse results
import deepdiff


BUF_SIZE = 65536  # arbitrary value of 64kb chunks!
logger = logging.getLogger(__name__)


def timer(func):
    @functools.wraps(func)
    def wrapper_timer(*args):
        start = time.perf_counter_ns()
        value = func(*args)
        end = time.perf_counter_ns()
        total = end - start
        arg_one = ""
        if len(args) > 1:
            arg_one = args[1]
        logger.debug(f"TIMER: {func.__name__!r}({arg_one}) took {total} ns.")
        return value
    return wrapper_timer


def recursive_stat(base_path):
    directory = {}

    if not os.access(base_path, os.R_OK):
        return directory

    for root, dirs, files in os.walk(base_path):
        dn = os.path.basename(root)
        directory[dn] = []

        if dirs:
            for d in dirs:
                directory[dn].append(
                    recursive_stat(base_path=os.path.join(base_path, d)
                    )
                )
            for f in files:
                file_info = get_file_info(root, f)
                logger.debug(f"file_info: {file_info}")
                directory[dn].append(file_info)
        else:
            directory[dn].append([get_file_info(root, f) for f in files])

        return directory


def get_file_info(root, filename):
    fpath = os.path.join(root, filename)
    # return { filename:
    #     {
    #         'crc': get_crc32(fpath, 'binascii'),
    #         'size': os.stat(fpath).st_size
    #     }
    # }
    return { filename:
        [
            get_crc32(fpath, 'binascii'),
            os.stat(fpath).st_size
        ]
    }
    # return [filename, get_crc32(fpath, 'binascii'), os.stat(fpath).st_size]


def generate(base_dir):
    base_path = Path(base_dir)
    op = open(args.output_dir
            + os.sep
            + os.path.basename(base_path)
            + "_hashes_"
            +  datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            + ".txt",
            'w')

    # if not os.access(base_path, os.R_OK):
    #     return
    # for root, dirs, files in os.walk(base_path):
    #     items = []
    #     for f in files:
    #         fpath = root + os.sep + f
    #         print(f"Hashes for {fpath}:")
    #         print("sha1: " + get_hash(fpath, 'sha1'))
    #         print("sha256: " + get_hash(fpath, 'sha256'))
    #         print("md5: " + get_hash(fpath, 'md5'))
    #         crc = get_crc32(fpath, 'binascii')
    #         print("crc32 binascii: " + crc)
    #         items.append([fpath, crc, os.stat(fpath).st_size])
    #     output = dump(items, stream=op, Dumper=Dumper)
    dir_content = recursive_stat(base_path)
    dump(dir_content, stream=op, Dumper=Dumper)
    op.close()

@timer
def get_hash(filename, hashtype):
    """sha1, sha256, md5"""
    _hash = hashlib.new(hashtype, usedforsecurity=False)
    with open(filename, 'rb') as fp:
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            _hash.update(data)
    hash_hex = _hash.hexdigest()
    return hash_hex

@timer
def get_crc32(filename, provider):
    """provider: "binascii" or "zlib" (same interface in this case)."""
    with open(filename,'rb') as fp:
        crc = 0
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            crc = eval(provider).crc32(data, crc)
    return f"{crc:x}"

@timer
def compare(path1, path2):
    """Compare each line from path1 to each line to path2, return any difference"""
    # TODO error on:
    # hash is '0'
    # size is 0
    # name is different
    # number of item is different / item is
    with open(Path(path1), 'r') as p1, open(Path(path2), 'r') as p2:
        t1 = load(p1, Loader=Loader)
        t2 = load(p2, Loader=Loader)
    logger.debug(dump(t1, stream=None, Dumper=Dumper))
    logger.debug(dump(t2, stream=None, Dumper=Dumper))

    ddiff_verbose0 = deepdiff.DeepDiff(t1, t2, verbose_level=2, view='text')
    pprint.pprint(ddiff_verbose0, indent=2)
    set_changed = ddiff_verbose0['values_changed']
    changed = list(set_changed)[0]
    for change in changed:
        print(f"changed: {change}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # TODO detect if paths point to a file or a directory, to keep scan content
    # in memory and avoid reloading from serialized file
    parser.add_argument('path1', type=str,
        help='Path to base directory to scan for files, or path to output file to compare.')
    parser.add_argument('path2', type=str, default=None, nargs='?',
        help='Compare file with path1 for differences.')
    parser.add_argument('--output_dir', default="./", type=str,\
            help="Output directory where to write results.")
    hashes = ('sha1', 'sha256', 'crc32', 'md5')
    parser.add_argument('-c', action='store', dest='hash_name', default="crc32",
        choices=hashes,
        help='hash function for checksum', required=False)
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    parser.add_argument('--log', action='store', default="DEBUG",
        choices=levels,
        help='Log level. [DEBUG, INFO, WARNING, ERROR, CRITICAL]')
    args = parser.parse_args()

    log_level = getattr(logging, args.log.upper(), None)
    if not isinstance(log_level, int):
        raise ValueError(f'Invalid log level: {args.log}')
    logger.setLevel(log_level)
    conhandler = logging.StreamHandler()
    conhandler.setLevel(log_level)
    logger.addHandler(conhandler)

    if args.path2:
        compare(args.path1, args.path2)
        exit(0)

    generate(args.path1)
