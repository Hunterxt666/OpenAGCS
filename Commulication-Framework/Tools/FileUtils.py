import os


def check_if_exist(path):
    if not os.path.exists(path):
        os.mkdir(path)


def build_run_python_sh(path, args):
    with open(path, 'w') as file:
        file.write(f"cd {os.getcwd()} \n")
        runpy_cmd = f"PYTHONPATH={os.getcwd()} ~/testvenv/bin/python"
        for arg in args:
            runpy_cmd += f" {arg}"
        runpy_cmd += "\n"
        file.write(runpy_cmd)

