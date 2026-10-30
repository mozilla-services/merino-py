#!/bin/sh
# Configure es02 as a cross-cluster replication (CCR) follower of es01.
#
# CCR is a Platinum feature, so both clusters are moved onto the 30-day trial license.
# Once it expires, `make docker-compose-down-v` wipes the volumes and resets it.
set -e
LEADER_URL="http://es01:9200"
FOLLOWER_URL="http://es02:9200"

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
