import time
import logging
import thread
from threading import Lock
from tools import *
RADIX_AVAILABLE=False
try:
    RADIX_AVAILABLE=True
    import radix
except:
    pass
import string
import os
import Queue
import string
import socket
import traceback
try:
    import cPickle as pickle
except:
    import pickle

class ReloadDefaults(object):
    def __init__(self):
        self._soa=None
        self._basetxttemplate=None
        self.txttemplate=None
        self.atemplate='127.0.0.2'
        self.ttl=None
        self.variables=[None for x in range(10)]
        self.maxrange4=None
        self._ns=None
        self._nsttl=0
        
    @property
    def basetxttemplate(self):
        return self._basetxttemplate
    
    @basetxttemplate.setter
    def basetxttemplate(self,value):
        if self._basetxttemplate==None:
            self._basetxttemplate=value
            
    @property
    def soa(self):
        return self._soa
    
    @soa.setter
    def soa(self,value):
        if self._soa==None:
            self._soa=value
            
            
    @property
    def ns(self):
        return self._ns
    
    @ns.setter
    def ns(self,value):
        if self._ns==None:
            self._ns=value
    
    @property
    def nsttl(self):
        return self._nsttl
    
    @nsttl.setter
    def nsttl(self,value):
        if self._nsttl==0:
            self._nsttl=value
        
    
        
