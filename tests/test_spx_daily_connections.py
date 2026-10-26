import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from spx_daily import connect, create_app

class ConnectionTests(unittest.TestCase):
    def test_requests_close_connections_including_early_return(self):
        with tempfile.TemporaryDirectory() as d:
            path=d+'/db';connect(path).close();opened=[]
            def tracked(p):
                db=connect(p);opened.append(db);return db
            with patch('spx_daily.connect',side_effect=tracked):
                client=create_app(path).test_client()
                self.assertEqual(client.get('/prediction/tomorrow').status_code,503)
                self.assertEqual(client.get('/performance').status_code,200)
            self.assertEqual(len(opened),2)
            for db in opened:
                with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
    def test_request_exception_also_closes_connection(self):
        with tempfile.TemporaryDirectory() as d:
            path=d+'/db';connect(path).close();db=connect(path)
            with patch('spx_daily.connect',return_value=db),patch('spx_daily.records',side_effect=RuntimeError('fixture')):
                app=create_app(path);app.testing=True
                with self.assertRaises(RuntimeError):app.test_client().get('/performance')
            with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
