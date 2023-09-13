# Updating Remote Settings (RS)

This runbook describes updating the JSON files for  Remote Settings (Firefox Suggest).

Remote Settings is typically updated though a process defined in an external repository.

To be able to make updates to Remote Settings:
1. Become to be a member of the `mozilla-services` organization if you aren't already.
Speak to an admin if you don't yet have access.
2. Speak to a member of the DISCO team for guidance. 
3. Access to the private repository to manage remote settings.
The steps defined in that repo provide you with a template to follow.
4. Walk though the process with a team member that is a 'Remote Settings Operator'.

After being walked through the process, you are a Remote Settings Operator and can complete this process on your own in the future.

## CSV and AMO RS Update Jobs

There are two RS related jobs that can upload a flat CSV file for Pocket, MDN or AMO. This is in the case that you have a CSV file or Google Sheet to upload.  This is a much less common flow, but the process is well documented in the [jobs][1] runbook.

[1]: ./jobs.md#csv-remote-settings-uploader