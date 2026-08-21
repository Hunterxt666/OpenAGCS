import os
import shlex
import stat
import sys


def check_if_exist(path):
    if not os.path.exists(path):
        os.mkdir(path)


def build_run_python_sh(path, args):
    working_directory = os.getcwd()
    command = " ".join(
        shlex.quote(str(arg)) for arg in [sys.executable, *args]
    )
    with open(path, 'w') as file:
        file.write("#!/usr/bin/env bash\n")
        file.write("set -e\n")
        file.write(f"cd -- {shlex.quote(working_directory)}\n")
        file.write(
            f"PYTHONPATH={shlex.quote(working_directory)} exec {command}\n"
        )
    current_mode = os.stat(path).st_mode
    os.chmod(path, current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
