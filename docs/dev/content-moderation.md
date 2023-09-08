# Content Moderation and Blocklists
This summarizes the mechanisms that block sensitive or questionable content in Merino.
Because Merino supports several providers that have a broad range of potential suggestions,
often from different sources, we require the ability to remove certain suggestions from being displayed.

Blocklists in Merino filter content at two distinct phases:
1. Content that is filtered at the _data creation and indexing phase._
   Provider backends serve suggestions to the client based on matching against searched terms.
   This ensures that data that could be sensitive is not available to search against since it is not indexed.
   For instance, the Wikipedia provider filters categories of articles that are tagged with a matching category term in the blocklist.

2. Content that is filtered at _application runtime._
   There are instances where we want to quickly and dynamically add to block lists without re-indexing or running a job.
   In this case, suggestions are compared to a static list in the code that blocks out these suggestions.

## Navigational Suggestions / Top Picks
In the Navigational Suggestions provider, a blocklist is used during data creation to block specific domains of websites that we do not want to suggest.

The blocklist is referenced during data generation of the `top_picks.json` file which is ingested by the provider backend. This ensures specific domains are not indexed for suggestions. The blocklist is loaded and an exact string comparison is made between all second-level domains and the second-level domains defined in the blocklist.

See [nav-suggestions blocklist runbook][1] for more information.

## Wikipedia
The Wikipedia Provider does both title filtering and category filtering. There are also filtering phases at both the indexing job level and at the provider level. Because we may desire to rapidly block a given title of a Wikipedia article, the title blocklist is implemented by the indexer and provider. 

### Indexer
The Wikipedia Indexer Job references a remote blocklist which contains sensitive categories.
At job runtime, the indexer reads the remote blocklist and creates a set which contains article categories that are be excluded from indexing. You may view this file to see common blocked categories, however you do not modify this file.

The indexer also blocks titles that are defined in the `title_blocklist` in the application, which is referenced below.  Any title that matches this blocklist is excluded from indexing. 

### Provider
When queried, the Wikipedia provider reads the `title_blocklist` when creating a `WikipediaSuggestion` and if the query matches a blocked title, the suggestion is not shown to the client. 

We have this feature because the indexing job is not run daily. Therefore, we desire having an option to rapidly add to this list should we need to block a specific article. 

See [wikipedia blocklist runbook][2] for more information.

[1]: ../operations/blocklist-nav-suggestions.md
[2]: ../operations/blocklist-wikipedia.md