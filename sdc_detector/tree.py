import os
import logging
from functools import partial
logger = logging.getLogger()
from datetime import datetime

from yaml import load, dump, parse
try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper

from .csum import *

#TODO we could walk the trees manually with a for k1, k2 in d1.keys(), d2.keys():

class DirTreeGenerator:
    def __init__(self, path, _args, printer):
        self._csum_name = _args.csum_name
        self.printer = printer
        # FIXME this could be in a nested class maybe
        if self._csum_name == 'crc32':
            self._get_csum = get_crc32
        elif self._csum_name == 'xxhash':
            self._get_csum = get_xxhash
        else:
            self._get_csum = partial(get_hash, hashtype=self._csum_name)

        self._path = path # pathlib.Path
        self._output_dir = _args.output_dir

    def generate(self, no_output=False):
        # FIXME this function might not need to be in this class,
        # perhaps standalone in __main__, since all we do is a "tee" on the
        # dir_content that will be returned regardless.
        dir_content = self._generate()

        if not no_output:
            filename = os.path.basename(self._path)\
                    + "_hashes_"\
                    +  datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            fpath = self._output_dir\
                    + os.sep\
                    + filename\
                    + ".yaml"
            with open(fpath, 'w') as op:
                dump(dir_content, stream=op, Dumper=Dumper)
            print(f"\nWrote results to YAML file: {fpath}.")
        return dir_content

    # Virtual
    def _generate(self):
        raise NotImplementedError()
    def _recursive_stat(self, base_path):
        raise NotImplementedError()
    def _get_file_info(self, root, filename):
        raise NotImplementedError()


class DirTreeGeneratorMixed(DirTreeGenerator):
    """Default implementation uses Dicts, and Lists for directory content."""
    def __init__(self, path, args, printer):
        super().__init__(path, args, printer)

    def _generate(self):
        """Return dictionary representing dir tree structure."""
        dir_content = self._recursive_stat(self._path)
        # self.printer.clear()

        # Rename the root node to be similar across comparisons
        # dir_content['root'] = dir_content.pop(base_path.name)
        dir_content['root'] = dir_content[self._path.name]
        del dir_content[self._path.name]
        return dir_content

    def _recursive_stat(self, base_path):
        directory = {}
        if not os.access(base_path, os.R_OK):
            return directory

        for root, dirs, files in os.walk(base_path):
            dn = os.path.basename(root)
            directory[dn] = []
            if dirs:
                for d in dirs:
                    dirname = os.path.join(base_path, d)
                    logger.info(f"Scanning {dirname}...")
                    self.printer.update(id(self), dirname)
                    directory[dn].append(self._recursive_stat(
                        base_path=os.path.join(base_path, d)
                        )
                    )
                for f in files:
                    try:
                        directory[dn].append(self._get_file_info(root, f))
                    except PermissionError as e:
                        logger.critical(f"\n{e}")
                        continue
            elif files:
                # directory[dn].append([self.get_file_info(root, f) for f in files])
                for f in files:
                    try:
                        directory[dn].append(self._get_file_info(root, f))
                    except PermissionError as e:
                        logger.critical(f"\n{e}")
                        continue
            return directory

    def _get_file_info(self, root, filename): # dict
        fpath = os.path.join(root, filename)
        sz = os.stat(fpath).st_size
        if sz == 0:
            logger.warning(f"\nFile {fpath} is {sz} length bytes!")
        return { 'n': filename,
                'cs': self._get_csum(fpath),
                'sz': sz
        }
        # return { filename: {
        #         'cs': self._csum_func(fpath, self._csum_name),
        #         'sz': os.stat(fpath).st_size
        #     }
        # }


class DirTreeGeneratorPureDict(DirTreeGenerator):
    """Default implementation uses nested Dicts only."""
    def __init__(self, path, args, printer):
        super().__init__(path, args, printer)

    def _generate(self):
        """Return dictionary representing dir tree structure."""
        dir_content = self._recursive_stat(self._path)
        # self.printer.clear()

        # Add back a root node -> this might not be necessary
        # dir_contents = {}
        # dir_contents['root'] = dir_content
        return dir_content

    def _recursive_stat(self, base_path):
        directory = {}
        if not os.access(base_path, os.R_OK):
            return directory

        for root, dirs, files in os.walk(base_path):
            # dn = os.path.basename(root)
            # directory[dn] = {}
            if dirs:
                for d in dirs:
                    dirname = os.path.join(base_path, d)
                    logger.info(f"Scanning {dirname}...")
                    self.printer.update(id(self), dirname)
                    directory[d] = self._recursive_stat(
                        base_path=os.path.join(base_path, d)
                    )
                for f in files:
                    try:
                        directory[f] = self._get_file_info(root, f)
                    except PermissionError as e:
                        logger.critical(f"\n{e}")
                        continue
            elif files:
                for f in files:
                    try:
                        directory[f] = self._get_file_info(root, f)
                    except PermissionError as e:
                        logger.critical(f"\n{e}")
                        continue
            return directory

    def _get_file_info(self, root, filename): # dict
        fpath = os.path.join(root, filename)
        sz = os.stat(fpath).st_size
        if sz == 0:
            logger.warning(f"\nFile {fpath} is {sz} length bytes!")
        return {
                'cs': self._get_csum(fpath),
                'sz': os.stat(fpath).st_size
        }


class DirTreeGeneratorPureList(DirTreeGeneratorMixed):
    """Implementation around Lists."""
    def __init__(self, path, args, printer):
        super().__init__(path, args, printer)

    def _generate(self):
        """Returns List of Lists representing dir tree structure."""
        dir_content = self._recursive_stat(self._path)
        # self.printer.clear()

        # Rename the root node since it will be different accross mounts
        dir_content[0] = 'root'
        return dir_content

    def _recursive_stat(self, base_path):
        directory = []
        if not os.access(base_path, os.R_OK):
            return directory

        for root, dirs, files in os.walk(base_path):
            dn = os.path.basename(root)
            directory.append(dn)
            if dirs:
                for d in dirs:
                    dirname = os.path.join(base_path, d)
                    logger.info(f"Scanning {dirname}...")
                    self.printer.update(id(self), dirname)
                    directory.append(
                        self._recursive_stat(base_path=os.path.join(base_path, d)
                        )
                    )
                for f in files:
                    try:
                        directory.append(self._get_file_info(root, f))
                    except PermissionError as e:
                        logger.critical(f"\n{e}")
                        continue
            elif files:
                try:
                    directory.append([self._get_file_info(root, f) for f in files])
                except PermissionError as e:
                    logger.critical(f"\n{e}")
            return directory

    def _get_file_info(self, root, filename):
        fpath = os.path.join(root, filename)
        sz = os.stat(fpath).st_size
        if sz == 0:
            logger.warning(f"\nFile {fpath} is {sz} length bytes!")
        return [filename, self._get_csum(fpath), sz]
