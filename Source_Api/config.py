import configparser
from dataclasses import dataclass


@dataclass
class Source_config:
    host: str
    port: int
    source_adress: str
    
@dataclass
class Config:
    api_src: Source_config


def load_config(path: str):
    config = configparser.ConfigParser()
    config.read(path)
    api_src = config["api_src"]


    return Config(
        api_ssrc = Source_config(
            host = api_src.get("host"),
            port = api_src.getint("port"),
            source_adress = api_src.get("source_adress")
        )
    )