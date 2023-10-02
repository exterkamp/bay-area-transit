#!/bin/bash
set -x

SCRIPT_DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

set -o allexport
source $SCRIPT_DIR/../secrets/api.cfg set
+o allexport

wget -O - https://api.511.org/transit/operators?api_key=$API_KEY > data/operators.json

touch data/LAST_MODIFIED

TIME_STAMP="$(date --rfc-3339=seconds)"
echo "$TIME_STAMP" > data/LAST_MODIFIED