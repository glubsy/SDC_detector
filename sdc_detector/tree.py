import os
import re
import logging
logger = logging.getLogger()
from datetime import datetime

from yaml import load, dump, parse
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper
import pprint

from .csum import * 


class DirTreeGenerator:
    def __init__(self, path, args):
        self._csum_name = args.csum_name
        # self._csum_func = get_csum
        self._path = path # pathlib.Path
        self._output_dir = args.output_dir

    def generate(self, no_output=False):
        dir_content = self._generate()
        if not no_output:
            filename = os.path.basename(self._path)\
                    + "_hashes_"\
                    +  datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            fpath = self._output_dir\
                    + os.sep\
                    + filename\
                    + ".txt"
            with open(fpath, 'w') as op:
                dump(dir_content, stream=op, Dumper=Dumper)
            print(f"Wrote results to YAML file: {fpath}.")
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
            if dirs:
                for d in dirs:
                    logger.info(f"Scanning {os.path.join(base_path, d)}...")
                    directory[dn].append(self._recursive_stat(
                        base_path=os.path.join(base_path, d)
                        )
                    )
                for f in files:
                    directory[dn].append(self._get_file_info(root, f))
            elif files:
                # directory[dn].append([self.get_file_info(root, f) for f in files])
                for f in files:
                    directory[dn].append(self._get_file_info(root, f))
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
                'cs': get_csum(fpath, self._csum_name),
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


class DirTreeGeneratorPureDict(DirTreeGenerator):
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
                    logger.info(f"Scanning {os.path.join(base_path, d)}...")
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
        # Add back a root node -> this might not be necessary
        # dir_contents = {}
        # dir_contents['root'] = dir_content
        return dir_content

    def _get_file_info(self, root, filename): # dict
        fpath = os.path.join(root, filename)
        sz = os.stat(fpath).st_size
        if sz == 0:
            logger.warning(f"File {fpath} is {sz} length bytes!")
        return {
                'cs': get_csum(fpath, self._csum_name),
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
                    logger.info(f"Scanning {os.path.join(base_path, d)}...")
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


def split_ddiff_path(string):
    """
    str: root['root'][1]['CGI'][2]['crc'] -> list: ["root", "CGI", "crc]
    """
    # path_items = [tuple(re.search('\[(.+)\]', key).group(1).split('][')) for key in diff.keys()]
    res = [s.strip("\'") for s in re.search('\[(.+)\]', string).group(1).split('][')]
    logger.debug(f"split_ddif_path(): {res}")
    return res

# @timer
def load_yaml(fpath):
    with open(fpath, 'r') as fp:
        return load(fp, Loader=Loader)
