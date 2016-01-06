import os
import pwd
import grp
import atexit

class DaemonStuff(object):
    """Makes a daemon out of a python program"""

    def __init__(self,pidfilename):
        self.pidfile=pidfilename

    def delpid(self):
        """Delete the pid file"""
        try:
            os.remove(self.pidfile)
        except:
            pass

    def writepid(self,pid=None):
        if pid==None:
            pid=os.getpid()
        atexit.register(self.delpid)
        pidfd=os.open(self.pidfile, os.O_WRONLY|os.O_CREAT, 0644)
        os.write(pidfd, "%s\n" % pid)
        os.close(pidfd)

    def createDaemon(self):
        """Detach a process from the controlling terminal and run it in the
        background as a daemon.
        Example from: http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/278731
        """

        try:
            pid = os.fork()
        except OSError, e:
            raise Exception, "%s [%d]" % (e.strerror, e.errno)

        if (pid == 0):
            os.setsid()
            try:
                pid = os.fork()    # Fork a second child.
            except OSError, e:
                raise Exception, "%s [%d]" % (e.strerror, e.errno)

            if (pid == 0):    # The second child.
                os.chdir('/')
                os.umask(0)
            else:
                # exit() or _exit()?  See below.
                os._exit(0)    # Exit parent (the first child) of the second child.
        else:
            os._exit(0)    # Exit parent of the first child.

        import resource        # Resource usage information.
        maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
        if (maxfd == resource.RLIM_INFINITY):
            maxfd = 1024

        # Iterate through and close all file descriptors.
        for fd in range(0, maxfd):
            try:
                os.close(fd)
            except OSError:    # ERROR, fd wasn't open to begin with (ignored)
                pass
        os.open('/dev/null', os.O_RDWR)    # standard input (0)

        # Duplicate standard input to standard output and standard error.
        os.dup2(0, 1)            # standard output (1)
        os.dup2(0, 2)            # standard error (2)


        # write pidfile
        if self.pidfile!=None:
            self.writepid()
        return(0)

    def drop_privs(self,username=None,groupname=None,umask=None):
        if umask:
            #umask=077
            os.umask(umask)
        
        if username!=None:
            running_uid = pwd.getpwnam(username).pw_uid
            os.setuid(running_uid)
        
        if groupname!=None:
            running_gid = grp.getgrnam(groupname).gr_gid
            os.setgid(running_gid)


        
        
        