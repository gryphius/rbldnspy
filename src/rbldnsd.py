#!/usr/bin/python


import time
from optparse import OptionParser
import sys
import os
from rbldnspy.daemon import DaemonStuff
from rbldnspy.dataset import DATASETMAP
from rbldnspy.zone import Zone
from rbldnspy.ruleyconsole import ConsoleConstants, RuleyConsole,make_escaped_string
from rbldnspy.tools import secs2human
import string
import select
import datetime
import random

import resource
from socket import socket
import thread
from dnslib import DNSRecord, RR, DNSHeader, A, QTYPE, TXT
from IN import AF_INET, SOCK_DGRAM
import traceback
from dnslib.dns import RDMAP, SOA
from dnslib.label import DNSLabel
import signal
import ConfigParser
import logging
from logging.handlers import SysLogHandler

class RBLDNSD_options(object):
    def __init__(self):
        self.user = None
        self.rootdir = None
        self.workdir = None
        self.listensockets = [] #tuples: addr, port
        self.ipv4only = False
        self.ipv6only = False
        self.ttl = 35 * 60
        self.minttl = None
        self.maxttl = None
        self.check = 60
        self.cidrprefixcheck = True
        self.quiet = False
        self.pidfile = None
        self.logfile = None
        self.statsfile = None
        self.nodaemon = False
        self.servewhilereloading = False
        self.dumpzonefile = False
        self.versioninfo = False
        self.zones = {} #key: zonename, value: list of tuples: dataset type, filename
    
    def parse(self, args):
        optionparser = OptionParser()
        optionparser.add_option("-u", dest="user")
        optionparser.add_option("-r", dest="rootdir")
        optionparser.add_option("-w", dest="workdir")
        optionparser.add_option("-b", dest="bind", action="append")
        optionparser.add_option("-4", dest="ipv4only", action="store_true", default=False)
        optionparser.add_option("-6", dest="ipv6only", action="store_true", default=False)
        optionparser.add_option("-t", dest="ttl", default="2100::")
        optionparser.add_option("-c", dest="check", type="int", default=60)
        optionparser.add_option("-e", dest="cidrprefixcheck", action="store_false", default=True)
        optionparser.add_option("-q", dest="quiet", action="store_true", default=False)
        optionparser.add_option("-p", dest="pidfile")
        optionparser.add_option("-l", dest="logfile")
        optionparser.add_option("-s", dest="statsfile")
        optionparser.add_option("-n", dest="nodaemon", action="store_true", default=False)
        optionparser.add_option("-f", dest="servewhilereloading", action="store_true", default=False)
        optionparser.add_option("-d", dest="dumpzonefile", action="store_true", default=False)
        optionparser.add_option("-v", dest="versioninfo", action="store_true", default=False)
        
        (options, pargs) = optionparser.parse_args(args)

        for attr in ['user', 'rootdir', 'workdir', 'ipv4only', 'ipv6only', 'ttl', 'check', 'cidrprefixcheck', 'quiet',
                           'pidfile', 'logfile', 'statsfile', 'nodaemon', 'servewhilereloading', 'dumpzonefile', 'versioninfo' ]:
            setattr(self, attr, getattr(options, attr))
        
        if options.bind==None:
            print "warning: No -b argument - will *not* listen for dns queries"
            options.bind=[]
        
        for bindlist in options.bind:
            ip, port = bindlist.split('/')
            self.listensockets.append((ip, port))
        
        zones = {}
        
        for zone in pargs:
            zonename, dntype, filename = self._parse_zone(zone)
            if not zonename in zones:
                zones[zonename] = []
            
            zones[zonename].append((dntype, filename))
        
        self.zones = zones
        
        
    def _parse_zone(self, argstring):
        try:
            zonename, dntype, filename = argstring.split(':')
        except:
            raise Exception("Could not parse dataset argument. Format is 'zonename:dntype:datasource' but I got '%s' "%argstring)
        assert dntype in DATASETMAP, "Type %s is unknown" % dntype
        return zonename, dntype, filename

