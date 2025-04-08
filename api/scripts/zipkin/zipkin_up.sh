#!/bin/sh

thisdir=`dirname $( realpath "$0"  )`

pushd $thisdir

docker compose -f docker-compose.yml up --wait

popd
