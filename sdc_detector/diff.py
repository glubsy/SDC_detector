import os
import logging
logger = logging.getLogger()
import pprint
import re

# import dictdiffer # smaller, faster but cannot traverse results
import deepdiff
from .tree import (DirTreeGeneratorPureDict,
                   DirTreeGeneratorMixed,
                   DirTreeGeneratorPureList)
# TODO "manual" implementation without deepdiff

# TODO error on:
# hash is '0'
# size is 0
# name is different? -> will not work!
# number of items is different / item is missing

def get_comparison(tree_struct):
    if tree_struct == DirTreeGeneratorPureDict:
        return ComparisonPureDict()
    elif tree_struct == DirTreeGeneratorMixed:
        return ComparisonMixed()
    elif tree_struct == DirTreeGeneratorPureList:
        return ComparisonPureList()


class TreeComparison:
    # Can be tied to class, as it is a singleton.
    results = {}

    def compare(self, tree1, tree2):
        type1 = type(tree1)
        type2 = type(tree2)
        if type1 != type2:
            logging.critical("Types are different! Cannot diff.")
            return None
        return self._compare(tree1, tree2)

   # @ŧimer
    def _compare(self, tree1, tree2):
        """
        Use deepdiff to compare and print differences between two tree strucs.
        """
        ddiff = self._get_diff(tree1, tree2)

        if not ddiff:
            print("No difference found. All is good!")
            return

        if logger.isEnabledFor(logging.DEBUG):
            pprint.pprint(ddiff, indent=2)
            pprint.pprint(ddiff.to_dict(view_override='text'), indent=2)
        logger.debug(ddiff.to_dict(view_override='text'))
        logger.debug(f"ddiff.pretty():\n{ddiff.pretty()}")

        set_added = ddiff.get('iterable_item_added')\
                    or ddiff.get('dictionary_item_added')
        if set_added is not None:
            list_added = list(set_added)
            for item in list_added:
                logger.debug(f"added path: {item.path()}"\
                            f"-> t1: {item.t1} -> t2: {item.t2}")

        set_removed = ddiff.get('iterable_item_removed')\
                    or ddiff.get('dictionary_item_removed')
        if set_removed is not None:
            list_removed = list(set_removed)
            for item in list_removed:
                logger.debug(f"removed path: {item.path()}"\
                            f"-> t1: {item.t1} -> t2: {item.t2}")

        set_changed = ddiff.get('values_changed')
        if set_changed is not None:
            changed_dict = self.parse_ddiff_changed(set_changed, tree1)
            for k, v in changed_dict.items():
                sentence = ", ".join(v)
                print(f"{k} {sentence}")

    @classmethod
    def add_to_result(cls, parsed_path, change_type, change):
        if change_type == "n":
            _type = "Filename"
        elif change_type == "cs":
            _type = "CSUM"
        elif change_type == "sz":
            _type = "Size"
        else:
            return
        logger.debug(f"{_type} changed for {parsed_path} from {change.t1} to {change.t2}")
        append_to_list(cls.results, parsed_path, \
                           f"{_type} changed from {change.t1} to {change.t2}")

    @classmethod
    def parse_ddiff_changed(cls, set_changed, base_tree):
        raise NotImplementedError


class ComparisonMixed(TreeComparison):
    """
    This class depends on tree struct implementation based on both Dicts
    and Lists: Lists for files in each directory content.
    """
    def _get_diff(self, tree1, tree2):
        return deepdiff.DeepDiff(
            tree1, tree2,
            verbose_level=2,
            view='tree',
            ignore_order=True,
            ignore_string_type_changes=True,
            cutoff_distance_for_pairs=1.0,
            cutoff_intersection_for_pairs=1.0
        )

    @classmethod
    def parse_ddiff_changed(cls, set_changed, base_tree):
        list_changed = list(set_changed)  # list of DiffLevel
        logger.debug(f"list_changed: {list_changed}")

        for change in list_changed:
            leaf = deepdiff.extract(base_tree, cls.get_leaf_from_path(change.path()))
            logger.debug(f"leaf: {leaf}")
            fname = leaf.get("n")
            logger.debug(f"---\nfilename: {fname}")
            logger.debug(f"change.path(): {change.path()}")
            parsed_path = cls._get_path_from_str(change.path()) + fname
            logger.debug(f"parsed_path: {parsed_path}")

            prop = split_ddiff_path(change.path())[-1]
            cls.add_to_result(parsed_path, prop, change)
        return cls.results

    @classmethod
    def _get_path_from_str(cls, string):
        path_items = split_ddiff_path(string)
        path = ""
        # Ignore first ('root') and last ('n', 'sz', 'cs')
        for i in range(1, len(path_items) -1):
            # ignore the list indices in the string
            if i % 2 == 0:
                path = os.path.join(path, path_items[i])
        return path + os.sep

    @classmethod
    def get_leaf_from_path(cls, string):
        """
        Get the patht to the item pointed by the last list index.
        str: "root['root'][1]['CGI'][2]['crc']" -> str: "root['root'][1]['CGI'][2]"
        """
        idx = string.rfind("][")
        s = string[:idx] + "]"
        logger.debug(f"get_leaf_from_path(): {s}")
        return s


