# Content Moderation
Merino is capable of filtering and blocking of sensitive content.

## Dynamic Wikipedia Provider

### Wikipedia Title Block List
Located in `/merino/utils/block_list.py`

This block list is used during the indexing job for Dynamic Wikipedia as well as at the
provider level for ensuring suggestions of a given title are not returned to the client.
This allows for granular control or ad-hoc updates of titles we wish to ignore.

*NOTE:* In adding to the block list, ensure the title field is added as it appears
with correct spacing between the words. Membership checks of the block list are not
case sensitive and any underscores in the titles should instead be spaces.
In adding to the list, one should attempt to add the title as it appears in Wikipedia.