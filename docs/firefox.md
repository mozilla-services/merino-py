# Configuring Firefox and Merino Environments

Merino has been enabled by default in Firefox. Though, you will need to enable
the data sharing for Firefox Suggest to fully enable the feature. To enable it,
type `about:config` in the URL bar set the Firefox preference
`browser.urlbar.quicksuggest.dataCollection.enabled` to `true`. By default,
Merino will connect to the production environments. This is controlled with the
`browser.urlbar.merino.endpointURL` preference. See below for other options.

You can also query any of the endpoint URLs below with something like:

```sh
curl 'https://stagepy.merino.nonprod.cloudops.mozgcp.net/api/v1/suggest?q=your+query'
```

## Environments

### Production

*Endpoint URL*: <https://merinopy.services.mozilla.com/api/v1/suggest>

The primary environment for end users. Firefox is configured to use this by
default.

### Stage

*Endpoint URL*: <https://stagepy.merino.nonprod.cloudops.mozgcp.net/api/v1/suggest>

This environment is used for manual and load testing of the server. It is not
guaranteed to be stable or available. It is used as a part of the deploy process
to verify new releases before they got to production.
