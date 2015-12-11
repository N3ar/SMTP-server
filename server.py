#!/usr/bin/python

import getopt
import socket
import sys
from threading import Thread, Lock, Condition
import string
import shutil
import os

# Don't change 'host' and 'port' values below.  If you do, we will not be able to contact 
# your server when grading.  Instead, you should provide command-line arguments to this
# program to select the IP and port on which you want to listen.  See below for more
# details.
host = "127.0.0.1"
port = 8765

# value definitions
POOL_THREADS = 32
FILE_NAME = 'mailbox'
FAULT_TOLERANCE = 10

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
        # Global variables
        global workerLock
        global workerReady
        global workerDone

        # Local variables
        self.numThreads = POOL_THREADS

        # Spawn 32 SMTPHandler Threads
        with workerLock:
            for i in range(self.numThreads):
                SMTPHandler()

    # If socket not in use, assign clientsocket
    def assign_thread(self, clientsocket):
        # global variables
        global socketInUse

        # Assign SMTP handlers to sockets
        with workerLock:
            while socketInUse is not None:
                workerDone.wait()
            socketInUse = clientsocket
            workerReady.notifyAll()


# each SMTP handling thread
class SMTPHandler(Thread):
    def __init__(self, num):
        # Global variables
        global workerLock
        global socketInUse

        # Local variable
        self.num = num

        # Start SMTP Handler thread
        Thread.__init__(self)
        self.start()

    # handle successful SMTP connections
    def run(self):
        # Global variables
        global workerLock
        global socketInUse

        # With lock, create ConnectionHandler object & pass it socket w/ conn.
        while True:
            with workerLock:
                # wait until socket assigned from client request
                while socketInUse is None:
                    workerReady.wait()
                successful_connection = ConnectionHandler(socketInUse)
                socketInUse = None
                workerDone.notifyAll()
            # "Handle" connection: digest mail
            successful_connection.handle()


# performs mail server backup
class BackupHandler(Thread):
    def __init__(self):
        # Global variables
        global numMessages
        global backupLock
        global backupStart
        global mailDelivery

        # Start Backup Handler thread
        Thread.__init__(self)
        self.start()

    # Execute backups
    def run(self):
        # Global variable
        global backupInProg

        # Backup thread runs continuously
        while True:
            # Backup thread waits for a notification from the handler that
            # there are 32 messages to backup
            with backupLock:
                while (numMessages == 0 or numMessages % 32 != 0) or backupInProg == 0:
                    backupStart.wait()

                # copy mailbox - Inspiration to use shutil from below link.
                # http://stackoverflow.com/questions/123198/how-do-i-copy-a-file-in-python
                backup_filename = './' + FILE_NAME + '.' + str(numMessages-31) + '-' + str(numMessages)
                shutil.copyfile('./' + FILE_NAME, backup_filename)
                os.remove('./' + FILE_NAME)
                cleared_box = open(FILE_NAME, 'w')
                cleared_box.write('')
                cleared_box.close()

                # Complete backup
                backupInProg = 0
                mailDelivery.notifyAll()


