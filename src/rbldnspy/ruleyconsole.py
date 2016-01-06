import os
import sys
import time
import string
import socket
import thread
import select
import traceback

class ConsoleConstants(object):
    COLOR_BLACK=0
    COLOR_RED=1
    COLOR_GREEN=2
    COLOR_BROWN=3
    COLOR_BLUE=4
    COLOR_MAGENTA=5
    COLOR_CYAN=6
    COLOR_GRAY=7
    COLOR_GREY=7
    COLOR_WHITE=8
    COLOR_YELLOW=9
    
    CODE_RESET="\x1b[0m"
    CODE_CLEAR="\x1bc"
    
    MODE_DEFAULT=0
    MODE_BOLD=1
    MODE_BLINK=2
    MODE_NOBLINK=3
    
    CONSOLE_BACKGROUNDS={
        COLOR_BLACK:'40',
        COLOR_RED:'41',
        COLOR_GREEN:'4',
        COLOR_BROWN:'43',
        COLOR_BLUE:'44',
        COLOR_MAGENTA:'45',
        COLOR_CYAN:'46',
        COLOR_WHITE:'47',        
    }
    
    CONSOLE_MODES={
       MODE_DEFAULT:'0',
       MODE_BOLD:'1',
       MODE_BLINK:'5',
       MODE_NOBLINK:'25',   
    }
    
    CONSOLE_FOREGROUNDS={
       COLOR_WHITE:'00',
       COLOR_BLACK:'30',
       COLOR_RED:'31',
       COLOR_GREEN:'32',
       COLOR_BROWN:'33',
       COLOR_BLUE:'34',
       COLOR_MAGENTA:'35',
       COLOR_CYAN:'36',
       COLOR_GRAY:'37',
       #special hack: yellow=brown+bold
       COLOR_YELLOW:"33;1",      
    }


def get_term_size():
    rows, columns = os.popen('stty size', 'r').read().split()
    return rows,columns


def make_escaped_string(content,fg=None,bg=None,mode=None,reset=True):
    """returns the content encapsulated in the escapesequences to print coloured output"""
    commandlist=[]
    
    if fg!=None and fg in ConsoleConstants.CONSOLE_FOREGROUNDS:
        commandlist.append(ConsoleConstants.CONSOLE_FOREGROUNDS[fg])
        
    if bg!=None and bg in ConsoleConstants.CONSOLE_BACKGROUNDS:
        commandlist.append(ConsoleConstants.CONSOLE_BACKGROUNDS[bg])

    esc=_buildescape(commandlist)
    ret=esc+str(content)
    if reset:
        ret=ret+ConsoleConstants.CODE_RESET
    return ret

def _buildescape(commandlist):
    """builds escape sequences"""
    escseq="\x1b["
    for cmd in commandlist:
        if cmd!=None:
            escseq=escseq+cmd+";"
    escseq=escseq[0:-1] # strip last ;
    escseq=escseq+"m"
    return escseq

class RuleyConsole(object):
    def __init__(self,template=None,templatevars=None):
        self.outputstream=sys.stdout
        self.stoplooping=0
        if template==None:
            self.template=""
        else:
            self.template=template
            
        if templatevars==None:
            self.templatevars={}
        else:
            self.templatevars=templatevars
    
    def loop(self,template=None,templatevars=None,refreshtime=1):
        """Loop the template to the current outputstream until stop_looping is called
        template : a standard python template string
        templatevars : dict, key=template keys, var=direct values or callable
        refreshtime : in seconds
        """
        if template==None:
            template=self.template
            
        if templatevars==None:
            templatevars=self.templatevars

        t=string.Template(template)
        
        while True:
            output=self._apply_template(t, templatevars)
            self.clear()
            self._write_to_stream(output)
            
            if self.stoplooping:
                self.stoplooping=0
                break
            time.sleep(refreshtime)

    
    def _apply_template(self,templateobj,templatevars):
        realvars={}
        for k,v in templatevars.iteritems():
            if callable(v):
                value=v()
            else:
                value=v
            realvars[k]=value
            
        output=templateobj.safe_substitute(realvars)
        return output
    
    def stop_looping(self):
        self.stoplooping=1
        
    def clear(self):
        self._write_to_stream(ConsoleConstants.CODE_CLEAR)
    
    def _write_to_stream(self,content,stream=None):
        if stream==None:
            stream=self.outputstream
        if hasattr(stream,'write'):
            stream.write(content)
        elif hasattr(stream,'sendall'):
            stream.sendall(content)
    
    def run_remote_console(self,port,bind="127.0.0.1"):
        """run a remote console with predefined template"""
        self.start_remote_console(port, self._remote_template_handler, bind)
        pass
    
    def _remote_template_handler(self,sock,address):
        sock.setblocking(0)
        try:
            t=string.Template(self.template)
            while True:
                ready = select.select([sock], [], [], 0.1)
                if ready[0]:
                    content=sock.recv(4096)
                    ctrl_c= "\xff\xf4\xff\xfd\x06"
                    if ctrl_c in content:
                        sock.close()
                        return
                output=self._apply_template(t, self.templatevars)
                self._write_to_stream(ConsoleConstants.CODE_CLEAR,stream=sock)
                self._write_to_stream(output,stream=sock)
                time.sleep(0.5)
        except Exception,e:
            import logging
            fmt=traceback
            logging.getLogger().error(traceback.format_exc(fmt))
            pass

    
    def start_remote_console(self,port,callback=None,bind="127.0.0.1"):
        """run a remote console
        callback: callable with arguments (socket, address)
        bind: bind ip
        """
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind((bind, port))
        thread.start_new_thread(self._serversock_listen, (serversocket,callback,))
        return serversocket
    
    def _serversock_listen(self,sock,callback):
        sock.listen(5)
        while True:
            (clientsocket, address) = sock.accept()
            if callback and callable(callback):
                thread.start_new_thread(callback, (clientsocket,address))
                
            
    
if __name__=='__main__':
    f=time.time
    colortime=make_escaped_string("${thetime}",ConsoleConstants.COLOR_RED)
    template="""Hello World!
    The time is %s
    
    """%colortime
    templatevars=dict(thetime=f)
    rc=RuleyConsole(template,templatevars)
    port=1337
    rc.run_remote_console(port)
    print "telnet localhost %s"%port
    while True:
        time.sleep(0.5)
    