class AbstractDataset(object):
    
    def __init__(self,filename):
        self.filename=filename
        #reload start time
        self.last_reload=0
        
        #autoreloader or other threads
        self.stay_alive=True
        
        #reload end time
        self.activesince=0
        self.logger=logging.getLogger("rbldnspy.dataset")
        self._reload_lock=Lock()
        
        
        #reload info stats
        self.reloading=False
        self.lastreloadinfo=None
        self.reload_check_interval=60 #how often do we check for reloads - set by the -c option
        
        #first time
        self.available=False
        self.defaults=None

        self._tempsoa=None
        self._tempns=[]

  
    @property
    def soa(self):
        return self.defaults.soa
    
    @property
    def ns(self):
        return self.defaults.ns
        
    @property
    def nsttl(self):
        return self.defaults.nsttl
        
    def start_autoreloader(self):
        thread.start_new_thread(self._autoreload, ())
    
    
    def shutdown(self):
        self.stay_alive=False
    
    def _autoreload(self):
        while self.stay_alive:
            if self.has_changed():
                logging.getLogger().info("%s has changed - reloading"%self.filename)
                self.reload()
            time.sleep(self.reload_check_interval)
    
    def apply_txt_template(self,template,question,result,defaults):
        """query time txt template"""
        origtemplate=template
        if defaults.basetxttemplate!=None:
            if template!=None and len(template)>0 and template[0]=='=':
                #special case.. disable basetemplate in the record with leading =
                template=template[1:]
            else:
                template=defaults.basetxttemplate
            
        if template==None:
            return None
        templen=len(template)
        outbuf=""
        i=0
        while i < templen:
            c=template[i]
            n=None
            if i<templen-1:
                n=template[i+1]
            if c=='$':
                if n=='$':
                    outbuf+='$'
                    i+=2
                    continue
                elif n!=None and n in string.digits:
                    varindex=int(n)
                    if defaults.variables[varindex]!=None:
                        outbuf+=defaults.variables[varindex]
                    i+=2
                    continue
                elif n=='=' and defaults.basetxttemplate!=None:
                    #base template
                    #assert False,"%s %s %s %s %s"%(template,c,n,outbuf,origtemplate)
                    if origtemplate!=None:
                        outbuf+=origtemplate
                    else:
                        #assert False,question
                        outbuf+=question
                    i+=2
                    continue
                else:
                    outbuf+=question    
                    i+=1
                    continue
                    
            outbuf+=c        
            i+=1
        return outbuf
            
    
    def reload(self):
        gotlock=self._reload_lock.acquire(False)
        if not gotlock:
            logging.getLogger().warning("%s is already being reloaded - skipping"%self.filename)
            return
        
        oldcount=self.get_record_count()
        starttime=time.time()
        self.reloading=True
        
        
        defaults=ReloadDefaults()
        self.reload_start(defaults)
        self.last_reload=time.time()
        for line in open(self.filename,'r'):
            line=line.strip()
            if line=='':
                continue
            
            if line.startswith('$'):
                self.parse_special(line[1:],defaults)
                continue
            
            if line.startswith('#$') or line.startswith(';#') or line.startswith(':$'):
                self.parse_special(line[2:],defaults)
                continue
            
            if line.startswith(':'):
                self.parse_defaultval(line[1:],defaults)
                continue
            
            if line.startswith('#'):
                continue
            
            #remove comments
            if '#' in line:
                line=line[:line.find('#')]
                
            if ';' in line:
                line=line[:line.find(';')]
            
            try:
                self.reload_line(line,defaults)
            except Exception:
                import traceback
                logging.getLogger().error("Error parsing line '%s'"%line)
                logging.getLogger().error(traceback.format_exc())

        self.reload_end(defaults)
        self.defaults=defaults
        self.reloading=False
        self.available=True
        self.activesince=time.time()
        newcount=self.get_record_count()
        loadtime=time.time()-starttime
        diff=newcount-oldcount
        
        recspersec=newcount/loadtime
        self.lastreloadinfo=(loadtime,newcount,diff)
        logging.getLogger().debug("Dataset(%s) reloaded in %.2fs, %s records (%s), %.2f records/sec"%(self.filename,loadtime,newcount,diff,recspersec))
        self._reload_lock.release()


    def parse_special(self,line,defaults):
        command,rest=line.split(None,1)
        
        
        if command=='SOA':
            
            if defaults.soa!=None:
                logging.getLogger().warning("multiple SOA entries in dataset, ignoring")
                return
            
            try:
                soattl,origindn,persondn,serial,refresh,retry,expire,minttl=rest.split()
                soattl=ttl2int(soattl)
                serial=ttl2int(serial)
                refresh=ttl2int(refresh)
                retry=ttl2int(retry)
                expire=ttl2int(expire)
                minttl=ttl2int(minttl)
                defaults.soa=(soattl,origindn,persondn,serial,refresh,retry,expire,minttl)
            except:
                logging.getLogger().warning("Could not parse SOA line %s"%line)
                
        elif command=='NS':
            if defaults.ns!=None:
                logging.getLogger().warning("multiple NS lines in dataset - ignoring")
                return
            else:
                try:
                    nameservers=rest.split()
                    ttl=ttl2int(nameservers[0])
                    defaults.ns=[ns for ns in nameservers[1:] if not ns.startswith('-')]
                    defaults.nsttl=ttl
                except:
                    logging.getLogger().warning("Could not parse NS line %s"%line)
        elif command=='TTL':
            parts=rest.split(':')
            defaults.ttl=ttl2int(parts[0])
        elif command=='MAXRANGE4':
            if rest.startswith('/'):
                bits=32-int(rest[1:])
                rng=2**bits
            else:
                rng=int(rest)
            
            if defaults.maxrange4==None or defaults.maxrange4>rng:
                defaults.maxrange4=rng
        elif command in ['0','1','2','3','4','5','6','7','8','9']:
            defaults.variables[int(command)]=rest
        elif command=='=':
            defaults.basetxttemplate=rest
        else:
            logging.warn('unknown special entry %s'%command)
    
    def split_line(self,line,a_default=None,txt_default=None):
        """splits a line into listed object, a and txt template. 
        returns a tuple (listed,a_template,txt_template)
        returns a_default / txt_default if the corresponding value is not defined in the line
        """
        sp=line.split(None,1)
        if len(sp)==1:
            return sp[0],a_default,txt_default
        
        k,rest=sp
        
        #strip comments
        if rest[0]=='#' or rest[0]==';':
            return k,a_default,txt_default
        
        apart=None
        txtpart=None
        txtpartwasdisabled=False
        
        if rest[0]==':':
            #we have an ip
            part=rest[1:]
            if ':' in part:
                #we have a txt as well
                apart,txtpart=part.split(':',1)
                if txtpart.strip()=='':
                    txtpart=None
                    txtpartwasdisabled=True
            else:
                #only a, no txt
                apart=part
                
        else:
            #only txt, no a
            txtpart=rest
        
        #test is apart is a digit only
        try:
            if int(apart)<256:
                apart="127.0.0.%s"%apart
        except:
            pass
        
        if apart==None:
            apart=a_default
          
        if txtpart==None and not txtpartwasdisabled:
            txtpart=txt_default
        
        return k,apart,txtpart
    
    def create_default_datarecord(self,line,defaults):
        value,a,txt=self.split_line(line, defaults.atemplate, defaults.txttemplate)
        data={
              'A':a,
              'TXT':txt,
              'excluded':False,
              'TTL':defaults.ttl,
        }
        if value.startswith('!'):
            value=value[1:]
            value=value.lower()
            data['excluded']=True
        return value,data
    
        
    def parse_defaultval(self,line,defaults):
        #assume we have an ip
        #todo: there is other special vars
        lineparts=line.split(':',1)
        
        #ugly hack
        ip=lineparts[0]
        if not '.' in ip:
            ip="127.0.0.%s"%ip
        defaults.atemplate=ip
        
        
        #txt
        if len(lineparts)>1:
            txtpart=lineparts[1]
            defaults.txttemplate=txtpart
        
    
    def has_changed(self):
        lastreload=self.last_reload
        statinfo=os.stat(self.filename)
        lastmod=statinfo.st_mtime
        return lastmod > lastreload
    
    

    ###### OVERRIDE THESE METHODS ###
    def reload_start(self,defaults):
        """init the temp storage for the reload process"""
        pass
    
    def reload_line(self,line,defaults):
        """parse a single data line"""
        pass
    
    def reload_end(self,defaults):
        """move the temp storage to the real deal and clean up"""
        pass
    
    def get_record_count(self):
        return 0
    
    def get_reload_info(self):
        """return the reload status, return None if not reloading"""
        return None
    
    def get(self,query):
        return None
    
    def apply_config(self,config):
        """additional config options from file"""
        pass

