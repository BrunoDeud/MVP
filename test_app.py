"""Testes automatizados de API, regras de negócio e persistência (unittest padrão)."""
import base64
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
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
        application.LOGIN_ATTEMPTS.clear()
        application.LAST_MAINTENANCE = 0
        application.init_db()
        cls.server = application.ThreadingHTTPServer(("127.0.0.1", 0), application.Handler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.student_token = cls.login("estudante@campus.edu.br", "Estudante@12345")["token"]
        cls.lucas_token = cls.login("lucas@campus.edu.br", "Lucas@12345")["token"]
        cls.mod_token = cls.login("moderador@campus.edu.br", "Moderador@12345")["token"]
        cls.admin_token = cls.login("admin@campus.edu.br", "Admin@12345")["token"]
        cls.photo_data = base64.b64encode((application.UPLOAD_DIR / "demo-bottle.png").read_bytes()).decode("ascii")

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
            with urllib.request.urlopen(req, timeout=8) as res:
                status = res.status
                raw = res.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read().decode("utf-8")
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"html": raw}
        if expected is not None and status != expected:
            raise AssertionError(f"{method} {path}: esperado {expected}, recebido {status}: {result}")
        return status, result

    @classmethod
    def login(cls, email, password):
        _, result = cls.request("/api/login", "POST", {"email": email, "password": password}, expected=200)
        return result

    @classmethod
    def image(cls):
        return {"name": "demo.png", "mime": "image/png", "data": "data:image/png;base64," + cls.photo_data}

    @classmethod
    def create_lost(cls, title="Chaves perdidas teste", category="Chaves", location="Bloco B — corredor do térreo", token=None):
        token = token or cls.student_token
        status, result = cls.request("/api/items", "POST", {
            "title": title, "type": "Perdido", "category": category,
            "description": "Descrição de teste com informações suficientes para publicação.",
            "location": location, "event_date": date.today().isoformat(), "photos": []
        }, token=token, expected=201)
        return result["item"]

    @classmethod
    def create_found(cls, title="Item achado teste", category="Garrafas", location="Biblioteca central", token=None):
        token = token or cls.student_token
        _, result = cls.request("/api/items", "POST", {
            "title": title, "type": "Achado", "category": category,
            "description": "Descrição do objeto encontrado para teste automatizado.",
            "location": location, "event_date": date.today().isoformat(), "photos": [cls.image()],
            "verification_question": "Qual detalhe está gravado no item?", "verification_answer": "teste azul"
        }, token=token, expected=201)
        return result["item"]

    def test_01_health_and_database(self):
        _, data = self.request("/api/health", expected=200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["database"], "SQLite")
        self.assertGreaterEqual(data["items"], 5)

    def test_02_seeded_items_and_verification_answer_private(self):
        _, data = self.request("/api/items", expected=200)
        self.assertGreaterEqual(len(data["items"]), 5)
        _, detail = self.request("/api/items/1", expected=200)
        self.assertNotIn("verification_answer", detail["item"])
        self.assertNotIn("verification_question", detail["item"])
        self.assertIn("pagination", data)

    def test_03_login_rejects_wrong_password(self):
        _, data = self.request("/api/login", "POST", {"email": "estudante@campus.edu.br", "password": "errada"}, expected=401)
        self.assertIn("incorretos", data["error"])

    def test_04_register_domain_validation_and_email_verification_flow(self):
        _, bad = self.request("/api/register", "POST", {"name": "Teste Qualquer", "email": "pessoa@gmail.com", "password": "Senha12345", "password_confirmation": "Senha12345"}, expected=400)
        self.assertIn("institucional", bad["error"].lower())
        _, created = self.request("/api/register", "POST", {"name": "Aluno Novo", "email": "aluno.novo@campus.edu.br", "password": "Senha12345", "password_confirmation": "Senha12345"}, expected=201)
        self.request("/api/login", "POST", {"email": "aluno.novo@campus.edu.br", "password": "Senha12345"}, expected=403)
        token = urllib.parse.parse_qs(urllib.parse.urlparse(created["verification_url"]).query)["token"][0]
        _, page = self.request("/api/verify-email?token=" + urllib.parse.quote(token), expected=200)
        self.assertIn("verificada com sucesso", page["html"].lower())
        _, logged = self.request("/api/login", "POST", {"email": "aluno.novo@campus.edu.br", "password": "Senha12345"}, expected=200)
        self.assertTrue(logged["token"])

    def test_05_found_item_requires_photo_and_verification(self):
        _, result = self.request("/api/items", "POST", {
            "title": "Chave encontrada teste", "type": "Achado", "category": "Chaves",
            "description": "Chave de teste sem foto", "location": "Biblioteca", "event_date": date.today().isoformat(),
            "photos": [], "verification_question": "Qual a cor?", "verification_answer": "azul"
        }, token=self.student_token, expected=400)
        self.assertIn("foto", result["error"].lower())

    def test_06_lost_item_create_and_persist(self):
        item = self.create_lost(title="Mochila perdida persistência")
        _, listed = self.request("/api/items?" + urllib.parse.urlencode({"q": "Mochila perdida persistência"}), expected=200)
        self.assertTrue(any(i["id"] == item["id"] for i in listed["items"]))

    def test_07_found_item_validates_photo_magic_bytes(self):
        payload = {"title":"Foto inválida teste", "type":"Achado", "category":"Garrafas",
                   "description":"Descrição válida", "location":"Biblioteca central", "event_date":date.today().isoformat(),
                   "photos":[{"mime":"image/png","data":"data:image/png;base64,"+base64.b64encode(b"nao e png").decode()}],
                   "verification_question":"Qual detalhe tem?", "verification_answer":"azul"}
        _, data = self.request("/api/items", "POST", payload, token=self.student_token, expected=400)
        self.assertIn("formato informado", data["error"].lower())

    def test_08_restrict_sensitive_found_categories_to_guard_point(self):
        _, data = self.request("/api/items", "POST", {
            "title":"Documento encontrado teste", "type":"Achado", "category":"Documentos",
            "description":"Documento sem número ou dados sensíveis.", "location":"Portaria principal",
            "event_date":date.today().isoformat(), "photos":[self.image()],
            "verification_question":"Qual marca d'água?", "verification_answer":"flor"
        }, token=self.student_token, expected=400)
        self.assertIn("ponto de guarda", data["error"].lower())

    def test_09_guard_point_item_and_role_permission(self):
        _, points = self.request("/api/guard-points", token=self.mod_token, expected=200)
        point = next(p for p in points["guard_points"] if p["name"] == "Guarda da portaria")
        payload = {"title":"Documento recebido na guarda", "type":"Achado", "category":"Documentos",
                   "description":"Envelope recebido e registrado pela instituição.", "location":point["location_name"],
                   "event_date":date.today().isoformat(), "guard_point_id":point["id"], "photos":[self.image()],
                   "verification_question":"Qual cor de envelope?", "verification_answer":"bege"}
        _, forbidden = self.request("/api/guard-points/items", "POST", payload, token=self.student_token, expected=403)
        self.assertIn("moderação", forbidden["error"].lower())
        _, created = self.request("/api/guard-points/items", "POST", payload, token=self.mod_token, expected=201)
        self.assertEqual(created["item"]["status"], "No ponto de guarda")

    def test_10_claim_validation_approval_duplicate_and_private_chat(self):
        _, question = self.request("/api/items/1/verification-question", token=self.lucas_token, expected=200)
        self.assertTrue(question["question"])
        self.request("/api/items/1/claims", "POST", {"answer":"resposta errada"}, token=self.lucas_token, expected=400)
        _, first = self.request("/api/items/1/claims", "POST", {"answer":"montanha"}, token=self.lucas_token, expected=201)
        self.request("/api/items/1/claims", "POST", {"answer":"montanha"}, token=self.lucas_token, expected=409)
        self.request(f"/api/claims/{first['claim_id']}/decision", "POST", {"decision":"Aprovada","note":"Resposta validada"}, token=self.student_token, expected=200)
        # RN09: depois de aprovada uma reivindicação, outro usuário não pode reivindicar o mesmo item.
        self.request("/api/items/1/claims", "POST", {"answer":"montanha"}, token=self.mod_token, expected=409)
        self.request(f"/api/claims/{first['claim_id']}/messages", "POST", {"body":"Vamos combinar a entrega na biblioteca."}, token=self.lucas_token, expected=201)
        _, messages = self.request(f"/api/claims/{first['claim_id']}/messages", token=self.student_token, expected=200)
        self.assertEqual(len(messages["messages"]), 1)
        self.assertNotIn("email", messages["messages"][0])
        self.request(f"/api/claims/{first['claim_id']}/messages", token=self.admin_token, expected=403)

    def test_11_guard_point_claim_requires_moderator_decision(self):
        _, created = self.request("/api/items/5/claims", "POST", {"answer":"sol"}, token=self.lucas_token, expected=201)
        claim_id = created["claim_id"]
        self.request(f"/api/claims/{claim_id}/decision", "POST", {"decision":"Aprovada","note":"teste"}, token=self.student_token, expected=403)
        _, queue = self.request("/api/moderation/claims", token=self.mod_token, expected=200)
        self.assertTrue(any(c["id"] == claim_id for c in queue["claims"]))
        self.request(f"/api/claims/{claim_id}/decision", "POST", {"decision":"Aprovada","note":"Identificação conferida"}, token=self.mod_token, expected=200)
        self.request(f"/api/claims/{claim_id}/returned", "POST", {}, token=self.mod_token, expected=200)
        _, history = self.request("/api/items/5/history", token=self.student_token, expected=200)
        self.assertTrue(any("Devolução" in h["action"] for h in history["history"]))

    def test_12_search_filters_dates_and_pagination(self):
        _, data = self.request("/api/items?type=Achado&date_from="+date.today().isoformat()+"&per_page=1", expected=200)
        self.assertLessEqual(len(data["items"]), 1)
        self.assertEqual(data["pagination"]["per_page"], 1)
        self.request("/api/items?date_from=2026-10-23&date_to=2026-10-01", expected=400)

    def test_13_notifications_are_private_and_can_be_marked_read(self):
        item = self.create_lost(title="Chaves para gerar correspondência")
        _, notes = self.request("/api/notifications", token=self.student_token, expected=200)
        self.assertIn("notifications", notes)
        if notes["notifications"]:
            notification = notes["notifications"][0]
            self.request(f"/api/notifications/{notification['id']}/read", "PATCH", {}, token=self.student_token, expected=200)
            _, again = self.request("/api/notifications", token=self.student_token, expected=200)
            self.assertTrue(any(n["id"] == notification["id"] and n["is_read"] == 1 for n in again["notifications"]))
        self.request("/api/notifications", token=self.lucas_token, expected=200)

    def test_14_profile_report_duplicate_and_moderation_flow(self):
        _, result = self.request("/api/users/4/reports", "POST", {"reason":"Perfil enviando conteúdo indevido"}, token=self.student_token, expected=201)
        self.request("/api/users/4/reports", "POST", {"reason":"Relato repetido do mesmo usuário"}, token=self.student_token, expected=409)
        _, queue = self.request("/api/moderation/profile-reports", token=self.mod_token, expected=200)
        self.assertTrue(any(r["id"] == result.get("id", -1) for r in queue["reports"]) or len(queue["reports"]) > 0)
        report = next(r for r in queue["reports"] if r["target_user_id"] == 4)
        self.request(f"/api/profile-reports/{report['id']}/decision", "POST", {"decision":"Improcedente","note":"Revisado; evidências insuficientes."}, token=self.mod_token, expected=200)

    def test_15_moderation_requires_role_and_logs_decisions(self):
        _, data = self.request("/api/moderation/reports", token=self.student_token, expected=403)
        self.assertIn("moderação", data["error"].lower())
        _, log = self.request("/api/moderation/log", token=self.mod_token, expected=200)
        self.assertIsInstance(log["actions"], list)

    def test_16_admin_crud_catalogs_domains_and_roles(self):
        _, created = self.request("/api/admin/categories", "POST", {"name":"Instrumentos musicais teste","requires_guard":False}, token=self.admin_token, expected=201)
        _, catalogs = self.request("/api/config", expected=200)
        self.assertTrue(any(c["name"] == "Instrumentos musicais teste" for c in catalogs["categories"]))
        self.request(f"/api/admin/categories/{created['id']}", "PATCH", {"active":False}, token=self.admin_token, expected=200)
        _, domain = self.request("/api/admin/domains", "POST", {"domain":"novos.alunos.example.edu.br"}, token=self.admin_token, expected=201)
        self.request(f"/api/admin/domains/{domain['id']}", "PATCH", {"active":False}, token=self.admin_token, expected=200)
        self.request("/api/admin/users", token=self.student_token, expected=403)

    def test_17_update_and_delete_item_crud(self):
        item = self.create_lost(title="Anúncio editável e removível", token=self.lucas_token)
        _, updated = self.request(f"/api/items/{item['id']}", "PATCH", {"title":"Anúncio editado", "description":"Descrição editada com tamanho suficiente."}, token=self.lucas_token, expected=200)
        _, detail = self.request(f"/api/items/{item['id']}", expected=200)
        self.assertEqual(detail["item"]["title"], "Anúncio editado")
        self.request(f"/api/items/{item['id']}", "DELETE", token=self.lucas_token, expected=200)
        self.request(f"/api/items/{item['id']}", expected=404)

    def test_18_account_suspension_invalidates_existing_token(self):
        # Conta de teste separada para não afetar os usuários usados pelos demais testes.
        _, created = self.request("/api/register", "POST", {"name":"Conta Suspensa", "email":"suspensa.teste@campus.edu.br", "password":"Senha12345", "password_confirmation":"Senha12345"}, expected=201)
        token_value = urllib.parse.parse_qs(urllib.parse.urlparse(created["verification_url"]).query)["token"][0]
        self.request("/api/verify-email?token="+urllib.parse.quote(token_value), expected=200)
        _, login = self.request("/api/login", "POST", {"email":"suspensa.teste@campus.edu.br", "password":"Senha12345"}, expected=200)
        _, users = self.request("/api/admin/users", token=self.admin_token, expected=200)
        user = next(u for u in users["users"] if u["email"]=="suspensa.teste@campus.edu.br")
        self.request(f"/api/admin/users/{user['id']}/status", "PATCH", {"status":"Suspenso"}, token=self.admin_token, expected=200)
        self.request("/api/me", token=login["token"], expected=401)

    def test_19_maintenance_expires_stale_items_and_saves_history(self):
        with application.connect() as db:
            category_id=db.execute("SELECT id FROM categories WHERE name='Outros'").fetchone()[0]
            location_id=db.execute("SELECT id FROM locations WHERE name='Biblioteca central'").fetchone()[0]
            old=(datetime.now()-timedelta(days=70)).replace(microsecond=0).isoformat()
            cur=db.execute("INSERT INTO items(title,type,category,category_id,description,location,location_id,event_date,status,owner_id,photos_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           ("Item antigo expira","Perdido","Outros",category_id,"Descrição do item antigo","Biblioteca central",location_id,(date.today()-timedelta(days=70)).isoformat(),"Aberto",1,"[]",old,old))
            item_id=cur.lastrowid
        application.maintenance(force=True)
        with application.connect() as db:
            item=db.execute("SELECT status FROM items WHERE id=?",(item_id,)).fetchone()
            events=db.execute("SELECT action FROM item_history WHERE item_id=?",(item_id,)).fetchall()
        self.assertEqual(item["status"],"Expirado")
        self.assertTrue(any("Expiração" in e["action"] for e in events))

    def test_20_invalid_json_has_clear_error(self):
        req=urllib.request.Request(self.base_url+"/api/login",data=b"{nao-json",headers={"Content-Type":"application/json"},method="POST")
        try:
            urllib.request.urlopen(req,timeout=8)
            self.fail("Era esperado status 400")
        except urllib.error.HTTPError as e:
            data=json.loads(e.read().decode())
            self.assertEqual(e.code,400)
            self.assertIn("JSON válido",data["error"])

    def test_21_frontend_is_served_and_email_preferences_persist(self):
        _, page = self.request("/", expected=200)
        self.assertIn("Encontrei", page["html"])
        self.assertIn("resendVerification", page["html"])
        self.assertIn("renderModeration", page["html"])
        self.assertIn("submitPublish", page["html"])
        self.assertIn("@media(max-width:600px)", page["html"])
        _, before = self.request("/api/me", token=self.student_token, expected=200)
        self.assertIn("email_notifications", before["user"])
        self.request("/api/me/preferences", "PATCH", {"email_notifications": True}, token=self.student_token, expected=200)
        _, after = self.request("/api/me", token=self.student_token, expected=200)
        self.assertTrue(after["user"]["email_notifications"])
        self.request("/api/me/preferences", "PATCH", {"email_notifications": False}, token=self.student_token, expected=200)

    def test_22_more_than_three_photos_is_rejected(self):
        photo = self.image()
        payload = {"title":"Anúncio com fotos demais", "type":"Perdido", "category":"Outros",
                   "description":"Teste do limite de quantidade de fotos.", "location":"Biblioteca central",
                   "event_date":date.today().isoformat(), "photos":[photo,photo,photo,photo]}
        _, result = self.request("/api/items", "POST", payload, token=self.lucas_token, expected=400)
        self.assertIn("3 fotos", result["error"].lower())


    def test_23_unknown_catalog_values_are_rejected(self):
        payload = {"title":"Categoria não cadastrada", "type":"Perdido", "category":"Categoria inventada",
                   "description":"Descrição válida para testar o catálogo controlado.", "location":"Biblioteca central",
                   "event_date":date.today().isoformat(), "photos":[]}
        _, result = self.request("/api/items", "POST", payload, token=self.lucas_token, expected=400)
        self.assertIn("categoria ativa cadastrada", result["error"].lower())
        payload["category"] = "Chaves"
        payload["location"] = "Local inventado"
        _, result = self.request("/api/items", "POST", payload, token=self.lucas_token, expected=400)
        self.assertIn("local cadastrado", result["error"].lower())
        with application.connect() as db:
            self.assertIsNone(db.execute("SELECT id FROM categories WHERE name='Categoria inventada'").fetchone())
            self.assertIsNone(db.execute("SELECT id FROM locations WHERE name='Local inventado'").fetchone())

    def test_24_match_date_window_has_correct_direction(self):
        today = date.today()
        with application.connect() as db:
            category_id = db.execute("SELECT id FROM categories WHERE name='Chaves'").fetchone()[0]
            location_id = db.execute("SELECT id FROM locations WHERE name='Bloco B — corredor do térreo'").fetchone()[0]
            stamp = application.now()
            def insert_item(title, typ, event_date):
                cur = db.execute("""INSERT INTO items(title,type,category,category_id,description,location,location_id,event_date,status,owner_id,photos_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (title,typ,"Chaves",category_id,"Descrição para teste de correspondência.","Bloco B — corredor do térreo",location_id,event_date,"Aberto",1,"[]",stamp,stamp))
                return cur.lastrowid
            lost_id = insert_item("Perda de teste com data antiga", "Perdido", (today-timedelta(days=10)).isoformat())
            found_after_id = insert_item("Achado posterior compatível", "Achado", (today-timedelta(days=5)).isoformat())
            found_before_id = insert_item("Achado anterior incompatível", "Achado", (today-timedelta(days=20)).isoformat())
            found_id = insert_item("Achado de teste", "Achado", (today-timedelta(days=10)).isoformat())
            loss_before_id = insert_item("Perda anterior compatível", "Perdido", (today-timedelta(days=15)).isoformat())
            loss_after_id = insert_item("Perda posterior incompatível", "Perdido", (today-timedelta(days=5)).isoformat())
            lost_row = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.id=?",(lost_id,)).fetchone()
            found_row = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.id=?",(found_id,)).fetchone()
            lost_matches = {x["id"] for x in application.find_matches(db,lost_row,limit=30)}
            found_matches = {x["id"] for x in application.find_matches(db,found_row,limit=30)}
        self.assertIn(found_after_id, lost_matches)
        self.assertNotIn(found_before_id, lost_matches)
        self.assertIn(loss_before_id, found_matches)
        self.assertNotIn(loss_after_id, found_matches)

    def test_25_edit_cannot_bypass_guard_category_rule(self):
        # Cria um achado de categoria comum diretamente no banco para isolar a regra de edição.
        with application.connect() as db:
            cat_id = db.execute("SELECT id FROM categories WHERE name='Garrafas'").fetchone()[0]
            loc_id = db.execute("SELECT id FROM locations WHERE name='Biblioteca central'").fetchone()[0]
            stamp = application.now()
            cur = db.execute("""INSERT INTO items(title,type,category,category_id,description,location,location_id,event_date,status,owner_id,photos_json,verification_question,verification_answer,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("Achado editável", "Achado", "Garrafas", cat_id, "Descrição válida para testar a edição de categoria.", "Biblioteca central", loc_id, date.today().isoformat(), "Aberto", 1, json.dumps(["/uploads/demo-bottle.png"]), "Qual a cor?", "verde", stamp, stamp))
            item_id = cur.lastrowid
        _, result = self.request(f"/api/items/{item_id}", "PATCH", {"category":"Documentos"}, token=self.student_token, expected=400)
        self.assertIn("ponto de guarda", result["error"].lower())



    def test_26_database_integrity_constraints_and_indexes(self):
        with application.connect() as db:
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            indexes = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
            self.assertIn("one_active_claim_per_user_item", indexes)
            self.assertIn("one_approved_claim_per_item", indexes)
            self.assertIn("idx_items_status_type_date", indexes)
            with self.assertRaises(application.sqlite3.IntegrityError):
                db.execute("INSERT INTO item_history(item_id,actor_id,action,note,created_at) VALUES(999999,1,'Teste','FK inválida',?)", (application.now(),))
            cat_id = db.execute("SELECT id FROM categories WHERE name='Outros'").fetchone()[0]
            loc_id = db.execute("SELECT id FROM locations WHERE name='Biblioteca central'").fetchone()[0]
            stamp = application.now()
            cur = db.execute("INSERT INTO items(title,type,category,category_id,description,location,location_id,event_date,status,owner_id,photos_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("Item para testar índice", "Perdido", "Outros", cat_id, "Descrição de integridade do banco.", "Biblioteca central", loc_id, date.today().isoformat(), "Aberto", 1, "[]", stamp, stamp))
            test_item_id = cur.lastrowid
            db.execute("INSERT INTO claims(item_id,claimant_id,answer,status,routed_to_moderation,created_at,updated_at) VALUES(?,3,'resposta','Aprovada',0,?,?)", (test_item_id,stamp,stamp))
            # A segunda pessoa é diferente: o índice impede outra aprovação para o mesmo item.
            with self.assertRaises(application.sqlite3.IntegrityError):
                db.execute("INSERT INTO claims(item_id,claimant_id,answer,status,routed_to_moderation,created_at,updated_at) VALUES(?,4,'resposta','Aprovada',0,?,?)", (test_item_id,stamp,stamp))



    def test_27_optional_smtp_notification_delivery_path(self):
        smtp_env = {
            "ENCONTREI_SMTP_HOST": "smtp.example.test",
            "ENCONTREI_SMTP_PORT": "587",
            "ENCONTREI_SMTP_USER": "mailer@example.test",
            "ENCONTREI_SMTP_PASSWORD": "fake-test-password",
            "ENCONTREI_SMTP_FROM": "mailer@example.test",
            "ENCONTREI_SMTP_TLS": "true",
            "ENCONTREI_SMTP_SSL": "false",
        }
        with patch.dict(os.environ, smtp_env), patch.object(application.smtplib, "SMTP") as smtp_factory:
            client = MagicMock()
            smtp_factory.return_value.__enter__.return_value = client
            sent = application.send_email("aluno@campus.edu.br", "Assunto de teste", "Corpo de teste")
        self.assertTrue(sent)
        smtp_factory.assert_called_once_with("smtp.example.test", 587, timeout=8)
        client.starttls.assert_called_once()
        client.send_message.assert_called_once()
        message = client.send_message.call_args.args[0]
        self.assertEqual(message["To"], "aluno@campus.edu.br")
        self.assertEqual(message["Subject"], "Assunto de teste")


    def test_28_maintenance_worker_runs_periodically_until_stopped(self):
        class StopAfterOneCycle:
            def __init__(self):
                self.calls = 0
            def wait(self, interval):
                self.calls += 1
                return self.calls > 1

        stop_event = StopAfterOneCycle()
        with patch.object(application, "maintenance") as maintenance_mock:
            application.maintenance_worker(stop_event, interval=0.01)
        maintenance_mock.assert_called_once_with(force=True)
        self.assertEqual(stop_event.calls, 2)


    def test_29_item_report_duplicate_and_moderation_decision(self):
        item = self.create_found(title="Anúncio para denúncia de teste", token=self.lucas_token)
        _, created = self.request(f"/api/items/{item['id']}/reports", "POST",
                                  {"reason": "Descrição potencialmente enganosa para teste."},
                                  token=self.student_token, expected=201)
        self.request(f"/api/items/{item['id']}/reports", "POST",
                     {"reason": "Tentativa de repetir a denúncia deste anúncio."},
                     token=self.student_token, expected=409)
        _, queue = self.request("/api/moderation/reports", token=self.mod_token, expected=200)
        report = next((r for r in queue["reports"] if r["item_id"] == item["id"]), None)
        self.assertIsNotNone(report)
        self.request(f"/api/reports/{report['id']}/decision", "POST",
                     {"decision": "Manter anúncio", "note": "Revisado; não há infração."},
                     token=self.mod_token, expected=200)
        _, detail = self.request(f"/api/items/{item['id']}", expected=200)
        self.assertEqual(detail["item"]["status"], "Aberto")

    def test_30_rejected_claim_sends_reason_notification(self):
        item = self.create_found(title="Achado para teste de recusa", token=self.lucas_token)
        _, claim = self.request(f"/api/items/{item['id']}/claims", "POST",
                                {"answer": "teste azul"}, token=self.student_token, expected=201)
        self.request(f"/api/claims/{claim['claim_id']}/decision", "POST",
                     {"decision": "Recusada", "note": "Resposta insuficiente para confirmar a posse."},
                     token=self.lucas_token, expected=200)
        _, my_claims = self.request("/api/my/claims", token=self.student_token, expected=200)
        saved = next(c for c in my_claims["claims"] if c["id"] == claim["claim_id"])
        self.assertEqual(saved["status"], "Recusada")
        _, notifications = self.request("/api/notifications", token=self.student_token, expected=200)
        self.assertTrue(any("recusada" in n["title"].lower() for n in notifications["notifications"]))


    def test_31_expired_verification_can_be_resent_and_used(self):
        email = "aluna.reenvio@campus.edu.br"
        _, created = self.request("/api/register", "POST", {
            "name": "Aluna Reenvio", "email": email,
            "password": "Senha12345", "password_confirmation": "Senha12345"
        }, expected=201)
        token1 = urllib.parse.parse_qs(urllib.parse.urlparse(created["verification_url"]).query)["token"][0]
        with application.connect() as db:
            db.execute("UPDATE users SET verification_expires_at=? WHERE email=?", ((datetime.now()-timedelta(hours=1)).replace(microsecond=0).isoformat(), email))
        self.request("/api/verify-email?token=" + urllib.parse.quote(token1), expected=410)
        _, resent = self.request("/api/resend-verification", "POST", {"email": email}, expected=200)
        token2 = urllib.parse.parse_qs(urllib.parse.urlparse(resent["verification_url"]).query)["token"][0]
        self.assertNotEqual(token1, token2)
        self.request("/api/verify-email?token=" + urllib.parse.quote(token2), expected=200)
        self.request("/api/login", "POST", {"email": email, "password": "Senha12345"}, expected=200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
