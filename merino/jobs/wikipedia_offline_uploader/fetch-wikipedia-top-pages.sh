#!/bin/bash

set -e

USAGE="
Usage:

# Fetch the top-viewed pages for the past 28 days
${0}

# Fetch the top-viewed pages for the past N days (e.g. 56)
${0} 56

# Fetch the top-viewed pages for the past 28 days with 30 day time offset
${0} -o 30

# Fetch the top-viewed pages for a specific Wikipedia access method: 'all-access' (default), 'desktop', 'mobile-app', and 'mobile-web'
${0} -a desktop

# Fetch the top-viewed pages for the 'desktop' access method for the past 30 days
${0} -a desktop 30

# Fetch the top-viewed pages and store the results in the 'dump' directory
${0} -d dump
"

# Default time range
days=28
# Default access method
access="all-access"
# Default output directory
dir="wikipedia-top-pages"
# Default day offset
offset=0
# Default language
language="en"

POSTIONAL=()
while [[ $# -gt 0 ]]; do
  key="${1}"
  case ${key} in
  -a | --access)
    access="${2}"
    case "${access}" in
    all-access | desktop | mobile-app | mobile-web)
      shift
      shift
      ;;
    *)
      echo "Unknown access-method: ${access}. Should be one of 'all-access', 'desktop', 'mobile-app', and 'mobile-web'"
      echo "${USAGE}"
      exit 1
      ;;
    esac
    ;;
  -l | --language)
  language="${2}"
  case "${language}" in
  en | fr | de | it | pl)
    shift
    shift
    ;;
  *)
    echo "Unknown access-method: ${access}. Should be one of 'en', 'fr', 'de', 'it', and 'pl'"
    echo "${USAGE}"
    exit 1
    ;;
  esac
  ;;
  -d | --dir)
    dir="${2}"
    shift
    shift
    ;;
  -o | --offset)
    offset="${2}"
    shift
    shift
    if [[ ${offset} -lt 0 ]]; then
      echo "Invalid offset: ${offset}. It should be a non-negative integer."
      echo "${USAGE}"
      exit 1
    fi
    ;;
  -h | --help)
    echo "${USAGE}"
    exit 0
    ;;
  *)
    POSTIONAL+=("$1")
    shift
    ;;
  esac
done

if [[ ${#POSTIONAL[@]} -gt 0 ]]; then
  days=${POSTIONAL[0]}
fi

# The parallel fetch via cURL
ACTION="curl -X GET --create-dirs --output-dir ${dir} -Zs"

url="https://wikimedia.org/api/rest_v1/metrics/pageviews/top/${language}.wikipedia.org/${access}"
i=1
action=${ACTION}

echo "Fetching begins..."
while [[ ${i} -le ${days} ]]; do
  o=$((offset + i))
  d=$(date -v-${o}d '+%Y/%m/%d')
  dd=$(date -v-${o}d '+%Y%m%d')
  action="${action} -o ${language}${dd}.json ${url}/${d}"
  if [[ $((i % 7)) -eq 0 ]]; then
    echo "Issuing a parallel fetch..."
    ${action}
    action=${ACTION}
  fi
  i=$((i + 1))
done

if [[ ${action} != "${ACTION}" ]]; then
  echo "Issuing a parallel fetch..."
  ${action}
fi
echo "Fetching finished."
