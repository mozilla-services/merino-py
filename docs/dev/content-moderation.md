# Content Moderation
Merino has many features that enable the filtering and blocking of sensitive content.

## Dynamic Wikipedia Provider

### Manual Block List
Located in `/dev/wiki_provider_block_list.txt`

This block list is used during the indexing job for dynamic wiki as well as at the provider 
level for ensuring suggestions of a given title are not returned to the client.
This allows for granular control or ad-hoc updates of titles we wish to ignore.

*NOTE:* In adding to the block list, ensure the title field is added as it appears
in the wiki url, respecting case sensitivity. Typically, the titles have the
first character capitalized, are separated by underscores with subsequent
words capitalized.