class TrivialSet(AbstractDataset):
    """trivia ip4set: a set of single IP addresses (one per line), with the same A+TXT template. 
    This dataset type is more efficient than ip4set (in both memory usage and access times), 
    but have obvious limitation. It is intended for DNSBLs like DSBL.org, ORDB.org and similar, 
    where each entry uses the same default A+TXT template. 
    This dataset uses only half a memory for the same list of IP addresses compared to ip4set. """
    
    
    def __init__(self,filename):
        AbstractDataset.__init__(self,filename)
        self.backend=[]
        self.nodecount=0
        
        #reload
        self.tmpbackend=[]
        self.tmpcount=0
        
        #fixed values
        self.atemplate='127.0.0.2'
        self.txttemplate=None
        
    def reload_start(self,defaults):
        self.tmpbackend=[]
        self.tmpcount=0
        
    
    def reload_line(self,line,defaults):
        lineparts=line.split()
        value=lineparts[0]
        self.tmpbackend.append(value)
        self.tmpcount+=1
        #todo: check if linepart is an ip...
    
    def reload_end(self,defaults):
        self.atemplate=defaults.atemplate
        self.backend=self.tmpbackend
        self.nodecount=self.tmpcount
        self.tmpbackend=None
        self.tmpcount=0    

    def get_record_count(self):
        return self.nodecount
    
    def get(self,query):
        query=ipreverse(query)
        if query in self.backend:
            rec={
                 'A':self.atemplate,
                 'TXT':self.apply_txt_template(self.txttemplate, query, self.atemplate, self.defaults),
            }
            return rec

