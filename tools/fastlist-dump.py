#!/usr/bin/python

import cPickle as pickle
import sys

if len(sys.argv)<2:
    print "arg: /path/to/dumpfile"
    sys.exit(1)
    
filename=sys.argv[1]

dic=pickle.load(open(filename,'rb'))
for k in sorted(dic.keys()):
   print k