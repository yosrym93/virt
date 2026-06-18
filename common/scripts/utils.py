import logging
import os
import pathlib
import sys


BASEDIR_NAME = 'virt'
basedir = None


def get_basedir():
    global basedir
    if basedir is None:
        current_path = pathlib.Path(__file__).resolve()
        while current_path.parent != current_path:
            current_path = current_path.parent
            if current_path.name == BASEDIR_NAME:
                basedir = current_path
                return basedir

        logging.error('Failed to find the base directory')
        exit(-1)
    return basedir


def find_path(pattern, is_dir, desc, parent=get_basedir(), allow_dup=False, allow_zero=False, recursive=True):
    results = []
    parent = pathlib.Path(parent)
    paths = parent.rglob(pattern) if recursive else parent.glob(pattern)
    for p in paths:
        if p.is_dir() == is_dir:
            results.append(p)

    if (len(results) == 0 and not allow_zero) or (len(results) > 1 and not allow_dup):
        logging.error('Expected to find one %s, found %d', desc, len(results))
        if results:
            logging.error('%s', results)
        exit(-1)
    elif results:
        logging.info('Found %s at %s', desc, results[0])
        return results[0]
    else:
        return None


def resolve_kernel_dir(kernel_name, search_dir):
    # Stage 1: Check if kernel_name is an explicit absolute or relative path
    p = pathlib.Path(kernel_name).expanduser()
    if p.exists() and p.is_dir():
        return p.resolve()

    # Stage 2: Search inside search_dir (~/builds) for directories named kernel_name
    search_root = pathlib.Path(search_dir).expanduser()
    if not search_root.exists():
        logging.error("Search directory '%s' does not exist.", search_root)
        sys.exit(1)

    matching_dirs = [d.resolve() for d in search_root.rglob(kernel_name) if d.is_dir() and d.name == kernel_name]

    if len(matching_dirs) == 1:
        logging.info("Found Kernel directory at %s", matching_dirs[0])
        return matching_dirs[0]

    logging.error("Expected to find exactly one Kernel directory named '%s' in '%s', found %d:\n%s",
                  kernel_name, search_root, len(matching_dirs), matching_dirs)
    sys.exit(1)


def find_kernel_binary(kernel_dir, binary_name='bzImage'):
    return find_path(binary_name, False, f'kernel binary ({binary_name})',
                     parent=kernel_dir, allow_dup=True)


def find_modules_dir(kernel_dir):
    for pat in [os.path.join('lib', 'modules', '*'), os.path.join('modules', 'lib', 'modules', '*')]:
        res = find_path(pat, True, 'modules dir', parent=kernel_dir, allow_zero=True)
        if res:
            return res
    return None
