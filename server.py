import socket, errno
import time
import select
import sys
import ssl
from urlparse import urlparse
from datetime import datetime
from response_header import response_header


class server:

    def __init__(self, port):
        try:
            #bind to main listening port for proxy server
            self.out("Server created")
            self.port = int(port)
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(('', self.port))
            self.sock.listen(200)

            #receive buffer size
            self.buffer_size = 4096

            #cache control system
            self.cache = {}
            self.cache_expiry = {}

            #a list of the files currently receiving on server sockets
            self.server_socket_path = {}

            #list of sockets/io for server to listen on
            #includes itself - special case - will handle new connections
            #and sys.stdin for user input
            self.active_sockets = [self.sock, sys.stdin]

            #maintains a list of clients that are blacklisted - ignores
            self.client_blacklist = []

            #maintains a list of servers that are blacklisted - ignores
            self.server_blacklist = []

            #maintains list of current servers requested by clients
            self.client_request_server = {}

	        #contains directions for sockets
            self.socket_directions = {}

            self.out("Successfully bound to PORT: " + port)

        except Exception, e:
            self.out("Error creating socket. Error code: ")
            print e
            sys.exit(2)

    def run(self):
        self.running = True
        try:
            while self.running:
                wait_io = select.select

                #block until an I/O device is ready
                in_ready, out_ready, except_ready = wait_io(
                    self.active_sockets,
                    [],
                    []
                )

                #iterate over ready io devices and handle
                for incoming in in_ready:
                    if incoming == self.sock:
                        #handle new client connection
                        conn, addr = self.sock.accept()
                        if addr[0] not in self.client_blacklist:
                            self.out("new connection from " + addr[0] + " " + str(addr[1]))
                            self.new_client(conn)
                        else:
                            conn.shutdown(socket.SHUT_RDWR)
                            conn.close()
                            msg =   "attempted connection from" \
                                    " blacklisted client " + str(addr[0])
                            self.out(msg)

                    elif incoming == sys.stdin:
                        #handle new stdin
                        self.out(self.parse_command(sys.stdin.readline()))
                    else:
                        #handle client <-> server
                        #closes socket when necessary
                        self.relay(incoming)
        except Exception, e:
            print e

    #closes all sockets and updates status
    def clear_status(self):
        for s in self.active_sockets:
            if s != self.sock and s != sys.stdin:
                self.close_and_clean(s)

    #parses input, executes commands, returns string
    def parse_command(self, command):
        command = command.lower()
        cms = command.split(' ')
        if  cms[0] == "blacklist":
            usage = "Usage: blacklist <client/server> <ip/hostname>"
            if len(cms) != 3:
                return usage
            if cms[1] == "server":
                server = str(cms[2]).strip('\n')
                self.server_blacklist.append(server)
                return "server " + server + " blacklisted"
            elif cms[1] == "client":
                ip = str(cms[2]).strip('\n')
                self.client_blacklist.append(ip)
                return "client " + ip + " blacklisted"
            else:
                return usage

        if cms[0].strip('\n') == "stop":
            self.running = False
            return "stopping"

        if cms[0].strip('\n') == "clean":
            self.clear_status()
            return "clear"

        if cms[0].strip('\n') == "clear-cache":
            self.cache = {}
            self.clear_status()
            return "cache cleared"

        return "please enter command"


    #relays data client <-> server
    #cleans up all status lists when necessary
    def relay(self, sock):
        try:
            data = sock.recv(self.buffer_size)

            #if data is a new get request from client - must handle
            if self.requesting_new(data, sock):
                self.new_get_request(data, sock)
                return

            if len(data) > 0:
                #relaying data here
                self.socket_directions[sock].send(data)
            else:
                #print sock
                self.close_and_clean(sock)

            #checks if a cache record has been created
            #if exists, writes data to it
            for (f,s) in self.cache:
                if s == sock:
                    self.cache[(f,s)].append(data)
                    if self.ok_response_header(data):
                        rh = response_header(data)
                        self.cache_expiry[(f,s)] = rh.get('expires_datetime')



        except Exception, e:
            #hack to ignore annoying & irrelevant socket timeouts
            pass

    #returns true if response header is returning code 200 OK
    def ok_response_header(self, data):
        if len(data) > 0:
            code = data.split('\n')[0].strip()
            if "OK" in code and "200" in code:
                return True
        return False

    #returns true if data indicates socket is attempting connect
    #different server
    def requesting_new(self, data, sock):
        #ensure its a GET request
        if len(data) > 0 and data.startswith("GET"):
            host, port, full = self.get_addr_from_string(data.split('\n')[0])
            if host != self.client_request_server[sock]:
                return True

        return False

    #close client <-> server conncetions
    #update status lists accordingly
    def close_and_clean(self, sock):
        #self.out("closing & cleaning")
        #remove from active sockets
        self.active_sockets.remove(sock)
        self.active_sockets.remove(self.socket_directions[sock])

        #close client <-> server connection
        reverse_direction = self.socket_directions[sock]
        self.socket_directions[sock].close()
        self.socket_directions[reverse_direction].close()

        #remove from directions dict
        del self.socket_directions[sock]
        del self.socket_directions[reverse_direction]

    #establish a connection with new client, relay request
    #update tracking lists
    def new_client(self, sock):
        #print sock
        if not self.forward_get_req(sock):
            pass
            #could increment counter here - blacklist repeat offenders?
            #sock.shutdown(socket.SHUT_RDWR)
            #sock.close()

    #similar to forward_get_req but for situation where
    #already connected client socket is attempting to send get to a different
    #server - must create a new forwarding connection
    def new_get_request(self, data, sock):
        try:
            if len(data) > 0:
                host, port, full = self.get_addr_from_string(data.split('\n')[0])

                self.client_request_server[sock] = host

                if host not in self.server_blacklist:
                    for (f, s) in self.cache:
                        if f == full and self.check_cache_expiry((f,s)):
                            self.out("cache HIT")
                            for d in self.cache[(f,s)]:
                                sock.send(d)
                            sock.close()
                            return
                    self.out("cache MISS")
                    #if not blacklisted, connect to desired server and forward get
                    forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    forward.connect((host, port))
                    forward.send(data)

                    #update state to ensure proper routing going forward
                    self.active_sockets.append(forward)
                    self.active_sockets.remove(self.socket_directions[sock])

                    self.socket_directions[sock] = forward
                    self.socket_directions[forward] = sock
                    self.cache[(full, forward)] = []
                    return True

                else:
                    msg =   "attempted access to" \
                            " blacklisted site " + host
                    sock.send("NO!")
                    sock.close()
                    self.out(msg)
                    return False
            else:
                return True
        except Exception, e:
            print e

    #returns true if get can be forwarded - false if not
    #data will not be forwarded if site is blacklisted
    #updates self.active_sockets and self.socket_directions accordingly
    def forward_get_req(self, sock):
        try:
            get_req = sock.recv(self.buffer_size)
            if len(get_req) > 0:
                host, port, full = self.get_addr_from_string(get_req.split('\n')[0])

                self.client_request_server[sock] = host
                if host not in self.server_blacklist:
                    for (f, s) in self.cache:
                        if f == full and self.check_cache_expiry((f,s)):
                            self.out("cache HIT")
                            for d in self.cache[(f,s)]:
                                sock.send(d)
                            sock.close()
                            return
                    self.out("cache MISS")
                    if port == 443:
                        forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        forward.connect((host, 443))
                        sock.send("HTTP/1.1 200 Connection established\nProxy-agent:%s\n\n"%("Python Proxy"))
                    else:
                        #if not blacklisted, connect to desired server and forward get
                        forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        forward.connect((host, port))
                        forward.send(get_req)

                    #update state to ensure proper routing going forward
                    self.active_sockets.append(sock)
                    self.active_sockets.append(forward)
                    self.socket_directions[sock] = forward
                    self.socket_directions[forward] = sock
                    self.cache[(full, forward)] = []
                    return True

                else:
                    msg =   "attempted access to" \
                            " blacklisted site " + host
                    sock.send("NO!")
                    sock.close()
                    self.out(msg)
                    return False
            else:
                return True
        except Exception, e:
            print e


    #parses a string containing url, returns tuple (host, port)
    def get_addr_from_string(self, string):
        url = string.split(' ')[1]
        #this is just a hack for urlparse
        if not url.startswith("http"):
            url = "http://" + url
        parsed = urlparse(url)
        port = 80 if parsed.port is None else parsed.port
        #print port
        return (str(parsed.hostname), int(port), str(parsed.hostname + parsed.path))

    #checks to see if cache page has expired
    #invalidates cache if expired
    def check_cache_expiry(self, (f,s)):
        if (f,s) in self.cache_expiry:
            if self.cache_expiry[(f,s)] < datetime.now():
                del self.cache[(f,s)]
                del self.cache_expiry[(f,s)]
                return False
            else:
                return True
        else:
            return True

    def out(self, msg):
        print "[*] SERVER: " + msg
