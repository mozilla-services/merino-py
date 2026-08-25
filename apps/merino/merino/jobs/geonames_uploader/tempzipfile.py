"""Utilities for writing zip files to a temporary directory and extracting
items from them.
"""

from io import BufferedRandom
from tempfile import TemporaryDirectory, TemporaryFile
from typing import Any
from zipfile import ZipFile


class TempZipFile:
    """This class writes a zip file to a temporary directory and extracts its
    items to the directory. This is useful when streaming large zip files from
    the web, for example, that you don't want to keep in memory all at once.

    Usage:

    # `file_like_obj` might be a streaming HTTP response.
    with TempZipFile(file_like_obj) as zip_file:
        txt_path = zip_file.extract("foo.txt")
        with open(txt_path) as txt_file:
            print(txt_file.read())

    """

    tmp_dir: TemporaryDirectory
    tmp_file: BufferedRandom
    zip_file: ZipFile

    def __init__(self, file_obj: Any) -> None:
        """Write `file_obj` to a temporary directory and initialize the zip
        file.

        """
        self.tmp_dir = TemporaryDirectory()
        self.tmp_file = TemporaryFile(dir=self.tmp_dir.name)
        read_len = -1
        while read_len != 0:
            chunk = file_obj.read()
            read_len = len(chunk)
            self.tmp_file.write(chunk)
        self.zip_file = ZipFile(self.tmp_file)

    def extract(self, item_name: str) -> str:
        """Extract an item named `item_name` to the temporary directory and
        return the path to it.

        """
        return self.zip_file.extract(item_name, path=self.tmp_dir.name)

    def close(self) -> None:
        """Clean up."""
        self.zip_file.close()
        self.tmp_file.close()
        self.tmp_dir.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
