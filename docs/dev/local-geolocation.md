# Local Geolocation

If you are running Merino locally (e.g. via `make dev`) and need the geolocation
middleware to function, you can enable it by addding the following to your
`development.local.toml`file:

```
[development]
debug = true
dynaconf_merge = true

[development.location]
# Germany IP
client_ip_override = "2a02:d180::1"
# US IP
#client_ip_override = "216.160.83.57"
# UK IP
#client_ip_override = "2.125.160.217"
# Romania IP
#client_ip_override = "2a02:d800::1"
# Sweden IP
#client_ip_override = "89.160.20.113"
```

Whenever you change the `client_ip_override` value, you'll need to restart your
local server.
