#!/bin/bash

# Languages we want retrieve
languages=("en" "fr" "de" "it" "pl")

for language in "${languages[@]}"; do
  echo "Fetching wikipedia articles for $language"
  ./fetch-wikipedia-top-pages.sh "90" -l "$language" | ./top_n_by_frequency.py 8000 "$language" | ./make_suggestions.py 7000 "$language"
done
