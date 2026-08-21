"""CLI commands for the navigational_suggestions module"""

import typer

from merino.configs import settings as config
from merino.jobs.navigational_suggestions.modes import run_local_mode, run_normal_mode

job_settings = config.jobs.navigational_suggestions

# CLI Options
source_gcp_project_option = typer.Option(
    job_settings.source_gcp_project,
    "--src-gcp-project",
    help="GCP project to use for downloading the domain data",
)

destination_gcp_project_option = typer.Option(
    job_settings.destination_gcp_project,
    "--dst-gcp-project",
    help="GCP project to use to store the domain metadata on GCS for navigational suggestions",
)

destination_gcs_bucket_option = typer.Option(
    job_settings.destination_gcs_bucket,
    "--dst-gcs-bucket",
    help="GCS bucket where the domain metadata for navigational suggestions will be stored",
)

destination_gcs_cdn_hostname_option = typer.Option(
    job_settings.destination_cdn_hostname,
    "--dst-cdn-hostname",
    help="GCS cdn hostname where the domain metadata for navigational suggestions will be stored",
)

force_upload_option = typer.Option(
    job_settings.force_upload,
    "--force-upload",
    help="Upload the domain metadata to GCS bucket even if it already exists there",
)

write_xcom_option = typer.Option(
    False,
    "--write-xcom",
    help="Write job results to Airflow XCom File",
)

min_favicon_width_option = typer.Option(
    job_settings.min_favicon_width,
    "--min-favicon-width",
    help="Minimum width of the domain favicon required for it to be a part of domain metadata",
)

local_mode_option = typer.Option(
    False,
    "--local",
    help="Run in local mode using custom domains instead of BigQuery",
)

local_sample_size_option = typer.Option(
    20,
    "--sample-size",
    help="Number of domains to process in local mode",
)

local_data_option = typer.Option(
    "./local_data",
    "--metrics-dir",
    help="Directory to save local run metrics",
)

monitor_option = typer.Option(
    False,
    "--monitor",
    help="Enable system monitoring during processing",
)

# Create CLI app
navigational_suggestions_cmd = typer.Typer(
    name="navigational-suggestions",
    help="Command for preparing top domain metadata for navigational suggestions",
)


@navigational_suggestions_cmd.command()
def prepare_domain_metadata(
    source_gcp_project: str = source_gcp_project_option,
    destination_gcp_project: str = destination_gcp_project_option,
    destination_gcs_bucket: str = destination_gcs_bucket_option,
    destination_cdn_hostname: str = destination_gcs_cdn_hostname_option,
    force_upload: bool = force_upload_option,
    write_xcom: bool = write_xcom_option,
    min_favicon_width: int = min_favicon_width_option,
    local_mode: bool = local_mode_option,
    local_sample_size: int = local_sample_size_option,
    local_data_dir: str = local_data_option,
    enable_monitoring: bool = monitor_option,
):
    """Prepare domain metadata for navigational suggestions.

    This command can run in two modes:

    1. **Production Mode** (default): Connects to Google Cloud, downloads domains
       from BigQuery, and processes them at scale.

    2. **Local Mode** (--local flag): Uses a GCS emulator and custom domains for
       local development and testing.
    """
    # Unwrap typer.Option objects to get their default values if present
    src_project = getattr(source_gcp_project, "default", source_gcp_project)
    dst_project = getattr(destination_gcp_project, "default", destination_gcp_project)
    dst_bucket = getattr(destination_gcs_bucket, "default", destination_gcs_bucket)
    dst_cdn = getattr(destination_cdn_hostname, "default", destination_cdn_hostname)
    force = getattr(force_upload, "default", force_upload)
    write_x = getattr(write_xcom, "default", write_xcom)
    min_width = getattr(min_favicon_width, "default", min_favicon_width)
    sample_size = getattr(local_sample_size, "default", local_sample_size)
    data_dir = getattr(local_data_dir, "default", local_data_dir)
    monitoring = getattr(enable_monitoring, "default", enable_monitoring)

    # Run the appropriate mode
    if local_mode:
        # Local mode for development and testing
        # Uses fake-gcs-server and custom domains instead of Google Cloud
        run_local_mode(
            local_sample_size=sample_size,
            local_data_dir=data_dir,
            min_favicon_width=min_width,
            enable_monitoring=monitoring,
        )
    else:
        # Normal mode used in production
        # Connects to Google Cloud and processes custom_domains AND domains from BigQuery
        run_normal_mode(
            source_gcp_project=src_project,
            destination_gcp_project=dst_project,
            destination_gcs_bucket=dst_bucket,
            destination_cdn_hostname=dst_cdn,
            force_upload=force,
            write_xcom=write_x,
            min_favicon_width=min_width,
            enable_monitoring=monitoring,
        )
