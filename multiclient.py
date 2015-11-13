#!/usr/bin/python
import sys
import socket
import datetime
from threading import Thread, Lock, Condition
import random
import string

# This is the multi-threaded client.  This program should be able to run
# with no arguments and should connect to "127.0.0.1" on port 8765.  It
# should run a total of 1000 operations, and be extremely likely to
# encounter all error conditions described in the README.

OPERATIONS = 1000
POOL_THREADS = 32
socketInUse = None

workerLock = Lock()
workerReady = Condition(workerLock)
workerDone = Condition(workerLock)

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
                SimulatedClient()

    # If socket not in use, assign clientsocket
    def assign_thread(self, clientsocket):
        # TODO why doesn't it make me redefine workerLock in this method after
        # TODO made me define socketInUse?
        global socketInUse
        global OPERATIONS

        with workerLock:
            while socketInUse is not None or OPERATIONS <= 0:
                workerDone.wait()
            socketInUse = clientsocket
            workerReady.notifyAll()


class SimulatedClient(Thread):
    def __init__(self):
        global workerLock
        global workerDone
        global workerReady

        Thread.__init__(self)
        self.start()

    def run(self):
        global socketInUse
        global OPERATIONS

        while True:
            with workerLock:
                while socketInUse is None:
                    workerReady.wait()
                communication = ConnectionHandler(socketInUse)
                socketInUse = None
                workerDone.notifyAll()
                OPERATIONS -= 1
            communication.handle()
            print('ops remaining: ' + str(OPERATIONS))


class ConnectionHandler:
    def __init__(self, socket):
        self.socket = socket
        self.raw_message = ''

    # Force byte formatting and send
    def send(self, mailstring):
        try:
            self.socket.send(mailstring.encode('utf-8') + '\r\n')
        except socket.error:
            self.socket.close()
            return

    def handle(self):
        commands = ['HELO', 'MAIL FROM:', 'RCPT TO:', 'DATA']
        #complete = False
        #while complete is False:
        if randomize() is True:
            command = random.randrange(0, 5)
            if command == 4:
                self.send(alter('HELO someN3RD'))
            else:
                self.send(commands[command] + alter(' someN3RD'))
        else:
            self.send('HELO someN3RD')
        reply = self.parse_msg() # will need to parse response
        if reply is not None:
            print('server: ' + reply)
        # MAIL FROM
        #while complete is False:
        if randomize() is True:
            command = random.randrange(0, 5)
            if command == 4:
                self.send(alter('MAIL FROM: some@N3RD.ru'))
            else:
                self.send(commands[command] + alter(' some@N3RD.ru'))
        else:
            self.send('MAIL FROM: some@N3RD.ru')
        reply = self.parse_msg()
        if reply is not None:
            print('server: ' + reply)
        # RCPT TO
        #while complete is False:
        for i in range(random.randint(1,4)):
            if randomize() is True:
                command = random.randrange(0, 5)
                if command == 4:
                    self.send(alter('RCPT TO: some@N3RD.ru'))
                else:
                    self.send(commands[command] + alter(' some@N3RD.ru'))
            else:
                self.send('RCPT TO: some@N3RD.ru')
            reply = self.parse_msg()
            if reply is not None:
                print('server: ' + reply)
        # DATA
        #while complete is False:
        if randomize() is True:
            self.send(alter('DATA\r\n'))
        else:
            self.send('DATA\r\n')
        # DATA CONTENT
        #while complete is False:
        if randomize() is True:
            self.send(alter(' Nerdy content from someN3RD is nerdy.\r\n.\r\n'))
        else:
            self.send(' Nerdy content from someN3RD is nerdy.\r\n.\r\n')
        reply = self.parse_msg()
        if reply is not None:
            print('server: ' + reply)

    def parse_msg(self):
        try:
            self.socket.settimeout(10)
            while True:
                if self.raw_message.find('\r\n') != -1:
                    break
                self.raw_message += self.socket.recv(500)
            self.socket.settimeout(None)
        except socket.error:
            self.socket.close()
            return

        command = self.raw_message[0:self.raw_message.find('\r\n')]
        self.raw_message = self.raw_message[self.raw_message.find('\r\n')+2:]
        return command


def randomize():
    if random.randrange(0, 10) >= 9:
        return True
    return False


#
# http://stackoverflow.com/questions/367586/generating-random-text-strings-of-a-given-pattern
def alter(content):
    return "".join([random.choice(string.letters) for i in content])


def send(socket, message):
    # In Python 3, must convert message to bytes explicitly.
    # In Python 2, this does not affect the message.
    socket.send(message.encode('utf-8'))


pool = ThreadPool()
while True:
    try:
        # Provided server.py code
        csocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        csocket.connect((host, port))
    except socket.error:
        print('connection error')
        csocket.close()
    pool.assign_thread(csocket)