class ComparisonPureDict(TreeComparison):
    """
    This class depends on tree struct implementation based purely on Dicts.
    """
    def _get_diff(self, tree1, tree2):
        return deepdiff.DeepDiff(
            tree1, tree2,
            verbose_level=2,
            view='tree',
            ignore_order=True,
            ignore_string_type_changes=True,
            cutoff_distance_for_pairs=1.0,
            cutoff_intersection_for_pairs=1.0
        )

    @classmethod
    def parse_ddiff_changed(cls, set_changed, base_tree):
        list_changed = list(set_changed)  # list of DiffLevel
        logger.debug(f"list_changed: {list_changed}")

        for change in list_changed:
            parsed_path = cls._get_path_from_str(change.path())
            logger.debug(f"---\n_get_path_from_str(): {parsed_path}")
            fname = parsed_path
            logger.debug(f"filename: {fname}")
            logger.debug(f"parsed_path: {parsed_path}")

            prop = split_ddiff_path(change.path())[-1]
            cls.add_to_result(parsed_path, prop, change)
        return cls.results

    @classmethod
    def _get_path_from_str(cls, string):
        path_items = split_ddiff_path(string)
        path = ""
        # Ignore last ('sz', 'cs')
        for i in range(0, len(path_items) -1):
            path = os.path.join(path, path_items[i])
        return path

    @classmethod
    def get_leaf_from_path(cls, string):
        """
        str: "root['root']['CGI']['item']['crc']" -> str: "root['root']['CGI']['item']"
        """
        idx = string.rfind("][")
        s = string[:idx] + "]"
        logger.debug(f"get_leaf_from_path(): {s}")
        return s


class ComparisonPureList(TreeComparison):
    """
    This class depends on the tree struct implementation based purely on Lists.
    """
    def _get_diff(self, tree1, tree2):
        # FIXME ddiff does not work well with purely list based tree structs:
        # leaf nodes differences are not correctly reported. File names,
        # size and csum values are randomly compared against one another
        # which yields false positive changes. We then need ignore_order=True,
        # but then another problem arises as filenames may be changed,
        # their index in the lists are not always the same, so the comparisons
        # are made between the wrong indices / items.
        return deepdiff.DeepDiff(
            tree1, tree2,
            verbose_level=2,
            view='tree',
            ignore_order=False, # List implementation specific
            ignore_string_type_changes=True,
            cutoff_distance_for_pairs=1.0,
            cutoff_intersection_for_pairs=1.0
        )

    @classmethod
    def parse_ddiff_changed(cls, set_changed, base_tree):
        list_changed = list(set_changed)  # list of DiffLevel
        logger.debug(f"list_changed: {list_changed}")

        for change in list_changed:
            path_list = split_ddiff_path(change.path())
            leaf = deepdiff.extract(base_tree, cls.get_leaf_from_path(change.path()))
            logger.debug(f"leaf: {leaf}")
            fname = leaf[0]
            logger.debug(f"filename: {fname}")
            logger.debug(f"change.path(): {change.path()}")

            parsed_path = cls._get_path_from_str(base_tree, path_list)
            logger.debug(f"parsed_path: {parsed_path}")

            prop = path_list[-1]
            if prop == "1":
                cls.add_to_result(parsed_path, "cs", change)
            elif prop == "2":
                cls.add_to_result(parsed_path, "sz", change)
            elif prop == "0":
                cls.add_to_result(parsed_path, "n", change)
        return cls.results


    @classmethod
    def _get_path_from_str(cls, base_tree, path_list):
        """
        Get the name of each parent folder in a row and recreate the path.
        """
        def recurse(t, idxs, l=[]):
            """Rebuild the path from names pointed by
               each index listed in idxs."""
            if not idxs:
                return
            # get the element pointed by the current index
            elem = t[int(idxs.pop(0))]
            # get the dir or file name only if it's an actual name (ie. not a list)
            if isinstance(elem[0], str):
                l.append(elem[0])
            recurse(elem, idxs, l)
            return l

        # ignore element reported by deepdiff that changed (always last one)
        path_items = path_list[:-1]
        pathl = recurse(base_tree, path_items)
        logger.debug(f"Rebuilt path elements: {pathl}")
        return os.path.join(*pathl)

    @classmethod
    def get_leaf_from_path(cls, string):
        """
        str: "root[2][9][0]" -> str: "root[2][9]"
        """
        idx = string.rfind("][")
        s = string[:idx] + "]"
        logger.debug(f"get_leaf_from_path(): {s}")
        return s


def split_ddiff_path(string):
    """
    Returns a list made of a deepdiff path.
    str: root['root'][1]['CGI'][2]['crc'] -> list: ["root", "1", "CGI", "2", "crc"]
    """
    # path_items = [tuple(re.search('\[(.+)\]', key).group(1).split('][')) for key in diff.keys()]
    res = [s.strip("\'") for s in re.search('\[(.+)\]', string).group(1).split('][')]
    logger.debug(f"split_ddif_path(): {res}")
    return res

def append_to_list(_dict, _key, _string):
    """Append string to _list pointed by _key of _dict,
       or create a new list at key if doesn't exist.
    """
    _list = _dict.get(_key, [])
    _list.append(_string)
    _dict[_key] = _list
