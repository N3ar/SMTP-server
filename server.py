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
FILE_NAME = 'mailbox'

# global variables
socketInUse = None
numMessages = 0
backupInProg = 0

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

    # Spawn 32 SMTPHandler Threads
    def run(self):
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
            print(socketInUse)
            workerReady.notify()


# each SMTP handling thread
class SMTPHandler(Thread):
    def __init__(self):
        global workerLock
        # TODO I can't explain why this doesn't work here but did work in the threadpool run function
        global socketInUse

        Thread.__init__(self)
        self.start()

    # handle successful SMTP connections
    def run(self):
        #global socketInUse

        while True:
            with workerLock:
                # wait until socket assigned from client request
                while socketInUse is None:
                    workerReady.wait()
                # Initialize a ConnectionHandler for this SMTP connection
                print('1) ' + socketInUse)
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
                while numMessages is 0 or numMessages % 32 is not 0:
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
        self.data = []
        self.message_contents = [None, None, self.recipients, self.data]
        self.client_stage = ['HELO', 'MAIL FROM', 'RCPT TO', 'DATA']
        self.delimiters = [' ', ':', ':', '']
        self.phase = 0
        # May want to track errors

    # Handle individual connection
    def handle(self):
        # Acknowledge message
        self.send(self.socket, '220 jfw222 SMTP CS4410MP3')
        # TEST PRINT #
        print('server: 220 jfw222 SMTP CS4410MP3')

        # Handle based on phase
        while self.phase is not None:
            if self.phase is 0:
                self.helo_handler()
            elif self.phase is 1:
                self.from_handler()
            elif self.phase is 2:
                self.to_handler()
            elif self.phase is 3:
                self.data_handler()
        self.socket.close()

    # Force byte formatting and send
    def send(self, string):
        self.socket.send(string.encode('utf-8') + '\r\n')

    # Parse received message
    def parse_msg(self):
        self.socket.settimeout(10)
        while True:
            if self.raw_message.find('\r\n') is not -1:
                break
            self.raw_message += self.socket.recv(500)
        self.socket.settimeout(None)

        command = self.raw_message[0:self.raw_message.find('\r\n')]
        self.raw_message = self.raw_message[self.raw_message.find('\r\n')+2:]
        print(self.raw_message)
        return command

    # Determine if there are command errors
    def command_errors(self, stage, brkpnt, content):

        # HELO Errors
        if self.phase is 0:
            # Correct command, some other syntax error
            if stage is self.client_stage[self.phase]:
                self.send('501 Syntax: HELO yourhostname')
                # TODO REMOVE TEST #
                print('server: 501 Syntax: HELO yourhostname')

            # Incorrect, but valid, command
            elif stage is self.client_stage[1] or stage is self.client_stage[2] or stage is self.client_stage[3]:
                self.send('503 Error: need HELO command')
                # TODO REMOVE TEST #
                print('server: 503 Error: need HELO command')

            # Invalid command/ catch all
            else:
                self.send('500 Error: command not recognized')
                # TODO REMOVE TEST #
                print('server: 500 Error: command not recognized')
            return

        # MAIL FROM Errors
        elif self.phase is 1:
            # Correct command, valid breakpoint, bad email addr
            if stage is self.client_stage[self.phase] and brkpnt is not -1:
                self.send('555 <' + content + '>: Sender address rejected')
                # TODO REMOVE TEST #
                print('server: 555 <' + content + '>: Sender address rejected')

            # Correct command, invalid breakpoint
            elif stage is self.client_stage[self.phase]:
                self.send('501 Syntax: MAIL FROM: email@host.com')
                # TODO REMOVE TEST #
                print('server: 501 Syntax: MAIL FROM: email@host.com')

            # Incorrect command, HELO received
            elif stage is self.client_stage[0]:
                self.send('503 Error: duplicate HELO')
                # TODO REMOVE TEST #
                print('server: 503 Error: duplicate HELO')

            # Incorrect command, one of the other 2 received
            elif stage is self.client_stage[2] or stage is self.client_stage[3]:
                self.send('503 Error: need MAIL FROM command')
                # TODO REMOVE TEST #
                print('server: 503 Error: need MAIL FROM command')

            # Invalid command, catch all
            else:
                self.send('500 Error: command not recognized')
                # TODO REMOVE TEST #
                print('server: 500 Error: command not recognized')
            return

        # RCPT TO Errors
        elif self.phase is 2:
            # Correct command, valid breakpoint, bad email addr
            if stage is self.client_stage[self.phase] and brkpnt is not -1:
                self.send('555 <' + content + '>: Sender address rejected')
                # TODO REMOVE TEST #
                print('server: 555 <' + content + '>: Sender address rejected')

            # Correct command, invalid breakpoint
            elif stage is self.client_stage[self.phase]:
                self.send('501 Syntax: RCPT TO: email@host.com')
                # TODO REMOVE TEST #
                print('server: 501 Syntax: RCPT TO: email@host.com')

            # Incorrect command, HELO received
            elif stage is self.client_stage[0]:
                self.send('503 Error: duplicate HELO')
                # TODO REMOVE TEST #
                print('server: 503 Error: duplicate HELO')

            # Incorrect command, MAIL FROM received
            elif stage is self.client_stage[1]:
                self.send('503 Error: nested MAIL command')
                # TODO REMOVE TEST #
                print('server: 503 Error: nested MAIL command')

            # Incorrect command, one of the other 2 received
            elif stage is self.client_stage[3]:
                self.send('503 Error: need MAIL FROM command')
                # TODO REMOVE TEST #
                print('server: 503 Error: need MAIL FROM command')

            # Invalid command, catch all
            else:
                self.send('500 Error: command not recognized')
                # TODO REMOVE TEST #
                print('server: 500 Error: command not recognized')
            return

        # DATA errors
        elif self.phase is 3:
            if stage is self.client_stage[self.phase] and brkpnt is not -1:
                self.send('555 <' + content + '>: Sender address rejected')
                # TODO REMOVE TEST #
                print('server: 555 <' + content + '>: Sender address rejected')

            # Correct command, invalid breakpoint
            elif stage is self.client_stage[self.phase]:
                self.send('501 Syntax: MAIL FROM: email@host.com')
                # TODO REMOVE TEST #
                print('server: 501 Syntax: MAIL FROM: email@host.com')

            # Incorrect command, HELO received
            elif stage is self.client_stage[0]:
                self.send('503 Error: duplicate HELO')
                # TODO REMOVE TEST #
                print('server: 503 Error: duplicate HELO')

            # Incorrect command, MAIL FROM received
            elif stage is self.client_stage[1]:
                self.send('503 Error: nested MAIL command')
                # TODO REMOVE TEST #
                print('server: 503 Error: nested MAIL command')

            # Incorrect command, one of the other 2 received
            elif stage is self.client_stage[2]:
                self.send('503 Error: OH no')
                # TODO REMOVE TEST #
                print('server: WTF Error: this shouldnt happen')

            # Invalid command, catch all
            else:
                self.send('500 Error: command not recognized')
                # TODO REMOVE TEST #
                print('server: 500 Error: command not recognized')
            return

    # Expecting a HELO
    def helo_handler(self):
        self.rec_message = self.parse_msg()

        # Ensure received message has contents
        if self.rec_message is None:
            print('error handle')
            return

        # Process parts of message
        self.rec_message = self.rec_message.strip()
        brkpnt = self.rec_message.find(self.delimiters[self.phase])
        stage = string.upper(self.rec_message[0:brkpnt].strip())
        content = self.rec_message[brkpnt:].strip()
        # TODO REMOVE TEST #
        print('client: ' + self.rec_message)

        # Correct command
        if stage is self.client_stage[self.phase] and brkpnt is not -1 and content.find(' ') is -1:
            self.message_contents[self.phase] = content
            self.phase += 1
            self.send('250 jfw222')
            # TODO REMOVE TEST #
            print('server: 250 jfw222')

        else:
            self.command_errors(stage, brkpnt, content)

    # Expecting a MAIL FROM
    def from_handler(self):
        self.rec_message = self.parse_msg()

        # Ensure received message has contents
        if self.rec_message is None:
            print('error handle')
            return

        # Process parts of message
        self.rec_message = self.rec_message.strip()
        brkpnt = self.rec_message.find(self.delimiters[self.phase])
        stage = string.upper(self.rec_message[0:brkpnt].strip())
        content = self.rec_message[brkpnt:].strip()
        # TODO REMOVE TEST #
        print('client: ' + self.rec_message)

        # Correct command
        if content is not None and stage is self.client_stage[self.phase] and brkpnt is not -1 and content.find(' ') is -1:
            self.message_contents[self.phase] = content
            self.phase += 1
            self.send('250 OK')
            # TODO REMOVE TEST #
            print('server: 250 OK')

        else:
            self.command_errors(stage, brkpnt, content)

    # Expecting a RCPT TO
    def to_handler(self):
        self.rec_message = self.parse_msg()

        # Ensure received message has contents
        if self.rec_message is None:
            print('error handle')
            return

        # Process parts of message
        self.rec_message = self.rec_message.strip()
        brkpnt = self.rec_message.find(self.delimiters[self.phase])
        stage = string.upper(self.rec_message[0:brkpnt].strip())
        content = self.rec_message[brkpnt:].strip()
        # TODO REMOVE TEST #
        print('client: ' + self.rec_message)

        # Correct command
        if content is not None and stage is self.client_stage[self.phase] and brkpnt is not -1 and content.find(' ') is -1:
            self.message_contents[self.phase] = content
            self.phase += 1
            self.send('250 OK')
            # TODO REMOVE TEST #
            print('server: 250 OK')

        else:
            self.command_errors(stage, brkpnt, content)

    # Expecting a DATA:
    def data_handler(self):
        # Declarations
        data_contents = None

        # Handle case for multiple recipients
        if self.raw_message.find('RCPT TO') is not -1:
            self.phase -= 1
            self.to_handler()
            return

        # Print
        self.send('354 End data with <CR><LF>.<CR><LF>')
        print('server: 354 End data with <CR><LF>.<CR><LF>')

        self.rec_message = self.parse_msg()

        # Ensure received message has contents
        if self.rec_message is None:
            print('error handle')
            return

        # Check to see if only content is period
        self.socket.settimeout(10)
        while self.rec_message is not '.':
            data_contents.append(self.rec_message)
            self.rec_message = self.parse_msg()
        self.socket.settimeout(None)

        self.data = data_contents

        # Backup if appropriate
        with backupLock:
            if numMessages > 0 and numMessages % 32 is 0:
                backupStart.notify()
                backupInProg = 1
                while backupInProg is 1:
                    mailDelivery.wait()

            self.send_message()

        self.phase = None

    # Data contents filled out and sent
    def send_message(self):
        # Initialize variables
        full_message = []
        main_mail_box = open(FILE_NAME, 'a')

        # Add to total messages
        numMessages += 1

        # Fill out message
        full_message.append('Received: from ' + self.message_contents[0] + ' by jfw222 (CS4410MP3)')
        full_message.append('Number: ' + str(self.numMessages))
        full_message.append('From: ' + self.message_contents[1])
        for i in self.recipients:
            full_message.append('To: ' + self.recipients[i])
        for i in self.data:
            full_message.append(self.data[i])

        # Add message to mailbox file
        for i in full_message:
            main_mail_box.write(full_message[i] + '\n\r')
        main_mail_box.write('\n\r')
        main_mail_box.close()

        # confirm delivery
        self.send('250 OK: delivered message ' + str(numMessages))
        # TODO REMOVE TEST #
        print('server: 250 OK: delivered message ' + str(numMessages))

    # Handle timeout
    def timeout(self):
        self.phase = None
        self.send('421 4.4.2 jfw222 Error: timeout exceeded')
        # TODO REMOVE TEST #
        print('server: 421 4.4.2 jfw222 Error: timeout exceeded')


# close main server loop
def serverloop():

    # Create mailbox
    newBox = open(FILE_NAME, 'w')
    newBox.write('')
    newBox.close()

    # Prepare SMTP connection handlers & Backup handler spawned by
    pool = ThreadPool()
    BackupHandler()

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
        pool.assign_thread(clientsocket)

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