class StatusMonitor(object):
    def __init__(self, master):
        self.rbldnsd = master
        self.startup = time.time()
        template = """running: ${runningsince} - ${qps} q/s
$zonedatasetlist        
"""
        
        variables = {
              'runningsince':self._tmpl_runninsince,
              #'zonelist':self._tmpl_zonelist,
              #'datasetlist':self._tmpl_datasetlist,
              'zonedatasetlist':self._tmpl_zonedatasetlist,
              'qps':self._tmpl_qps,
        }
        
        self.netconsole = RuleyConsole(template, variables)
        
        self.querybuffer = {}
        self.buffertime = 5 
        self.serversocket=None
    
    def _tmpl_runninsince(self):
        return make_escaped_string(secs2human(int(time.time() - self.startup)), fg=ConsoleConstants.COLOR_CYAN)
        
    def _tmpl_qps(self):
        slottime = 5
        now = time.time()
        then = now - slottime
        bufferkeys = self.querybuffer.keys()
        counter = 0
        for k in bufferkeys:
            if k > then:
                counter += 1
        qps = float(counter) / float(slottime)
        return make_escaped_string("%.2f" % qps, fg=ConsoleConstants.COLOR_BLUE, bg=ConsoleConstants.COLOR_WHITE)
    
    def add_query(self, query):
        self.querybuffer[time.time()] = query
    
    def _tmpl_zonelist(self):
        tmpl = ""
        for zonename, zone in self.rbldnsd.zones.iteritems():
            if not zone.is_available():
                display = make_escaped_string(zonename, ConsoleConstants.COLOR_RED)
            elif zone.is_reloading():
                display = make_escaped_string(zonename, ConsoleConstants.COLOR_YELLOW)
            else:
                display = make_escaped_string(zonename, ConsoleConstants.COLOR_GREEN)
            tmpl += " " + display
        return tmpl
    
    def _tmpl_datasetlist(self):
        tmpl = ""

        for filename, dataset in self.rbldnsd.datasets.iteritems():
            if not dataset.available:
                activetime = "unavailable"
                filename = make_escaped_string(filename, ConsoleConstants.COLOR_RED)
            elif dataset.reloading:
                filename = make_escaped_string(filename, ConsoleConstants.COLOR_YELLOW)
                activetime = "(reloading)"
            else:
                filename = make_escaped_string(filename, ConsoleConstants.COLOR_GREEN)
                humanreadableactivetime = secs2human(int(time.time() - dataset.activesince))
                activetime = make_escaped_string(humanreadableactivetime, ConsoleConstants.COLOR_CYAN)
            
            reloadinfo = dataset.lastreloadinfo
            if reloadinfo == None:
                info = ''
            else:
                (loadtime, newcount, diff) = reloadinfo
                loadtime = "%.2fs" % loadtime
                if diff >= 0:
                    diff = "+%s" % diff
                newcount = make_escaped_string(newcount, ConsoleConstants.COLOR_MAGENTA)
                info = "loadtime: %s , %s records(%s)" % (loadtime, newcount, diff)
                
                         
            tmpl += "%s age: %s %s\n" % (filename, activetime, info)
        return tmpl
    
    
    def _tmpl_zonedatasetlist(self):
        """zone+dataset combined"""
        tmpl = ""
        for zonename, zone in self.rbldnsd.zones.iteritems():
            if not zone.is_available():
                display = make_escaped_string(zonename, ConsoleConstants.COLOR_RED)
            elif zone.is_reloading():
                display = make_escaped_string(zonename, ConsoleConstants.COLOR_YELLOW)
            else:
                display = make_escaped_string(zonename, ConsoleConstants.COLOR_GREEN)
            tmpl += "\n"+display+": \n"
            
            
            for dataset in zone.datasets:
                filename=dataset.filename
                
                if not dataset.available:
                    activetime = "unavailable"
                    filename = make_escaped_string(filename, ConsoleConstants.COLOR_RED)
                elif dataset.reloading:
                    filename = make_escaped_string(filename, ConsoleConstants.COLOR_YELLOW)
                    activetime = "(reloading)"
                else:
                    filename = make_escaped_string(filename, ConsoleConstants.COLOR_GREEN)
                    humanreadableactivetime = secs2human(int(time.time() - dataset.activesince))
                    activetime = make_escaped_string(humanreadableactivetime, ConsoleConstants.COLOR_CYAN)
                
                reloadinfo = dataset.lastreloadinfo
                if reloadinfo == None:
                    info = ''
                else:
                    (loadtime, newcount, diff) = reloadinfo
                    loadtime = "%.2fs" % loadtime
                    if diff >= 0:
                        diff = "+%s" % diff
                    newcount = make_escaped_string(newcount, ConsoleConstants.COLOR_MAGENTA)
                    info = "loadtime: %s , %s records(%s)" % (loadtime, newcount, diff)
                    
                             
                tmpl += " %s age: %s %s\n" % (filename, activetime, info)
            
            
        return tmpl 
    
    def start(self):
        port = 5353
        logging.info("""**** monitor running on port %s *****""" % port)
        try:
            self.serversocket=self.netconsole.run_remote_console(port)
        except:
            logging.getLogger().error("Exception in run_remote_console: %s"%traceback.format_exc())
        

    def debug_console(self):
        self.netconsole.loop()
        
    def shutdown(self):
        self.netconsole.stop_looping()
        if self.serversocket!=None:
            try:
                self.serversocket.close()
            except:
                pass


