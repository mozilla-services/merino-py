#!/bin/bash

set -e

USAGE="
Usage:

# Quick check against the Merino production endpoint
${0} prod

# Verbose mode will print out the API response
${0} -v prod

# Quick check against the Merino staging endpoint
${0} staging
"

verbose=no

positional=()
while [[ $# -gt 0 ]]; do
  key="${1}"
  case ${key} in
  -v | --verbose)
    verbose=yes
    shift
    ;;
  -h | --help)
    echo "${USAGE}"
    exit 0
    ;;
  *)
    positional+=("$1")
    shift
    ;;
  esac
done

if [[ ${#positional[@]} -eq 0 ]]; then
  echo "${USAGE}"
  exit 1
else
  target=${positional[0]}
fi

if [[ "${target}" == "staging" ]]; then
  endpoint="https://stage.merino.nonprod.cloudops.mozgcp.net/api/v1/suggest"
elif [[ "${target}" == "prod" ]]; then
  endpoint="https://merino.services.mozilla.com/api/v1/suggest"
else
  echo "${USAGE}"
  exit 1
fi

providers=("adm" "wikipedia" "accuweather" "top_picks")
queries=("amazon" "mozilla" "" "reddit")
status=yay
red="\033[31m"
blue="\033[34m"
green="\033[32m"
nocolor="\033[0m"

for i in "${!providers[@]}"; do
  echo
  echo -e "🔍 ${blue}the provider: ${providers[$i]}${nocolor}"
  resp=$(curl -SsL "${endpoint}?q=${queries[i]}&providers=${providers[$i]}")
  len=$(echo "${resp}" | jq '.suggestions | length')

  if [[ ${len} -eq 0 ]]; then
    echo -e "🛬 ${red}Found ${len} suggestion.${nocolor}"
    status=doh
  else
    echo -e "🛬 ${green}Found ${len} suggestion(s).${nocolor}"
  fi

  if [[ "${verbose}" == "yes" ]]; then
    echo "${resp}" | jq .
  fi
done

echo
if [[ "${status}" == "yay" ]]; then
  echo -e "${green}All good!${nocolor}😸"
  exit 0
else
  echo -e "${red}Doh, Merino kept some secrets from us!${nocolor}😿"
  exit 1
fi
