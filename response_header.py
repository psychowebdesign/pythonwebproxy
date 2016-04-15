from datetime import datetime, timedelta

class response_header:
    def __init__(self, header):
        self.raw_header = header
        self.parse_header()

    def parse_header(self):
        lines = self.raw_header.split('\n')
        self.parsed_header = {}
        for line in lines:
            if ": " in line:
                line_spl = line.split(":")
                key = line_spl[0].strip()
                if len(line_spl) > 2:
                    del line_spl[0]
                    value = ':'.join(line_spl).strip()
                else:
                    value = line_spl[1].strip()
                self.parsed_header[key] = value
            else:
                #response line
                self.parsed_header["response"] = line

        if 'Expires' in self.parsed_header:
            self.parsed_header['expires_datetime'] = datetime.strptime(
                self.parsed_header['Expires'],
                '%a, %d %b %Y %H:%M:%S GMT'
            )
        else:
            self.parsed_header['expires_datetime'] = datetime.now() + timedelta(0, 86400)

    def get(self, key):
        #if 'parsed_header' not in vars():
        if not hasattr(self, 'parsed_header'):
            print "no header parsed!"
            return None

        if key in self.parsed_header:
            return self.parsed_header[key]
        else:
            return None
