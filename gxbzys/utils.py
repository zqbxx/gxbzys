import os
import sys
from pathlib import Path


def init_nuitka_env():
    exe_dir = sys.path[1]
    lib_dir = os.path.join(exe_dir, 'lib')
    dll_dir = os.path.join(exe_dir, 'dll')
    sys.path.append(lib_dir)
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ["PATH"]
    os.environ["nuitka"] = '0'
    os.environ["nuitka_exe_dir"] = exe_dir

def is_in_nuitka() -> bool:
    t = os.environ.get("nuitka", None)
    return t is not None


def get_abs_path(rel_path=None) -> Path:

    if is_in_nuitka():
        if rel_path is not None:
            return (Path(os.environ.get('nuitka_exe_dir')) / Path(rel_path)).absolute()
        else:
            return Path(os.environ.get('nuitka_exe_dir')).absolute()
    elif rel_path is not None:
        return Path(rel_path).absolute()
    else:
        return Path('.').absolute()

