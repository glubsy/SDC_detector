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
import re
from datetime import datetime
import time
import functools
from pathlib import Path

logger = logging.getLogger(__name__)
from hashlib import new
try:
    from crc32c import hardware_based, crc32c as crc32
    if not hardware_based:
        logger.warning(f"crc32c module is not hardware accelerated!")
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


class DirTreeGenerator:
    def __init__(self, path, args):
        self._csum_name = args.csum_name
        self._csum_func = get_crc32 if args.csum_name == "crc32" else get_hash
        self._path = path # pathlib.Path
        self._output_dir = args.output_dir

    def generate(self, no_output=False):
        dir_content = self._generate()
        if not no_output:
            with open(self._output_dir
                    + os.sep
                    + os.path.basename(self._path)
                    + "_hashes_"
                    +  datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    + ".txt",
                    'w') as op:
                dump(dir_content, stream=op, Dumper=Dumper)
        return dir_content

    # Virtual
    def _recursive_stat(self, base_path):
        raise NotImplementedError()
    def _generate(self):
        raise NotImplementedError()
    def _get_file_info(self, root, filename):
        raise NotImplementedError()
    @staticmethod
    def get_path_from_str(string):
        raise NotImplementedError()
    @staticmethod
    def get_leaf_from_path(string):
        raise NotImplementedError()


class DirTreeGeneratorMixed(DirTreeGenerator):
    """Default implementation uses Dicts, and Lists for folder content."""
    def __init__(self, path, args):
        super().__init__(path, args)

    def _recursive_stat(self, base_path):
        directory = {}
        if not os.access(base_path, os.R_OK):
            return directory

        for root, dirs, files in os.walk(base_path):
            dn = os.path.basename(root)
            directory[dn] = []
            # directory[dn] = {}
            if dirs:
                for d in dirs:
                    directory[dn].append(self._recursive_stat(
                    # directory[dn][d] = self._recursive_stat(
                        base_path=os.path.join(base_path, d)
                        )
                    )
                for f in files:
                    directory[dn].append(self._get_file_info(root, f))
                    # directory[dn][f] = self.get_file_info(root, f)
            elif files:
                # directory[dn].append([self.get_file_info(root, f) for f in files])
                for f in files:
                    directory[dn].append(self._get_file_info(root, f))
                    # directory[dn][f] = self.get_file_info(root, f)
            return directory

    def _generate(self):
        """Return dictionary representing dir tree structure."""
        dir_content = self._recursive_stat(self._path)
        # Rename the root node to be similar across comparisons
        # dir_content['root'] = dir_content.pop(base_path.name)
        dir_content['root'] = dir_content[self._path.name]
        del dir_content[self._path.name]
        return dir_content

    def _get_file_info(self, root, filename): # dict
        fpath = os.path.join(root, filename)
        sz = os.stat(fpath).st_size
        if sz == 0:
            logger.warning(f"File {fpath} is {sz} length bytes!")
        return { 'n': filename,
                'cs': self._csum_func(fpath, self._csum_name),
                'sz': sz
        }
        # return { filename: {
        #         'cs': self._csum_func(fpath, self._csum_name),
        #         'sz': os.stat(fpath).st_size
        #     }
        # }

    @staticmethod
    def get_path_from_str(string):
        path_items = split_ddiff_path(string)
        path = ""
        # Ignore first ('root') and last ('n', 'sz', 'cs')
        for i in range(1, len(path_items) -1):
            # ignore the list indices in the string
            if i % 2 == 0:
                path = os.path.join(path, path_items[i])
        return path + os.sep

    @staticmethod
    def get_leaf_from_path(string):
        """
        str: "root['root'][1]['CGI'][2]['crc']" -> str: "root['root'][1]['CGI'][2]"
        """
        idx = string.rfind("][")
        s = string[:idx] + "]"
        logger.debug(f"get_leaf_from_path(): {s}")
        return s


