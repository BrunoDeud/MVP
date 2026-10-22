#!/usr/bin/env python3
"""Encontrei - versão local simplificada usando apenas a biblioteca padrão do Python."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime, date, timedelta
from contextlib import contextmanager
import base64, hashlib, hmac, json, mimetypes, os, re, secrets, sqlite3, threading, webbrowser

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = ROOT / "uploads"
DB_PATH = DATA_DIR / "encontrei.sqlite3"
WEB_PATH = ROOT / "index.html"
HOST, PORT = "127.0.0.1", 8000
MAX_BODY = 24 * 1024 * 1024
DB_LOCK = threading.RLock()
TOKENS = {}

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)


def now():
    return datetime.now().isoformat(timespec="seconds")


def norm(text):
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return salt, digest


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with DB_LOCK, connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            role TEXT NOT NULL DEFAULT 'Estudante',
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('Achado','Perdido')),
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            event_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Aberto',
            owner_id INTEGER NOT NULL REFERENCES users(id),
            verification_question TEXT,
            verification_answer TEXT,
            photos_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            claimant_id INTEGER NOT NULL REFERENCES users(id),
            answer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decision_by INTEGER REFERENCES users(id),
            decision_note TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_claim_per_user_item
          ON claims(item_id, claimant_id) WHERE status IN ('Pendente','Aprovada');
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            reporter_id INTEGER NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente',
            created_at TEXT NOT NULL,
            UNIQUE(item_id, reporter_id)
        );
        CREATE TABLE IF NOT EXISTS moderation_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            moderator_id INTEGER NOT NULL REFERENCES users(id),
            item_id INTEGER REFERENCES items(id),
            report_id INTEGER REFERENCES reports(id),
            action TEXT NOT NULL,
            justification TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            claim_id INTEGER NOT NULL REFERENCES claims(id),
            sender_id INTEGER NOT NULL REFERENCES users(id),
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        users = [
            ("Ana Souza", "estudante@campus.edu.br", "Estudante", "Estudante@12345"),
            ("Carlos Moderador", "moderador@campus.edu.br", "Moderador", "Moderador@12345"),
            ("Patrícia Administradora", "admin@campus.edu.br", "Administrador", "Admin@12345"),
            ("Lucas Pereira", "lucas@campus.edu.br", "Estudante", "Lucas@12345"),
        ]
        for name, email, role, pwd in users:
            if not db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
                salt, digest = hash_password(pwd)
                db.execute("INSERT INTO users(name,email,role,salt,password_hash,created_at) VALUES(?,?,?,?,?,?)",
                           (name, email, role, salt, digest, now()))
        if db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
            student = db.execute("SELECT id FROM users WHERE email='estudante@campus.edu.br'").fetchone()[0]
            lucas = db.execute("SELECT id FROM users WHERE email='lucas@campus.edu.br'").fetchone()[0]
            today = date.today()
            sample = [
                ("Garrafa térmica verde", "Achado", "Garrafas", "Garrafa térmica verde-escura, sem marca aparente.", "Biblioteca central", (today-timedelta(days=1)).isoformat(), student, "Qual adesivo está na parte de baixo?", "montanha", "Aberto"),
                ("Chaveiro com duas chaves", "Achado", "Chaves", "Chaveiro de tecido azul com duas chaves prateadas.", "Bloco B — corredor do térreo", (today-timedelta(days=2)).isoformat(), lucas, "Qual é a cor do tecido do chaveiro?", "azul", "Aberto"),
                ("Fone de ouvido branco", "Perdido", "Eletrônicos", "Fone sem fio branco dentro de um estojo pequeno.", "Cantina", (today-timedelta(days=1)).isoformat(), lucas, None, None, "Aberto"),
                ("Caderno de capa preta", "Achado", "Material escolar", "Caderno universitário de capa preta, com elástico.", "Sala 204 — Bloco A", (today-timedelta(days=3)).isoformat(), student, "Qual a cor do elástico?", "vermelho", "Aberto"),
                ("Cartão de transporte", "Achado", "Cartões", "Cartão encontrado próximo à entrada principal. Para segurança, dados foram omitidos.", "Portaria principal", (today-timedelta(days=4)).isoformat(), student, "Qual desenho há no verso?", "sol", "Aberto"),
            ]
            for title, typ, cat, desc, loc, dt, owner, question, answer, status in sample:
                db.execute("""INSERT INTO items(title,type,category,description,location,event_date,status,owner_id,
                            verification_question,verification_answer,photos_json,created_at,updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (title,typ,cat,desc,loc,dt,status,owner,question,answer,"[]",now(),now()))
        db.commit()


