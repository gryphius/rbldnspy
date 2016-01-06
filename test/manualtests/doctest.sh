#!/bin/bash
rbldnsd.py -n -e -f -v -w . -b 0.0.0.0/5300 example.doc.test:ip4set:doctest.rbldns

# test: dig 4.3.2.1.example.doc.test. @127.0.0.1 -p 5300 +short
