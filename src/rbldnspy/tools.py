from socket import inet_aton,inet_ntoa
import struct
from dateutil.relativedelta import relativedelta

def ipreverse(ip):
    #todo: ip6: set delim=:, check for ::
    delim='.'
    parts=ip.split(delim)
    parts=reversed(parts)
    return ".".join(parts)
    
  
def ip2long(ip):
    packed = inet_aton(ip)
    lng = struct.unpack("!L", packed)[0]
    return lng

def long2ip(lng):
    packed = struct.pack("!L", lng)
    ip=inet_ntoa(packed)
    return ip


def cidr2lowerupper(ip_str, mask_cidr):
    """returns tuple ((network_itn, network_str), (broadcast_int, broadcast_str))
    adapted from http://code.activestate.com/recipes/577375-ip-address-and-cidr-mask-conversion-to-network-and/"""
    ip_int = ip2long(ip_str)
    mask_int = (~0 << (32 - mask_cidr));
    net_int = (ip_int & mask_int);
    brdcast_int = (net_int | ~(mask_int));
    return net_int,brdcast_int
    
def ip_pad(ippart,fillupper=False):
    """completes partial ip. pads missing quads automatically.
    :param fillupper: if true, missing quads are padded with value 255, if false, they are padded with 0
    """
    sp=ippart.split('.')
    fill='0'
    if fillupper:
        fill='255'
    
    quads=[]
    for part in sp:
        if part=='':
            continue
        quads.append(str(part))
    
    while len(quads)<4:
        quads.append(fill)
    
    return '.'.join(quads)

def ip4range(iprange):
    """convert an rbldnsnd iprange in lower and uper ip"""
    assert not ('/' in iprange and '-' in iprange),'cidr and dash notation is not possible'
    if '/' in iprange:
        #cidr range
        ippart,mask=iprange.split('/',1)
        mask=int(mask)
        ip=ip_pad(ippart)
        lowerlong,upperlong=cidr2lowerupper(ip,mask)
        lowerip=long2ip(lowerlong)
        upperip=long2ip(upperlong)
        
    elif '-' in iprange:
        lpart,upart=iprange.split('-',1)
        lowerip=ip_pad(lpart)
        
        #upperip only one octet? fill last specified octed from lpart
        if '.' not in upart:
            sp=lpart.split('.')
            sp[-1]=upart
            upart='.'.join(sp)
        
        upperip=ip_pad(upart,True)
    else:
        lowerip=ip_pad(iprange)
        upperip=ip_pad(iprange,True)
        
    return lowerip,upperip

def ttl2int(ttl):
        modifiers={
        's':1,
        'm':60,
        'h':3600,
        'd':24*3600,
        'w':7*12*3600,           
        }
        mod=ttl[-1]
        if mod in modifiers:
            ret=int(ttl[:-1])*modifiers[mod]
        else:
            ret=int(ttl)
        return ret
    
def secs2human(secs):
    delta=relativedelta(seconds=secs)
    attrs = ['years', 'months', 'days', 'hours', 'minutes', 'seconds']
    ret= ['%d %s' % (getattr(delta, attr), getattr(delta, attr) > 1 and attr or attr[:-1])  for attr in attrs if getattr(delta, attr)]
    return ",".join(ret)