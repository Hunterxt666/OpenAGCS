import yaml


def read_config(path):
    with open(path, encoding='utf-8') as f:
        data = yaml.load(f.read(), Loader=yaml.FullLoader)
    return data
