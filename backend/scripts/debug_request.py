from fastapi.testclient import TestClient
import os
from app.api.main import create_app
os.environ['DATABASE_URL']='sqlite+aiosqlite:///:memory:'
app=create_app()
with TestClient(app) as client:
    resp=client.get('/api/v1/market-data/candles/FOO?start=2020-01-01T00:00:00Z&end=2020-01-02T00:00:00Z&timeframe=1d')
    print('STATUS', resp.status_code)
    try:
        print('TEXT', resp.text)
        print('JSON', resp.json())
    except Exception as e:
        print('ERROR PARSING JSON:', e)
