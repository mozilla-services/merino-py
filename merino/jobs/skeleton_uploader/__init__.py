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

from merino.configs import settings
from merino.configs.app_configs.config_logging import configure_logging

# Remote Settings accepts CSV files as the upload, so we need to convert
# our data into CSV format.
# from merino.jobs.csv_rs_uploader import ChunkedRemoteSettingsSuggestionUploader

# Your provider class will contain the data structures we will want to use
# from merino.providers.suggest.skeleton.addons_data import ADDON_DATA
# from merino.providers.suggest.skeleton.backends import SkeletonBackend

# ## Errors


class SkeletonError(BaseException):
    """General purpose error. Specialize accordingly."""

    msg: str = "An error has occurred"

    def __init__(self, msg: str):
        self.msg = msg


class SkeletonUploader:
    """Perform the upload functions required for your Skeleton app.

    Since this does not have to go through the Web interface, you do
    not need to root objects to things like BaseModel.
    """

    # Ensure that your local variables are declared.
    auth: str
    logger: logging.Logger

    def __init__(self, auth: str | None):
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Defining options")
        self.auth = auth or "NoAuth"

    def load_data(self) -> bool:
        """Pretend to do things like fetch and store the data"""
        self.logger.info(f"Uploading...{self.auth}")
        # Get the data store reference
        # Fetch the data from the provider
        # Format it for storage
        # Store the data
        # Go have ice cream
        return True


# initialize our settings
# Settings are stored in `/configs` in the `.toml` files.
# You can generally do `config.providers.{YourProject}`. I'm doing this
# because this is a template.

skeleton_settings = getattr(settings.providers, "skeleton", {})
"""
# Since we don't have any settings defined, we'll skip this check.
if not skeleton_settings:
    raise GeneralError(
        "Missing project configuration. Did you create it under providers?"
    )
#"""

skeleton_cmd: typer.Typer = typer.Typer(
    name="skeleton_app",
    help="A generic template app demonstrating merino ingestion",
)


# Include this in the `cli.py` file to add the command to the general set.
@skeleton_cmd.command()
def upload(
    auth: str | None = skeleton_settings.get("auth"),
):
    """Sample Upload function that just prints something. This text is used as the command help."""
    # This is a no-op since the skeleton has no meat, so no upload required.
    # Feel free to flesh this out with the things that you need to do.
    # It's generally frowned upon to pass the LazySettings to the classes.
    uploader = SkeletonUploader(auth=auth)
    uploader.load_data()


# This allows you to call this function outside of the `uv` construct.
if __name__ == "__main__":  # pragma: no cover
    # Logging is handled universally by `merino.configs.app_configs.configure_logging`
    # which uses `settings.logging.level` to specify the logging level
    # (DEBUG=10 .. CRITICAL=50)
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting up the skeleton.")
    upload()
