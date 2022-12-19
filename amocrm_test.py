import os

import httplib2
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
import creds

from pathlib import Path
from amocrm.v2.entity.lead import Lead
from amocrm.v2 import tokens


'''Вводим токены пользователя'''
tokens.default_token_manager(
    client_id="some_id_xxxx",
    client_secret="client_key",
    subdomain="amocrm3yopmailcom",
    redirect_url="http://tests.com",
    storage=tokens.FileTokensStorage(directory_path=str(Path.home())),
)
#tokens.default_token_manager.init(code="..very long code...", skip_error=True)

'''Получаем лог события (json файл с полями: ID события, Тип события, ID сущности события, Сущность события, ID пользователя, создавшиего событие'''
lead = Lead.objects.get(query="test")


''' Подкючаемся к нужной гугл таблице'''
def get_service_simple():
    return build('sheets', 'v4', developerKey=creds.api_key)


def get_service_sacc():
    
    creds_json = os.path.dirname(__file__) + "/creds/sacc1.json"
    scopes = ['https://www.googleapis.com/auth/spreadsheets']

    creds_service = ServiceAccountCredentials.from_json_keyfile_name(creds_json, scopes).authorize(httplib2.Http())
    return build('sheets', 'v4', http=creds_service)
# service = get_service_simple()
service = get_service_sacc()
sheet = service.spreadsheets()
sheet_id = "xxx"

'''Добавляем лог события в таблицу (если кортеж таблицы уже заполнен, метод аppend по умолчанию пишет в пустую строку ниже)'''
resp = sheet.values().append(
    spreadsheetId=sheet_id,
    range="Лист2!A1",
    valueInputOption="RAW",
    body=lead).execute()