class DirTreeGeneratorPureDict(DirTreeGeneratorMixed):
    """Default implementation uses nested Dicts only."""
    def __init__(self, path, args):
        super().__init__(path, args)

    def _recursive_stat(self, base_path):
        directory = {}
        if not os.access(base_path, os.R_OK):
            return directory

        for root, dirs, files in os.walk(base_path):
            # dn = os.path.basename(root)
            # directory[dn] = {}
            if dirs:
                for d in dirs:
                    directory[d] = self._recursive_stat(
                        base_path=os.path.join(base_path, d)
                    )
                for f in files:
                    directory[f] = self._get_file_info(root, f)
            elif files:
                for f in files:
                    directory[f] = self._get_file_info(root, f)
            return directory

    def _generate(self):
        """Return dictionary representing dir tree structure."""
        dir_content = self._recursive_stat(self._path)
        # Add back a root node - this might not be necessary
        # dir_contents = {}
        # dir_contents['root'] = dir_content
        return dir_content

    def _get_file_info(self, root, filename): # dict
        fpath = os.path.join(root, filename)
        sz = os.stat(fpath).st_size
        if sz == 0:
            logger.warning(f"File {fpath} is {sz} length bytes!")
        return {
                'cs': self._csum_func(fpath, self._csum_name),
                'sz': os.stat(fpath).st_size
        }

    @staticmethod
    def get_path_from_str(string):
        path_items = split_ddiff_path(string)
        path = ""
        # Ignore last ('sz', 'cs')
        for i in range(0, len(path_items) -1):
            path = os.path.join(path, path_items[i])
        return path

    @staticmethod
    def get_leaf_from_path(string):
        """
        str: "root['root']['CGI']['item']['crc']" -> str: "root['root']['CGI']['item']"
        """
        idx = string.rfind("][")
        s = string[:idx] + "]"
        logger.debug(f"get_leaf_from_path(): {s}")
        return s


class DirTreeGeneratorList(DirTreeGeneratorMixed):
    """Implementation around Lists."""
    def __init__(self, path, args):
        super().__init__(path, args)

    def _recursive_stat(self, base_path):
        directory = []
        if not os.access(base_path, os.R_OK):
            return directory

        for root, dirs, files in os.walk(base_path):
            dn = os.path.basename(root)
            directory.append(dn)
            if dirs:
                for d in dirs:
                    directory.append(
                        self._recursive_stat(base_path=os.path.join(base_path, d)
                        )
                    )
                for f in files:
                    directory.append(self._get_file_info(root, f))
            elif files:
                directory.append([self._get_file_info(root, f) for f in files])
            return directory

    def _generate(self):
        """Returs List of Lists representing dir tree structure."""
        dir_content = self._recursive_stat(self._path)
        # Rename the root node since it will be different accross mounts
        dir_content[0] = 'root'
        return dir_content

    def _get_file_info(self, root, filename):
        fpath = os.path.join(root, filename)
        return [filename, get_crc32(fpath), os.stat(fpath).st_size]


@timer
def get_hash(filename, hashtype):
    """Return sha1, sha256 or md5 as a string of hexadecimal hash."""
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
def get_crc32(filename, notused):
    """Return string of crc32 csum."""
    #binascii, zlib and crc32c share a similar interface.
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
def ddiff_compare(tree1, tree2, tree_class):
    """Compare each line from path1 to each line to path2, return any difference"""
    type1 = type(tree1)
    type2 = type(tree2)
    if type1 != type2:
        logging.critical("Types are different! Cannot diff.")
        return
    if type1 == "dict":
        # We assume this is mixed dict here.
        ignore_order = True
    else:
        ignore_order = False

    # FIXME ddiff does not work well with list based tree structs:
    # leaf nodes differences are not correctly reported: file names, size and
    # crc values are randomly compared against one another which yields false
    # changes. We then need ignore_order=True, but then another problem arises
    # as filenames may be changed, their index in the lists are not always the
    # same, so the comparisons are made between the wrong indices / items.
    ddiff = deepdiff.DeepDiff(tree1, tree2,
        verbose_level=2,
        view='tree',
        ignore_order=ignore_order,
        ignore_string_type_changes=True,
        cutoff_distance_for_pairs=1.0,
        cutoff_intersection_for_pairs=1.0
        )
    pprint.pprint(ddiff, indent=2)

    pprint.pprint(ddiff.to_dict(view_override='text'), indent=2)
    logger.debug(ddiff.to_dict(view_override='text'))
    logger.debug(f"PRETTY:\n{ddiff.pretty()}")

    set_changed = ddiff.get('values_changed')
    if set_changed is not None:
        changed_dict = parse_ddiff_changed(set_changed, tree_class, tree1)
        for k, v in changed_dict.items():
            sentence = ", ".join(v)
            logger.warning(f"{k} {sentence}")

    set_added = ddiff.get('iterable_item_added')
    if set_added is not None:
        list_added = list(set_added)
        for item in list_added:
            logger.debug(f"added path: {item.path()} -> t1: {item.t1} -> t2: {item.t2}")

    set_removed = ddiff.get('iterable_item_removed')
    if set_removed is not None:
        list_removed = list(set_removed)
        for item in list_removed:
            logger.debug(f"removed path: {item.path()} -> t1: {item.t1} -> t2: {item.t2}")

    # TODO error on:
    # hash is '0'
    # size is 0
    # name is different? -> will not work!
    # number of items is different / item is missing