class RadixTrieSet(AbstractDataset):
    def __init__(self,filename):
        if not RADIX_AVAILABLE:
            raise Exception("radix library not available - TrieSet is not available")
        AbstractDataset.__init__(self,filename)
        self.rtree=radix.Radix()
        self.nodecount=0
    
        #reload
        self.tmpradix=None
        self.tmpcount=0
    
    def reload_start(self,defaults):
        self.tmpradix=radix.Radix()
        self.tmpcount=0
    
    def reload_line(self,line,defaults):
        cidr,data=self.create_default_datarecord(line, defaults)
        if defaults.maxrange4!=None and '/' in cidr:
            rest=cidr[cidr.find('/')]
            bits=32-int(rest[1:])
            rng=2**bits
            if rng>defaults.maxrange4:
                logging.warn("MAXRANGE4 prohobits adding %s in %s"%(cidr,self.filename))
                return
        rnode=self.tmpradix.add(cidr)
        self.tmpcount+=1
        rnode.data['content']=data
        
    def reload_end(self,defaults):
        self.rtree=self.tmpradix
        self.nodecount=self.tmpcount
        self.tmpradix=None
        self.tmpcount=0
    
    def get_record_count(self):
        return self.nodecount
    
    def get(self,query):
        query=ipreverse(query)
        res=self.rtree.search_best(query)
        if res==None:
            return None
        data=res.data['content']
        if data['excluded']:
            return None
            
        if 'TXT' in data:
            data['TXT']=self.apply_txt_template(data['TXT'], query, data['A'], self.defaults)
        return data

from intervaltree import IntervalTree,Interval



class IntervalTreeSet(AbstractDataset):
    def __init__(self,filename):
        AbstractDataset.__init__(self,filename)
        self.backend=IntervalTree([])
        self.nodecount=0
    
        #reload
        self.intervals=None
        self.tmpcount=0
    
    def reload_start(self,defaults):
        self.tmpintervals=[]
        self.tmpcount=0
    
    def reload_line(self,line,defaults):
        
        value,data=self.create_default_datarecord(line, defaults)

        #TODO: how do we initialize default TTL from command line

        lower,upper=ip4range(value)
        lowerlong=ip2long(lower)
        upperlong=ip2long(upper)
        
        if defaults.maxrange4!=None and upperlong-lowerlong>defaults.maxrange4:
            logging.warn("MAXRANGE4 prohobits adding %s in %s"%(value,self.filename))
            return
        
        interval=Interval(lowerlong,upperlong)
        interval.data=data
        self.tmpintervals.append(interval)
        self.tmpcount+=1
        
    def reload_end(self,defaults):
        newtree=IntervalTree(self.tmpintervals)
        self.backend=newtree
        del newtree
        self.nodecount=self.tmpcount
        self.tmpintervals=None
        self.tmpcount=0
    
    def get_record_count(self):
        return self.nodecount

    def get(self,query):
        query=ipreverse(query)
        q=ip2long(query)
        res=self.backend.search(q)
        for r in res:
            try:
                if r.data['excluded']:
                    return None
            except KeyError:
                continue
        
        #no exclusions, return first match
        if len(res)>0:
            data=res[0].data
            if 'TXT' in data:
                data['TXT']=self.apply_txt_template(data['TXT'], query, data['A'], self.defaults)
            return data
        
class DNSet(AbstractDataset):
    def __init__(self,filename):
        AbstractDataset.__init__(self,filename)
        self.backend={}
        self.nodecount=0
        
        #reload
        self.tmpbackend={}
        self.tmpcount=0
        
    def reload_start(self,defaults):
        self.tmpbackend={}
        self.tmpcount=0
        
    
    def reload_line(self,line,defaults):
        value,data=self.create_default_datarecord(line, defaults)
        value=value.lower()
        #TODO: wildcard... 
        self.tmpbackend[value]=data
        self.tmpcount+=1
    
    def reload_end(self,defaults):
        self.backend=self.tmpbackend
        self.nodecount=self.tmpcount
        self.tmpbackend=None
        self.tmpcount=0    

    def get_record_count(self):
        return self.nodecount
    
    def get(self,question):
        question=question.lower()
        #TODO: check wildcard
        
        try:
            data=self.backend[question]
            if 'excluded' in data and data['excluded']:
                return None
            else:
                return data
        except:
            return None

