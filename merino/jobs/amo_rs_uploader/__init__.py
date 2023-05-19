"""CLI commands for the amo_rs_uploader module"""
import asyncio
import hashlib
import logging
from typing import Any

import typer

from merino.config import settings as config
from merino.jobs.amo_rs_uploader.remote_settings import RemoteSettings
from merino.providers.amo.addons_data import ADDON_DATA, ADDON_KEYWORDS
from merino.providers.amo.backends.dynamic import DynamicAmoBackend

logger = logging.getLogger(__name__)

job_settings = config.jobs.amo_rs_uploader

# Options
auth_option = typer.Option(
    job_settings.auth,
    "--auth",
    help="Remote settings authorization token",
)

cid_option = typer.Option(
    job_settings.cid,
    "--cid",
    help="Remote settings collection ID",
)

dry_run_option = typer.Option(
    job_settings.dry_run,
    "--dry-run",
    help="Log the records that would be uploaded but don't upload them",
)

server_option = typer.Option(
    job_settings.server,
    "--server",
    help="Remote settings server",
)

workspace_option = typer.Option(
    job_settings.workspace,
    "--workspace",
    help="Remote settings workspace",
)

amo_rs_uploader_cmd = typer.Typer(
    name="amo-rs-uploader",
    help="Command for uploading AMO add-on suggestions to remote settings",
)


@amo_rs_uploader_cmd.command()
def upload(
    auth: str = auth_option,
    dry_run: bool = dry_run_option,
    cid: str = cid_option,
    server: str = server_option,
    workspace: str = workspace_option,
):
    """Upload AMO suggestions to remote settings"""
    asyncio.run(_upload(auth, dry_run, cid, server, workspace))


async def _upload(
    auth: str,
    dry_run: bool,
    cid: str,
    server: str,
    workspace: str,
):
    # Fetch the dynamic addons data from AMO.
    logger.info("Fetching addons data from AMO")
    backend = DynamicAmoBackend(config.amo.dynamic.api_url)
    await backend.initialize_addons()

    # Create suggestion record data for each addon.
    logger.info("Creating data for remote settings")
    records = []
    for addon, dynamic_data in backend.dynamic_data.items():
        # Merge static and dynamic addon data.
        suggestion: dict[str, Any] = ADDON_DATA[addon] | dynamic_data

        # Add keywords.
        suggestion["keywords"] = [kw.lower() for kw in ADDON_KEYWORDS[addon]]

        # Compute the record ID. We can't use addon guids directly because they
        # can contain characters that are invalid in record IDs, so use the hex
        # digest instead.
        m = hashlib.md5(usedforsecurity=False)
        m.update(suggestion["guid"].encode("utf-8"))
        hex_id = m.hexdigest()
        record_id = f"amo_suggestion_{hex_id}"

        records.append(
            {
                "id": record_id,
                "type": "amo_suggestion",
                "amo_suggestion": suggestion,
            }
        )

    if dry_run:
        logger.info(records)
        return

    # Upload the records.
    logger.info(f"Uploading to {server}")
    rs = RemoteSettings(
        auth=auth,
        cid=cid,
        server=server,
        workspace=workspace,
    )
    await rs.upload_records(records)
