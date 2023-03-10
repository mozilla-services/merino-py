"""Util module to read block list for Dynamic Wikipedia provider."""
import json


def read_block_list(file_path: str) -> list[str]:
    """Read manual block list of blocked titles for manual content moderation."""
    with open(file_path, mode="r") as block_list:
        return [title.strip() for title in json.load(block_list)]
