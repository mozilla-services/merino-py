"""A base skeleton of an uploader. Customize this to fit your needs.

This file is called by declaring it in `./merino/jobs/cli.py`.
```
from merino.jobs.skeleton_uploader import skeleton_uploader_cmd

# ...

# Add the skeleton uploader subcommands.
cli.add_typer(skeleton_uploader_cmd, no_args_is_help=True)

# ...
```

This will include `skeleton_app` as a valid command

```
uv run merino-jobs skeleton_app

"""

import logging
from dynaconf.base import LazySettings

import typer

from merino.configs import settings as config
from merino.configs.app_configs.config_logging import configure_logging

# Remote Settings accepts CSV files as the upload, so we need to convert
# our data into CSV format.
# from merino.jobs.csv_rs_uploader import ChunkedRemoteSettingsSuggestionUploader

# Your provider class will contain the data structures we will want to use
# from merino.providers.suggest.skeleton.addons_data import ADDON_DATA
# from merino.providers.suggest.skeleton.backends import SkeletonBackend

# ## Errors


class GeneralError(BaseException):
    """General purpose error. Specialize accordingly."""

    msg: str = "An error has occurred"

    def __init__(self, msg: str):
        self.msg = msg


class Options:
    """Specify the options for the Skeleton app."""

    # Ensure that your local variables are declared.
    auth: str
    other_option: str

    def __init__(self, base_settings: LazySettings):
        logger.debug("Defining options")
        # """
        self.auth = typer.Option(
            "default",
            "--auth",  # parameter declaration
            help="Remote settings authorization token",
        )
        self.other_option = typer.Option("gorp", "--foo", help="Set something else")
        # """

    def get_command(self) -> typer.Typer:
        """Define the app name and help screen"""
        return typer.Typer(
            name="skeleton_app",
            help="A generic template app demonstrating merino ingestion",
        )


# initialize our settings
# Settings are stored in `/configs` in the `.toml` files.
# You can generally do `config.providers.{YourProject}`. I'm doing this
# because this is a template.

skeleton_settings = getattr(config.providers, "skeleton", None)
"""
# Since we don't have any settings defined, we'll skip this check.
if not skeleton_settings:
    raise GeneralError(
        "Missing project configuration. Did you create it under providers?"
    )
#"""

rs_settings = config.remote_settings
options: Options = Options(base_settings=rs_settings)
skeleton_cmd: typer.Typer = options.get_command()


# Include this in the `cli.py` file to add the command to the general set.
@skeleton_cmd.command()
def upload(
    auth: str = options.auth,
    other: str = options.other_option,
):
    """Sample Upload function that just prints something. This text is used as the command help."""
    logger = logging.getLogger(__name__)
    logger.info(f"Uploading...{auth}")
    # This is a no-op since the skeleton has no meat, so no upload required.
    # Feel free to flesh this out with the things that you need to do.


# This allows you to call this function outside of the `uv` construct.
if __name__ == "__main__":
    # Logging is handled universally by `merino.configs.app_configs.configure_logging`
    # which uses `settings.logging.level` to specify the logging level
    # (DEBUG=10 .. CRITICAL=50)
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting up the skeleton.")
    upload()
