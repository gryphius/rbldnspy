import unittest
import unittestsetup

from rbldnsd import RBLDNSD_options, RBLDNSD
from tempfile import mkstemp
import os
from rbldnspy.tools import ipreverse

FAILNOTIMPLEMENTED=False

class ManPageTest(unittest.TestCase):
    """Tests examples from the manpage"""
    def setUp(self):
        self.defaultopts=RBLDNSD_options()
        self.rbldnsd=RBLDNSD(self.defaultopts)
        self.tempfiles=[]
        
    def _set_zone(self,datasetcontent,dntype="ip4set",zonename="testsuite.example"):
        (fd,name)=mkstemp(".rbldns", text=True)
        handle=os.fdopen(fd,'w')
        handle.write(datasetcontent)
        handle.close()
        newopts=RBLDNSD_options()
        zones={}
        l=[(dntype,name),]
        zones[zonename]=l
        newopts.zones=zones
        self.rbldnsd.options=newopts
        self.rbldnsd.load_zones(autoreloader=False)
        self.tempfiles.append(name)
        return name
    
    def lookup_domain(self,q,zone="testsuite.example",t='A'):
        """perform a lookup. use t=None to get all available data as dict
        if more than one result is available, returns the whole list of dicts and t is ignored
        
        """
        q="%s.%s"%(q,zone)
        dct=self.rbldnsd.lookup(q)
        assert type(dct)==dict,"Expected dict, got %s : %s"%(type(res),res)
        res=dct['results']
        if t!=None:
            t=t.upper()
            
            
        if t=='SOA':
            return dct['SOA']
        
        if t=='NS':
            return dct['NS']
        
        if len(res)==0:
            return None
        
        if len(res)>1:
            return res
        
        #get first item
        res=res[0]
        if res==None:
            return None
        
        if t==None:
            return res
        elif t not in res:
            return None
        return res[t]
    
    def lookup_ip(self,q,zone="testsuite.example",t='A'):
        q=ipreverse(q)
        return self.lookup_domain(q, zone, t)
    
    def tearDown(self):
        for filename in self.tempfiles:
            os.unlink(filename)
    
    
    def test_simple(self):
        """test to test the tests :-) """
        dnset="""#simple test
127.0.0.2
127.0.0.3
127.0.0.4
"""
        self._set_zone(dnset)
        self.assertEqual(self.lookup_ip('127.0.0.5'), None)
        self.assertEqual(self.lookup_ip('127.0.0.4'), '127.0.0.2')

    def test_soa(self):
        """
        $SOA ttl origindn persondn serial refresh retry expire minttl
    Specifies SOA (Start Of Authority) record for all zones using this dataset. Only first SOA record is interpreted. 
    This is the only way to specify SOA - by default, rbldnsd will not add any SOA record into answers, 
    and will REFUSE to answer to certain queries (notably, SOA query to zone's base domain name).
     It is recommended, but not mandatory to specify SOA record for every zone. 
     If no SOA is given, negative replies will not be cacheable by caching nameservers. 
     Only one, first $SOA line is recognized in every dataset (all subsequent
      $SOA lines encountered in the same dataset are silently ignored). 
      When constructing a zone, SOA will be taken from first dataset where $SOA line is found,
       in an order as specified in command line, subsequent $SOA lines, if any, are ignored. 
       This way, one may overwrite $SOA found in 3rd party data by 
       prepending small local file to the dataset in question, listing it before any other files. 
If serial value specified is zero, timestamp of most recent
    modified file will be substituted as serial. 
If ttl field is zero, default ttl (-t option or last $TTL
    value, see below) will be used. 
All time fields (ttl, refresh, retry, expire, minttl
"""
        self._set_zone("""
#$SOA 7m localhost. hostmaster.localhost. 1211140933 1h 10m 5d 30s
#$SOA 5m bla. blah.blah. 1211140935 2h 120m 1d 2s

        """)
        res=self.rbldnsd.lookup("testsuite.example")
        self.assertTrue(res!=None and 'SOA' in res,'did not get a SOA response')
        self.assertTrue('SOATTL' in res)
        self.assertEquals(res['SOATTL'],420,'wrong SOA TTL')
        soa=res['SOA']
        self.assertTrue(len(soa)==7,'SOA did not return expected 7 parts')
        origindn,persondn,serial,refresh,retry,expire,minttl=soa
        self.assertEquals(origindn,'localhost.')
        self.assertEquals(persondn,'hostmaster.localhost.')
        self.assertEquals(serial,1211140933)
        self.assertEquals(refresh,3600)
        self.assertEquals(retry,600)
        self.assertEquals(expire,432000)
        self.assertEquals(minttl,30)
        
        #TODO: TEST if soa is in additional records?
    
    def test_ns(self):
        """
        $NS ttl nameserverdn nameserverdn...
    Specifies NS (Name Server) records for all zones using this dataset. Only first $NS line in a dataset is recognized, 
    all subsequent lines are silently ignored. When constructing a zone from several datasets,
     rbldnsd uses nameservers from $NS line in only first dataset where $NS line is given, 
     in command-line order, just like for $SOA record. Only first 32 namservers are recognized.
      Individual nameserver(s) may be prefixed with a minus sign (-), which means this single nameserver
       will be ignored by rbldnsd. This is useful to temporary comment out one nameserver 
       entry without removing it from the list. If ttl is zero, default ttl will be used.
        The list of NS records, just like $SOA value, are taken from the first data file in a 
        dataset where the $NS line is found, subsequent $NS lines, if any, are ignored. 
    """
        self._set_zone("""
$NS 900 ns1.rbldnsd.py -ns0.rbldnsd.py ns2.rbldnsd.py
$NS 700 ns5.example.com ns6.example.com

        """)
        
        #check if ns' are loaded
        zone=self.rbldnsd.zones['testsuite.example']
        nslist=zone.datasets[0].ns
        self.assertIn('ns1.rbldnsd.py', nslist)
        self.assertIn('ns2.rbldnsd.py', nslist)
        
        res=self.rbldnsd.lookup("testsuite.example")
        self.assertTrue(res!=None and 'NS' in res,'did not get a NS response')
        self.assertTrue('NSTTL' in res)
        self.assertEquals(res['NSTTL'],900,'wrong NS TTL')
        ns=res['NS']
        
        self.assertIn('ns1.rbldnsd.py', ns)
        self.assertIn('ns2.rbldnsd.py', ns)
        self.assertNotIn("ns0.rbldnsd.py", ns)
        self.assertNotIn("-ns0.rbldnsd.py", ns)
        self.assertNotIn("ns5.example.com", ns)
        self.assertNotIn("ns6.example.com", ns)

    
    def test_ttl(self):
        """
        $TTL time-to-live
    Specifies TTL (time-to-live) value for all records in current dataset. See also -t option. 
    $TTL special overrides -t value on a per-dataset basis. 
        """
        if FAILNOTIMPLEMENTED:
            self.fail("test not implemented")
    
    def test_timstamp(self):
        """
        $TIMESTAMP dstamp [expires]
    (experimental) Specifies the data timestamp dstamp when the data has been generated, and optionally when it will expire. The timestamps are in form yyyy:mm:dd[:hh[:mi[:ss]]], where yyyy is the year like 2005, mm is the month number (01..12), dd is the month day number (01..31), hh is hour (00..23), mi and ss are minutes and secounds (00.59); hours, minutes and secounds are optional and defaults to 0; the delimiters (either colon or dash may be used) are optional too, but are allowed for readability. Also, single zero (0) or dash (-) may be used as dstamp and/or expires, indicating the value is not given. expires may also be specified as +rel, where rel is a time specification (probably with suffix like s, m, h, d) as an offset to dstamp. rbldnsd compares dstamp with current timestamp and refuses to load the file if dstamp specifies time in the future. And if expires is specified, rbldnsd will refuse to service requests for that data if current time is greather than the value specified in expires field. 
Note that
    rbldnsd will check the data expiry time every time it checks for data file updates (when receiving SIGHUP signal or every -c interval). If automatic data reload timer (-c option) is disabled, zones will not be exipired automatically. 
        """
        if FAILNOTIMPLEMENTED:
            self.fail("test not implemented")
    
    
    def test_maxrange4(self):
        """
        $MAXRANGE4 range-size
    Specifies maximum size of IPv4 range allowed for IPv4-based datasets. If an entry covers more IP addresses than range-size, it will be ignored (and a warning will be logged).
     range-size may be specified as a number of hosts, like 256, or as network prefix lenght, 
     like /24 (the two are the same):

    $MAXRANGE4 /24
    $MAXRANGE4 256

    This constraint is active for a dataset it is specified in, and can be owerwritten (by subsequent $MAXRANGE statement)
     by a smaller value, but can not be increased. 
        
        """
        self._set_zone("""
10.0.0.0/8    #should be listed
$MAXRANGE4 /16
11.0.0.0/16  #should be listed
12.0.0.0/8   #should not be listed
$MAXRANGE4 256
13.0.0.0/16 #should not be listed
13.0.0.0/24 # should be listed
        """)
        self.assertEqual(self.lookup_ip('10.255.255.255'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('11.0.255.255'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('12.0.255.255'), None)
        self.assertEqual(self.lookup_ip('13.0.1.1'), None)
        self.assertEqual(self.lookup_ip('13.0.0.255'), '127.0.0.2')
        
        
        
    
    def test_variable(self):
        """
        $n text
    (n is a single digit). Specifies a substitution variable for use as $n placeholders (the $n entries are ignored in generic daaset). 
    See section "Resulting A values and TXT templates" below for description and usage examples. 
        """
        self._set_zone("""
$0    one
$1    two
$2    three
$3    four
$4    five
$5    six
$6    seven
$7    eight
$8    nine
$9    ten

127.0.0.2 $0 $1 $2 $3 $4 $5 $6 $7 $8 $9
        """)
        self.assertEqual(self.lookup_ip('127.0.0.2',t='txt'), 'one two three four five six seven eight nine ten')
        
    
    
    
    def test_ip4set_dataset(self):
        """
        ip4set Dataset

A set of IP addresses or CIDR address ranges, together with A and TXT resulting values. IP addresses are specified one per line, by an IP address prefix (initial octets), complete IP address, CIDR range, or IP prefix range (two IP prefixes or complete addresses delimited by a dash, inclusive). 
        """
     
#        """
#        Examples, to specify 127.0.0.0/24:
#        
#        127.0.0.0/24
#        127.0.0
#        127/24
#        127-127.0.0
#        127.0.0.0-127.0.0.255
#        127.0.0.1-255
#        """
        self._set_zone("127.0.0.0/24\n")
        self.assertEqual(self.lookup_ip('127.0.0.10'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.1.0'), None)
        
        self._set_zone("127.0.0\n")
        self.assertEqual(self.lookup_ip('127.0.0.255'), '127.0.0.2')
        
        self._set_zone("127/24\n")
        self.assertEqual(self.lookup_ip('127.0.0.1'), '127.0.0.2')
        
        self._set_zone("127-127.0.0\n")
        self.assertEqual(self.lookup_ip('127.0.0.13'), '127.0.0.2')
        
        self._set_zone("127.0.0.0-127.0.0.255\n")
        self.assertEqual(self.lookup_ip('127.0.0.37'), '127.0.0.2')
        
        self._set_zone("127.0.0.1-255\n")
        self.assertEqual(self.lookup_ip('127.0.0.255'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.0.0'), None)
        
        #"""
        #to specify 127.16.0.0-127.31.255.255:
        #
        #127.16.0.0-127.31.255.255
        #127.16.0-127.31.255
        #127.16-127.31
        #127.16-31
        #127.16.0.0/12
        #127.16.0/12
        #127.16/12
        
        self._set_zone("127.16.0.0-127.31.255.255\n")
        self.assertEqual(self.lookup_ip('127.24.3.23'), '127.0.0.2')
        
        self._set_zone("127.16.0-127.31.255\n")
        self.assertEqual(self.lookup_ip('127.31.255.255'), '127.0.0.2')
        
        self._set_zone("127.16-127.31\n")
        self.assertEqual(self.lookup_ip('127.24.3.23'), '127.0.0.2')
        
        self._set_zone("127.16-31\n")
        self.assertEqual(self.lookup_ip('127.24.3.23'), '127.0.0.2')
        
        self._set_zone("127.16.0.0/12\n")
        self.assertEqual(self.lookup_ip('127.24.3.23'), '127.0.0.2')
        
        self._set_zone("127.16.0/12\n")
        self.assertEqual(self.lookup_ip('127.24.3.23'), '127.0.0.2')
        
        self._set_zone("127.16/12\n")
        self.assertEqual(self.lookup_ip('127.24.3.23'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.32.0.0'), None)
        
        
#
#Note that in prefix range, last boundary is completed with all-ones (255), not all-zeros line 
#with first boundary and a prefix alone. 
#In prefix ranges, if last boundary is only one octet (127.16-31), 
#it is treated as "suffix", as value of last specified octet of the first boundary prefix 


        self._set_zone("127.16-31\n")
        self.assertEqual(self.lookup_ip('127.15.255.255'), None)
        self.assertEqual(self.lookup_ip('127.16.0.0'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.16.31.255'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.16.32.0'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.31.255.255'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.32.0.0'), None)
        
#(127.16.0-31 is treated as 127.16.0.0-127.16.31.255, i.e. 127.16.0.0/19). 
        self._set_zone("127.16.0-31\n")       
        self.assertEqual(self.lookup_ip('127.15.255.255'), None)
        self.assertEqual(self.lookup_ip('127.16.0.0'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.16.31.255'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.16.32.0'), None)
        
        
#
#After an IP address range, A and TXT values for a given entry may be specified. 
#If none given, default values in current scope (see below) applies. 
#If a value starts with a colon, it is interpreted as a pair of A record and TXT template, 
#delimited by colon (:127.0.0.2:This entry is listed). If a value does not start with a colon, 
#it is interpreted as TXT template only, with A record defaulting to the 
#default A value in current scope.
#

        #IP address range may be followed by a comment char (either hash character (#) or semicolon (;)), e.g.:
#
#127/8 ; loopback network
#
#In this case all characters up to the end of line are ignored, and default A and TXT values will be used for this IP range.
#


        self._set_zone("""
1.2.3.2 # comment here
:4:whassup
1.2.3.5 :7
1.2.3.6 :8:hello world 
1.2.3.7 pick me! 
1.2.3.4 ; comment here!
        """)
        self.assertEqual(self.lookup_ip('1.2.3.2'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('1.2.3.3'), None)
        self.assertEqual(self.lookup_ip('1.2.3.4'), '127.0.0.4')
        self.assertEqual(self.lookup_ip('1.2.3.5'), '127.0.0.7')
        self.assertEqual(self.lookup_ip('1.2.3.6'), '127.0.0.8')
        self.assertEqual(self.lookup_ip('1.2.3.7'), '127.0.0.4')
        
        
        self.assertEqual(self.lookup_ip('1.2.3.2', t='txt'), None)
        self.assertEqual(self.lookup_ip('1.2.3.3', t='txt'), None)
        self.assertEqual(self.lookup_ip('1.2.3.4', t='txt'), 'whassup')
        self.assertEqual(self.lookup_ip('1.2.3.5', t='txt'), 'whassup')
        self.assertEqual(self.lookup_ip('1.2.3.6', t='txt'), 'hello world')
        self.assertEqual(self.lookup_ip('1.2.3.7', t='txt'), 'pick me!')



#Every IP address that fits within any of specified ranges is "listed", and rbldnsd will respond 
#to reverse queries against it within specified zone with positive results. 
#In contrast, if an entry starts with an exclamation sign (!), this is an exclusion entry, 
#i.e. corresponding address range is excluded from being listed (and any value for this record 
#is ignored). This may be used to specify large range except some individual addresses, in a compact form.
#

        self._set_zone("""
!127.0.0.42
127.0.0.0/24
        """)
        
        self.assertEqual(self.lookup_ip('127.0.0.41'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.0.42'), None)

#If a line starts with a colon (:), this line specifies the default A value and TXT template to return (see below) for all subsequent 
#entries up to end of current file. If no default entry specified, and no value specified for a 
#given record, rbldnsd will return 127.0.0.2 for matching A queries and no record for matching TXT queries.
# If TXT record template is specified and contains occurences of of dollar sign ($), every such
# occurence is replaced with an IP address in question, so singe TXT template may be used to e.g.
# refer to a webpage for an additional information for a specific IP address. 
#        
#        """

        self._set_zone("""
:2:$ is listed!
127.0.0.0/24
        """)
        self.assertEqual(self.lookup_ip('127.0.0.42',t='txt'), "127.0.0.42 is listed!")
    
    
    def test_ip4trie_dataset(self):
        """
        Set of IP4 CIDR ranges with corresponding (A, TXT) values. Similar to ip4set, but uses different internal 
        representation (implemented as a patricia trie), accepts CIDR ranges only (not a.b.c.d-e.f.g.h),
         allows to specify only one value per CIDR range, and returns only one, most close matching, 
         entry on queries. Exclusions are supported too. This dataset is not memory-efficient to store many 
         single IP addresses, but it is ok to use it to store many possible wide CIDR ranges. 
        """
        if FAILNOTIMPLEMENTED:
            self.fail("test not implemented")
    
    def test_ip4tset_dataset(self):
        """
        "trivial" ip4set: a set of single IP addresses (one per line), with the same A+TXT template. This dataset type is more efficient than ip4set (in both memory usage and access times), but have obvious limitation. It is intended for DNSBLs like DSBL.org, ORDB.org and similar, where each entry uses the same default A+TXT template. This dataset uses only half a memory for the same list of IP addresses compared to ip4set. 
        """
        if FAILNOTIMPLEMENTED:
            self.fail("test not implemented")
    
    
    def test_dnset_dataset(self):
        if FAILNOTIMPLEMENTED:
            self.fail("test not implemented")
    
    def test_generic_dataset(self):
        if FAILNOTIMPLEMENTED:
            self.fail("test not implemented")
    
    def test_combined_dataset(self):
        if FAILNOTIMPLEMENTED:
            self.fail("test not implemented")
    
    def test_default_template(self):
#        """
#      :127.0.0.2:Blacklisted: http://example.com/bl?$
#
#If a line starts with a colon, it specifies default A and TXT for all subsequent entries in this dataset. 
#
        self._set_zone("""
:127.0.0.2:Blacklisted: http://example.com/bl?$
127.0.0.3

        """)
        self.assertEqual(self.lookup_ip('127.0.0.3'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.0.3',t='txt'), 'Blacklisted: http://example.com/bl?127.0.0.3')
        
#
#Similar format is used to specify values for individual records, with the A value (enclosed by colons) being optional:
#
#127.0.0.2 :127.0.0.2:Blacklisted: http://example.com/bl?$


        self._set_zone("""
127.0.0.2 :127.0.0.2:Blacklisted: http://example.com/bl?$
        """)
        self.assertEqual(self.lookup_ip('127.0.0.2'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.0.2',t='txt'), 'Blacklisted: http://example.com/bl?127.0.0.2')
        
#
#or, without specific A value:
#
#127.0.0.2 Blacklisted: http://example.com/bl?$
#        """
#        
        self._set_zone("""
127.0.0.2 Blacklisted: http://example.com/bl?$
        """)
        self.assertEqual(self.lookup_ip('127.0.0.2'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.0.2',t='txt'), 'Blacklisted: http://example.com/bl?127.0.0.2')
        
        

    
    def test_txt_template(self):
        """
        When A value is specified for a given entry, but TXT template is omitted, there may be two cases interpreted differently, 
        namely, whenever there's a second semicolon (:) after the A value. 
        If there's no second semicolon, default TXT value for this scope will be used.
         In contrast, when second semicolon is present, no TXT template will be generated at all. 
         All possible cases are outlined in the following example:
        """
        self._set_zone("""
# default A value and TXT template
:127.0.0.2:IP address $ is listed
# 127.0.0.4 will use default A and TXT
127.0.0.4
# 127.0.0.5 will use specific A and default TXT
127.0.0.5 :5
# 127.0.0.6 will use specific a and no TXT
127.0.0.6 :6:
# 127.0.0.7 will use default A and specific TXT
127.0.0.7 IP address $ running an open relay        
        """)
        self.assertEqual(self.lookup_ip('127.0.0.4'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.0.4',t='txt'), 'IP address 127.0.0.4 is listed')
        self.assertEqual(self.lookup_ip('127.0.0.5'), '127.0.0.5')
        self.assertEqual(self.lookup_ip('127.0.0.5',t='txt'), 'IP address 127.0.0.5 is listed')
        self.assertEqual(self.lookup_ip('127.0.0.6'), '127.0.0.6')
        self.assertEqual(self.lookup_ip('127.0.0.6',t='txt'), None)
        self.assertEqual(self.lookup_ip('127.0.0.7'), '127.0.0.2')
        self.assertEqual(self.lookup_ip('127.0.0.7',t='txt'), 'IP address 127.0.0.7 running an open relay')
        
    
    def test_txt_substitution_variables(self):
        """
        In a TXT template, references to substitution variables are replaced with values of that variables. 
        In particular, single dollar sign ($) is replaced by a listed entry (an IP address in question for IP-based
         datasets and the domain name for domain-based datasets). 
         $n-style constructs, where n is a single digit, are replaced by a substitution 
         variable $n defined for this dataset in current scope (see section "Special Entries" above).
          To specify a dollar sign as-is, use $$.
          
          """

#For example, the following lines:
#
#$1 See http://www.example.com/bl
#$2 for details
#127.0.0.2  $1/spammer/$ $2
#127.0.0.3  $1/relay/$ $2
#127.0.0.4  This spammer wants some $$$$.  $1/$
#
#will result in the following text to be generated:
#
#See http://www.example.com/bl/spammer/127.0.0.2 for details
#See http://www.example.com/bl/relay/127.0.0.3 for details
#This spammer wants some $$.  See http://www.example.com/bl/127.0.0.4

        self._set_zone("""
$1 See http://www.example.com/bl
$2 for details
127.0.0.2  $1/spammer/$ $2
127.0.0.3  $1/relay/$ $2
127.0.0.4  This spammer wants some $$$$.  $1/$       
        """)
        self.assertEqual(self.lookup_ip('127.0.0.2',t='txt'), 'See http://www.example.com/bl/spammer/127.0.0.2 for details')
        self.assertEqual(self.lookup_ip('127.0.0.3',t='txt'), 'See http://www.example.com/bl/relay/127.0.0.3 for details')
        self.assertEqual(self.lookup_ip('127.0.0.4',t='txt'), 'This spammer wants some $$.  See http://www.example.com/bl/127.0.0.4')
        

    
    def test_txt_base_template(self):
        """
        If the "base template" ($= variable) is defined, this template is used for expansion, instead of the one specified for an entry being queried. Inside the base template, $= construct is substituted with the text given for individual entries. 
        In order to stop usage of base template $= for a single record, 
        start it with = (which will be omitted from the resulting TXT value). For example,

$0 See http://www.example.com/bl?$= ($) for details
127.0.0.2    r123
127.0.0.3
127.0.0.4    =See other blocklists for details about $

produces the following TXT records:

See http://www.example.com/bl?r123 (127.0.0.2) for details
See http://www.example.com/bl?127.0.0.3 (127.0.0.3) for details
See other blocklists for details about 127.0.0.4
        """
        self._set_zone("""
$= See http://www.example.com/bl?$= ($) for details
127.0.0.2    r123
127.0.0.3
127.0.0.4    =See other blocklists for details about $     
        """)
        self.assertEqual(self.lookup_ip('127.0.0.2',t='txt'), 'See http://www.example.com/bl?r123 (127.0.0.2) for details')
        self.assertEqual(self.lookup_ip('127.0.0.3',t='txt'), 'See http://www.example.com/bl?127.0.0.3 (127.0.0.3) for details')
        self.assertEqual(self.lookup_ip('127.0.0.4',t='txt'), 'See other blocklists for details about 127.0.0.4')


class SpecialTests(ManPageTest):


    def test_range_exclusion(self):
        self._set_zone("""
192.168.10.10
!192.168.10.
        """)
        self.assertEqual(self.lookup_ip('192.168.10.10'), None)