# handle requests from socket
class ConnectionHandler:
    def __init__(self, socket):
        # Global variables
        global numMessages

        # Local variables
        self.socket = socket
        self.raw_message = ''
        self.rec_message = ''
        self.recipients = []
        self.data = []
        self.message_contents = [None, None, self.recipients, self.data]
        self.client_stage = ['HELO', 'MAIL FROM', 'RCPT TO', 'DATA', 'nope']
        self.delimiters = [' ', ':', ':', ' ', '']
        self.phase = 0
        self.errors = 0

    # Handle individual connection
    def handle(self):
        # Acknowledge message
        self.send('220 jfw222 SMTP CS4410MP3')

        # Handle differently based on phase
        while self.phase < 4 and self.errors < FAULT_TOLERANCE:
            if self.phase == 0:
                self.helo_handler()
            elif self.phase == 1:
                self.from_handler()
            elif self.phase == 2:
                self.to_handler()
            elif self.phase == 3:
                self.data_handler()

        # Close socket after
        self.socket.close()

    # Force byte formatting and send
    def send(self, mailstring):
        # Make sure socket isn't closed w/ try
        try:
            self.socket.send(mailstring.encode('utf-8') + '\r\n')
        except socket.error:
            self.socket.close()
            self.errors += 1
            return

    # Parse received message
    def parse_msg(self):
        # Make sure socket isn't closed w/ try
        try:
            # Account for potential timeout (10 sec)
            self.socket.settimeout(10)
            while True:
                if self.raw_message.find('\r\n') != -1:
                    break
                self.raw_message += self.socket.recv(500)
            self.socket.settimeout(None)

        # Timeout with socket issues
        except socket.error:
            self.timeout()
            return '.'

        # Parse this phase's command from the rest of the content
        command = self.raw_message[0:self.raw_message.find('\r\n')]
        self.raw_message = self.raw_message[self.raw_message.find('\r\n')+2:]
        return command

    # Determine if there are command errors
    def command_errors(self, stage, brkpnt, content):
        # HELO Errors
        if self.phase == 0:
            # Correct command, some other syntax error
            if stage == self.client_stage[self.phase]:
                self.send('501 Syntax: HELO yourhostname')
            # Incorrect, but valid, command
            elif stage == self.client_stage[1] or stage == self.client_stage[2] or stage == self.client_stage[3]:
                self.send('503 Error: need HELO command')
            # Invalid command/ catch all
            else:
                self.send('500 Error: command not recognized')
            return

        # MAIL FROM Errors
        elif self.phase == 1:
            # Correct command, valid breakpoint, bad email addr
            if stage == self.client_stage[self.phase] and brkpnt != -1:
                self.send('555 <' + content + '>: Sender address rejected')
            # Correct command, invalid breakpoint
            elif stage == self.client_stage[self.phase]:
                self.send('501 Syntax: MAIL FROM: email@host.com')
            # Incorrect command, HELO received
            elif stage == self.client_stage[0]:
                self.send('503 Error: duplicate HELO')
            # Incorrect command, one of the other 2 received
            elif stage == self.client_stage[2] or stage == self.client_stage[3]:
                self.send('503 Error: need MAIL FROM command')
            # Invalid command, catch all
            else:
                self.send('500 Error: command not recognized')
            return

        # RCPT TO Errors
        elif self.phase == 2:
            # Correct command, valid breakpoint, bad email addr
            if stage == self.client_stage[self.phase] and brkpnt != -1:
                self.send('555 <' + content + '>: Sender address rejected')
            # Correct command, invalid breakpoint
            elif stage == self.client_stage[self.phase]:
                self.send('501 Syntax: RCPT TO: email@host.com')
            # Incorrect command, HELO received
            elif stage == self.client_stage[0]:
                self.send('503 Error: duplicate HELO')
            # Incorrect command, MAIL FROM received
            elif stage == self.client_stage[1]:
                self.send('503 Error: nested MAIL command')
            # Incorrect command, one of the other 2 received
            elif stage == self.client_stage[3]:
                self.send('503 Error: need MAIL FROM command')
            # Invalid command, catch all
            else:
                self.send('500 Error: command not recognized')
            return

        # DATA errors
        elif self.phase == 3:
            if stage == self.client_stage[self.phase] and brkpnt != -1:
                self.send('555 <' + content + '>: Sender address rejected')
            # Correct command, invalid breakpoint
            elif stage == self.client_stage[self.phase]:
                self.send('501 Syntax: MAIL FROM: email@host.com')
            # Incorrect command, HELO received
            elif stage == self.client_stage[0]:
                self.send('503 Error: duplicate HELO')
            # Incorrect command, MAIL FROM received
            elif stage == self.client_stage[1]:
                self.send('503 Error: nested MAIL command')
            # Incorrect command, one of the other 2 received
            elif stage == self.client_stage[2]:
                self.send('503 Error: OH no')
            # Invalid command, catch all
            else:
                self.send('500 Error: command not recognized')
            return

    # Handles HELO commands
    def helo_handler(self):
        # Fetch command
        self.rec_message = self.parse_msg()

        # Ensure received message has contents
        if self.rec_message is None:
            self.send('500 Error: command not recognized')
            self.errors += 1
            return

        # Process parts of message
        self.rec_message = self.rec_message.strip()
        brkpnt = self.rec_message.find(self.delimiters[self.phase])
        stage = string.upper(self.rec_message[0:brkpnt].strip())
        content = self.rec_message[brkpnt:].strip()

        # Correct command received
        if stage == self.client_stage[self.phase] and brkpnt != -1 and content.find(' ') == -1:
            self.message_contents[self.phase] = content
            self.phase += 1
            self.send('250 jfw222')

        # Command incorrect, pass to error handler
        else:
            self.errors += 1
            self.command_errors(stage, brkpnt, content)

    # Expecting a MAIL FROM
    def from_handler(self):
        # Fetch command
        self.rec_message = self.parse_msg()

        # Ensure received message has contents
        if self.rec_message is None:
            self.send('500 Error: command not recognized')
            self.errors += 1
            return

        # Process parts of message
        self.rec_message = self.rec_message.strip()
        brkpnt = self.rec_message.find(self.delimiters[self.phase])
        stage = string.upper(self.rec_message[0:brkpnt].strip())
        content = self.rec_message[brkpnt+1:].strip()

        # Correct command received
        if content is not None and stage == self.client_stage[self.phase] and brkpnt != -1 and content.find(self.delimiters[self.phase]) == -1:
            self.message_contents[self.phase] = content
            self.phase += 1
            self.send('250 OK')

        # Error handler
        else:
            self.errors += 1
            self.command_errors(stage, brkpnt, content)

    # Expecting a RCPT TO
    def to_handler(self):
        # Fetch command
        self.rec_message = self.parse_msg()

        # Ensure received message has contents
        if self.rec_message is None:
            self.send('500 Error: command not recognized')
            self.errors += 1
            return

        # Process parts of message
        self.rec_message = self.rec_message.strip()
        brkpnt = self.rec_message.find(self.delimiters[self.phase])
        stage = string.upper(self.rec_message[0:brkpnt].strip())
        content = self.rec_message[brkpnt+1:].strip()

        # Correct command received
        if content is not None and stage == self.client_stage[self.phase] and brkpnt != -1 and content.find(self.delimiters[self.phase]) == -1:
            self.message_contents[self.phase] = content
            self.phase += 1
            self.send('250 OK')

        # Command incorrect, pass to error handler
        else:
            self.errors += 1
            self.command_errors(stage, brkpnt, content)

    # Duct tape fix for cases with extra "RCPT TO:" lines
    def to_additional_handler(self):
        # Ensure received message has contents
        if self.rec_message is None:
            self.send('500 Error: command not recognized')
            self.errors += 1
            return

        # Process parts of message
        self.rec_message = self.rec_message.strip()
        brkpnt = self.rec_message.find(self.delimiters[self.phase])
        stage = string.upper(self.rec_message[0:brkpnt].strip())
        content = self.rec_message[brkpnt+1:].strip()

        # Correct command received
        if content is not None and stage == self.client_stage[self.phase] and brkpnt != -1 and content.find(self.delimiters[self.phase]) == -1:
            self.message_contents[self.phase] = content
            self.phase += 1
            self.send('250 OK')

        # Command incorrect, pass to error handler
        else:
            self.errors += 1
            self.command_errors(stage, brkpnt, content)

    # Expecting a "DATA"
    def data_handler(self):
        # Global variables
        global numMessages
        global backupInProg

        # Local variable
        data_contents = []

        # Print
        self.send('354 End data with <CR><LF>.<CR><LF>')

        # Fetch command
        self.rec_message = self.parse_msg()

        # Handle case for multiple recipients
        while self.rec_message.find('RCPT TO') != -1:
            self.phase -= 1
            # Handle extra recipient
            self.to_additional_handler()
            # Fetch next message
            self.rec_message = self.parse_msg()

        # Handle corrupted command type
        if self.rec_message.find('DATA') == -1:
            self.send('500 Error: command not recognized')
            self.errors += 1
            return

        # While within time-limit, fetch DATA contents of message
        try:
            self.socket.settimeout(10)
            while self.rec_message != '.' and self.rec_message is not None:
                data_contents.append(self.rec_message)
                self.rec_message = self.parse_data_msg()
            self.socket.settimeout(None)
            # Store content in local variable
            self.data = data_contents
        except socket.error:
            self.timeout()
            return

        # Backup if there are 32 messages in 'mailbox'
        with backupLock:
            if numMessages > 0 and numMessages % 32 == 0:
                backupInProg = 1
                backupStart.notify()
                while backupInProg is 1:
                    mailDelivery.wait()

            # Send with backupLock making backup and deliver mutually exclusive
            self.send_message()

        # Indicate to handler that there is nothing left to do
        self.phase = 4

    # Special message parser for single use in data_handler
    # It is the same as the rest, but with no timeout, as the timeout is
    # handled by that specific spot in data_handler.
    def parse_data_msg(self):
        while True:
            if self.raw_message.find('\r\n') != -1:
                return None
            try:
                self.raw_message += self.socket.recv(500)
            except socket.error:
                self.timeout()
                return '.'
        command = self.raw_message[0:self.raw_message.find('\r\n')]
        self.raw_message = self.raw_message[self.raw_message.find('\r\n')+2:]
        return command

    # Data contents filled out and sent
    def send_message(self):
        # Global variable
        global numMessages

        # Local variables
        full_message = []
        main_mail_box = open(FILE_NAME, 'a')

        # Add to total messages
        numMessages += 1

        # Fill out message
        full_message.append('Received: from ' + self.message_contents[0] + ' by jfw222 (CS4410MP3)')
        full_message.append('Number: ' + str(numMessages))
        full_message.append('From: ' + self.message_contents[1])
        for i in self.recipients:
            full_message.append('To: ' + self.recipients[i])
        for i in self.data:
            full_message.append(i)

        # Add message to mailbox file
        for i in full_message:
            main_mail_box.write(i + '\n')
        main_mail_box.write('\r\n')
        main_mail_box.close()

        # confirm delivery
        self.send('250 OK: delivered message ' + str(numMessages))

    # Handle timeout
    def timeout(self):
        self.phase = 4
        self.send('421 4.4.2 jfw222 Error: timeout exceeded')


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
