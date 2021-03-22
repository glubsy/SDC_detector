#!/bin/env python

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
# To consider: write to file by chunks (buffer)
# don't keep everything in memory, use iterator / generators

import os
import argparse
import logging
from datetime import datetime, date
import time
import functools
from pathlib import Path
import hashlib
import crccheck
import zlib
import binascii

BUF_SIZE = 65536  # arbitrary value of 64kb chunks!
logger = logging.getLogger(__name__)


def timer(func):
    @functools.wraps(func)
    def wrapper_timer(*args):
        start = time.perf_counter_ns()
        value = func(*args)
        end = time.perf_counter_ns()
        total = end - start
        print(f"TIMER: function {func.__name__!r} took {total} ns.")
        # times[func.__name__] = total
        return value
    return wrapper_timer

def generate(base_dir):
    base_path = Path(base_dir)
    op = open(args.output_dir + os.sep + "hashes_" +  date.fromtimestamp(time.time()).__str__() + ".txt", 'w')

    recursive_stat(base_path)

    # for _file in base_path.iterdir():
    #     # mtime = _file.stat().st_mtime
    #     fsize = _file.stat().st_size
    #     # sha = hashlib.sha256()
    #     crcinst = crccheck.crc.Crc32()
    #     with open(_file, 'rb') as fp:
    #         while True:
    #             data = fp.read(BUF_SIZE)
    #             if not data:
    #                 break
    #             # sha.update(data)
    #             crcinst.process(data)
    #     # crchex = sha.hexdigest()
    #     crchex = crcinst.finalhex()

    #     out_line = [_file.relative_to(base_path), crchex, str(fsize)]
    #     logger.info(f"{out_line}")
    #     print(out_line, sep="\t", file=op)

    op.close()

@timer
def get_sha(filename):
    sha = hashlib.sha1()
    with open(filename, 'rb') as fp:
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            sha.update(data)
    shahex = sha.hexdigest()
    print(f"sha for {filename}: {shahex}")
    return shahex

@timer
def get_crc32_buffered(filename):
    """This is slow!?"""
    crcinst = crccheck.crc.Crc32()
    with open(filename, 'rb') as fp:
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            crcinst.process(data)
    crchex = crcinst.finalhex()
    print(f"crccheck buffered for {filename}: {crchex}")
    return crchex

@timer
def get_crc32(filename):
    """This is slow!?"""
    with open(filename, 'rb') as fp:
        data = fp.read()
        crc = crccheck.crc.Crc32.calchex(data)
        # checksum = crccheck.checksum.Checksum32.calchex(data)
    print(f"crccheck crc32 for {filename}: {crc}")
    return crc

@timer
def CRC32_from_file(filename):
    with open(filename,'rb') as fp:
        crc = 0
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            crc = binascii.crc32(data, crc)
    crchex = "{:#010x}".format(crc)
    print("crc32_from_file: " + crchex)
    return crchex

@timer
def get_crc32_zlib(filename):
    with open(filename,'rb') as fp:
        crc = 0
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            crc = zlib.crc32(data, crc)
    crchex = "{:#010x}".format(crc)
    print("zlib crc32: " + crchex)
    return crchex

def recursive_stat(base_path):
    if not os.access(base_path, os.R_OK):
        return

    for root, dirs, files in os.walk(base_path):
        for f in files:
            fpath = root + os.sep + f
            get_sha(fpath)
            get_crc32(fpath)
            get_crc32_buffered(fpath)
            CRC32_from_file(fpath)
            get_crc32_zlib(fpath)


def compare(path1, path2):
    """Compare each line from path1 to each line to path2, return any difference"""
    with open(Path(path1), 'r') as p1, open(Path(path2), 'r') as p2:
        l1 = p1.readline()
        l2 = p2.readline()
        if l1.split("\t")[0] != l2.split("\t")[0]:
            # path are different!
            logger.error(f"{l1} != {l2}!")
            return
    return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('path1', type=str,
        help='Path to base directory to scan for files, or path to output file to compare.')
    # parser.add_argument('path2', type=str, default=None,
    #     help='Compare file with path1 for differences.')
    parser.add_argument('--output_dir', default="./", type=str,\
            help="Output directory where to write results.")
    hashes = ('sha1', 'sha256', 'crc32', 'md5')
    parser.add_argument('-c', action='store', dest='hash_name', default="sha1", 
        choices=hashes,
        help='hash function for checksum', required=False)
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    parser.add_argument('--log', action='store', default="DEBUG", 
        choices=levels,
        help='Log level. [DEBUG, INFO, WARNING, ERROR, CRITICAL]')
    args = parser.parse_args()
    logger.setLevel(args.log)
    
    # if args.path2:
    #     compare(args.path1, args.path2)
    #     exit(0)

    generate(args.path1)
