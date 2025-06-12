#!/bin/bash

set -e
shopt -s nullglob

USAGE="Usage:

./upload-data.sh [-dh] -e environment {{scheme bearer_token}}

-d indicates dry run, and will print instead of uploading
-e specifies environment, valid values are "prod", "stage", or "dev"
-h print this message and exit
"

function error () {
  echo "$1"
  exit 1
}

while getopts e:dh flag; do
  case $flag in
    d) DRY_RUN=echo ;;
    e) env_flag="${OPTARG}" ;;
    h) error "${USAGE}" ;;
    *) error "Unsupported flag specified" ;;
  esac
done
shift $(($OPTIND - 1))

if [ ! $# -eq 2 ]; then
  echo "Unexpected number of arguments for bearer_token. received ${#}, expected 2"
  error "${USAGE}"
fi

SERVER=''
case $env_flag in
  "prod") SERVER="https://remote-settings.mozilla.org/v1" ;;
  "stage") SERVER="https://remote-settings.allizom.org/v1" ;;
  "dev") SERVER="https://remote-settings-dev.allizom.org/v1" ;;
  *) error "Unsupported value for -e, \"${env_flag}\". Must be \"prod\", \"stage\", or \"dev\"" ;;
esac

AUTH="${1} ${2}"
OFFLINE_CID=quicksuggest-other
WORKSPACE=main-workspace

# get the latest data directory.
RESULT_DIR=rs-data



echo "==== 'Offline' Data"
# Upload the "offline" data. These files are older and thus
# may not have a prefix.


if [ "$OFFLINE_CID" != "" ]
then
  for file in $RESULT_DIR/data-*;
  do
    # NAME=$(basename "${file}" .json)
    NAME=`echo $(basename "${file}" .json) | sed "s/^off-//"`
    echo "Uploading file ${file} to ${NAME}.";
    language=$(echo "$file" | cut -d'-' -f4)
    echo $language
    case "$language" in
      "en") fe="env.locale in ['en-GB', 'en-CA', 'en-US']" ;;
      "fr") fe="env.locale in ['fr', 'fr-FR']" ;;
      "de") fe="env.locale in ['de', 'de-DE']" ;;
      "it") fe="env.locale in ['it', 'it-IT']" ;;
      "pl") fe="env.locale in ['pl', 'pl-PL']" ;;
      *) error "Unsupported language specified" ;;
    esac

    echo "{\"type\": \"wikipedia\", \"filter_expression\": \"${fe}\"}"

    $DRY_RUN curl -X POST ${SERVER}/buckets/${WORKSPACE}/collections/${OFFLINE_CID}/records/${NAME}/attachment \
        -H 'Content-Type:multipart/form-data' \
        -F "attachment=@${file};type=application/json" \
        -F data="{\"type\": \"wikipedia\", \"filter_expression\": \"${fe}\"}" \
        -H "Authorization: ${AUTH}"
    echo
  done
else
  echo "## Skipping (no CID)"
fi

