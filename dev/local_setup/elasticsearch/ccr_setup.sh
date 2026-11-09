#!/bin/sh
# Configure es02 as a cross-cluster replication (CCR) follower of es01.
#
# CCR is a Platinum feature, required on both the leader and the follower, so both
# clusters are moved onto the 30-day trial license here. The default `LICENSE=basic` in
# `dev/.env` is left alone, so clusters started without the `ccr` profile stay on basic.
# A cluster can start a trial only once; after it expires, use
# `make docker-compose-down-v` to wipe the volumes and reset it.
set -e
LEADER_URL="http://es01:9200"
FOLLOWER_URL="http://es02:9200"

# Move the cluster at $1 onto the trial license, unless a trial is already active.
start_trial() {
  # Whitespace is stripped so the matches work whether or not the JSON is pretty-printed.
  license=$(curl -sf "$1/_license" | tr -d ' \n')
  if echo "$license" | grep -q '"type":"trial"' \
    && echo "$license" | grep -q '"status":"active"'; then
    echo "Trial license already active on $1"
    return
  fi
  if curl -s -X POST "$1/_license/start_trial?acknowledge=true" | tr -d ' \n' \
    | grep -q '"trial_was_started":true'; then
    echo "Started trial license on $1"
  else
    echo "Could not start a trial license on $1: a trial was already used on this" >&2
    echo "cluster and has expired. Run 'make docker-compose-down-v' to reset it." >&2
    exit 1
  fi
}

echo "--- Starting trial licenses ---"
start_trial "$LEADER_URL"
start_trial "$FOLLOWER_URL"

echo "--- Registering es01 as remote cluster 'leader' on es02 ---"
curl -sf -X PUT "$FOLLOWER_URL/_cluster/settings" \
  -H "Content-Type: application/json" \
  -d '{"persistent": {"cluster.remote.leader.seeds": ["es01:9300"]}}'
echo ""

echo "--- Creating auto-follow pattern for wikipedia indices ---"
# Only indices created on the leader after this point are followed.
#
# The wikipedia indexer builds into `temp-*` and clones the finished index to its real
# name. Followers bootstrap by copying the leader's segments, so excluding the build
# index means they start with the force merged, searchable result. (Refreshes and force
# merges on the leader are not replicated, and the `refresh_interval: -1` of the build
# would otherwise leave followers holding documents they never make searchable.)
curl -sf -X PUT "$FOLLOWER_URL/_ccr/auto_follow/wikipedia" \
  -H "Content-Type: application/json" \
  -d '{
    "remote_cluster": "leader",
    "leader_index_patterns": ["*wiki-*", "*sports-*"],
    "leader_index_exclusion_patterns": ["temp-*"],
    "follow_index_pattern": "{{leader_index}}"
  }'
echo ""

echo "--- Remote cluster info ---"
curl -s "$FOLLOWER_URL/_remote/info"
echo ""
echo "--- Done ---"
