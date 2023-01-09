import time, functools, logging
import pyvisa
import asyncio
import aiomisc
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

resource_manager = pyvisa.ResourceManager()
src = resource_manager.open_resource("TCPIP0::169.254.129.17::INSTR") #connecting to source


class HTTPError(Exception):
    def __init__(self, code, reason):
        super(HTTPError, self).__init__(reason)
        self.code = code


class Source:
    
    
    def __init__(self):
        self.work = {1:0, 2:0, 3:0, 4:0} # working channels
     
    def switching_on(self, channel, current, voltage):
        if self.work[channel] == 0:
           self.set_current(channel, current)
           self.set_voltage(channel, voltage)
           self.turn_on(channel)
           self.work[channel] = 1
        else:
            print(f'{channel} already works')

    def turn_off(self, channel):
        if self.work[channel] == 1:
            src.write(f':OUTPut{channel}:STATe OFF')
            self.work[channel] = 0
        else:
            print(f'channel {channel} is not working')
    
    #calling current state on all channels
    def current_state(self):
        book = []
        for channel in range(1, 5):
            if self.work[channel] == 1:
                result = self.measure(channel)
                book.append(result)
        return book
            
    def set_current(self,channel, current):
        src.write(f':SOURce{channel}:CURRent {current}')
        return f':SOURce{channel}:CURRent {current}'
        
    def set_voltage(self,channel, voltage):
        src.write(f':SOURce{channel}:VOLTage {voltage}')
        return f':SOURce{channel}:VOLTage {voltage}'
           
    def turn_on(self, channel):
        src.write(f':OUTPut{channel}:STATe ON')
        return f':OUTPut{channel}:STATe ON'
        
    def measure(self, channel):
        src.write(f':MEASure{channel}:ALL?')
        src.query("*OPC?")
        readback = src.query_ascii_values("READ?")
        data = {'time': time.time(),
                'channel': channel,
                'voltage': readback[0],
                'current':readback[1],
                'power':readback[2]}   
        return data 

   
class Logger(Source):
    
    
    CONFIG = logging.basicConfig(
        filename='source.log', 
        filemode='w', 
        format='%(asctime)s - %(message)s', 
        datefmt='%H:%M:%S',
        level= logging.INFO
        )  
    _ch = 'channel'
    _vl = 'voltage'
    _cr = 'current'
    _pw = 'power'
    
    @aiomisc.threaded
    def logging_function(self, ch_num):
        data = self.measure(ch_num)
        logging.info(f'channel = {data[self._ch]}, current = {self._cr}A, voltage = {self._vl}V, power = {self._pw}Vt')
        time.sleep(15)
  
    async def main(self):
        await asyncio.gather(
            self.logging_function(1),
            self.logging_function(2),
            self.logging_function(3),
            self.logging_function(4)
        )

class Handler(BaseHTTPRequestHandler, Source):
    
    def do_GET(self):
        if self.path == '/current_state/':
            data =  self.current_state()
            return json.dumps(data, sort_keys=True)
    
    def do_POST(self):
        if self.path == '/switching_on/':      
            return self.process_request(201, functools.partial(self.call_with_body, self.switching_on))
        elif self.path == '/turn_off/':
            return self.process_request(201, functools.partial(self.call_with_body, self.turn_off))
    
    def get_data(self):
    # Get request params from body
        if not self.headers['Content-Type'].startswith('application/json'):
            raise HTTPError(415, 'expected application/json')

        number_of_bits = int(self.headers['Content-Length'])
        body = self.rfile.read(number_of_bits)
        return json.loads(body, encoding='utf-8')
    
    def call_with_body(self, handler):
        """Call handler with request body."""
        try:
            data = self.get_data()
        except Exception as e:
            raise HTTPError(400, str(e))
        return handler(data) 
    
    def process_request(self, status, handler):
        """Process requests and handle exceptions"""
        try:
            data = handler()
        except HTTPError as e:
            data = {'error': str(e)}
            status = e.code
        except Exception as e:
            data = {'error': str(e)}
            status = 500

        self.write_response(status, data)

if __name__ == '__main__':
    log = Logger()
    server_address = ('127.0.0.1', 8080)
    server = HTTPServer(server_address, Handler)
    server.serve_forever()
    with aiomisc.entrypoint(log_config=log.CONFIG) as loop:
            while True:
                loop.run_until_complete(log.main())

