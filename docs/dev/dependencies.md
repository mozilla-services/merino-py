# Development Dependencies

This project uses [Poetry][1] for dependency management. While you can use the
vanilla virtualenv to set up the dev environment, we highly recommend to check
out [pyenv][2] and [pyenv-virtualenv][3], as they work nicely with Poetry.
Follow the instructions to install [pyenv][4], [pyenv-virtualenv][5], and
[poetry][6].

Feel free to browse the [pyproject.toml][7] file for a listing of dependencies
and their versions.

Once Poetry is installed, install all the dependencies:

```
$ poetry install
```

Add packages to project via poetry
```
$ poetry add <package_name>
```

After that you should be to run Merino as follows:

```
$ poetry run uvicorn merino.main:app --reload

# Or you can fire up a poetry shell to make it shorter
$ poetry shell
$ uvicorn merino.main:app --reload
```

[1]: https://python-poetry.org/
[2]: https://github.com/pyenv/pyenv
[3]: https://github.com/pyenv/pyenv-virtualenv
[4]: https://github.com/pyenv/pyenv#installation
[5]: https://github.com/pyenv/pyenv-virtualenv#installation
[6]: https://python-poetry.org/docs/#installation
[7]: /pyproject.toml
