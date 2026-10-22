"""Testes de integração locais usando apenas unittest da biblioteca padrão."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import app as application


class EncontreiAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        base = Path(cls.temp.name)
        application.DATA_DIR = base / "data"
        application.UPLOAD_DIR = base / "uploads"
        application.DB_PATH = application.DATA_DIR / "test.sqlite3"
        application.DATA_DIR.mkdir(exist_ok=True)
        application.UPLOAD_DIR.mkdir(exist_ok=True)
        application.TOKENS.clear()
        application.init_db()
        cls.server = application.ThreadingHTTPServer(("127.0.0.1", 0), application.Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.student_token = cls.login("estudante@campus.edu.br", "Estudante@12345")["token"]
        cls.lucas_token = cls.login("lucas@campus.edu.br", "Lucas@12345")["token"]
        cls.mod_token = cls.login("moderador@campus.edu.br", "Moderador@12345")["token"]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()
        application.TOKENS.clear()

    @classmethod
    def request(cls, path, method="GET", body=None, token=None, expected=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(cls.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                status = res.status
                result = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            status = e.code
            result = json.loads(e.read().decode("utf-8"))
        if expected is not None:
            if status != expected:
                raise AssertionError(f"{method} {path}: esperado {expected}, recebido {status}: {result}")
        return status, result

    @classmethod
    def login(cls, email, password):
        status, result = cls.request("/api/login", "POST", {"email": email, "password": password}, expected=200)
        return result

    def test_health_endpoint(self):
        status, result = self.request("/api/health", expected=200)
        self.assertTrue(result["ok"])
        self.assertEqual(result["database"], "SQLite")

    def test_seeded_items_exist_and_verification_answer_is_private(self):
        status, result = self.request("/api/items", expected=200)
        self.assertGreaterEqual(len(result["items"]), 4)
        status, detail = self.request("/api/items/1", expected=200)
        self.assertNotIn("verification_answer", detail["item"])
        self.assertNotIn("verification_question", detail["item"])

    def test_found_item_requires_photo_and_verification_question(self):
        status, result = self.request("/api/items", "POST", {
            "title": "Chave encontrada", "type": "Achado", "category": "Chaves",
            "description": "Chave de teste", "location": "Biblioteca", "event_date": "2026-10-22",
            "photos": [], "verification_question": "Qual a cor?", "verification_answer": "azul"
        }, token=self.student_token, expected=400)
        self.assertIn("foto", result["error"].lower())

    def test_lost_item_can_be_created_without_photo_and_persists(self):
        status, result = self.request("/api/items", "POST", {
            "title": "Mochila de teste", "type": "Perdido", "category": "Acessórios",
            "description": "Mochila preta usada para teste de integração", "location": "Bloco C",
            "event_date": "2026-10-22", "photos": []
        }, token=self.student_token, expected=201)
        self.assertEqual(result["item"]["title"], "Mochila de teste")
        status, listed = self.request("/api/items?q=Mochila%20de%20teste", expected=200)
        self.assertTrue(any(i["title"] == "Mochila de teste" for i in listed["items"]))

    def test_claim_approval_and_internal_message(self):
        status, question = self.request("/api/items/1/verification-question", token=self.lucas_token, expected=200)
        self.assertTrue(question["question"])
        status, result = self.request("/api/items/1/claims", "POST", {"answer": "resposta errada"}, token=self.lucas_token, expected=400)
        self.assertIn("não confere", result["error"].lower())
        status, result = self.request("/api/items/1/claims", "POST", {"answer": "montanha"}, token=self.lucas_token, expected=201)
        claim_id = result["claim_id"]
        status, result = self.request(f"/api/claims/{claim_id}/decision", "POST", {"decision": "Aprovada", "note": "Resposta validada"}, token=self.student_token, expected=200)
        self.assertIn("aprovada", result["message"])
        status, result = self.request(f"/api/claims/{claim_id}/messages", "POST", {"body": "Vamos combinar a entrega na biblioteca."}, token=self.lucas_token, expected=201)
        status, messages = self.request(f"/api/claims/{claim_id}/messages", token=self.student_token, expected=200)
        self.assertEqual(len(messages["messages"]), 1)
        self.assertIn("biblioteca", messages["messages"][0]["body"].lower())

    def test_non_moderator_cannot_view_moderation_queue(self):
        status, result = self.request("/api/moderation/reports", token=self.student_token, expected=403)
        self.assertIn("moderação", result["error"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
