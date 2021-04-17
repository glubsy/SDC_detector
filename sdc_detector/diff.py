import logging
logger = logging.getLogger()
import pprint

# import dictdiffer # smaller, faster but cannot traverse results
import deepdiff
from .tree import (DirTreeGeneratorPureDict,
                   DirTreeGeneratorMixed,
                   DirTreeGeneratorList,
                   split_ddiff_path)

# @timer
def ddiff_compare(tree1, tree2, tree_class):
    """Compare each line from path1 to each line to path2, return any difference"""
    type1 = type(tree1)
    type2 = type(tree2)
    if type1 != type2:
        logging.critical("Types are different! Cannot diff.")
        return
    if type1 == "dict":
        # FIXME We assume this is mixed dict here.
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
    if not ddiff:
        print("No difference found. All is good!")
        return

    pprint.pprint(ddiff, indent=2)
    pprint.pprint(ddiff.to_dict(view_override='text'), indent=2)
    logger.debug(ddiff.to_dict(view_override='text'))
    logger.debug(f"ddiff.pretty():\n{ddiff.pretty()}")

    set_changed = ddiff.get('values_changed')
    if set_changed is not None:
        changed_dict = parse_ddiff_changed(set_changed, tree_class, tree1)
        for k, v in changed_dict.items():
            sentence = ", ".join(v)
            print(f"{k} {sentence}")

    set_added = ddiff.get('iterable_item_added')
    if not set_added:
        set_added = ddiff.get('dictionary_item_added')
    if set_added is not None:
        list_added = list(set_added)
        for item in list_added:
            logger.debug(f"added path: {item.path()} -> t1: {item.t1} -> t2: {item.t2}")

    set_removed = ddiff.get('iterable_item_removed')
    if not set_removed:
        set_removed = ddiff.get('dictionary_item_removed')
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
