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
import concurrent.futures
logger = logging.getLogger("sdc_detector")
from pathlib import Path

from yaml import load, dump, parse
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper
import pprint

from sdc_detector.tree import DirTreeGeneratorPureDict, DirTreeGeneratorList,\
    DirTreeGeneratorMixed, load_yaml
from sdc_detector.diff import ddiff_compare


# Obsolete
def check_empty_items(base_tree):
    empty_items = set()
    def recurse(dict_or_list, p):
        path = p + os.sep
        if isinstance(dict_or_list, list):
            for item in dict_or_list:
                path = path + recurse(item, path)
                if item.get('sz') == 0:
                    empty_items.add([item, sz])
                return path
        elif isinstance(dict_or_list, dict):
            for item in dict_or_list.values():
                recurse(item, path)
                fname = item.get("n")
                if fname is not None:
                    fsize = item.get("sz")
                    if not fsize: # empty file!
                        fpath = recurse(item, path)
                        empty_items.add([fname, fsize])
            return item.get("n")

    for item in base_tree.values():
        recurse(item, 'root')
    return empty_items

# Obsolete
def find_key(d, value):
    for k,v in d.items():
        if isinstance(v, dict):
            p = find_key(v, value)
            if p:
                return [k] + p
        elif v == value:
            return [k]

# Obsolete
def breadcrumb(dict_or_list, value):
    if dict_or_list == value:
        return [dict_or_list]
    elif isinstance(dict_or_list, dict):
        for k, v in dict_or_list.items():
            p = breadcrumb(v, value)
            if p:
                return [k] + p
    elif isinstance(dict_or_list, list):
        lst = dict_or_list
        for i in lst:
            p = breadcrumb(i, value)
            if p and p.get("n") is not None:
                return p.get("n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('path1', type=str,
        help='Path to directory to scan for files, or path to output file.')
    parser.add_argument('path2', type=str, default=None, nargs='?',
        help='Path to directory to scan for files, or path to output file.')
    parser.add_argument('--output_dir', default="./", type=str,\
            help="Output directory where to write results.")
    parser.add_argument('-n', '--no_output', action='store_true',\
            help="Do not write results to yaml or text files.")
    # TODO add xxhash, blake2b?
    hashes = ('sha1', 'sha256', 'crc32', 'md5')
    parser.add_argument('-c', action='store', dest='csum_name', default="sha1",
        choices=hashes,
        help='hash or crc algorithm to use for integrity checking.',
        required=False)
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    parser.add_argument('--log', action='store', default="DEBUG",
        choices=levels,
        help='Log level. [DEBUG, INFO, WARNING, ERROR, CRITICAL]')
    implementations = ('pure_dict', 'mixed_dict', 'pure_list')
    parser.add_argument('--impl', action='store', default='pure_dict',
        choices=implementations,
        help=f'Tree representation implementation to use. Default "pure_dict".')
    args = parser.parse_args()

    log_level = getattr(logging, args.log.upper(), None)
    if not isinstance(log_level, int):
        raise ValueError(f'Invalid log level: {args.log}')
    logger.setLevel(log_level)
    conhandler = logging.StreamHandler()
    conhandler.setLevel(log_level)
    logger.addHandler(conhandler)

    if args.impl == 'mixed_dict':
        fs_struct_type = DirTreeGeneratorMixed
    elif args.impl == 'pure_list':
        fs_struct_type = DirTreeGeneratorList
    else:
        fs_struct_type = DirTreeGeneratorPureDict
    # TODO write tree type to yaml to avoid comparing different types of trees?
    # for now we assume the same type was generated across scans.

    if not args.path2:
        gen = fs_struct_type(Path(args.path1), args)
        gen.generate(no_output=args.no_output)
        exit(0)

    args_set = (args.path1, args.path2)

    executor = concurrent.futures.ProcessPoolExecutor()
    queue = []
    for path_str in args_set:
        path = Path(path_str)
        gen = fs_struct_type(path, args)
        if path.is_dir():
            future = executor.submit(gen.generate, no_output=args.no_output)
        else:
            future = executor.submit(load_yaml, path)
        queue.append(future)
    results = []
    for future in queue:
        results.append(future.result())
    executor.shutdown()

    for tree_struct in results:
        logger.debug(f"Dump of generate() output:")
        logger.debug(dump(tree_struct, stream=None, Dumper=Dumper))
    if logger.isEnabledFor(logging.DEBUG):
        for tree_struct in results:
            logger.debug(f"PPrint of dictionaries:")
            logger.debug(pprint.pformat(tree_struct))

    # TODO extra option: for each file listed in yaml, compare with a target
    # dir (partial backups) only those files.
    ddiff_compare(
        # HACK always place first argument passed to the left hand side
        results[args_set.index(args.path1)],
        results[args_set.index(args.path2)],
        fs_struct_type
        )
