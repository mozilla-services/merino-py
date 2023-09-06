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

In the Navigational Suggestions provider, a blocklist is used to block specific domains of websites that we do not want to suggest.