def parse_ddiff_changed(set_changed, tree_class, base_tree):
    list_changed = list(set_changed)  # list of DiffLevel
    logger.debug(f"list_changed: {list_changed}")
    results = {}

    def append_to_list(_d, _k, _s):
        _l = _d.get(_k, [])
        _l.append(_s)
        _d[_k] = _l

    for change in set_changed:
        if tree_class == DirTreeGeneratorPureDict:
            parsed_path = tree_class.get_path_from_str(change.path())
            logger.debug(f"---\nget_path_from_str(): {parsed_path}")
            fname = parsed_path
            logger.debug(f"filename: {fname}")
            logger.debug(f"parsed_path: {parsed_path}")
        else:
            leaf = deepdiff.extract(base_tree, tree_class.get_leaf_from_path(change.path()))
            logger.debug(f"leaf: {leaf}")
            fname = leaf.get("n")
            logger.debug(f"---\nfilename: {fname}")
            logger.debug(f"change.path(): {change.path()}")
            parsed_path = tree_class.get_path_from_str(change.path()) + fname
            logger.debug(f"parsed_path: {parsed_path}")
        prop = split_ddiff_path(change.path())[-1]
        if prop == "cs":
            logger.debug(f"CSUM value changed for {fname} from {change.t1} to {change.t2}")
            append_to_list(results, parsed_path, f"changed csum from {change.t1} to {change.t2}")
        elif prop == "sz":
            logger.debug(f"Size changed for {fname} from {change.t1} to {change.t2}")
            append_to_list(results, parsed_path, f"size changed from {change.t1} to {change.t2}")
        elif prop == "n":
            logger.debug(f"Filename changed for {fname} from {change.t1} to {change.t2}")
            append_to_list(results, parsed_path, f"filename changed from {change.t1} to {change.t2}")

    return results


def split_ddiff_path(string):
    """
    str: root['root'][1]['CGI'][2]['crc'] -> list: ["root", "CGI", "crc]
    """
    # path_items = [tuple(re.search('\[(.+)\]', key).group(1).split('][')) for key in diff.keys()]
    res = [s.strip("\'") for s in re.search('\[(.+)\]', string).group(1).split('][')]
    logger.debug(f"split_ddif_path(): {res}")
    return res

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

    if not args.path2:
        gen = fs_struct_type(Path(args.path1), args)
        gen.generate(no_output=args.no_output)
        exit(0)

    path1 = Path(args.path1)
    path2 = Path(args.path2)
    gen1 = fs_struct_type(path1, args)
    gen2 = fs_struct_type(path2, args)
    # TODO add threading here
    # FIXME write tree type to yaml to avoid comparing different types of trees?
    # for now we assume the same type was generated across scans.
    dir_dict1 = gen1.generate(no_output=args.no_output) if path1.is_dir() else load_yaml(path1)
    dir_dict2 = gen2.generate(no_output=args.no_output) if path2.is_dir() else load_yaml(path2)
    logger.debug(f"Dump of generate() output:")
    logger.debug(dump(dir_dict1, stream=None, Dumper=Dumper))
    logger.debug(dump(dir_dict2, stream=None, Dumper=Dumper))
    logger.debug(f"PPrint of dictionaries:")
    pprint.pprint(dir_dict1)
    pprint.pprint(dir_dict2)
    # TODO extra option: for each file listed in yaml, compare with a target
    # dir (partial backups) only those files.
    ddiff_compare(dir_dict1, dir_dict2, fs_struct_type)
