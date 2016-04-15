import os
import hashlib
import MySQLdb
import sys
from datetime import datetime

class cache:

    def __init__(self):
        #cache {(url, expiry): packets}
        self.cache = {}

        #sockets that are currently writing to cache
        self.receiving_sockets = {}
        #self.cache = {("www.example.com/index.html", datetime.strptime('Jun 1 2020  1:40PM', '%b %d %Y %I:%M%p'))}
        self.out("Cache created")

    #returns list of packets for valid url file if present
    #returns None on cache miss or expired file
    def search(self, dest_url, resp_header, sock):
        for (url, expiry) in self.cache:
            if url == dest_url:
                if expiry > datetime.now():
                    self.out("hit " + dest_url)
                    return self.cache[(url, expiry)]
                else:
                    self.out("miss")
                    del self.cache[(url, expiry)]
                    self.new_writer(dest_url, resp_header, sock)
                    return None

        self.out("miss")
        self.new_writer(dest_url, resp_header, sock)
        return None

    def new_writer(self, dest, resp_header, sock):
        exp = resp_header.get('expires_datetime')
        key = (dest, exp)
        self.receiving_sockets[sock] = key
        self.cache[key] = []

    def write(self, sock, data):
        if sock in self.receiving_sockets:
            if len(data) > 0:
                self.out("writing")
                self.cache[self.receiving_sockets[sock]].append(data)
            else:
                del self.receiving_sockets[sock]
                print "closing----------------"

    def close_write(self, socks):
        for sock in socks:
            if sock in self.receiving_sockets:
                del self.receiving_sockets[sock]
                print "closing----------------"


    def show(self):
        for (url, exp) in self.cache:
            print str(url) + ":" +str(len(self.cache[(url,exp)]))

    def clear(self):
        self.cache = {}

    def out(self, msg):
        print "[*] CACHE: " + msg
