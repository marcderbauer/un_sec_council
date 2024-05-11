from os import listdir
from os.path import isfile, join


def get_files_from_folder(folder_name: str) -> list[str]:
    return [f for f in listdir(folder_name) if isfile(join(folder_name, f))]
