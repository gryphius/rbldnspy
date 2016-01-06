#!/bin/bash
if [ "$1" == "" ] ; then
  echo "usage: fast-delist.sh port value"
  exit 1
fi

magic='@!'
echo "${magic}${2}" > /dev/udp/127.0.0.1/$1