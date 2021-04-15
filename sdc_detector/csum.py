import logging
logger = logging.getLogger("sdc_detector")
import functools
import time

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
BUF_SIZE = 65536  # arbitrary value of 64kb chunks!


def timer(func):
    @functools.wraps(func)
    def wrapper_timer(*args):
        start = time.perf_counter_ns()
        value = func(*args)
        end = time.perf_counter_ns()
        total = end - start
        logger.debug(f"TIMER: {func.__name__!r}{args[0]} took {total} ns.")
        return value
    return wrapper_timer

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
