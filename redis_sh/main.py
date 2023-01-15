import os
import aiomisc, asyncio
import glob
import redis
import post
from config import load_config

config = load_config(r'redis_sh\source.ini')

class Loader():
    
    
    _config  = 0

    def picture_load(self, path):
        client, resp = self.redis_connection()
        for name in glob.glob(path):
            stat = os.stat(name)
            client.rpush('image_list', stat.st_size)
        return resp
        
        
    def redis_connection(self):
        client = redis.Redis(host = config.res.host, port=config.res.port, db=config.res.db)
        return client, 200

class Dumper(Loader):
    
    
    @aiomisc.threaded
    def dump_function(self):
        client, resp = self.redis_connection()
        size = client.lpop('image_list')
        deb = post.Db_connnect()
        deb.add_log(int(size))
        return resp
        
  
    async def main(self):
        await asyncio.gather(
            self.dump_function()
            )
  
if __name__ == '__main__':
    start = Dumper()
    start.picture_load(config.path.path)
    client = start.redis_connection()
    with aiomisc.entrypoint() as loop:
        while client.llen('image_list') >= 1:
            try:
                loop.run_until_complete(start.main())  
            except RuntimeError:
                loop.stop()
