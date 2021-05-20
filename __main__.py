#!/bin/env python3
import os
import sys
import argparse
import logging
import concurrent.futures
logger = logging.getLogger()
from pathlib import Path

from yaml import load, dump, parse
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper
import pprint


class StatusPrinter:
    """
    Only works with ThreadPoolExecutor, but requires hacks in every
    logger call: need a newline character everytime to avoid overwriting
    the current output.
    """
    def __init__(self):
        self.msg = {}
        # HACK Avoid overwriting the first line
        print("\n")

    def clear(self):
        """Blank any previous output."""
        sys.stdout.write("\033[A\33[2KT\r")
        # sys.stdout.flush()

    def update(self, _id, data):
        if logger.isEnabledFor(logging.INFO) or logger.isEnabledFor(logging.DEBUG):
            return

        self.msg[_id] = data
        out = "\n".join(f"Scanning tree: {value}" for key, value in self.msg.items())

        if len(self.msg.keys()) <= 1:
            # Erase & go back to the beginning of the line 
            # can be used with " | ".join(...)
            sys.stdout.write("\33[2K\r" + out)
        else:
            # Move column up, erase go back to beginning of the line
            sys.stdout.write("\033[A\33[2KT\r" + out)

        sys.stdout.flush()


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

# @timer
def load_yaml(fpath):
    with open(fpath, 'r') as fp:
        return load(fp, Loader=Loader)


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
    # TODO add blake2s?
    hashes = ('sha1', 'sha256', 'crc32', 'md5', 'blake2b', 'xxhash')
    parser.add_argument('-c', action='store', dest='csum_name', default="sha1",
        choices=hashes,
        help='hash or crc algorithm to use for integrity checking.',
        required=False)
    levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    parser.add_argument('--log', action='store', default="WARNING",
        choices=levels,
        help='Log level. [DEBUG, INFO, WARNING, ERROR, CRITICAL]')
    implementations = ('pure_dict', 'mixed_dict', 'pure_list')
    parser.add_argument('--tree_type', action='store', default='mixed_dict',
        choices=implementations,
        help=f'Tree representation implementation to use. Default "mixed_dict".')
    args = parser.parse_args()

    log_level = getattr(logging, args.log.upper(), None)
    if not isinstance(log_level, int):
        raise ValueError(f'Invalid log level: {args.log}')
    logger.setLevel(log_level)
    conhandler = logging.StreamHandler()
    conhandler.setLevel(log_level)
    logger.addHandler(conhandler)

    from sdc_detector.tree import DirTreeGeneratorMixed, \
        DirTreeGeneratorPureDict, \
        DirTreeGeneratorPureList

    from sdc_detector.diff import get_comparison
    from sdc_detector.csum import HAS_XXHASH

    if args.csum_name == 'xxhash' and not HAS_XXHASH:
        args.csum_name = 'sha1'
        logger.warning(f"'xxhash' module not found. \
Defaulting back to {args.csum_name}.")

    if args.tree_type == 'mixed_dict':
        fs_struct_type = DirTreeGeneratorMixed
    elif args.tree_type == 'pure_list':
        fs_struct_type = DirTreeGeneratorPureList
    else:
        fs_struct_type = DirTreeGeneratorPureDict

    # TODO write tree type to yaml to avoid comparing different types of trees?
    # for now we assume the same underlying type was generated across scans.

    # TODO
    # * write to file in chunks (buffered, sadly not possible due to the need to
    # serialize python objects into json or yaml)
    # * don't keep everything in memory, use iterators / generators

    printer = StatusPrinter()

    if not args.path2:
        gen = fs_struct_type(Path(args.path1), args, printer)
        gen.generate(no_output=args.no_output)
        exit(0)

    args_set = (args.path1, args.path2)

    # executor = concurrent.futures.ProcessPoolExecutor()
    # Only threads work for sharing a common printer.
    executor = concurrent.futures.ThreadPoolExecutor()
    queue = []

    for path_str in args_set:
        path = Path(path_str)
        if path.is_dir():
            # Generate yaml tree file
            gen = fs_struct_type(path, args, printer)
            future = executor.submit(gen.generate, no_output=args.no_output)
        else:
            # Load a yaml tree file
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
    # HACK always place first argument passed to the left hand side
    if not get_comparison(fs_struct_type).compare(
        results[args_set.index(args.path1)],
        results[args_set.index(args.path2)],
        ):
        print("\nNo difference found. All is good.\n")
