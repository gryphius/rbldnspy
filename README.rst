rbldnspy is a blacklist daemon like rbldnsd.

to combat the current replication lag of standard rbl setups , there is a "fast list" functionality to quickly insert new listings over a simple network UDP packet
these fast list packets expire after a short time in the assumption they're now in the standard zone file

usage and zonefile format are similar to rbldnsd
 

Install
-------
Dependencies: dnslib , dateutils



.. image:: https://travis-ci.org/gryphius/rbldnspy.svg?branch=master
    :target: https://travis-ci.org/gryphius/rbldnspy
    :alt: Build status