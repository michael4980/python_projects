#!/usr/bin/python3
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class EventHandler(FileSystemEventHandler):
    def on_created(self, event):
        name = os.path.basename(event.src_path)
        with open(event.src_path) as f:
            line_count = sum(1 for _ in f)
            print(f' DELETED {name} AND amount of lines = {line_count}')
        os.remove(event.src_path)
    
if __name__ == '__main__':
    path = os.getcwd() 
    event_handler, observer = EventHandler(), Observer()
    observer.schedule(event_handler, path)
    observer.start()
    try:
        print('Waiting for files...')
        while True:
            pass
    except KeyboardInterrupt:
        observer.stop()