def user_public(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}


def item_public(row, include_owner=True):
    photos = json.loads(row["photos_json"] or "[]")
    result = {"id": row["id"], "title": row["title"], "type": row["type"], "category": row["category"],
              "description": row["description"], "location": row["location"], "event_date": row["event_date"],
              "status": row["status"], "photos": photos, "created_at": row["created_at"]}
    if include_owner:
        result["owner_name"] = row["owner_name"] if "owner_name" in row.keys() else "Usuário"
        result["owner_id"] = row["owner_id"]
    return result


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message); self.status = status; self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "EncontreiLocal/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:%s" % PORT)
        self.end_headers(); self.wfile.write(raw)

    def body_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY: raise APIError(413, "Dados enviados excedem o limite permitido.")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, "O conteúdo enviado não é um JSON válido.")

    def current_user(self, required=True):
        auth = self.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        uid = TOKENS.get(token)
        if not uid:
            if required: raise APIError(401, "Entre no sistema para realizar esta ação.")
            return None
        with connect() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row and required: raise APIError(401, "Sessão inválida. Entre novamente.")
        return row

    def require_moderator(self, user):
        if user["role"] not in ("Moderador", "Administrador"):
            raise APIError(403, "Esta ação é exclusiva da moderação.")

    def do_OPTIONS(self):
        self.send_response(204); self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:%s" % PORT)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS"); self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path); path = parsed.path
            if path in ("/", "/index.html"):
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                body = WEB_PATH.read_bytes(); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if path.startswith("/uploads/"):
                name = Path(path.removeprefix("/uploads/")).name
                f = UPLOAD_DIR / name
                if not f.is_file(): raise APIError(404, "Arquivo não encontrado.")
                data = f.read_bytes(); self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(f))[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store")
                self.end_headers(); self.wfile.write(data); return
            qs = parse_qs(parsed.query)
            if path == "/api/health": self.send_json({"ok": True, "app": "Encontrei", "database": "SQLite"}); return
            if path == "/api/me":
                user = self.current_user(); self.send_json({"user": user_public(user)}); return
            if path == "/api/items":
                query = (qs.get("q", [""])[0]).strip()
                typ = qs.get("type", [""])[0]
                cat = qs.get("category", [""])[0]
                location = qs.get("location", [""])[0]
                status = qs.get("status", ["Aberto"])[0]
                sql = "SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE 1=1"
                vals = []
                # Buscas públicas não exibem anúncios ocultos ou já resolvidos (RN16).
                if status == "Todos":
                    sql += " AND i.status NOT IN ('Resolvido','Oculto')"
                elif status == "Aberto":
                    sql += " AND i.status='Aberto'"
                else:
                    # Status encerrados são acessíveis somente pela área privada do usuário.
                    sql += " AND 1=0"
                if typ in ("Achado", "Perdido"): sql += " AND i.type=?"; vals.append(typ)
                if cat: sql += " AND i.category=?"; vals.append(cat)
                if location: sql += " AND i.location LIKE ?"; vals.append("%"+location+"%")
                if query:
                    sql += " AND (i.title LIKE ? OR i.description LIKE ? OR i.category LIKE ? OR i.location LIKE ?)"
                    vals += ["%"+query+"%"]*4
                sql += " ORDER BY i.created_at DESC, i.id DESC"
                with connect() as db: rows = db.execute(sql, vals).fetchall()
                self.send_json({"items": [item_public(r) for r in rows]}); return
            if path.startswith("/api/items/"):
                match = re.fullmatch(r"/api/items/(\d+)(?:/(verification-question|claims))?", path)
                if not match: raise APIError(404, "Rota não encontrada.")
                item_id = int(match.group(1)); action = match.group(2)
                with connect() as db:
                    row = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.id=?", (item_id,)).fetchone()
                    if not row: raise APIError(404, "Item não encontrado.")
                    if action == "verification-question":
                        user = self.current_user()
                        if user["id"] == row["owner_id"]: raise APIError(403, "Você não pode reivindicar seu próprio anúncio.")
                        if row["type"] != "Achado" or row["status"] != "Aberto": raise APIError(400, "Este item não aceita reivindicações.")
                        if not row["verification_question"]: raise APIError(400, "Este item não tem pergunta de verificação configurada.")
                        self.send_json({"question": row["verification_question"]}); return
                    if action == "claims":
                        user = self.current_user()
                        if user["id"] != row["owner_id"] and user["role"] not in ("Moderador", "Administrador"):
                            raise APIError(403, "Somente o publicador ou a moderação pode consultar as reivindicações.")
                        claims = db.execute("SELECT c.*,u.name AS claimant_name FROM claims c JOIN users u ON u.id=c.claimant_id WHERE c.item_id=? ORDER BY c.created_at DESC", (item_id,)).fetchall()
                        self.send_json({"claims": [{"id":c["id"],"claimant_name":c["claimant_name"],"status":c["status"],"created_at":c["created_at"]} for c in claims]}); return
                    self.send_json({"item": item_public(row)}); return
            if path == "/api/my/items":
                user = self.current_user()
                with connect() as db: rows = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.owner_id=? ORDER BY i.created_at DESC", (user["id"],)).fetchall()
                self.send_json({"items": [item_public(r) for r in rows]}); return
            if path == "/api/my/claims":
                user = self.current_user()
                with connect() as db: rows = db.execute("SELECT c.*,i.title AS item_title,i.location,i.status AS item_status FROM claims c JOIN items i ON i.id=c.item_id WHERE c.claimant_id=? ORDER BY c.created_at DESC", (user["id"],)).fetchall()
                self.send_json({"claims": [dict(r) for r in rows]}); return
            if path == "/api/moderation/reports":
                user = self.current_user(); self.require_moderator(user)
                with connect() as db:
                    rows = db.execute("SELECT r.*,i.title AS item_title,u.name AS reporter_name FROM reports r JOIN items i ON i.id=r.item_id JOIN users u ON u.id=r.reporter_id WHERE r.status='Pendente' ORDER BY r.created_at",).fetchall()
                self.send_json({"reports": [dict(r) for r in rows]}); return
            if path.startswith("/api/claims/") and path.endswith("/messages"):
                claim_id = int(path.split("/")[3]); user = self.current_user()
                with connect() as db:
                    claim = db.execute("SELECT c.*,i.owner_id FROM claims c JOIN items i ON i.id=c.item_id WHERE c.id=?", (claim_id,)).fetchone()
                    if not claim: raise APIError(404, "Reivindicação não encontrada.")
                    if user["id"] not in (claim["owner_id"], claim["claimant_id"]): raise APIError(403, "Você não participa desta conversa.")
                    if claim["status"] != "Aprovada": raise APIError(400, "A conversa é liberada após a aprovação da reivindicação.")
                    rows = db.execute("SELECT m.id,m.body,m.created_at,u.name AS sender_name,m.sender_id FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.claim_id=? ORDER BY m.id", (claim_id,)).fetchall()
                self.send_json({"messages": [dict(r) for r in rows], "current_user_id": user["id"]}); return
            raise APIError(404, "Rota não encontrada.")
        except APIError as e: self.send_json({"error": e.message}, e.status)
        except Exception as e:
            print("ERRO GET:", repr(e)); self.send_json({"error": "Erro interno. Confira o terminal para detalhes."}, 500)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            data = self.body_json()
            if path == "/api/login":
                email = str(data.get("email", "")).strip().lower(); password = str(data.get("password", ""))
                with connect() as db: user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if not user: raise APIError(401, "E-mail ou senha incorretos.")
                _, digest = hash_password(password, user["salt"])
                if not hmac.compare_digest(digest, user["password_hash"]): raise APIError(401, "E-mail ou senha incorretos.")
                token = secrets.token_urlsafe(32); TOKENS[token] = user["id"]
                self.send_json({"token": token, "user": user_public(user)}); return
            if path == "/api/logout":
                token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip(); TOKENS.pop(token, None)
                self.send_json({"ok": True}); return
            if path == "/api/items":
                user = self.current_user()
                title = str(data.get("title", "")).strip(); typ = data.get("type", ""); cat = str(data.get("category", "")).strip()
                desc = str(data.get("description", "")).strip(); location = str(data.get("location", "")).strip(); event_date = str(data.get("event_date", "")).strip()
                question = str(data.get("verification_question", "")).strip(); answer = norm(data.get("verification_answer", ""))
                photos_in = data.get("photos", [])
                if not title or len(title)>100: raise APIError(400, "Informe um título com até 100 caracteres.")
                if typ not in ("Achado", "Perdido"): raise APIError(400, "Selecione se o item foi achado ou perdido.")
                if not cat or not desc or len(desc)>1200 or not location or len(location)>160: raise APIError(400, "Preencha categoria, descrição (até 1.200 caracteres) e local.")
                try: date.fromisoformat(event_date)
                except ValueError: raise APIError(400, "Informe uma data válida.")
                if not isinstance(photos_in, list) or len(photos_in)>3: raise APIError(400, "Você pode enviar no máximo 3 fotos.")
                if typ == "Achado" and not photos_in: raise APIError(400, "Itens achados precisam de pelo menos uma foto.")
                if typ == "Achado" and (not question or not answer): raise APIError(400, "Itens achados precisam de uma pergunta e uma resposta de verificação.")
                with connect() as db:
                    open_count = db.execute("SELECT COUNT(*) FROM items WHERE owner_id=? AND status='Aberto'", (user["id"],)).fetchone()[0]
                    day_count = db.execute("SELECT COUNT(*) FROM items WHERE owner_id=? AND substr(created_at,1,10)=?", (user["id"], date.today().isoformat())).fetchone()[0]
                if open_count >= 10: raise APIError(400, "Você já tem 10 anúncios abertos. Resolva algum antes de publicar outro.")
                if day_count >= 5: raise APIError(400, "Limite de 5 anúncios por dia atingido.")
                photo_urls = []
                for image in photos_in:
                    if not isinstance(image, dict): raise APIError(400, "Formato de foto inválido.")
                    mime = image.get("mime", ""); raw = image.get("data", "")
                    if mime not in ("image/jpeg", "image/png", "image/webp"): raise APIError(400, "Use fotos JPG, PNG ou WEBP.")
                    if not isinstance(raw, str) or "," not in raw: raise APIError(400, "Uma foto enviada está inválida.")
                    encoded = raw.split(",",1)[1]
                    try: binary = base64.b64decode(encoded, validate=True)
                    except Exception: raise APIError(400, "Uma foto enviada está inválida.")
                    if len(binary)>5*1024*1024: raise APIError(400, "Cada foto deve ter no máximo 5 MB.")
                    ext = {"image/jpeg":".jpg", "image/png":".png", "image/webp":".webp"}[mime]
                    name = secrets.token_hex(12)+ext; (UPLOAD_DIR/name).write_bytes(binary); photo_urls.append("/uploads/"+name)
                with connect() as db:
                    cur = db.execute("""INSERT INTO items(title,type,category,description,location,event_date,status,owner_id,
                    verification_question,verification_answer,photos_json,created_at,updated_at) VALUES(?,?,?,?,?,?,'Aberto',?,?,?,?,?,?)""",
                    (title,typ,cat,desc,location,event_date,user["id"],question or None,answer or None,json.dumps(photo_urls),now(),now()))
                    item_id = cur.lastrowid
                    row = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.id=?", (item_id,)).fetchone()
                self.send_json({"message":"Anúncio publicado com sucesso!", "item":item_public(row)}, 201); return
            if path.startswith("/api/items/") and path.endswith("/claims"):
                match = re.fullmatch(r"/api/items/(\d+)/claims", path)
                if not match: raise APIError(404,"Rota não encontrada.")
                item_id = int(match.group(1)); user = self.current_user(); response = norm(data.get("answer", ""))
                if not response: raise APIError(400, "Responda à pergunta de verificação.")
                with connect() as db:
                    item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
                    if not item: raise APIError(404, "Item não encontrado.")
                    if item["owner_id"] == user["id"]: raise APIError(403, "Você não pode reivindicar seu próprio anúncio.")
                    if item["type"] != "Achado" or item["status"] != "Aberto": raise APIError(400, "Este item não aceita reivindicações.")
                    if norm(item["verification_answer"]) != response: raise APIError(400, "Resposta não confere. Confira os detalhes que você lembra e tente novamente.")
                    try:
                        cur = db.execute("INSERT INTO claims(item_id,claimant_id,answer,status,created_at,updated_at) VALUES(?,?,?,'Pendente',?,?)", (item_id,user["id"],str(data.get("answer",""))[:250],now(),now()))
                    except sqlite3.IntegrityError: raise APIError(409, "Você já possui uma reivindicação ativa para este item.")
                    claim_id = cur.lastrowid
                self.send_json({"message":"Reivindicação enviada ao publicador.","claim_id":claim_id}, 201); return
            if path.startswith("/api/claims/") and path.endswith("/decision"):
                match = re.fullmatch(r"/api/claims/(\d+)/decision", path)
                if not match: raise APIError(404, "Rota não encontrada.")
                claim_id = int(match.group(1)); user = self.current_user(); decision = data.get("decision")
                if decision not in ("Aprovada", "Recusada"): raise APIError(400, "Decisão inválida.")
                with connect() as db:
                    claim = db.execute("SELECT c.*,i.owner_id,i.title FROM claims c JOIN items i ON i.id=c.item_id WHERE c.id=?",(claim_id,)).fetchone()
                    if not claim: raise APIError(404, "Reivindicação não encontrada.")
                    if user["id"] != claim["owner_id"] and user["role"] not in ("Moderador","Administrador"): raise APIError(403, "Somente o publicador ou a moderação pode decidir.")
                    if claim["status"] != "Pendente": raise APIError(400, "Esta reivindicação já foi respondida.")
                    db.execute("UPDATE claims SET status=?,updated_at=?,decision_by=?,decision_note=? WHERE id=?", (decision,now(),user["id"],str(data.get("note",""))[:300],claim_id))
                    if decision == "Aprovada":
                        db.execute("UPDATE claims SET status='Cancelada',updated_at=? WHERE item_id=? AND id<>? AND status='Pendente'", (now(),claim["item_id"],claim_id))
                    db.commit()
                self.send_json({"message":"Reivindicação " + ("aprovada" if decision=="Aprovada" else "recusada") + " com sucesso."}); return
            if path.startswith("/api/items/") and path.endswith("/resolve"):
                item_id = int(path.split("/")[3]); user = self.current_user()
                with connect() as db:
                    item = db.execute("SELECT * FROM items WHERE id=?",(item_id,)).fetchone()
                    if not item: raise APIError(404,"Item não encontrado.")
                    if user["id"] != item["owner_id"] and user["role"] not in ("Moderador","Administrador"): raise APIError(403,"Você não pode encerrar este anúncio.")
                    db.execute("UPDATE items SET status='Resolvido',updated_at=? WHERE id=?",(now(),item_id)); db.commit()
                self.send_json({"message":"Anúncio marcado como resolvido."}); return
            if path.startswith("/api/items/") and path.endswith("/reports"):
                item_id = int(path.split("/")[3]); user = self.current_user(); reason = str(data.get("reason", "")).strip()
                if len(reason)<5: raise APIError(400,"Descreva o motivo da denúncia (mínimo 5 caracteres).")
                with connect() as db:
                    item = db.execute("SELECT id,status FROM items WHERE id=?",(item_id,)).fetchone()
                    if not item: raise APIError(404,"Item não encontrado.")
                    try: db.execute("INSERT INTO reports(item_id,reporter_id,reason,created_at) VALUES(?,?,?,?)", (item_id,user["id"],reason[:500],now()))
                    except sqlite3.IntegrityError: raise APIError(409,"Você já denunciou este anúncio.")
                    count = db.execute("SELECT COUNT(DISTINCT reporter_id) FROM reports WHERE item_id=? AND status='Pendente'",(item_id,)).fetchone()[0]
                    if count >= 3: db.execute("UPDATE items SET status='Oculto',updated_at=? WHERE id=?",(now(),item_id))
                    db.commit()
                self.send_json({"message":"Denúncia registrada. Obrigado por ajudar a manter a comunidade segura."},201); return
            if path.startswith("/api/reports/") and path.endswith("/decision"):
                match = re.fullmatch(r"/api/reports/(\d+)/decision",path)
                if not match: raise APIError(404,"Rota não encontrada.")
                user=self.current_user(); self.require_moderator(user); report_id=int(match.group(1)); decision=data.get("decision"); note=str(data.get("note","")).strip()
                if decision not in ("Manter anúncio","Ocultar anúncio"): raise APIError(400,"Selecione uma ação válida.")
                if not note: raise APIError(400,"Informe a justificativa da ação de moderação.")
                with connect() as db:
                    report=db.execute("SELECT * FROM reports WHERE id=?",(report_id,)).fetchone()
                    if not report: raise APIError(404,"Denúncia não encontrada.")
                    db.execute("UPDATE reports SET status='Analisada' WHERE id=?",(report_id,))
                    status='Oculto' if decision=="Ocultar anúncio" else 'Aberto'
                    db.execute("UPDATE items SET status=?,updated_at=? WHERE id=?",(status,now(),report["item_id"]))
                    db.execute("INSERT INTO moderation_actions(moderator_id,item_id,report_id,action,justification,created_at) VALUES(?,?,?,?,?,?)",(user["id"],report["item_id"],report_id,decision,note,now())); db.commit()
                self.send_json({"message":"Análise de moderação registrada."}); return
            if path.startswith("/api/claims/") and path.endswith("/messages"):
                claim_id=int(path.split("/")[3]); user=self.current_user(); body=str(data.get("body","")).strip()
                if not body or len(body)>500: raise APIError(400,"A mensagem deve ter entre 1 e 500 caracteres.")
                with connect() as db:
                    claim=db.execute("SELECT c.*,i.owner_id FROM claims c JOIN items i ON i.id=c.item_id WHERE c.id=?",(claim_id,)).fetchone()
                    if not claim: raise APIError(404,"Reivindicação não encontrada.")
                    if user["id"] not in (claim["owner_id"],claim["claimant_id"]): raise APIError(403,"Você não participa desta conversa.")
                    if claim["status"]!="Aprovada": raise APIError(400,"A conversa é liberada após a aprovação.")
                    db.execute("INSERT INTO messages(claim_id,sender_id,body,created_at) VALUES(?,?,?,?)",(claim_id,user["id"],body,now())); db.commit()
                self.send_json({"message":"Mensagem enviada."},201); return
            raise APIError(404, "Rota não encontrada.")
        except APIError as e: self.send_json({"error": e.message}, e.status)
        except Exception as e:
            print("ERRO POST:", repr(e)); self.send_json({"error": "Erro interno. Confira o terminal para detalhes."}, 500)


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("\n==============================================")
    print("  ENCONTREI - ACHADOS E PERDIDOS")
    print(f"  Aplicação: http://{HOST}:{PORT}")
    print(f"  Banco local: {DB_PATH}")
    print("  Para encerrar, volte aqui e pressione Ctrl+C")
    print("==============================================\n")
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nServidor encerrado.")
    finally: server.server_close()

if __name__ == "__main__": main()
