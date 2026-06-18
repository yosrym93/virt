import logging
import pathlib


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
