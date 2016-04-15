import os
import sys

from server import server

port = 0

#get port argument
if (len(sys.argv) < 2):
    print "usage main <port>"
    sys.exit()
else:
    port = sys.argv[1]

srvr = server(port)
srvr.run()
