import sys
from pathlib import Path
sys.path.insert(1, Path.home())

import post, main
from config import load_config

config = load_config(r'redis_sh\source.ini')
conn = post.Db_connnect()
start = main.Dumper()

def test_connect_postgre():
    obj, resp = conn.connect_db()
    assert resp == 200, 'postgre db didn`t connect'

def test_create_tb():
    resp = conn.create_table()
    assert resp == 200, 'postgre db didn`t create'

def test_drop_table():
    resp = conn.delete_table('some_table')
    assert resp == 200, 'postgre db didn`t delete'  

def test_add_log():
    resp = conn.add_log(3000)
    assert resp == 200, 'postgre db didn`t add log'  
    
def test_redis_connection():
    cl, resp = start.redis_connection()
    assert resp == 200, 'redis db didn`t connect'
    
def test_image_load():
    resp = start.picture_load(config.path.path)
    assert resp == 200, 'redis queue didn`t fill'
    

    

    
    
