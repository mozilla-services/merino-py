"""Unit tests for the wikipedia article blocklist CLI commands."""

import pytest

from merino.jobs.wikipedia_article_blocklist import generate

MODULE = "merino.jobs.wikipedia_article_blocklist"


@pytest.fixture(name="collaborators")
def fixture_collaborators(mocker):
    """Replace everything the CLI command constructs or calls out to."""
    generator = mocker.patch(f"{MODULE}.ArticleBlocklistGenerator")
    generator.return_value.generate.return_value = "title,qid\r\nBlocked,Q1\r\n"
    datetime = mocker.patch(f"{MODULE}.datetime")
    datetime.now.return_value.strftime.return_value = "20260316120000"

    return {
        "file_manager": mocker.patch(f"{MODULE}.FileManager"),
        "generator": generator,
        "storage_client": mocker.patch(f"{MODULE}.initialize_storage_client"),
        "create_blocklist": mocker.patch(f"{MODULE}.create_blocklist", return_value={"meme"}),
    }


def _generate(**overrides):
    """Invoke the generate command with every option supplied explicitly.

    Typer's defaults are `OptionInfo` objects, so calling the function directly
    requires passing real values.
    """
    kwargs = {
        "blocklist_file_url": "http://blocklist/cats.csv",
        "total_docs": 100,
        "gcs_path": "bucket/prefix",
        "gcp_project": "a-project",
        "gcs_storage_bucket": "storage-bucket",
        "gcs_storage_project": "storage-project",
    }
    kwargs.update(overrides)
    return generate(**kwargs)


def test_generate_builds_the_generator_for_english_and_runs_it(collaborators):
    """Verify the command reads the English export and starts generating."""
    _generate()

    collaborators["create_blocklist"].assert_called_once_with("http://blocklist/cats.csv")
    collaborators["file_manager"].assert_called_once_with("bucket/prefix", "a-project", "", "en")
    collaborators["generator"].assert_called_once_with(
        {"meme"}, collaborators["file_manager"].return_value
    )
    collaborators["generator"].return_value.generate.assert_called_once_with(100)


def test_generate_uploads_timestamped_csv_and_copies_it_to_latest(collaborators):
    """Verify the CSV is uploaded once, then copied to the latest destination."""
    _generate()

    prefix = "suggest-merino-exports/wikipedia/article_blocklist"
    collaborators["storage_client"].assert_called_once_with(
        destination_gcp_project="storage-project"
    )
    bucket = collaborators["storage_client"].return_value.bucket
    bucket.assert_called_once_with("storage-bucket")
    bucket.return_value.blob.assert_called_once_with(f"{prefix}/20260316120000.csv")
    blob = bucket.return_value.blob.return_value
    blob.upload_from_string.assert_called_once_with(
        "title,qid\r\nBlocked,Q1\r\n", content_type="text/csv"
    )
    blob.make_public.assert_not_called()
    bucket.return_value.copy_blob.assert_called_once_with(
        blob, bucket.return_value, f"{prefix}/latest.csv"
    )


def test_generate_raises_when_upload_fails(collaborators):
    """Verify an upload failure fails the job instead of being swallowed."""
    bucket = collaborators["storage_client"].return_value.bucket.return_value
    bucket.blob.return_value.upload_from_string.side_effect = Exception("forbidden")

    with pytest.raises(Exception, match="forbidden"):
        _generate()

    bucket.copy_blob.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [{"gcs_storage_bucket": ""}, {"gcs_storage_project": ""}],
    ids=["missing_bucket", "missing_project"],
)
def test_generate_requires_the_storage_destination(collaborators, overrides):
    """Verify a missing destination fails before the export is scanned."""
    with pytest.raises(ValueError, match="GCS storage bucket and project must be set"):
        _generate(**overrides)

    collaborators["create_blocklist"].assert_not_called()
    collaborators["generator"].return_value.generate.assert_not_called()
