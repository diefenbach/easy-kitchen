#!/bin/bash

# Check if version number is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <version>"
    exit 1
fi

VERSION="$1"

docker build --platform=linux/amd64 -t registry.iqpp.de/iqpp/easylist:$VERSION .
docker push registry.iqpp.de/iqpp/easylist:$VERSION
