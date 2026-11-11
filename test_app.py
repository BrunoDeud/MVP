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
        application.RATE_LIMITS.clear()
        application.LAST_MAINTENANCE = 0
        # Os testes usam o modo demonstração (contas fictícias e link de verificação na resposta).
        cls._demo_before = application.DEMO_MODE
        application.DEMO_MODE = True
        application.MAX_OPEN_ITEMS = application.MAX_ITEMS_PER_DAY = 100  # vários testes publicam com a mesma conta
        application.init_db(demo=True)
        cls.server = application.LocalHTTPServer(("127.0.0.1", 0), application.Handler)
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
        application.DEMO_MODE = cls._demo_before

    def setUp(self):
        # Limites de taxa são por IP; cada teste começa com a janela limpa.
        application.RATE_LIMITS.clear()

    @classmethod
    def request(cls, path, method="GET", body=None, token=None, expected=None, headers=None, with_headers=False):
        data = None if body is None else json.dumps(body).encode("utf-8")
        all_headers = {"Content-Type": "application/json"}
        if token:
            all_headers["Authorization"] = "Bearer " + token
        all_headers.update(headers or {})
        req = urllib.request.Request(cls.base_url + path, data=data, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as res:
                status = res.status
                raw = res.read().decode("utf-8")
                response_headers = res.headers
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read().decode("utf-8")
            response_headers = e.headers
        try:
            result = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            result = {"html": raw}
        if expected is not None and status != expected:
            raise AssertionError(f"{method} {path}: esperado {expected}, recebido {status}: {result}")
        if with_headers:
            return status, result, response_headers
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
        self.assertNotIn("items", data)  # V13: não divulga contagem de anúncios

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

    # ------------------------------------------------------------------
    # Regressão das vulnerabilidades documentadas em docs/seguranca/
    # ------------------------------------------------------------------

    @classmethod
    def new_user(cls, email, role=None, aged=False):
        """Cadastra, verifica (modo demonstração) e autentica uma conta de teste."""
        _, created = cls.request("/api/register", "POST", {"name": "Conta de Teste", "email": email, "password": "Senha12345", "password_confirmation": "Senha12345"}, expected=201)
        token = urllib.parse.parse_qs(urllib.parse.urlparse(created["verification_url"]).query)["token"][0]
        cls.request("/api/verify-email?token=" + urllib.parse.quote(token), expected=200)
        with application.connect() as db:
            user_id = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
            if aged:
                db.execute("UPDATE users SET created_at=? WHERE id=?", ((datetime.now()-timedelta(days=10)).replace(microsecond=0).isoformat(), user_id))
        if role:
            cls.request(f"/api/admin/users/{user_id}/role", "PATCH", {"role": role}, token=cls.admin_token, expected=200)
        return cls.login(email, "Senha12345")["token"], user_id

    @staticmethod
    def age_seed_accounts():
        with application.connect() as db:
            db.execute("UPDATE users SET created_at=? WHERE email LIKE '%@campus.edu.br'", ((datetime.now()-timedelta(days=10)).replace(microsecond=0).isoformat(),))

    def item_status(self, item_id):
        with application.connect() as db:
            return db.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()[0]

    def test_32_v01_verification_link_not_returned_outside_demo(self):
        application.DEMO_MODE = False
        try:
            with patch("builtins.print"):
                _, created = self.request("/api/register", "POST", {"name": "Fora do Demo", "email": "fora.demo@campus.edu.br", "password": "Senha12345", "password_confirmation": "Senha12345"}, expected=201)
                self.assertNotIn("verification_url", created)
                self.assertNotIn("user_id", created)
                # V08: e-mail já cadastrado recebe a mesma resposta (sem 409).
                _, again = self.request("/api/register", "POST", {"name": "Fora do Demo", "email": "fora.demo@campus.edu.br", "password": "Senha12345", "password_confirmation": "Senha12345"}, expected=201)
                self.assertEqual(created["message"], again["message"])
                _, unknown = self.request("/api/resend-verification", "POST", {"email": "ninguem@campus.edu.br"}, expected=200)
                _, pending = self.request("/api/resend-verification", "POST", {"email": "fora.demo@campus.edu.br"}, expected=200)
                self.assertEqual(unknown["message"], pending["message"])
                self.assertNotIn("verification_url", pending)
            self.request("/api/login", "POST", {"email": "fora.demo@campus.edu.br", "password": "Senha12345"}, expected=403)
        finally:
            application.DEMO_MODE = True

    def test_33_v02_claim_answer_attempts_are_limited(self):
        item = self.create_found(title="Achado com limite de tentativas", token=self.lucas_token)
        for remaining in (2, 1, 0):
            _, data = self.request(f"/api/items/{item['id']}/claims", "POST", {"answer": "chute"}, token=self.student_token, expected=400)
            self.assertIn(str(remaining), data["error"])
        # Mesmo a resposta certa é recusada depois do bloqueio.
        self.request(f"/api/items/{item['id']}/claims", "POST", {"answer": "teste azul"}, token=self.student_token, expected=429)
        _, notes = self.request("/api/notifications", token=self.lucas_token, expected=200)
        self.assertTrue(any(n["title"] == "Tentativas incorretas" and n["item_id"] == item["id"] for n in notes["notifications"]))
        with application.connect() as db:
            stored = db.execute("SELECT verification_answer FROM items WHERE id=?", (item["id"],)).fetchone()[0]
        self.assertTrue(stored.startswith("hmac$"))  # V11
        self.assertNotIn("azul", stored)

    def test_34_v03_new_accounts_do_not_auto_hide_items(self):
        item = self.create_lost(title="Anúncio contra contas novas", token=self.lucas_token)
        for i in range(3):
            token, _ = self.new_user(f"fantoche{i}@alunos.campus.edu.br")
            self.request(f"/api/items/{item['id']}/reports", "POST", {"reason": "Denúncia de conta recém-criada."}, token=token, expected=201)
        self.assertEqual(self.item_status(item["id"]), "Aberto")

    def test_35_nv05_dismissal_restores_previous_status(self):
        self.age_seed_accounts()
        third_token, _ = self.new_user("terceiro.denunciante@campus.edu.br", aged=True)
        item = self.create_lost(title="Item guardado para restauração", token=self.lucas_token)
        with application.connect() as db:
            db.execute("UPDATE items SET status='No ponto de guarda' WHERE id=?", (item["id"],))
        for token in (self.student_token, self.admin_token, third_token):
            self.request(f"/api/items/{item['id']}/reports", "POST", {"reason": "Denúncia para ocultar o anúncio."}, token=token, expected=201)
        self.assertEqual(self.item_status(item["id"]), "Oculto")
        _, queue = self.request("/api/moderation/reports", token=self.mod_token, expected=200)
        for report in [r for r in queue["reports"] if r["item_id"] == item["id"]]:
            self.request(f"/api/reports/{report['id']}/decision", "POST", {"decision": "Manter anúncio", "note": "Sem fundamento."}, token=self.mod_token, expected=200)
        self.assertEqual(self.item_status(item["id"]), "No ponto de guarda")
        # Itens encerrados não são ocultados nem reabertos por denúncias.
        resolved = self.create_lost(title="Item resolvido denunciado", token=self.lucas_token)
        self.request(f"/api/items/{resolved['id']}/resolve", "POST", {}, token=self.lucas_token, expected=200)
        for token in (self.student_token, self.admin_token, third_token):
            self.request(f"/api/items/{resolved['id']}/reports", "POST", {"reason": "Denúncia em item resolvido."}, token=token, expected=201)
        self.assertEqual(self.item_status(resolved["id"]), "Resolvido")

    def test_36_nv03_staff_not_auto_suspended_and_no_self_judging(self):
        mod2_token, _ = self.new_user("moderador.dois@campus.edu.br", role="Moderador")
        for n in range(3):
            item = self.create_lost(title=f"Anúncio da administração {n}", token=self.admin_token)
            self.request(f"/api/items/{item['id']}/reports", "POST", {"reason": "Conteúdo indevido no anúncio."}, token=self.student_token, expected=201)
            _, queue = self.request("/api/moderation/reports", token=self.mod_token, expected=200)
            report = next(r for r in queue["reports"] if r["item_id"] == item["id"])
            self.request(f"/api/reports/{report['id']}/decision", "POST", {"decision": "Ocultar anúncio", "note": "Procedente para teste."}, token=self.mod_token, expected=200)
        _, me = self.request("/api/me", token=self.admin_token, expected=200)
        self.assertEqual(me["user"]["status"], "Ativo")
        # Moderador não decide denúncia sobre o próprio anúncio.
        own = self.create_lost(title="Anúncio do moderador", token=self.mod_token)
        self.request(f"/api/items/{own['id']}/reports", "POST", {"reason": "Denúncia contra o moderador."}, token=self.student_token, expected=201)
        _, queue = self.request("/api/moderation/reports", token=self.mod_token, expected=200)
        report = next(r for r in queue["reports"] if r["item_id"] == own["id"])
        self.request(f"/api/reports/{report['id']}/decision", "POST", {"decision": "Manter anúncio", "note": "Decidindo em causa própria."}, token=self.mod_token, expected=403)
        self.request(f"/api/reports/{report['id']}/decision", "POST", {"decision": "Manter anúncio", "note": "Revisado por outra pessoa."}, token=mod2_token, expected=200)

    def test_37_nv04_v12_hidden_item_blocks_approval_and_return(self):
        item = self.create_found(title="Achado ocultado depois", token=self.lucas_token)
        _, pending = self.request(f"/api/items/{item['id']}/claims", "POST", {"answer": "teste azul"}, token=self.student_token, expected=201)
        with application.connect() as db:
            db.execute("UPDATE items SET status='Oculto' WHERE id=?", (item["id"],))
        self.request(f"/api/claims/{pending['claim_id']}/decision", "POST", {"decision": "Aprovada", "note": "ok"}, token=self.lucas_token, expected=409)
        with application.connect() as db:
            db.execute("UPDATE items SET status='Aberto' WHERE id=?", (item["id"],))
        self.request(f"/api/claims/{pending['claim_id']}/decision", "POST", {"decision": "Aprovada", "note": "ok"}, token=self.lucas_token, expected=200)
        with application.connect() as db:
            db.execute("UPDATE items SET status='Oculto' WHERE id=?", (item["id"],))
        self.request(f"/api/claims/{pending['claim_id']}/returned", "POST", {}, token=self.lucas_token, expected=409)
        self.assertEqual(self.item_status(item["id"]), "Oculto")
        with application.connect() as db:
            db.execute("UPDATE items SET status='Aberto' WHERE id=?", (item["id"],))
        self.request(f"/api/claims/{pending['claim_id']}/returned", "POST", {}, token=self.lucas_token, expected=200)
        self.request(f"/api/claims/{pending['claim_id']}/returned", "POST", {}, token=self.lucas_token, expected=409)

    def test_38_v04_nv06_seed_accounts(self):
        # Uma suspensão sobrevive a um novo init_db no modo demonstração.
        with application.connect() as db:
            db.execute("UPDATE users SET status='Suspenso' WHERE email='lucas@campus.edu.br'")
        try:
            application.init_db(demo=True)
            with application.connect() as db:
                self.assertEqual(db.execute("SELECT status FROM users WHERE email='lucas@campus.edu.br'").fetchone()[0], "Suspenso")
        finally:
            with application.connect() as db:
                db.execute("UPDATE users SET status='Ativo' WHERE email='lucas@campus.edu.br'")
        # Fora do modo demonstração: banco novo sem contas públicas e senhas públicas trocadas.
        original = application.DB_PATH
        try:
            application.DB_PATH = application.DATA_DIR / "fora-do-demo.sqlite3"
            with patch("builtins.print") as printed:
                application.init_db(demo=False)
            with application.connect() as db:
                emails = {r[0] for r in db.execute("SELECT email FROM users").fetchall()}
                self.assertEqual(emails, {"admin@campus.edu.br"})
                self.assertEqual(db.execute("SELECT COUNT(*) FROM items").fetchone()[0], 0)
            self.assertTrue(any("senha" in str(c) for c in printed.call_args_list))
            application.DB_PATH = application.DATA_DIR / "demo-depois.sqlite3"
            application.init_db(demo=True)
            with patch("builtins.print"):
                application.init_db(demo=False)
            with application.connect() as db:
                row = db.execute("SELECT salt,password_hash,password_iterations FROM users WHERE email='admin@campus.edu.br'").fetchone()
            _, digest = application.hash_password("Admin@12345", row["salt"], row["password_iterations"])
            self.assertNotEqual(digest, row["password_hash"])
        finally:
            application.DB_PATH = original

    def test_39_nv07_unknown_host_is_rejected(self):
        _, data = self.request("/api/items", headers={"Host": "rebind.attacker.example:8000"}, expected=421)
        self.assertIn("Host", data["error"])
        self.request("/api/login", "POST", {"email": "admin@campus.edu.br", "password": "Admin@12345"}, headers={"Host": "rebind.attacker.example"}, expected=421)

    def test_40_nv08_v06_login_limits_and_bounded_keys(self):
        huge = "x" * 10000 + "@campus.edu.br"
        for _ in range(3):
            self.request("/api/login", "POST", {"email": huge, "password": "errada"}, expected=401)
        self.assertTrue(all(len(str(k)) < 400 for k in application.RATE_LIMITS))
        for _ in range(8):
            self.request("/api/login", "POST", {"email": "estudante@campus.edu.br", "password": "errada"}, expected=401)
        self.request("/api/login", "POST", {"email": "estudante@campus.edu.br", "password": "Estudante@12345"}, expected=429)
        application.RATE_LIMITS.clear()
        # Bloqueio por conta, independente do IP: 10 erros em 15 minutos.
        for _ in range(10):
            application.rate_hit(("login-fail", "estudante@campus.edu.br"), 10**6, 900)
        self.request("/api/login", "POST", {"email": "estudante@campus.edu.br", "password": "Estudante@12345"}, expected=429)
        application.RATE_LIMITS.clear()
        _, data = self.request("/api/register", "POST", {"name": "Senha Comum", "email": "senha.comum@campus.edu.br", "password": "12345678", "password_confirmation": "12345678"}, expected=400)
        self.assertIn("comum", data["error"])

    def test_41_v06_legacy_hash_is_upgraded_on_login(self):
        salt, digest = application.hash_password("Legado@2024", iterations=application.LEGACY_PBKDF2_ITERATIONS)
        with application.connect() as db:
            db.execute("INSERT INTO users(name,email,role,salt,password_hash,password_iterations,created_at,status,email_verified) VALUES('Conta Legada','legado@campus.edu.br','Estudante',?,?,?,?,'Ativo',1)",
                       (salt, digest, application.LEGACY_PBKDF2_ITERATIONS, application.now()))
        self.login("legado@campus.edu.br", "Legado@2024")
        with application.connect() as db:
            self.assertEqual(db.execute("SELECT password_iterations FROM users WHERE email='legado@campus.edu.br'").fetchone()[0], application.PBKDF2_ITERATIONS)
        self.login("legado@campus.edu.br", "Legado@2024")

    def test_42_nv09_v09_photo_edit_validates_before_writing(self):
        item = self.create_found(title="Achado com edição de fotos", token=self.lucas_token)
        before = set(application.UPLOAD_DIR.iterdir())
        bad = {"mime": "image/png", "data": "data:image/png;base64," + base64.b64encode(b"nao e png").decode()}
        self.request(f"/api/items/{item['id']}", "PATCH", {"photos": [self.image(), bad]}, token=self.lucas_token, expected=400)
        self.request(f"/api/items/{item['id']}", "PATCH", {"photos": [self.image()], "location": "Local inexistente"}, token=self.lucas_token, expected=400)
        self.request(f"/api/items/{item['id']}", "PATCH", {"photos": ["texto"]}, token=self.lucas_token, expected=400)
        self.assertEqual(set(application.UPLOAD_DIR.iterdir()), before)
        self.request(f"/api/items/{item['id']}", "PATCH", {"photos": [self.image()]}, token=self.lucas_token, expected=200)

    def test_43_v10_image_metadata_is_removed(self):
        exif = b"Exif\x00\x00GPS-LATITUDE-SECRETA"
        jpeg = (b"\xff\xd8" + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                + b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
                + b"\xff\xfe\x00\x0ccomentario" + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\x12\x34" + b"\xff\xd9")
        clean = application.strip_jpeg_metadata(jpeg)
        self.assertNotIn(b"GPS-LATITUDE", clean)
        self.assertNotIn(b"comentario", clean)
        self.assertIn(b"JFIF", clean)
        png = (application.UPLOAD_DIR / "demo-bottle.png").read_bytes()
        text_chunk = b"tEXt" + b"Author\x00Fulano"
        crc = application.zlib.crc32(text_chunk).to_bytes(4, "big")
        tagged = png[:33] + (len(text_chunk) - 4).to_bytes(4, "big") + text_chunk + crc + png[33:]
        self.assertNotIn(b"Fulano", application.strip_png_metadata(tagged))
        vp8x = b"VP8X" + (10).to_bytes(4, "little") + bytes([0x08]) + b"\x00" * 9
        exif_chunk = b"EXIF" + (4).to_bytes(4, "little") + b"GPS!"
        body = b"WEBP" + vp8x + exif_chunk
        webp = application.strip_webp_metadata(b"RIFF" + len(body).to_bytes(4, "little") + body)
        self.assertNotIn(b"GPS!", webp)
        self.assertEqual(int.from_bytes(webp[4:8], "little"), len(webp) - 8)
        self.assertEqual(webp[20] & 0x08, 0)
        # Pela API: a foto publicada não contém os metadados.
        _, result = self.request("/api/items", "POST", {
            "title": "Achado com EXIF", "type": "Achado", "category": "Garrafas",
            "description": "Foto com metadados de localização.", "location": "Biblioteca central",
            "event_date": date.today().isoformat(),
            "photos": [{"mime": "image/jpeg", "data": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}],
            "verification_question": "Qual detalhe está gravado?", "verification_answer": "teste"
        }, token=self.lucas_token, expected=201)
        saved = (application.UPLOAD_DIR / Path(result["item"]["photos"][0]).name).read_bytes()
        self.assertNotIn(b"GPS-LATITUDE", saved)

    def test_44_v11_verification_token_stored_hashed(self):
        _, created = self.request("/api/register", "POST", {"name": "Token Hash", "email": "token.hash@campus.edu.br", "password": "Senha12345", "password_confirmation": "Senha12345"}, expected=201)
        raw = urllib.parse.parse_qs(urllib.parse.urlparse(created["verification_url"]).query)["token"][0]
        with application.connect() as db:
            stored = db.execute("SELECT verification_token FROM users WHERE email='token.hash@campus.edu.br'").fetchone()[0]
        self.assertNotEqual(stored, raw)
        self.assertEqual(stored, application.token_digest(raw))

    def test_45_v05_v13_headers_cookie_and_csrf(self):
        _, _, headers = self.request("/", with_headers=True, expected=200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertNotIn("Python", headers["Server"])
        _, login, headers = self.request("/api/login", "POST", {"email": "lucas@campus.edu.br", "password": "Lucas@12345"}, with_headers=True, expected=200)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        session = cookie.split(";", 1)[0]
        self.request("/api/me", headers={"Cookie": session}, expected=200)
        # Com cookie, POST sem o cabeçalho do frontend é recusado (CSRF).
        self.request("/api/notifications/read-all", "POST", {}, headers={"Cookie": session}, expected=403)
        self.request("/api/notifications/read-all", "POST", {}, headers={"Cookie": session, "X-Encontrei": "1"}, expected=200)
        self.request("/api/logout", "POST", {}, headers={"Cookie": session, "X-Encontrei": "1"}, expected=200)
        self.request("/api/me", headers={"Cookie": session}, expected=401)

    def test_46_v15_smtp_login_requires_encryption(self):
        smtp_env = {"ENCONTREI_SMTP_HOST": "smtp.example.test", "ENCONTREI_SMTP_USER": "mailer@example.test",
                    "ENCONTREI_SMTP_PASSWORD": "fake-test-password", "ENCONTREI_SMTP_TLS": "false", "ENCONTREI_SMTP_SSL": "false"}
        with patch.dict(os.environ, smtp_env), patch.object(application.smtplib, "SMTP") as smtp_factory, patch("builtins.print"):
            sent = application.send_email("aluno@campus.edu.br", "Assunto", "Corpo")
        self.assertFalse(sent)
        smtp_factory.assert_not_called()

    def test_47_v07_session_idle_timeout_and_body_limit(self):
        token = self.login("lucas@campus.edu.br", "Lucas@12345")["token"]
        uid, expires, _ = application.TOKENS[token]
        application.TOKENS[token] = (uid, expires, application.time.time() - application.SESSION_IDLE - 1)
        self.request("/api/me", token=token, expected=401)
        req = urllib.request.Request(self.base_url + "/api/login", data=b"{" + b" " * (application.MAX_SMALL_BODY + 10) + b"}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=8)
            self.fail("Era esperado 413")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 413)
        except (ConnectionError, urllib.error.URLError):
            pass  # o servidor pode fechar a conexão antes de ler o corpo inteiro


if __name__ == "__main__":
    unittest.main(verbosity=2)
