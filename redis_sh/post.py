import psycopg2
import datetime
from datetime import datetime
from config import load_config

config = load_config(r'redis_sh\source.ini')


class Db_connnect():
    
    
    _config = {"database": config.db.database, 
            "user": config.db.user, 
            "password": config.db.password, 
            "host": config.db.host, 
            "port": config.db.port}
     
    def connect_db(self):
        connect = psycopg2.connect(**self._config)
        return connect, 200
   
    def create_table(self):
        connect, resp = self.connect_db()
        with connect:
            with connect.cursor() as curs:
                curs.execute('''CREATE TABLE IF NOT EXISTS IMAGE_LOG  
                    (TIME TIMESTAMP NOT NULL,
                    SIZE INT NOT NULL);''')
        connect.close()
        return resp
    
    def delete_table(self, name):
        connect, resp = self.connect_db()
        with connect:
            with connect.cursor() as curs:
                curs.execute(f'''DROP TABLE IF EXISTS {name} ''')
        connect.close()
        return resp
    
    def add_log(self, size):
        connect, resp = self.connect_db()
        with connect:
            with connect.cursor() as curs:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                curs.execute("INSERT INTO IMAGE_LOG  VALUES (%s, %s)", (timestamp, size))
        connect.close()
        return resp




