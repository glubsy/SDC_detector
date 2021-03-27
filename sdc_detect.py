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

# from hashlib import new
try:
    from crc32c import hardware_based, crc32c as crc32
    if not hardware_based:
        logger.warning(f"crc32c module iw not hardware accelerated!")
except Exception as e:
    logger.debug(f"Failed to load crc32c module: {e}")
    # Fallbacks
    # from zlib import crc32
    from binascii import crc32 # seems a tiny bit faster than zlib?

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
        logger.debug(f"TIMER: {func.__name__!r} took {total} ns.")
        return value
    return wrapper_timer


def recursive_stat_dict(base_path):
    directory = {}
    if not os.access(base_path, os.R_OK):
        return directory

    for root, dirs, files in os.walk(base_path):
        dn = os.path.basename(root)
        directory[dn] = []
        # directory[dn] = {}
        if dirs:
            for d in dirs:
                directory[dn].append(recursive_stat_dict(
                # directory[dn][d] = recursive_stat_dict(
                    base_path=os.path.join(base_path, d)
                    )
                )
            for f in files:
                directory[dn].append(get_file_info_dict(root, f))
                # directory[dn][f] = get_file_info_dict(root, f)
        elif files:
            # directory[dn].append([get_file_info_dict(root, f) for f in files])
            for f in files:
                directory[dn].append(get_file_info_dict(root, f))
                # directory[dn][f] = get_file_info_dict(root, f)
        return directory


def get_file_info_dict(root, filename):
    fpath = os.path.join(root, filename)
    return { 'n': filename,
            'crc': get_crc32(fpath),
            'sz': os.stat(fpath).st_size
    }
    # return {
    #         'crc': get_crc32(fpath),
    #         'sz': os.stat(fpath).st_size
    # }
    # return { filename: {
    #         'crc': get_crc32(fpath),
    #         'sz': os.stat(fpath).st_size
    #     }
    # }


def get_file_info_list(root, filename):
    fpath = os.path.join(root, filename)
    return [filename, get_crc32(fpath), os.stat(fpath).st_size]


def recursive_stat_list(base_path):
    directory = []
    if not os.access(base_path, os.R_OK):
        return directory

    for root, dirs, files in os.walk(base_path):
        dn = os.path.basename(root)
        directory.append(dn)
        if dirs:
            for d in dirs:
                directory.append(
                    recursive_stat_list(base_path=os.path.join(base_path, d)
                    )
                )
            for f in files:
                directory.append(get_file_info_list(root, f))
        elif files:
            directory.append([get_file_info_list(root, f) for f in files])
        return directory


def generate(base_path, struct_type="dict"):
    if not args.no_output:
        op = open(args.output_dir
                + os.sep
                + os.path.basename(base_path)
                + "_hashes_"
                +  datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                + ".txt",
                'w')
    if struct_type == "list":
        dir_content = recursive_stat_list(base_path)
        # Rename the root node since it will be different accross mounts
        dir_content[0] = 'root'
    elif struct_type == "dict":
        dir_content = recursive_stat_dict(base_path)
        # dir_content['root'] = dir_content.pop(base_path.name)
        dir_content['root'] = dir_content[base_path.name]
        del dir_content[base_path.name]

    if not args.no_output:
        dump(dir_content, stream=op, Dumper=Dumper)
        op.close()

    return dir_content

@timer
def get_hash(filename, hashtype):
    """sha1, sha256, md5 but this is probably overkill."""
    _hash = new(hashtype, usedforsecurity=False)
    with open(filename, 'rb') as fp:
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            _hash.update(data)
    hash_hex = _hash.hexdigest()
    return hash_hex

@timer
def get_crc32(filename):
    """binascii, zlib and crc32c share a similar interface."""
    with open(filename,'rb') as fp:
        crc = 0
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            crc = crc32(data, crc)
    return f"{crc:x}"


def load_yaml(fpath):
    with open(fpath, 'r') as fp:
        return load(fp, Loader=Loader)

# @timer
def compare(d1, d2):
    """Compare each line from path1 to each line to path2, return any difference"""
    # TODO error on:
    # hash is '0'
    # size is 0
    # name is different? -> will not work!
    # number of item is different / item is missing

    ddiff = deepdiff.DeepDiff(d1, d2,
        verbose_level=2,
        view='tree',
        ignore_order=True,
        ignore_string_type_changes=True,
        cutoff_distance_for_pairs=1.0,
        cutoff_intersection_for_pairs=1.0
        )
    pprint.pprint(ddiff, indent=2)

    pprint.pprint(ddiff.to_dict(view_override='text'), indent=2)
    print(ddiff.to_dict(view_override='text'))
    print(f"PRETTY:\n{ddiff.pretty()}")

    set_changed = ddiff.get('values_changed')
    if set_changed is not None:
        list_changed = list(set_changed)
        for change in list_changed:
            print(f"path: {change.path()}")

    set_added = ddiff.get('iterable_item_added')
    if set_added is not None:
        list_added = list(set_added)
        for item in set_added:
            print(f"added path: {item.path()} -> t1: {item.t1} -> t2: {item.t2}")


def compare_naive(d1, d2):
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # TODO detect if paths point to a file or a directory, to keep scan content
    # in memory and avoid reloading from serialized file
    parser.add_argument('path1', type=str,
        help='Path to directory to scan for files, or path to output file.')
    parser.add_argument('path2', type=str, default=None, nargs='?',
        help='Path to directory to scan for files, or path to output file.')
    parser.add_argument('--output_dir', default="./", type=str,\
            help="Output directory where to write results.")
    parser.add_argument('-n', '--no_output', action='store_true',\
            help="Do not write results to yaml or text files.")
    # TODO add xxhash, probably don't need sha256
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

    if not args.path2:
        generate(Path(args.path1))
        exit(0)
    path1 = Path(args.path1)
    path2 = Path(args.path2)
    # TODO threading here
    dir_dict1 = generate(path1) if path1.is_dir else load_yaml(path1)
    dir_dict2 = generate(path2) if path2.is_dir else load_yaml(path2)
    logger.debug(dump(dir_dict1, stream=None, Dumper=Dumper))
    logger.debug(dump(dir_dict2, stream=None, Dumper=Dumper))
    pprint.pprint(dir_dict1)
    pprint.pprint(dir_dict2)
    compare(dir_dict1, dir_dict2)
