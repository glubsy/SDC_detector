Detect silent data corruption (SDC) of data stored on media storage devices.

# Rationale

Compare two similar file system trees for differing file hashes / checksums, or differing number of files returned by the operating system.

This should help determine if bit fade (or bit flip) has occured between two file system clones.

The advantage over `rsync -c` is saving the results to a YAML file for further comparisons without having to recompute hashes every time.
However, this being a static file, it has to be generated again if the file system tree has changed.

# Usage

* Generate text result file:
`python __main__.py -c "xxhash" --output_dir ./ /path/to/directory`

* Compare two text result files:
`python __main__.py results_1.yaml results_2.yaml`

NOTE:

* Files are considered missing (added or removed) if their exact name is not found in the second result set.
* the "mixed_dict" implementation works the best, followed by "pure_dict. "pure_list" seems to work, but needs "ignore_order=True" at least.

# Dependencies

* deepdiff
* hashlib
* [xxhash](https://github.com/Cyan4973/xxHash) (optional, recommended)
* [crc32c](https://github.com/ICRAR/crc32c) (optional)
* yaml
* pprint

# License

GPLv3

# TODO

* A proper test suite.
* Diff results comparison without deepdiff module, by walking the trees and comparing by ourselves.
* Do more than 2 comparisons at a time, ie. compare >2 file systems at once.