from dnslib import DNSRecord, RR, DNSHeader, A, QTYPE
# requires http://pypi.python.org/pypi/dnslib

class DNSFrontend(object):
    
    RCODE_SERVFAIL = 2
    RCODE_NXDOMAIN = 3
    RCODE_NOTIMPLEMENTED = 4
    RCODE_REFUSED = 5
    
    def __init__(self, master, ip="127.0.0.1", port=53):
        self.rbldnsd = master
        self.socket = None
        self.ip = ip
        self.port = port
        self.stayAlive = True
        
    
    def send_nxdomain(self,d,addr):
        response = DNSRecord(DNSHeader(id=d.header.id, gr=1, aa=1, ra=1, qr=1, rcode=DNSFrontend.RCODE_NXDOMAIN),
                        q=d.get_q()
                        )
        self.socket.sendto(response.pack(), addr)
        
    def send_servfail(self,d,addr):
        response = DNSRecord(DNSHeader(id=d.header.id, gr=1, aa=1, ra=1, qr=1, rcode=DNSFrontend.RCODE_SERVFAIL),
                        q=d.get_q()
                        )
        self.socket.sendto(response.pack(), addr)
     
    def serve(self):
        try:
            udpsocket = socket(AF_INET, SOCK_DGRAM)
            udpsocket.bind((self.ip, self.port))
            self.socket = udpsocket        
            logging.getLogger().debug('now serving on %s/%s' % (self.ip, self.port))
            
            while self.stayAlive:
                try:
                    data, addr = self.socket.recvfrom(512)
                    d = DNSRecord.parse(data)
                    
                    #print "Question from  ",addr
                    #print d
                    question = d.get_q()
                    qname = str(question.qname)
                    qtype = str(QTYPE[question.qtype]).upper()
                    
                    try:
                        ansdict = self.rbldnsd.lookup(qname)
                        
                        #logging.getLogger().debug("ansdict: %s"%ansdict)
                        if qtype=='SOA':
                            if ansdict['SOA']!=None:
                                response = DNSRecord(DNSHeader(id=d.header.id, gr=1, aa=1, ra=1, qr=1, q=d.get_q()))
                                soa=ansdict['SOA']
                                packet=SOA()
                                packet.set_mname(soa[0])
                                packet.set_rname(soa[1])
                                packet.times=soa[2:]
                                if 'SOATTL' in ansdict:
                                    packet.ttl=ansdict['SOATTL']
                                response.rr.append(packet)
                                self.socket.sendto(response.pack(), addr)
                                continue
                            else:
                                self.send_nxdomain(d, addr)
                                continue
                        elif qtype=='NS':
                            if ansdict['NS']!=None:
                                #TODO
                                pass
                            else:
                                self.send_nxdomain(d, addr)
                                continue
                        elif qtype=='A' or qtype=='TXT':
                            if 'results' not in ansdict:
                                self.send_nxdomain(d, addr)
                                logging.getLogger().debug("client=%s q=%s %s -> NXDOMAIN"%(addr[0],qname,qtype))
                                continue
                            anslist=ansdict['results']
                            anspacklist=[]
                            for answer in anslist:
                                if answer==None:
                                    continue
                                if qtype not in answer:
                                    continue
                                packet=RR(question.qname,question.qtype,rdata=RDMAP[QTYPE[question.qtype]](answer[qtype]))
                                if 'TTL' in answer and answer['TTL']!=None:
                                    packet.ttl=answer['TTL']
                                anspacklist.append(packet)
                                
                            if len(anspacklist)>0:
                                response = DNSRecord(DNSHeader(id=d.header.id,bitmap=d.header.bitmap, aa=1, ra=0, qr=1,q=1))
                                response.add_question(question)
                                response.rr.extend(anspacklist)
                                response.set_header_qa()
                                #logging.getLogger().debug(response)
                                #make sure answer bit is set
                                #response.header.qr=1
                                
                                self.socket.sendto(response.pack(), addr)
                                logging.getLogger().debug("client=%s q=%s %s -> NOERROR"%(addr[0],qname,qtype))
                            else:
                                self.send_nxdomain(d, addr)
                                logging.getLogger().debug("client=%s q=%s %s -> NXDOMAIN"%(addr[0],qname,qtype))
                            
                            continue
                        else:
                            logging.getLogger().warning("unsupported qtype %s"%qtype)
                            
                        
                    except:
                        fmt = traceback.format_exc()
                        logging.getLogger().error(fmt)
                        self.send_servfail(d, addr)
                        continue
                    
                   
                except Exception:
                    fmt = traceback.format_exc()
                    logging.getLogger().error(fmt)
        except:
            fmt = traceback.format_exc()
            logging.getLogger().error("Could not start serversocket on %s/%s: %s" % (self.ip, self.port, fmt))
        logging.getLogger().debug('serve() complete')
    
    def shutdown(self):
        logging.getLogger().debug("closing socket on %s/%s" % (self.ip, self.port))
        self.stayAlive = False
        try:
            self.socket.close()
        except Exception, e:
            logging.getLogger().error('problem while shutting down socket: %s' % str(e))
        



