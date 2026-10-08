"""Redis settings shared by integration tests."""

# Matches production and `dev/docker-compose.yaml`. Pinned so that a cached test result can't
# drift from a newly released `latest`.
REDIS_IMAGE = "redis:7.2"
