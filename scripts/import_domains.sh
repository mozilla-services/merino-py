#!/bin/bash

# Check if a CSV file was provided
if [ $# -ne 1 ]; then
    echo "Usage: $0 <csv_file>"
    echo "Example: $0 domain_list.csv"
    exit 1
fi

# Get the CSV file from command line argument
CSV_FILE="$1"
EXISTING_PY_FILE="merino/jobs/navigational_suggestions/custom_domains.py"
TEMP_OUTPUT_FILE=$(mktemp)
SORTED_DOMAINS_FILE=$(mktemp)
CSV_DOMAINS_FILE=$(mktemp)

# Check if the files exist
if [ ! -f "$CSV_FILE" ]; then
    echo "Error: CSV file $CSV_FILE does not exist."
    exit 1
fi

if [ ! -f "$EXISTING_PY_FILE" ]; then
    echo "Error: Python file $EXISTING_PY_FILE does not exist."
    exit 1
fi

# Extract existing domains from the file (excluding docstring)
grep -o '"[^"]*",' "$EXISTING_PY_FILE" | grep -v '"""' | sed 's/"//g; s/,//g' > "$SORTED_DOMAINS_FILE"
ORIGINAL_COUNT=$(wc -l < "$SORTED_DOMAINS_FILE" | xargs)

# Extract domains from CSV and clean them
tail -n +2 "$CSV_FILE" | cut -d, -f1 | sort | uniq | while read domain; do
    # Skip empty domains
    if [ -n "$domain" ]; then
        # Remove any quotes and trim whitespace
        clean_domain=$(echo "$domain" | tr -d '"' | xargs)
        echo "$clean_domain" >> "$CSV_DOMAINS_FILE"
    fi
done

# Count CSV domains
CSV_DOMAIN_COUNT=$(wc -l < "$CSV_DOMAINS_FILE" | xargs)

# Count how many were actually new (not in the original file)
ACTUALLY_ADDED=0
while read domain; do
    if ! grep -q "^$domain$" "$SORTED_DOMAINS_FILE"; then
        echo "$domain" >> "$SORTED_DOMAINS_FILE"
        ACTUALLY_ADDED=$((ACTUALLY_ADDED + 1))
    fi
done < "$CSV_DOMAINS_FILE"

# Sort all domains alphabetically
LC_ALL=C sort -u -o "$SORTED_DOMAINS_FILE" "$SORTED_DOMAINS_FILE"
FINAL_COUNT=$(wc -l < "$SORTED_DOMAINS_FILE" | xargs)

# Create the output file with docstring and sorted domains
cat > "$TEMP_OUTPUT_FILE" << 'EOF'
"""Custom domains data for navigational suggestions"""

CUSTOM_DOMAINS: list[str] = [
EOF

# Add sorted domains
while read domain; do
    if [ -n "$domain" ]; then
        echo "    \"$domain\"," >> "$TEMP_OUTPUT_FILE"
    fi
done < "$SORTED_DOMAINS_FILE"

# Close the list
echo "]" >> "$TEMP_OUTPUT_FILE"

# Replace the original file with the new one
mv "$TEMP_OUTPUT_FILE" "$EXISTING_PY_FILE"

# Clean up
rm "$SORTED_DOMAINS_FILE" "$CSV_DOMAINS_FILE" 2>/dev/null

echo "Domain merge complete:"
echo "- Original domains in file: $ORIGINAL_COUNT"
echo "- Domains in CSV file: $CSV_DOMAIN_COUNT"
echo "- New domains added: $ACTUALLY_ADDED"
echo "- Total domains after merge: $FINAL_COUNT"
echo ""
echo "File updated: $EXISTING_PY_FILE"
