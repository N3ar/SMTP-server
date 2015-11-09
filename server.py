#!/usr/bin/python

import getopt
import socket
import sys
from threading import Thread, Lock, Condition
import string

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
    def assign_thread(self, clientsocket):
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

        while True:
            with workerLock:
                # wait until socket assigned from client request
                while socketInUse is None:
                    workerReady.wait()
                # Initialize a ConnectionHandler for this SMTP connection
                successful_connection = ConnectionHandler(socketInUse)
                socketInUse = None
                workerDone.notify()

            # Handle connection outside of lock
            # Efficient and no global vars modified
            # TODO Are my assumptions correct? Or should this happen inside the lock because the socket is busy?
            successful_connection.handle()


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
        self.raw_message = ''
        self.rec_message = ''
        self.recipients = []
        self.message_contents = [None, None, self.recipients, None]
        self.client_state = ['HELO', 'MAIL FROM:', 'RCPT TO:', 'DATA']
        self.phase = 0
        # May want to track errors

    def handle(self):
        # Acknowledge message
        self.send(self.socket, '220 jfw222 SMTP CS4410MP3')
        # TEST PRINT #
        print('server: 220 jfw222 SMTP CS4410MP3')

        #
        while True:
            self.socket.settimeout(10)
            # TODO I have no idea how many bytes I should be ready to take
            self.raw_message += self.socket.recv(500)
            self.socket.settimeout(None)
            self.parse_msg(self, self.raw_message)


    # Force byte formatting and send
    def send(self, string):
        self.socket.send(string.encode('utf-8') + '\r\n')

    # Parse received message
    # TODO THIS IS WHERE I LEFT OFF - Needs to be updated with better string parsing.
    def parse_msg(self, raw):
        fragments = string.split(raw, '\r\n')
        raw = fragments[len(fragments) - 1]
        for i in range(len(fragments) - 1):
            if self.phase < 4:
                email = fragments[i] + '\r\n'
                cmd = self.command_errors(email)


    # Determine if there are command errors
    def command_errors(self, command): #stuff


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
