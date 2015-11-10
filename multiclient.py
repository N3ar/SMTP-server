#!/usr/bin/python
import sys
import socket
import datetime
from threading import Thread, Lock, Condition

# This is the multi-threaded client.  This program should be able to run
# with no arguments and should connect to "127.0.0.1" on port 8765.  It
# should run a total of 1000 operations, and be extremely likely to
# encounter all error conditions described in the README.

OPERATIONS = 1000
POOL_THREADS = 32

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
toaddr = sys.argv[3] if len(sys.argv) > 3 else "nobody@example.com"
fromaddr = sys.argv[4] if len(sys.argv) > 4 else "nobody@example.com"

# thread pool clone from server.py
class ThreadPool:
    def __init__(self):
        # Do I have to import locks used during init?
        global workerLock
        global workerReady
        global workerDone

        # TODO Or should I just use a global? :(
        self.numThreads = POOL_THREADS

    # Spawn 32 SMTPHandler Threads
    # TODO Initially I had this as a run method and it failed... I don't know why
        with workerLock:
            for i in range(self.numThreads):
                SMTPHandler()

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

def send(socket, message):
    # In Python 3, must convert message to bytes explicitly.
    # In Python 2, this does not affect the message.
    socket.send(message.encode('utf-8'))

def sendmsg(msgid, hostname, portnum, sender, receiver):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((hostname, portnum))

    send(s, "HELO %s\r\n" % socket.gethostname())
    print(s.recv(500))

    send(s, "MAIL FROM: %s\r\n" % sender)
    print(s.recv(500))


    send(s, "RCPT TO: %s\r\n" % receiver)
    print(s.recv(500))

    send(s, "DATA\r\nFrom: %s\r\nTo: %s\r\nDate: %s -0500\r\nSubject: msg %d\r\n\r\nContents of message %d end here.\r\n.\r\n" % (sender, receiver, datetime.datetime.now().ctime(), msgid, msgid))
    print(s.recv(500))

for i in range(1, 10):
    sendmsg(i, host, port, fromaddr, toaddr)