class UDPSocketSet(DNSet):
    def __init__(self,filename):
        DNSet.__init__(self,filename)
        del self.tmpbackend
        self.udpsocket=None
        logging.getLogger().info("initializing fastlist zone %s"%filename)
        
        self.listdefaults={
            'a_content':'127.0.0.2',
            'txt_content':None,
            'ttl':120,
            'expiration':12*3600,
        }

    def apply_config(self,config):
        bind,port=self.filename.split('/')
        port="%s"%port
        if config.has_option(port,'A'):
            self.listdefaults['a_content']=config.get(port,'A')
        
        if config.has_option(port,'TXT'):
            self.listdefaults['txt_content']=config.get(port,'TXT')
            
        if config.has_option(port,'TTL'):
            self.listdefaults['ttl']=config.getint(port,'TTL')
            
        if config.has_option(port,'expiration'):
            self.listdefaults['expiration']=config.getint(port,'expiration')
        
        
        

    def reload_start(self):
        """no op"""
        pass
    
    def reload_end(self):
        """no op"""
        pass
    
    def reload(self):
        """Initialize the socket"""
        if self.udpsocket==None:
            logging.getLogger().info("starting fastlist UDP socket on %s"%(self.filename))
            self.defaults=ReloadDefaults()
            bind,port=self.filename.split('/')
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            sock.bind((bind,int(port)),)
            self.udpsocket=sock
            
            self.last_reload=time.time()
            self.activesince=time.time()
            #test point
            #TODO: configurable from static file?
            self.load_zone()
            self.fastlist('test',dict(A=self.listdefaults['a_content'],excluded=False,ttl=3600))

            self.lastreloadinfo=(0,len(self.backend),0)
            self.start_threads()
            self.available=True
            
            logging.getLogger().info("Fastlist UDP socket ready on %s/%s"%(bind,port))
    
    def start_autoreloader(self):
        """no op, just make sure the socket is initialized"""
        self.reload()
    
    
    def start_threads(self):
        thread.start_new_thread(self.listen, ())
        thread.start_new_thread(self.expire, ())
        thread.start_new_thread(self.save, ())
        
    def save(self):
        while self.stay_alive:
            time.sleep(60)
            self.save_zone()
        
    def expire(self):
        try:
            while self.stay_alive:
                time.sleep(20)
                now=time.time()
                self._reload_lock.acquire()
                delcount=0
                for key in self.backend.keys():
                    data=self.backend[key]
                    if 'expires' in data and now>data['expires']:
                        logging.getLogger().info("expiring %s"%key)
                        del self.backend[key]
                        delcount+=1
                self._reload_lock.release()
                
                if delcount>0:
                    self.touch(-delcount)
        except:
            logging.getLogger().error("fasthash expiration thread crashing: %s"%traceback.format_exc())
            
    
        
    def touch(self,change=1):
        self.lastreloadinfo=(0,len(self.backend),change)
        self.last_reload=time.time()
        self.activesince=time.time()
    
    def fastlist(self,name,rec):
        try:
            self._reload_lock.acquire()
            self.backend[name]=rec
            self._reload_lock.release()
            self.touch()
            return rec
        except Exception,e:
            logging.getLogger().warn("Fastlisting failed, possible deadlock: %s"%str(e))
            return None   
        
    def delist(self,value): 
        if value in self.backend:
            try:
                self._reload_lock.acquire()
                del self.backend[value]
                self._reload_lock.release()
                logging.getLogger().info("%s: de-listed %s"%(self.filename,value))
                self.touch(-1)
            except Exception,e:
                logging.getLogger().warn("Fast-delisting of %s failed: %s"%(value,str(e))) 
        else:
            logging.getLogger().warn("Fast-delisting of %s failed: not found"%(value)) 
            
                 
    def handlepacket(self,content,ip):
        #<name> <a-content> <txt-content> <action> <ttl> <expiration>
        logging.getLogger().debug("dbg packethandler(received) from %s: %s"%(ip,content))
        num_fields=6
        fields=content.strip().split('\t')
        
        #pad fields to correct size
        fields+=[''] * (num_fields - len(fields))
        fields=map(string.strip, fields)
        name,a_content,txt_content,action,ttl,expiration=fields
        name=name.lower()
        if name=='':
            raise Exception("empty name")
        if a_content=='':
            a_content=self.listdefaults['a_content']
        if txt_content=='':
            txt_content=self.listdefaults['txt_content']
        if action=='':
            action='a'
            
        if action not in ['a','d']:
            raise Exception('unknown action : %s'%action)
        
        if ttl=='':
            ttl=self.listdefaults['ttl']
        else:
            try:
                ttl=int(ttl)
            except:
                raise Exception('invalid ttl: %s'%ttl)
        
        if expiration=='':
            expiration=self.listdefaults['expiration']
        else:
            try:
                expiration=int(expiration)
            except:
                raise Exception('invalid expiration: %s'%expiration)
        logging.getLogger().debug("dbg  packethandler(final values): name=%s a=%s txt=%s action=%s ttl=%s expiration=%s"%(name,a_content,txt_content,action,ttl,expiration)) 
        
        #TODO: ACL based on addr
        if action=='a':
            rec={
                  'A':a_content,
                  'excluded':False,
                  'TTL':ttl,
            }
            if expiration!=None and expiration!=0:
                rec['expires']=time.time()+expiration
            if txt_content:
                rec['TXT']=txt_content
            self.fastlist(name, rec)
            logging.getLogger().info("Listener %s : fastlisted %s from %s"%(self.filename,name,ip))
            
        elif action=='d':
            self.delist(name)
            
    def listen(self):
        try:
            while self.stay_alive:
                if self.udpsocket==None:
                    logging.getLogger().debug("waiting for fastlist socket to become ready...")
                    time.sleep(1)
                    continue
                
                #logging.getLogger().debug("waiting for fastlist packet...")
                packetcontent, addr = self.udpsocket.recvfrom(1024)
                ip=addr[0]
                
                try:
                    self.handlepacket(packetcontent, ip)
                except Exception,e:
                    logging.getLogger().error("Listener %s : throwing packet away from %s : %s"%(self.filename,ip,str(e)))
                
        except:
            logging.getLogger().error("fasthash listener thread crashing: %s"%traceback.format_exc())
            
        try:
            self.save_zone()
            self.udpsocket.close()
        except:
            pass
        
    def shutdown(self):
        self.stay_alive=False
        self.save_zone()
        
    def save_zone(self):
        """simple persistence"""
        try:
            filename='/tmp/fastlist-%s.p'%self.filename.split('/')[1]
            self._reload_lock.acquire()
            pickle.dump(self.backend, open(filename,'wb'))
            logging.getLogger().info("fastlist zone %s saved to %s "%(self.filename,filename))
            self._reload_lock.release()
        except:
            logging.getLogger().error("save_zone failed: %s"%traceback.format_exc())
            
    def load_zone(self):
        """try to load pickle"""
        
        filename='/tmp/fastlist-%s.p'%self.filename.split('/')[1]
        
        if not os.path.exists(filename):
            logging.getLogger().info("no save file found for %s"%(self.filename))
            return
        logging.getLogger().info("found save file for %s"%(self.filename))
        
        
        
        try:
            self._reload_lock.acquire()
            newback=pickle.load(open(filename,'rb'))
            self.backend=newback
            self._reload_lock.release()
            logging.getLogger().info("successfuly reloaded %s from %s"%(self.filename,filename))
        except:
            logging.getLogger().error("load failed: %s"%traceback.format_exc())
            

DATASETMAP={
   'dnset':DNSet,
   'ip4set':IntervalTreeSet,
   'ip4tset':TrivialSet,
   'ip4trie':RadixTrieSet, 
   'fastlist':UDPSocketSet, 
}