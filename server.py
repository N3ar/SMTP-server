#!/usr/bin/python

import getopt
import socket
import sys
#import threading
from threading import Thread, Lock, Condition

# Don't change 'host' and 'port' values below.  If you do, we will not be able to contact 
# your server when grading.  Instead, you should provide command-line arguments to this
# program to select the IP and port on which you want to listen.  See below for more
# details.
host = "127.0.0.1"
port = 8765

# value definitions
POOL_THREADS = 32

# global variables
socketInUse = None
numMessages = 0

# global locks and conditions
workerLock = Lock()                     #
workerReady = Condition(workerLock)     # SMTP thread lock and condition vars
workerDone = Condition(workerLock)      #

backupLock = Lock()                     #
backupStart = Condition(backupLock)     # locks and condition variable ensuring
mailDelivery = Condition(backupLock)    # backup and delivery don't overlap


# thread pool
class ThreadPool:
    def __init__(self):
        # Do I have to import locks used during init?
        global workerLock
        global workerReady
        global workerDone

        # TODO Or should I just use a global? :(
        self.numThreads = POOL_THREADS

    # Spawn 32 SMTPHandler Threads and 1 BackupHandler
    def run(self):
        with workerLock:
            for i in range(self.numThreads):
                SMTPHandler()
        BackupHandler()

    # If socket not in use, assign clientsocket
    def assignThread(self, clientsocket):
        # TODO why doesn't it make me redefine workerLock in this method after
        # TODO made me define socketInUse?
        global socketInUse

        with workerLock:
            while socketInUse is not None:
                workerDone.wait()
            socketInUse = clientsocket
            workerReady.notify()


# each SMTP handling thread
class SMTPHandler(Thread):
    def __init__(self):
        global workerLock
        # TODO I can't explain why this doesn't work here but did work in the threadpool run function
        #global socketInUse

        Thread.__init__(self)
        self.start()

    # handle successful SMTP connections
    def run(self):
        global socketInUse

        with workerLock:
            # wait until socket assigned from client request
            while socketInUse is None:
                workerReady.wait()
            # Initialize a ConnectionHandler for this SMTP connection
            successfulConnection = ConnectionHandler(socketInUse)
            socketInUse = None
            workerDone.notify()

        # Handle connection outside of lock
        # Efficient and no global vars modified
        # TODO Are my assumptions correct? Or should this happen inside the lock because the socket is busy?
        successfulConnection.handle()


# performs mail server backup
class BackupHandler(Thread):
    def __init__(self):
        global numMessages
        global backupLock
        global backupStart
        global mailDelivery

        Thread.__init__(self)
        self.start()

    def run(self):
        # Thread delivering message will wait for the backup process to complete and visa versa
        # NEED LOCK ON THIS AND DELIVERY
        while True:
            with backupLock:
                while numMessages % 32 is not 0:
                    backupStart.wait()
                # copy mailbox
                # clear "mailbox"
                print('Backup success, mailbox is empty') # TEST STATEMENT
                mailDelivery.notify()


# handle a single client request
class ConnectionHandler:
    def __init__(self, socket):
        global numMessages

        self.socket = socket
        #self.

    def handle(self):
        # Acknowledge message

# close main server loop
def serverloop():

    # write to mailbox

    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # mark the socket so we can rebind quickly to this port number
    # after the socket is closed
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # bind the socket to the local loopback IP address and special port
    serversocket.bind((host, port))
    # start listening with a backlog of 5 connections
    serversocket.listen(5)

    while True:
        # accept a connection
        (clientsocket, address) = serversocket.accept()
        ct = ConnectionHandler(clientsocket)
        ct.handle()

# You don't have to change below this line.  You can pass command-line arguments
# -h/--host [IP] -p/--port [PORT] to put your server on a different IP/port.
opts, args = getopt.getopt(sys.argv[1:], 'h:p:', ['host=', 'port='])

for k, v in opts:
    if k in ('-h', '--host'):
        host = v
    if k in ('-p', '--port'):
        port = int(v)

print("Server coming up on %s:%i" % (host, port))
serverloop()
