#!/bin/bash
# Comprehensive test for query normalization
# Runs 100 queries through both control and treatment paths
# and reports differences.
#
# Usage: bash tests/manual/test_normalization_queries.sh
# Requires: server running on localhost:8000 with normalization enabled

BASE="http://localhost:8000/api/v1/suggest"
VARIANT="client_variants=query_norm_treatment"
QUERIES_FILE="tests/manual/normalization_test_queries.txt"

TOTAL=0
CHANGED=0
ERRORS=0

echo "=== Query Normalization Validation ==="
echo "Reading queries from $QUERIES_FILE"
echo ""

printf "%-40s %-12s %-12s %-8s\n" "QUERY" "CONTROL" "TREATMENT" "CHANGED"
printf "%s\n" "--------------------------------------------------------------------------------"

while IFS= read -r query; do
    [ -z "$query" ] && continue
    TOTAL=$((TOTAL + 1))

    # URL-encode the query
    encoded=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$query'))" 2>/dev/null)

    # Control (no variant)
    control_provider=$(curl -s "${BASE}?q=${encoded}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(d['suggestions'][0]['provider'] if d['suggestions'] else 'none')
" 2>/dev/null)

    # Treatment (with variant)
    treatment_provider=$(curl -s "${BASE}?q=${encoded}&${VARIANT}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(d['suggestions'][0]['provider'] if d['suggestions'] else 'none')
" 2>/dev/null)

    if [ -z "$control_provider" ] || [ -z "$treatment_provider" ]; then
        printf "%-40s %-12s %-12s %-8s\n" "${query:0:40}" "ERROR" "ERROR" ""
        ERRORS=$((ERRORS + 1))
        continue
    fi

    changed=""
    if [ "$control_provider" != "$treatment_provider" ]; then
        changed="***"
        CHANGED=$((CHANGED + 1))
    fi

    printf "%-40s %-12s %-12s %-8s\n" "${query:0:40}" "$control_provider" "$treatment_provider" "$changed"

done < "$QUERIES_FILE"

echo ""
echo "=== Results ==="
echo "Total queries:  $TOTAL"
echo "Changed:        $CHANGED"
echo "Unchanged:      $((TOTAL - CHANGED - ERRORS))"
echo "Errors:         $ERRORS"
