

class Zone(object):
    def __init__(self,name):
        self.datasets=[]
        self.name=name
        
    def add_dataset(self,dataset):
        self.datasets.append(dataset)
        
    def lookup(self,query):
        """Returns answer of given query after consulting all datasets Returns None for NXDOMAIN"""
        soa=None
        ns=None
        nsttl=None
        soattl=None
        
        reslist=[]
        for dataset in self.datasets:                
            if ns==None and dataset.ns!=None:
                ns=dataset.ns
                if dataset.nsttl!=0:
                    nsttl=dataset.nsttl
                
            if soa==None and dataset.soa!=None:
                soa=dataset.soa[1:]
                soattl=dataset.soa[0]
                
            if query!='':
                result = dataset.get(query)
                if type(result)==list:
                    reslist.extend(result)
                else:
                    reslist.append(result)
               
        if ns==None:
            ns=[] 
        retpack={
                 'SOA':soa,
                 'NS':ns,
                'results':reslist
        }
        if nsttl!=None:
            retpack['NSTTL']=nsttl
        if soattl!=None:
            retpack['SOATTL']=soattl
        return retpack
    
    def reload_all(self):
        for ds in self.datasets:
            ds.reload()
            
    def __str__(self):
        return self.name
            
    def is_available(self):
        for dataset in self.datasets:
            if not dataset.available:
                return False
        return True
        
    def is_reloading(self):
        for dataset in self.datasets:
            if dataset.reloading:
                return True
        return False
        
