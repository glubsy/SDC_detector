import logging
logger = logging.getLogger()
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

HAS_XXHASH = False
try:
    # TODO allow user choice of either, or according to platform support?
    from xxhash import xxh64, xxh32
    HAS_XXHASH = True
except Exception as e:
    logger.debug(f"Failed to load xxhash module. {e}")

BUF_SIZE = 65536  # arbitrary value of 64kb chunks


def timer(func):
    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start = time.perf_counter_ns()
        value = func(*args, **kwargs)
        end = time.perf_counter_ns()
        total = end - start
        logger.debug(f"TIMER: {func.__name__!r}{args}"\
                     f"{kwargs} took {total} ns.")
        return value
    return wrapper_timer

@timer
def get_hash(filename, hashtype):
    """Return hashes available from hashlib as a string of hexadecimal hash."""
    _hash = new(hashtype, usedforsecurity=False)
    with open(filename, 'rb') as fp:
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            _hash.update(data)
    return _hash.hexdigest()

@timer
def get_xxhash(filename):
    _hash = xxh64()
    with open(filename, 'rb') as fp:
        while True:
            data = fp.read(BUF_SIZE)
            if not data:
                break
            _hash.update(data)
    return _hash.hexdigest()

@timer
def get_crc32(filename):
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
