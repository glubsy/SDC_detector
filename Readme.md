## Rationale

Detect silent data corruption ("SDC") for data stored on hard drives.
We compare two similar file system trees for differing files hashes / checksums, or differing number of files listed.
This should help deduce if bit fade (or bit flip) has occured between two file system  clones.
The advantage over `rsync -c` is saving the results to a yaml file for further comparisons without having to recompute every time.

## Usage

* Generate text result file:
`python sdc_detect.py --output_dir ./ /path/to/directory`

* Compare two text result files:
`python sdc_detect.py result1.txt result2.txt`

NOTES:

* Files are considered missing (added or removed) if their exact name are not found in the second result set.

## Dependencies

deepdiff
hashlib
crc32c (optional)
yaml

## TODO

* Test suite
* Diff results without deepdiff (by walking the trees and comparing ourselves)