class RBLDNSD(object):
    def __init__(self, options):
        self.options = options
        self.zones = {}
        self.datasets = {}
        self.statusmonitor = StatusMonitor(self)
        self.stay_alive=True
        self.dnsfrontends=[]
    
        self.configfile='/etc/rbldnspy/rbldnspy.conf'
        self.dconfdir='/etc/rbldnspy/conf.d'
        self.config=self.reloadconfig()

    def reloadconfig(self):
        """reload configuration file"""
    
        newconfig=ConfigParser.ConfigParser()
        if os.path.exists(self.configfile):
            newconfig.readfp(open(self.configfile))
        
        #load conf.d
        if os.path.isdir(self.dconfdir):
            filelist=os.listdir(self.dconfdir)
            configfiles=[self.dconfdir+'/'+c for c in filelist if c.endswith('.conf')]
            newconfig.read(configfiles)

        return newconfig
     
    def startup(self):
        starttime = time.time()
        
        #unimplemented stuff
        notyetimplemented = ['ipv4only', 'ipv6only', 'ttl', 'cidrprefixcheck', 'quiet',
                           'logfile', 'statsfile', 'dumpzonefile', 'versioninfo' 
                           ]
        defaults = RBLDNSD_options()
        for attr in notyetimplemented:
            if getattr(self.options, attr) != getattr(defaults, attr):
                print "The option %s is not yet implemented" % attr
                
        #implemented option
        pidfile = None
        
        if self.options.pidfile:
            pidfile = self.options.pidfile
        
        daemonstuff = DaemonStuff(pidfile)
        
        if self.options.rootdir:
            if not os.path.isdir(self.options.rootdir):
                msg = "Cannot chroot to %s - no such directory" % self.options.rootdir
                print msg
                sys.exit(1)
            os.chroot(self.options.rootdir)
        
        if self.options.workdir:
            if not os.path.isdir(self.options.workdir):
                msg = "Cannot set workdir to %s - no such directory" % self.options.workdir
                print msg
                sys.exit(1)
            os.chdir(self.options.workdir)
        
        if self.options.user:
            daemonstuff.drop_privs(self.options.user)
            
        
        if self.options.nodaemon:
            if pidfile:
                daemonstuff.writepid(pidfile)
        else:
            print "backgrounding..."
            #writes pidfile automatically
            daemonstuff.createDaemon()

            
        #now we are either in child process or no-daemon mode, so we can safely instantiate logging
        init_logging()

        try:
            self.load_zones(autoreloader=True)
        except:
            logging.getLogger().error("Exception while loading zones: %s"%traceback.format_exc())
            
        try:
            self.statusmonitor.start()
        except:
            logging.getLogger().error("Exception starting statusmonitor: %s"%traceback.format_exc())
        
        
        #init frontend
        for sock in self.options.listensockets:
            try:
                ip, port = sock
                dnsf = DNSFrontend(self, ip, int(port))
                thread.start_new(dnsf.serve, ())
                self.dnsfrontends.append(dnsf)
            except:
                logging.getLogger().error("Exception starting dns frontent on %s/%s: %s"%(ip,port,traceback.format_exc()))
        
        difftime = time.time() - starttime
        logging.getLogger().info("startup complete after %.2f seconds" % difftime)
      
    def shutdown(self):
        self.stay_alive=False
        
        logging.getLogger().error("stopping dns frontends...")
        for dnsf in self.dnsfrontends:
            dnsf.shutdown()
        
        logging.getLogger().error("closing zones...")
        for k,dataset in self.datasets.iteritems():
            dataset.shutdown()
            
        logging.getLogger().error("stopping status monitor...")
        self.statusmonitor.shutdown()
        
        logging.getLogger().error("rbldnspy shut down")
        
    def load_zones(self, autoreloader=True):  
        #preload zones
        datasets = {}
        zones = {}
        
        for zonename in self.options.zones.keys():
            #logging.getLogger().debug('init zone %s'%zonename)
            datasetlist = self.options.zones[zonename]
            #logging.getLogger().debug("datasets for zone %s : %s"%(zonename,datasetlist))
            
            if zonename not in zones:
                zones[zonename] = Zone(zonename)
            
            for dsettype, dsetfile in datasetlist:
                logging.getLogger().info("now handling zone argument %s : %s"%(dsettype,dsetfile))
                if not os.path.isfile(dsetfile) and dsettype!='fastlist':
                    msg = "File does not exist: %s" % dsetfile
                    logging.getLogger().error(msg)
                    sys.exit(1)
                
                if dsetfile not in datasets:
                    datasetclass = DATASETMAP[dsettype]
                    if datasetclass == None:
                        logging.getLogger().error("Dataset type %s not yet implemented" % dsettype)
                        continue
                    dataset = datasetclass(dsetfile)
                    dataset.apply_config(self.config)
                    if self.options.check:
                        dataset.reload_check_interval=self.options.check
                    #logging.getLogger().debug("Starting initial load for %s/%s"%(dsetfile,dsettype))
                    #dataset.reload()
                    if autoreloader:
                        logging.getLogger().debug("Starting auto-reloader for %s: %s , check every %s seconds"%(dsettype,dsetfile,dataset.reload_check_interval))
                        dataset.start_autoreloader()
                    else:
                        dataset.reload()
                    datasets[dsetfile] = dataset
                    
                zones[zonename].add_dataset(datasets[dsetfile])        
            self.zones = zones
            self.datasets = datasets
        
    def sighandler(self,signum,frame):
        logging.getLogger().info("Shutting down...")
        self.shutdown()
    
    def serve_forever(self):
        signal.signal(signal.SIGTERM, self.sighandler)
        #main thread
        while self.stay_alive:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                self.shutdown()

            
            
    def lookup(self, query):
        """Returns a dict
        
        Keys:
        SOA: soa record
        NS: list of ns records
        results: list of dicts
        """
        query = query.rstrip('.')
        self.statusmonitor.add_query(query)
        logging.getLogger().debug("query: %s" % query)
        for k in sorted(self.zones, key=len, reverse=True):
            if query==k or query.endswith('.%s' % k):
                if query==k:
                    search=''
                else:
                    search = query[:-len(k) - 1]
                zone = self.zones[k]
                if not zone.is_available():
                    raise Exception("Zone %s unavailable" % zone)
                logging.getLogger().debug("query trace: zone=%s" % k)
                result = zone.lookup(search)
                logging.getLogger().debug('result: %s' % result)
                return result
        return {}
        
    
def init_logging():
    """do not call this before createDaemon!"""
    
    loglevel=logging.DEBUG
    #logging.basicConfig(level=loglevel)
    logger = logging.getLogger()
    logger.setLevel(loglevel)
    slh=SysLogHandler(address = '/dev/log')
    slh.setFormatter(logging.Formatter("rbldnspy[%(process)d]: %(message)s"))
    #log debug/error messages to syslog info level
    slh.priority_map["DEBUG"]="info"
    slh.priority_map["ERROR"]="info"
    
    slh.setLevel(loglevel)
    logger.addHandler(slh)
    return logger
    

if __name__ == '__main__':

    args=sys.argv
    #logger.info("Started with arguments: %s"%args)
    
    try:
        opts = RBLDNSD_options()
        opts.parse(args[1:])
    
        rbldns = RBLDNSD(opts)
    
        rbldns.startup()
        rbldns.serve_forever()
    except Exception:
        fmt=traceback.format_exc()
        print "Rbldnspy crashed: %s"%fmt

