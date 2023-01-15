import configparser
from dataclasses import dataclass


@dataclass
class DbConfig:
    host: str
    password: str
    user: str
    database: str
    port: str


@dataclass
class Rd:
    host: str
    port: int
    db: int
    
    
@dataclass
class Path:
    path: str

@dataclass
class Config:
    res: Rd
    db: DbConfig
    path: Path


def load_config(path: str):
    config = configparser.ConfigParser()
    config.read(path)

    return Config(
        res = Rd(**config["rs"]),
        db = DbConfig(**config["db"]),
        path = Path(**config["path"])
    )

