# Particle Game Provider

_last updated: 2026-06-08_

## Summary

Particle is a third-party daily crossword-style game intended to be displayed as a widget on New Tab. At a high level, the game is a static website consisting of HTML, JS, CSS, Wasm, and image files hosted in a GCS bucket that is served via an iframe on New Tab.

## Hosting

Particle is hosted in a GCS bucket in our GCP environment. In order to provide both CSP headers and a custom URL, the GCS bucket is fronted by a load balancer. The load balancer has specific CSP headers to ensure data security between New Tab and the iframe containing the static website.

The GCS bucket and related infra configuration is managed in the webservices-infra repo [here](https://github.com/mozilla/webservices-infra/blob/main/merino/tf/modules/resources/gcs.tf).

_Note_ - In addition to the static website files, we also store a JSON manifest in the GCS bucket in order to manage/compare file for updates.

## New Tab Delivery

The URL to the static website is provided to New Tab by the `/games/particle` endpoint. No other data is returned to New Tab.

### Directory Structure

The static website that is Particle is made up of two related filesets (called "channels" by Particle): the daily puzzle files (referred to as "daily") and the underlying engine files (the "runtime").

- root
  - index.html (runtime)
  - assets
    - cluster-images
      - HASH.jpg (daily)
      - HASH.jpg (daily)
    - crossword_engine_bindings_wasm_bg-HASH.wasm (runtime)
    - generated
      - cluster-images.manifest.v1.json (daily)
      - daily-puzzle.v1.json (daily)
    - index-HASH.css (runtime)
    - index-HASH.js (runtime)
    - particle-logo-white-HASH.svg (runtime)
  - runtime-manifest.v1.json

## Infrastructure

To avoid hundreds of pods attempting to update the same Particle files, a dedicated, single-pod Merino deployment run by a K8s cron job is responsible for managing the file update process.

## Updating Particle

The complexity of Particle comes in managing updates to the static website.

### Overview

The daily channel is (or at least _should_ be) updated daily. The runtime channel is updated as needed by Particle, and does not have a predictable update cadence. This means that for any given run of the update process, either 0, 1, or 2 of the channels (daily, runtime) may be updated.

_Note_ All files in a channel must pass SHA validation and be uploaded successfully to GCS to be promoted to "production". If any file fails SHA validation or upload for any reason, the update for that channel is aborted.

### Updating Files

#### File Names

Particle file names may or may not be consistent between updates. This is due to Particle's bundler (Vite, at the time of this writing) changing file names when file contents change for cache-busting purposes.

#### 1. Determine Channels to Update

1. Retrieve the remote manifest JSON from Particle's public HTTP endpoint.
2. Validate the remote manifest JSON according to a JSON schema validator supplied by Particle and hosted in Merino.
   a. If the manifest is invalid, stop processing.
3. Retrieve the manifest JSON in GCS - this describes the current version of Particle we are serving.
4. For each channel (daily, runtime), compare the version value in the remote manifest to the version value in the GCS manifest. If either do _not_ match, mark that channel as needing an update.

#### 2. Update Channel Files

1. Retrieve the list files for the given channel (daily, runtime) from the remote manifest JSON.
2. For each file, download it locally and verify the computed SHA against the SHA specified in the remote manifest JSON.
   a. If the download or SHA validation fails for any file, stop processing the update for the given channel.
3. Upload each channel file to a sub-directory in GCS. (This sub-directory acts as the "green" deployment.)
   a. If any file upload to GCS fails, stop processing the update for the given channel and delete any already-uploaded files for the given channel from the GCS bucket sub-folder.
   b. To keep the URL to the static website consistent across updates, the single HTML file for the game requires special processing. It must be renamed to `index.html` prior to upload. (Runtime channel update only.)

#### 3. Deploy Updated Files

_Note_ GCS offers strong/immediate consistency on file uploads.

Once any channels flagged for update are successfully updloaded to the sub-folder in GCS, all files in the sub-folder are moved into the GCS bucket root. Any files with name collisions will be overridden. At this point, the new version of the game is "deployed". (Though old files may still exist in the GCS bucket root.)

#### 4. Delete Old Files

As file names are _sometimes_ consistent between updates, a bit of extra calculation needs to happen to delete old files:

1. For each channel being updated, compare the list of files for that channel from both the old manifest that already exists in GCS and the list of files for that channel in the new manifest.
2. From these two lists, create a list of files that exist in the old manifest but do _not_ exist in the new manifest ("where not in", basically). This will provide a single list of files that should be deleted for the given channel.
3. Delete each file in this list from the GCS bucket root.

#### 5. Update Manifest

Upload the new manifest JSON file to the GCS bucket root, replacing the existing manifest JSON.
