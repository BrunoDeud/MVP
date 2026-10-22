#!/usr/bin/env python3
"""Encontrei — MVP local com Python e SQLite (biblioteca padrão)."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, date, timedelta
from contextlib import contextmanager
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import smtplib
import ssl
import sqlite3
import struct
import threading
import time
import webbrowser
import zlib
from email.message import EmailMessage

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = ROOT / "uploads"
DB_PATH = DATA_DIR / "encontrei.sqlite3"
WEB_PATH = ROOT / "index.html"
HOST, PORT = "127.0.0.1", 8000
MAX_BODY = 24 * 1024 * 1024
MAX_PHOTO = 5 * 1024 * 1024
DB_LOCK = threading.RLock()
TOKENS = {}  # token -> (user_id, expires_epoch)
LOGIN_ATTEMPTS = {}  # client/email -> [epoch timestamps]
LAST_MAINTENANCE = 0

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)


def now():
    return datetime.now().replace(microsecond=0).isoformat()


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def text_value(value, field, minimum=1, maximum=255):
    if not isinstance(value, (str, int, float)):
        raise APIError(400, f"Informe {field} em formato válido.")
    value = str(value).strip()
    if len(value) < minimum or len(value) > maximum:
        raise APIError(400, f"{field.capitalize()} deve ter entre {minimum} e {maximum} caracteres.")
    return value


def valid_date(value, field="data"):
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise APIError(400, f"Informe uma {field} válida no formato AAAA-MM-DD.")
    if parsed > date.today() + timedelta(days=1):
        raise APIError(400, f"A {field} não pode estar muito no futuro.")
    return parsed.isoformat()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return salt, digest


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def table_columns(db, table):
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}


def ensure_column(db, table, name, declaration):
    if name not in table_columns(db, table):
        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def create_demo_png(path, kind="bottle"):
    """Gera uma pequena ilustração PNG sem dependências para os dados de exemplo."""
    width, height = 420, 220
    rows = []
    bg = (235, 241, 231)
    pixels = [[bg for _ in range(width)] for _ in range(height)]

    def rect(x1, y1, x2, y2, color):
        for yy in range(max(0, y1), min(height, y2)):
            for xx in range(max(0, x1), min(width, x2)):
                pixels[yy][xx] = color

    # Sombra e pedestal simples.
    rect(125, 182, 295, 190, (211, 221, 207))
    if kind == "bottle":
        rect(185, 45, 235, 62, (48, 70, 55)); rect(177, 60, 243, 166, (64, 111, 77))
        rect(184, 78, 195, 150, (115, 155, 119)); rect(177, 106, 243, 117, (222, 230, 211))
    elif kind == "keys":
        rect(170, 82, 182, 150, (79, 92, 86)); rect(160, 72, 192, 105, (79, 92, 86))
        rect(238, 67, 250, 147, (184, 166, 114)); rect(226, 60, 258, 92, (184, 166, 114))
        rect(170, 144, 205, 154, (79, 92, 86)); rect(238, 141, 265, 151, (184, 166, 114))
    elif kind == "card":
        rect(145, 65, 275, 153, (64, 92, 121)); rect(154, 74, 266, 144, (239, 237, 222))
        rect(154, 91, 266, 106, (64, 92, 121)); rect(166, 119, 215, 126, (177, 185, 168))
    elif kind == "notebook":
        rect(160, 40, 260, 172, (47, 55, 51)); rect(170, 49, 251, 164, (248, 247, 240))
        for yy in range(70, 150, 16): rect(182, yy, 240, yy+2, (185, 197, 182))
    else:
        rect(160, 65, 260, 155, (130, 145, 128))
    for row in pixels:
        raw = bytearray([0])
        for r, g, b in row:
            raw.extend((r, g, b))
        rows.append(bytes(raw))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 8)) + chunk(b"IEND", b""))
    path.write_bytes(data)


def init_db():
    """Cria esquema, índices, catálogos e contas/dados fictícios idempotentemente."""
    with DB_LOCK, connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 2 AND 80),
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            role TEXT NOT NULL DEFAULT 'Estudante' CHECK(role IN ('Estudante','Moderador','Administrador')),
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS institutional_domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL UNIQUE COLLATE NOCASE,
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            requires_guard INTEGER NOT NULL DEFAULT 0 CHECK(requires_guard IN (0,1)),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            block_name TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS guard_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            location_id INTEGER NOT NULL REFERENCES locations(id),
            reference TEXT NOT NULL DEFAULT '',
            retention_days INTEGER NOT NULL DEFAULT 90 CHECK(retention_days BETWEEN 30 AND 365),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL,
            UNIQUE(name, location_id)
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('Achado','Perdido')),
            category TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            location_id INTEGER REFERENCES locations(id),
            event_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Aberto',
            owner_id INTEGER NOT NULL REFERENCES users(id),
            guard_point_id INTEGER REFERENCES guard_points(id),
            verification_question TEXT,
            verification_answer TEXT,
            photos_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            expiration_warned_at TEXT
        );
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            claimant_id INTEGER NOT NULL REFERENCES users(id),
            answer TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente',
            routed_to_moderation INTEGER NOT NULL DEFAULT 0 CHECK(routed_to_moderation IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            decision_by INTEGER REFERENCES users(id),
            decision_note TEXT,
            returned_at TEXT
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            reporter_id INTEGER NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente',
            created_at TEXT NOT NULL,
            decision_by INTEGER REFERENCES users(id),
            decision_note TEXT,
            decided_at TEXT,
            UNIQUE(item_id, reporter_id)
        );
        CREATE TABLE IF NOT EXISTS profile_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_user_id INTEGER NOT NULL REFERENCES users(id),
            reporter_id INTEGER NOT NULL REFERENCES users(id),
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendente',
            created_at TEXT NOT NULL,
            decision_by INTEGER REFERENCES users(id),
            decision_note TEXT,
            decided_at TEXT,
            UNIQUE(target_user_id, reporter_id),
            CHECK(target_user_id <> reporter_id)
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
            body TEXT NOT NULL CHECK(length(trim(body)) BETWEEN 1 AND 500),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            item_id INTEGER REFERENCES items(id),
            claim_id INTEGER REFERENCES claims(id),
            is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0,1)),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS item_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id),
            actor_id INTEGER REFERENCES users(id),
            action TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_items_status_type_date ON items(status,type,event_date);
        CREATE INDEX IF NOT EXISTS idx_items_owner_status ON items(owner_id,status);
        CREATE INDEX IF NOT EXISTS idx_claims_status_date ON claims(status,created_at);
        CREATE INDEX IF NOT EXISTS idx_reports_status_date ON reports(status,created_at);
        CREATE INDEX IF NOT EXISTS idx_notifications_user_read_date ON notifications(user_id,is_read,created_at);
        CREATE INDEX IF NOT EXISTS idx_messages_claim_date ON messages(claim_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_history_item_date ON item_history(item_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_profile_reports_target_status ON profile_reports(target_user_id,status);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_claim_per_user_item
          ON claims(item_id, claimant_id) WHERE status IN ('Pendente','Aprovada');
        """)

        # Migração incremental para bancos criados por versões anteriores do pacote.
        for table, name, decl in [
            ("users", "status", "TEXT NOT NULL DEFAULT 'Ativo'"),
            ("users", "email_verified", "INTEGER NOT NULL DEFAULT 1"),
            ("users", "verification_token", "TEXT"),
            ("users", "verification_expires_at", "TEXT"),
            ("users", "email_notifications", "INTEGER NOT NULL DEFAULT 0"),
            ("items", "category_id", "INTEGER REFERENCES categories(id)"),
            ("items", "location_id", "INTEGER REFERENCES locations(id)"),
            ("items", "guard_point_id", "INTEGER REFERENCES guard_points(id)"),
            ("items", "resolved_at", "TEXT"),
            ("items", "expiration_warned_at", "TEXT"),
            ("claims", "routed_to_moderation", "INTEGER NOT NULL DEFAULT 0"),
            ("claims", "returned_at", "TEXT"),
            ("reports", "decision_by", "INTEGER REFERENCES users(id)"),
            ("reports", "decision_note", "TEXT"),
            ("reports", "decided_at", "TEXT"),
        ]:
            ensure_column(db, table, name, decl)

        # Garante RN09 mesmo em bancos locais antigos criados antes desta regra.
        db.execute("""UPDATE claims SET status='Cancelada', updated_at=? WHERE status='Aprovada'
                    AND id NOT IN (SELECT MIN(id) FROM claims WHERE status='Aprovada' GROUP BY item_id)""", (now(),))
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_approved_claim_per_item ON claims(item_id) WHERE status='Aprovada'")

        for domain in ("campus.edu.br", "alunos.campus.edu.br"):
            db.execute("INSERT OR IGNORE INTO institutional_domains(domain,active,created_at) VALUES(?,1,?)", (domain, now()))
        category_seed = [
            ("Garrafas", 0), ("Chaves", 0), ("Eletrônicos", 1), ("Material escolar", 0),
            ("Cartões", 1), ("Documentos", 1), ("Roupas", 0), ("Acessórios", 0), ("Outros", 0),
        ]
        for name, guard in category_seed:
            db.execute("INSERT OR IGNORE INTO categories(name,requires_guard,active,created_at) VALUES(?,?,1,?)", (name, guard, now()))
        for name, block in [("Biblioteca central", "Biblioteca"), ("Bloco B — corredor do térreo", "Bloco B"),
                            ("Cantina", "Cantina"), ("Sala 204 — Bloco A", "Bloco A"), ("Portaria principal", "Portaria")]:
            db.execute("INSERT OR IGNORE INTO locations(name,block_name,active,created_at) VALUES(?,?,1,?)", (name, block, now()))

        users = [
            ("Ana Souza", "estudante@campus.edu.br", "Estudante", "Estudante@12345"),
            ("Carlos Moderador", "moderador@campus.edu.br", "Moderador", "Moderador@12345"),
            ("Patrícia Administradora", "admin@campus.edu.br", "Administrador", "Admin@12345"),
            ("Lucas Pereira", "lucas@campus.edu.br", "Estudante", "Lucas@12345"),
        ]
        for name, email, role, pwd in users:
            row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if not row:
                salt, digest = hash_password(pwd)
                db.execute("INSERT INTO users(name,email,role,salt,password_hash,created_at,status,email_verified) VALUES(?,?,?,?,?,?, 'Ativo',1)",
                           (name, email, role, salt, digest, now()))
            else:
                db.execute("UPDATE users SET status='Ativo',email_verified=1 WHERE email=?", (email,))

        portaria = db.execute("SELECT id FROM locations WHERE name='Portaria principal'").fetchone()[0]
        guard = db.execute("SELECT id FROM guard_points WHERE name='Guarda da portaria' AND location_id=?", (portaria,)).fetchone()
        if not guard:
            cur = db.execute("INSERT INTO guard_points(name,location_id,reference,retention_days,active,created_at) VALUES('Guarda da portaria',?,'Balcão de atendimento',90,1,?)", (portaria, now()))
            guard_id = cur.lastrowid
        else:
            guard_id = guard[0]

        # Completa os vínculos de registros antigos sem alterar os textos históricos.
        for row in db.execute("SELECT id,category,location FROM items WHERE category_id IS NULL OR location_id IS NULL").fetchall():
            cat = db.execute("SELECT id FROM categories WHERE name=? COLLATE NOCASE", (row["category"],)).fetchone()
            if not cat:
                cur = db.execute("INSERT INTO categories(name,requires_guard,active,created_at) VALUES(?,?,1,?)", (row["category"], int(norm(row["category"]) in ("documentos","cartões","eletrônicos")), now()))
                cat_id = cur.lastrowid
            else:
                cat_id = cat[0]
            loc = db.execute("SELECT id FROM locations WHERE name=? COLLATE NOCASE", (row["location"],)).fetchone()
            if not loc:
                block = extract_block(row["location"])
                cur = db.execute("INSERT INTO locations(name,block_name,active,created_at) VALUES(?,?,1,?)", (row["location"], block, now()))
                loc_id = cur.lastrowid
            else:
                loc_id = loc[0]
            db.execute("UPDATE items SET category_id=COALESCE(category_id,?),location_id=COALESCE(location_id,?) WHERE id=?", (cat_id, loc_id, row["id"]))

        if db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
            student = db.execute("SELECT id FROM users WHERE email='estudante@campus.edu.br'").fetchone()[0]
            lucas = db.execute("SELECT id FROM users WHERE email='lucas@campus.edu.br'").fetchone()[0]
            today = date.today()
            samples = [
                ("Garrafa térmica verde", "Achado", "Garrafas", "Garrafa térmica verde-escura, sem marca aparente.", "Biblioteca central", (today-timedelta(days=1)).isoformat(), student, "Qual adesivo está na parte de baixo?", "montanha", "Aberto", None, "bottle"),
                ("Chaveiro com duas chaves", "Achado", "Chaves", "Chaveiro de tecido azul com duas chaves prateadas.", "Bloco B — corredor do térreo", (today-timedelta(days=2)).isoformat(), lucas, "Qual é a cor do tecido do chaveiro?", "azul", "Aberto", None, "keys"),
                ("Fone de ouvido branco", "Perdido", "Eletrônicos", "Fone sem fio branco dentro de um estojo pequeno.", "Cantina", (today-timedelta(days=1)).isoformat(), lucas, None, None, "Aberto", None, "notebook"),
                ("Caderno de capa preta", "Achado", "Material escolar", "Caderno universitário de capa preta, com elástico.", "Sala 204 — Bloco A", (today-timedelta(days=3)).isoformat(), student, "Qual a cor do elástico?", "vermelho", "Aberto", None, "notebook"),
                ("Cartão de transporte", "Achado", "Cartões", "Cartão encontrado próximo à entrada principal. Dados sensíveis foram omitidos.", "Portaria principal", (today-timedelta(days=4)).isoformat(), student, "Qual desenho há no verso?", "sol", "No ponto de guarda", guard_id, "card"),
            ]
            for title, typ, cat, desc, loc, dt, owner, question, answer, status, gp, imagekind in samples:
                cat_id = db.execute("SELECT id FROM categories WHERE name=?", (cat,)).fetchone()[0]
                loc_id = db.execute("SELECT id FROM locations WHERE name=?", (loc,)).fetchone()[0]
                photo_name = f"demo-{imagekind}.png"
                photo_path = UPLOAD_DIR / photo_name
                if not photo_path.exists(): create_demo_png(photo_path, imagekind)
                photo_urls = ["/uploads/" + photo_name] if typ == "Achado" else []
                db.execute("""INSERT INTO items(title,type,category,category_id,description,location,location_id,event_date,status,owner_id,guard_point_id,
                           verification_question,verification_answer,photos_json,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (title, typ, cat, cat_id, desc, loc, loc_id, dt, status, owner, gp, question, norm(answer) if answer else None,
                            json.dumps(photo_urls), now(), now()))
        db.commit()


def extract_block(location):
    value = str(location or "").strip()
    match = re.search(r"\b(bloco\s+[A-Za-z0-9]+|pr[eé]dio\s+[A-Za-z0-9]+)\b", value, re.I)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).title()
    return value.split("—", 1)[0].split("-", 1)[0].strip()


def catalog_ids(db, category, location):
    """Resolve IDs somente de catálogos ativos gerenciados pela administração."""
    cat = db.execute("SELECT id,requires_guard FROM categories WHERE name=? COLLATE NOCASE AND active=1", (category,)).fetchone()
    if not cat:
        raise APIError(400, "Selecione uma categoria ativa cadastrada no sistema.")
    loc = db.execute("SELECT id,active FROM locations WHERE name=? COLLATE NOCASE", (location,)).fetchone()
    if not loc:
        raise APIError(400, "Selecione um local cadastrado no sistema.")
    if not loc[1]:
        raise APIError(400, "Este local está inativo. Escolha outro.")
    return cat["id"], loc["id"]


def user_public(row):
    result = {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"],
              "status": row["status"] if "status" in row.keys() else "Ativo"}
    if "email_notifications" in row.keys():
        result["email_notifications"] = bool(row["email_notifications"])
    if "email_verified" in row.keys():
        result["email_verified"] = bool(row["email_verified"])
    return result


def item_public(row, include_owner=True):
    photos = json.loads(row["photos_json"] or "[]")
    result = {"id": row["id"], "title": row["title"], "type": row["type"], "category": row["category"],
              "description": row["description"], "location": row["location"], "event_date": row["event_date"],
              "status": row["status"], "photos": photos, "created_at": row["created_at"], "updated_at": row["updated_at"]}
    if include_owner:
        result["owner_name"] = row["owner_name"] if "owner_name" in row.keys() else "Usuário"
        result["owner_id"] = row["owner_id"]
    return result


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def smtp_settings():
    """Lê configuração SMTP opcional. Sem host/remetente, o modo local só guarda notificações in-app."""
    host = os.environ.get("ENCONTREI_SMTP_HOST", "").strip()
    sender = os.environ.get("ENCONTREI_SMTP_FROM", "").strip() or os.environ.get("ENCONTREI_SMTP_USER", "").strip()
    if not host or not sender:
        return None
    try:
        port = int(os.environ.get("ENCONTREI_SMTP_PORT", "587"))
    except ValueError:
        print("[SMTP] Porta inválida; e-mail desativado.")
        return None
    return {
        "host": host,
        "port": port,
        "sender": sender,
        "username": os.environ.get("ENCONTREI_SMTP_USER", "").strip(),
        "password": os.environ.get("ENCONTREI_SMTP_PASSWORD", ""),
        "tls": os.environ.get("ENCONTREI_SMTP_TLS", "true").strip().lower() in ("1", "true", "yes", "sim"),
        "ssl": os.environ.get("ENCONTREI_SMTP_SSL", "false").strip().lower() in ("1", "true", "yes", "sim"),
    }


def send_email(recipient, subject, body):
    """Tenta enviar uma mensagem SMTP se configurado; falha de e-mail nunca derruba a operação local."""
    cfg = smtp_settings()
    if not cfg or not recipient:
        return False
    message = EmailMessage()
    message["From"] = cfg["sender"]
    message["To"] = recipient
    message["Subject"] = subject[:180]
    message.set_content(body[:6000])
    try:
        if cfg["ssl"]:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=8, context=ssl.create_default_context()) as client:
                if cfg["username"]:
                    client.login(cfg["username"], cfg["password"])
                client.send_message(message)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=8) as client:
                client.ehlo()
                if cfg["tls"]:
                    client.starttls(context=ssl.create_default_context())
                    client.ehlo()
                if cfg["username"]:
                    client.login(cfg["username"], cfg["password"])
                client.send_message(message)
        return True
    except Exception as exc:
        # Não imprime destinatário, usuário SMTP nem senha no terminal.
        print(f"[SMTP] Envio não concluído ({type(exc).__name__}); a notificação in-app foi preservada.")
        return False


def add_notification(db, user_id, kind, title, body, item_id=None, claim_id=None):
    if user_id is None:
        return
    db.execute("INSERT INTO notifications(user_id,type,title,body,item_id,claim_id,created_at) VALUES(?,?,?,?,?,?,?)",
               (user_id, kind, title[:120], body[:500], item_id, claim_id, now()))
    user = db.execute("SELECT email,email_verified,email_notifications,status FROM users WHERE id=?", (user_id,)).fetchone()
    if user and user["status"] == "Ativo" and user["email_verified"] and user["email_notifications"]:
        send_email(user["email"], f"Encontrei: {title[:120]}", body[:500])


def notify_moderators(db, kind, title, body, item_id=None, claim_id=None):
    ids = db.execute("SELECT id FROM users WHERE role IN ('Moderador','Administrador') AND status='Ativo'").fetchall()
    for row in ids:
        add_notification(db, row[0], kind, title, body, item_id, claim_id)


def write_history(db, item_id, actor_id, action, note=""):
    db.execute("INSERT INTO item_history(item_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)",
               (item_id, actor_id, action, note[:1000], now()))


def location_matches(left, right):
    a, b = norm(left), norm(right)
    ba, bb = norm(extract_block(left)), norm(extract_block(right))
    # Se as duas localizações citam explicitamente bloco/prédio, comparar o identificador.
    ea = bool(re.search(r"\b(bloco|pr[eé]dio)\s+[a-z0-9]+", a))
    eb = bool(re.search(r"\b(bloco|pr[eé]dio)\s+[a-z0-9]+", b))
    return ba == bb if ea and eb else a == b


def find_matches(db, item, limit=5):
    opposite = "Perdido" if item["type"] == "Achado" else "Achado"
    rows = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.type=? AND i.status IN ('Aberto','No ponto de guarda') AND i.id<>? ORDER BY i.created_at DESC", (opposite, item["id"])).fetchall()
    result = []
    item_date = date.fromisoformat(item["event_date"])
    for row in rows:
        if norm(row["category"]) != norm(item["category"]):
            continue
        if not location_matches(row["location"], item["location"]):
            continue
        try:
            candidate_date = date.fromisoformat(row["event_date"])
            # Um objeto encontrado precisa ter sido encontrado na data da perda ou depois.
            # Uma perda compatível deve ocorrer antes ou na data em que o objeto foi achado.
            if item["type"] == "Perdido":
                delta = (candidate_date - item_date).days
            else:
                delta = (item_date - candidate_date).days
        except (TypeError, ValueError):
            continue
        if 0 <= delta <= 15:
            result.append(item_public(row))
            if len(result) >= limit:
                break
    return result


def maintenance_worker(stop_event, interval=60):
    """Executa manutenção periodicamente enquanto o servidor local está ativo."""
    while not stop_event.wait(interval):
        try:
            maintenance(force=True)
        except Exception as exc:  # mantém o servidor vivo se uma rodada falhar
            print("AVISO: manutenção automática falhou:", repr(exc))


def maintenance(force=False):
    """Executa regras de expiração e encaminhamento sem precisar de serviço externo."""
    global LAST_MAINTENANCE
    if not force and time.time() - LAST_MAINTENANCE < 60:
        return
    with DB_LOCK, connect() as db:
        stamp = now()
        open_cutoff = (datetime.now() - timedelta(days=60)).isoformat(timespec="seconds")
        old_items = db.execute("SELECT id,owner_id,title FROM items WHERE status='Aberto' AND updated_at<=?", (open_cutoff,)).fetchall()
        for item in old_items:
            db.execute("UPDATE items SET status='Expirado',updated_at=? WHERE id=?", (stamp, item["id"]))
            write_history(db, item["id"], None, "Expiração automática", "Anúncio sem atividade há 60 dias.")
            add_notification(db, item["owner_id"], "expiracao", "Anúncio expirado", f"O anúncio '{item['title']}' expirou após 60 dias sem atividade.", item["id"])

        pending = db.execute("SELECT c.id,c.item_id,c.claimant_id,i.owner_id,i.title FROM claims c JOIN items i ON i.id=c.item_id WHERE c.status='Pendente' AND c.routed_to_moderation=0 AND c.created_at<=?", ((datetime.now()-timedelta(days=7)).isoformat(timespec="seconds"),)).fetchall()
        for claim in pending:
            db.execute("UPDATE claims SET routed_to_moderation=1,updated_at=? WHERE id=?", (stamp, claim["id"]))
            notify_moderators(db, "reivindicacao", "Reivindicação aguardando análise", f"A solicitação do item '{claim['title']}' está pendente há mais de 7 dias.", claim["item_id"], claim["id"])

        guard_items = db.execute("SELECT i.id,i.owner_id,i.title,i.created_at,i.expiration_warned_at,i.guard_point_id,g.retention_days FROM items i JOIN guard_points g ON g.id=i.guard_point_id WHERE i.status='No ponto de guarda' AND g.active=1").fetchall()
        for item in guard_items:
            created = datetime.fromisoformat(item["created_at"])
            age = (datetime.now() - created).days
            retention = item["retention_days"]
            if age >= retention:
                db.execute("UPDATE items SET status='Expirado',updated_at=? WHERE id=?", (stamp, item["id"]))
                write_history(db, item["id"], None, "Expiração de item guardado", f"Prazo de guarda configurado: {retention} dias.")
                add_notification(db, item["owner_id"], "expiracao", "Prazo de guarda encerrado", f"O prazo de guarda de '{item['title']}' foi encerrado; procure a instituição para obter orientação.", item["id"])
                notify_moderators(db, "expiracao", "Item com prazo de guarda encerrado", item["title"], item["id"])
            elif age >= retention - 7 and not item["expiration_warned_at"]:
                db.execute("UPDATE items SET expiration_warned_at=?,updated_at=? WHERE id=?", (stamp, stamp, item["id"]))
                add_notification(db, item["owner_id"], "expiracao", "Aviso de prazo de guarda", f"O prazo de guarda de '{item['title']}' termina em até 7 dias.", item["id"])
                notify_moderators(db, "expiracao", "Item próximo do fim do prazo de guarda", item["title"], item["id"])
        LAST_MAINTENANCE = time.time()


class Handler(BaseHTTPRequestHandler):
    server_version = "EncontreiLocal/2.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def send_html(self, page, status=200):
        raw = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise APIError(400, "Cabeçalho Content-Length inválido.")
        if length < 0: raise APIError(400, "Tamanho de corpo inválido.")
        if length > MAX_BODY: raise APIError(413, "Dados enviados excedem o limite permitido.")
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, "O conteúdo enviado não é um JSON válido.")
        if not isinstance(value, dict): raise APIError(400, "O corpo JSON deve ser um objeto.")
        return value

    def current_user(self, required=True):
        auth = self.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        token_data = TOKENS.get(token)
        if not token_data:
            if required: raise APIError(401, "Entre no sistema para realizar esta ação.")
            return None
        uid, expires = token_data
        if expires < time.time():
            TOKENS.pop(token, None)
            if required: raise APIError(401, "Sua sessão expirou. Entre novamente.")
            return None
        with connect() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not row or row["status"] != "Ativo" or not row["email_verified"]:
            TOKENS.pop(token, None)
            if required: raise APIError(403, "Conta inativa ou suspensa. Procure a moderação.")
            return None
        return row

    def require_moderator(self, user):
        if not user or user["role"] not in ("Moderador", "Administrador"):
            raise APIError(403, "Esta ação é exclusiva da moderação.")

    def require_admin(self, user):
        if not user or user["role"] != "Administrador":
            raise APIError(403, "Esta ação é exclusiva da administração.")

    def item_row(self, db, item_id):
        row = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.id=?", (item_id,)).fetchone()
        if not row: raise APIError(404, "Anúncio não encontrado.")
        return row

    def api_start(self):
        maintenance()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)
            if path == "/api/verify-email":
                token = qs.get("token", [""])[0]
                with connect() as db:
                    user = db.execute("SELECT id,verification_expires_at FROM users WHERE verification_token=? AND status='Pendente'", (token,)).fetchone()
                    if not user:
                        self.send_html("<!doctype html><html lang='pt-br'><meta charset='utf-8'><title>Encontrei</title><h1>Link inválido</h1><p>O link de verificação é inválido ou já foi utilizado.</p><a href='/'>Voltar ao Encontrei</a></html>", 400); return
                    if not user["verification_expires_at"] or datetime.fromisoformat(user["verification_expires_at"]) < datetime.now():
                        self.send_html("<!doctype html><html lang='pt-br'><meta charset='utf-8'><title>Encontrei</title><h1>Link expirado</h1><p>Solicite um novo link de verificação na tela de cadastro.</p><a href='/'>Voltar ao Encontrei</a></html>", 410); return
                    db.execute("UPDATE users SET status='Ativo',email_verified=1,verification_token=NULL,verification_expires_at=NULL WHERE id=?", (user["id"],))
                    add_notification(db, user["id"], "conta", "E-mail verificado", "Sua conta foi ativada e já pode ser utilizada.")
                self.send_html("<!doctype html><html lang='pt-br'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Conta ativada</title><body style='font:16px system-ui;max-width:640px;margin:60px auto;padding:20px;color:#24382f'><h1>Conta verificada com sucesso!</h1><p>Sua conta do Encontrei foi ativada. Volte ao sistema e entre com seu e-mail e senha.</p><a href='/'>Ir para o Encontrei</a></body></html>"); return
            if path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("X-Content-Type-Options", "nosniff")
                body = WEB_PATH.read_bytes()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if path.startswith("/uploads/"):
                name = Path(path.removeprefix("/uploads/")).name
                if name != path.removeprefix("/uploads/") or name.startswith("."):
                    raise APIError(404, "Arquivo não encontrado.")
                file_path = UPLOAD_DIR / name
                if not file_path.is_file(): raise APIError(404, "Arquivo não encontrado.")
                body = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "no-store")
                self.end_headers(); self.wfile.write(body); return

            self.api_start()
            if path == "/api/health":
                with connect() as db:
                    db.execute("SELECT 1").fetchone()
                    size = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                self.send_json({"ok": True, "app": "Encontrei", "database": "SQLite", "items": size}); return
            if path == "/api/config":
                with connect() as db:
                    categories = db.execute("SELECT name,requires_guard FROM categories WHERE active=1 ORDER BY name").fetchall()
                    locations = db.execute("SELECT name,block_name FROM locations WHERE active=1 ORDER BY name").fetchall()
                self.send_json({"categories": [dict(r) for r in categories], "locations": [dict(r) for r in locations]}); return
            if path == "/api/me":
                self.send_json({"user": user_public(self.current_user())}); return
            if path == "/api/items":
                query = qs.get("q", [""])[0].strip()
                typ = qs.get("type", [""])[0]
                cat = qs.get("category", [""])[0]
                location = qs.get("location", [""])[0]
                status_filter = qs.get("status", ["Aberto"])[0]
                date_from = qs.get("date_from", [""])[0]
                date_to = qs.get("date_to", [""])[0]
                try:
                    page = max(1, int(qs.get("page", ["1"])[0]))
                    per_page = min(100, max(1, int(qs.get("per_page", ["50"])[0])))
                except ValueError: raise APIError(400, "Parâmetros de paginação inválidos.")
                sql = "SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE 1=1"
                vals = []
                if status_filter == "Todos": sql += " AND i.status IN ('Aberto','No ponto de guarda')"
                elif status_filter == "Aberto": sql += " AND i.status IN ('Aberto','No ponto de guarda')"
                elif status_filter in ("Resolvido", "Expirado", "Oculto", "No ponto de guarda"):
                    if status_filter == "Oculto":
                        user = self.current_user(); self.require_moderator(user)
                    sql += " AND i.status=?"; vals.append(status_filter)
                else: raise APIError(400, "Filtro de status inválido.")
                if typ:
                    if typ not in ("Achado", "Perdido"): raise APIError(400, "Filtro de tipo inválido.")
                    sql += " AND i.type=?"; vals.append(typ)
                if cat: sql += " AND i.category=? COLLATE NOCASE"; vals.append(cat)
                if location: sql += " AND i.location LIKE ? COLLATE NOCASE"; vals.append("%"+location+"%")
                if query:
                    sql += " AND (i.title LIKE ? COLLATE NOCASE OR i.description LIKE ? COLLATE NOCASE OR i.category LIKE ? COLLATE NOCASE OR i.location LIKE ? COLLATE NOCASE)"
                    vals += ["%"+query+"%"]*4
                if date_from:
                    sql += " AND i.event_date>=?"; vals.append(valid_date(date_from, "data inicial"))
                if date_to:
                    sql += " AND i.event_date<=?"; vals.append(valid_date(date_to, "data final"))
                if date_from and date_to and date_from > date_to: raise APIError(400, "A data inicial precisa ser anterior à data final.")
                with connect() as db:
                    total = db.execute("SELECT COUNT(*) FROM ("+sql+")", vals).fetchone()[0]
                    rows = db.execute(sql+" ORDER BY i.created_at DESC,i.id DESC LIMIT ? OFFSET ?", vals+[per_page,(page-1)*per_page]).fetchall()
                self.send_json({"items": [item_public(r) for r in rows], "pagination": {"page": page, "per_page": per_page, "total": total, "pages": (total+per_page-1)//per_page}}); return
            if path == "/api/items/categories":
                with connect() as db: rows = db.execute("SELECT id,name,requires_guard FROM categories WHERE active=1 ORDER BY name").fetchall()
                self.send_json({"categories": [dict(r) for r in rows]}); return
            if path == "/api/items/locations":
                with connect() as db: rows = db.execute("SELECT id,name,block_name FROM locations WHERE active=1 ORDER BY name").fetchall()
                self.send_json({"locations": [dict(r) for r in rows]}); return
            if path == "/api/guard-points":
                user = self.current_user()
                with connect() as db:
                    rows = db.execute("SELECT g.id,g.name,g.location_id,g.reference,g.retention_days,l.name AS location_name FROM guard_points g JOIN locations l ON l.id=g.location_id WHERE g.active=1 AND l.active=1 ORDER BY g.name").fetchall()
                self.send_json({"guard_points": [dict(r) for r in rows]}); return
            match = re.fullmatch(r"/api/items/(\d+)(?:/(verification-question|claims|matches|history))?", path)
            if match:
                item_id = int(match.group(1)); action = match.group(2)
                with connect() as db:
                    row = self.item_row(db, item_id)
                    user = self.current_user(required=False)
                    if row["status"] == "Oculto" and (not user or (user["id"] != row["owner_id"] and user["role"] not in ("Moderador", "Administrador"))):
                        raise APIError(404, "Anúncio não encontrado.")
                    if action == "verification-question":
                        user = self.current_user()
                        if user["id"] == row["owner_id"]: raise APIError(403, "Você não pode reivindicar seu próprio anúncio.")
                        if row["type"] != "Achado" or row["status"] not in ("Aberto", "No ponto de guarda"): raise APIError(400, "Este item não aceita reivindicações.")
                        if not row["verification_question"]: raise APIError(400, "Este item não tem pergunta de verificação configurada.")
                        self.send_json({"question": row["verification_question"]}); return
                    if action == "claims":
                        user = self.current_user()
                        if user["id"] != row["owner_id"] and user["role"] not in ("Moderador", "Administrador"):
                            raise APIError(403, "Somente o publicador ou a moderação pode consultar as reivindicações.")
                        claims = db.execute("SELECT c.id,c.status,c.created_at,c.routed_to_moderation,u.name AS claimant_name FROM claims c JOIN users u ON u.id=c.claimant_id WHERE c.item_id=? ORDER BY c.created_at DESC", (item_id,)).fetchall()
                        self.send_json({"claims": [dict(r) for r in claims]}); return
                    if action == "matches":
                        user = self.current_user()
                        if user["id"] != row["owner_id"] and user["role"] not in ("Moderador", "Administrador"):
                            raise APIError(403, "Somente o publicador pode consultar correspondências do anúncio.")
                        self.send_json({"matches": find_matches(db, row)}); return
                    if action == "history":
                        user = self.current_user()
                        if user["id"] != row["owner_id"] and user["role"] not in ("Moderador", "Administrador"):
                            raise APIError(403, "Histórico disponível apenas ao publicador ou à moderação.")
                        history = db.execute("SELECT h.*,u.name AS actor_name FROM item_history h LEFT JOIN users u ON u.id=h.actor_id WHERE h.item_id=? ORDER BY h.created_at DESC", (item_id,)).fetchall()
                        self.send_json({"history": [dict(r) for r in history]}); return
                    self.send_json({"item": item_public(row)}); return
            if path == "/api/my/items":
                user = self.current_user()
                with connect() as db:
                    rows = db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.owner_id=? ORDER BY i.created_at DESC", (user["id"],)).fetchall()
                self.send_json({"items": [item_public(r) for r in rows]}); return
            if path == "/api/my/claims":
                user = self.current_user()
                with connect() as db:
                    rows = db.execute("SELECT c.*,i.title AS item_title,i.location,i.status AS item_status FROM claims c JOIN items i ON i.id=c.item_id WHERE c.claimant_id=? ORDER BY c.created_at DESC", (user["id"],)).fetchall()
                self.send_json({"claims": [dict(r) for r in rows]}); return
            if path == "/api/my/history":
                user = self.current_user()
                with connect() as db:
                    rows = db.execute("SELECT h.*,i.title FROM item_history h JOIN items i ON i.id=h.item_id WHERE i.owner_id=? ORDER BY h.created_at DESC LIMIT 100", (user["id"],)).fetchall()
                self.send_json({"history": [dict(r) for r in rows]}); return
            if path in ("/api/notifications", "/api/notifications/unread-count"):
                user = self.current_user()
                with connect() as db:
                    unread = db.execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user["id"],)).fetchone()[0]
                    if path.endswith("unread-count"):
                        self.send_json({"unread": unread}); return
                    rows = db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100", (user["id"],)).fetchall()
                self.send_json({"notifications": [dict(r) for r in rows], "unread": unread}); return
            if path.startswith("/api/claims/") and path.endswith("/messages"):
                match = re.fullmatch(r"/api/claims/(\d+)/messages", path)
                if not match: raise APIError(404, "Rota não encontrada.")
                claim_id = int(match.group(1)); user = self.current_user()
                with connect() as db:
                    claim = db.execute("SELECT c.*,i.owner_id FROM claims c JOIN items i ON i.id=c.item_id WHERE c.id=?", (claim_id,)).fetchone()
                    if not claim: raise APIError(404, "Reivindicação não encontrada.")
                    if user["id"] not in (claim["owner_id"], claim["claimant_id"]): raise APIError(403, "Você não participa desta conversa.")
                    if claim["status"] != "Aprovada": raise APIError(400, "A conversa é liberada após a aprovação da reivindicação.")
                    rows = db.execute("SELECT m.id,m.body,m.created_at,u.name AS sender_name,m.sender_id FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.claim_id=? ORDER BY m.id", (claim_id,)).fetchall()
                self.send_json({"messages": [dict(r) for r in rows], "current_user_id": user["id"]}); return
            if path == "/api/moderation/reports":
                user = self.current_user(); self.require_moderator(user)
                with connect() as db:
                    rows = db.execute("SELECT r.*,i.title AS item_title,u.name AS reporter_name FROM reports r JOIN items i ON i.id=r.item_id JOIN users u ON u.id=r.reporter_id WHERE r.status='Pendente' ORDER BY r.created_at").fetchall()
                self.send_json({"reports": [dict(r) for r in rows]}); return
            if path == "/api/moderation/profile-reports":
                user = self.current_user(); self.require_moderator(user)
                with connect() as db:
                    rows = db.execute("SELECT r.*,target.name AS target_name,reporter.name AS reporter_name FROM profile_reports r JOIN users target ON target.id=r.target_user_id JOIN users reporter ON reporter.id=r.reporter_id WHERE r.status='Pendente' ORDER BY r.created_at").fetchall()
                self.send_json({"reports": [dict(r) for r in rows]}); return
            if path == "/api/moderation/claims":
                user = self.current_user(); self.require_moderator(user)
                with connect() as db:
                    rows = db.execute("SELECT c.id,c.status,c.created_at,c.routed_to_moderation,i.title AS item_title,i.status AS item_status,i.guard_point_id,u.name AS claimant_name FROM claims c JOIN items i ON i.id=c.item_id JOIN users u ON u.id=c.claimant_id WHERE c.status='Pendente' AND (c.routed_to_moderation=1 OR i.guard_point_id IS NOT NULL) ORDER BY c.created_at").fetchall()
                self.send_json({"claims": [dict(r) for r in rows]}); return
            if path == "/api/moderation/log":
                user = self.current_user(); self.require_moderator(user)
                with connect() as db:
                    rows = db.execute("SELECT a.*,u.name AS moderator_name,i.title AS item_title FROM moderation_actions a JOIN users u ON u.id=a.moderator_id LEFT JOIN items i ON i.id=a.item_id ORDER BY a.created_at DESC LIMIT 200").fetchall()
                self.send_json({"actions": [dict(r) for r in rows]}); return
            if path == "/api/admin/categories":
                user = self.current_user(); self.require_admin(user)
                with connect() as db: rows = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
                self.send_json({"categories": [dict(r) for r in rows]}); return
            if path == "/api/admin/locations":
                user = self.current_user(); self.require_admin(user)
                with connect() as db: rows = db.execute("SELECT * FROM locations ORDER BY name").fetchall()
                self.send_json({"locations": [dict(r) for r in rows]}); return
            if path == "/api/admin/guard-points":
                user = self.current_user(); self.require_admin(user)
                with connect() as db:
                    rows = db.execute("SELECT g.*,l.name AS location_name FROM guard_points g JOIN locations l ON l.id=g.location_id ORDER BY g.name").fetchall()
                self.send_json({"guard_points": [dict(r) for r in rows]}); return
            if path == "/api/admin/domains":
                user = self.current_user(); self.require_admin(user)
                with connect() as db: rows = db.execute("SELECT * FROM institutional_domains ORDER BY domain").fetchall()
                self.send_json({"domains": [dict(r) for r in rows]}); return
            if path == "/api/admin/users":
                user = self.current_user(); self.require_admin(user)
                with connect() as db: rows = db.execute("SELECT id,name,email,role,status,email_verified,created_at FROM users ORDER BY created_at DESC").fetchall()
                self.send_json({"users": [dict(r) for r in rows]}); return
            raise APIError(404, "Rota não encontrada.")
        except APIError as e:
            self.send_json({"error": e.message}, e.status)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:
            print("ERRO GET:", repr(e)); self.send_json({"error": "Erro interno. Confira o terminal para detalhes."}, 500)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            data = self.body_json()
            self.api_start()
            if path == "/api/register":
                name = text_value(data.get("name"), "nome", 2, 80)
                email = text_value(data.get("email"), "e-mail", 6, 190).lower()
                password = str(data.get("password", ""))
                confirmation = str(data.get("password_confirmation", ""))
                if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email): raise APIError(400, "Informe um e-mail válido.")
                if len(password) < 8 or len(password) > 128: raise APIError(400, "A senha deve ter entre 8 e 128 caracteres.")
                if password != confirmation: raise APIError(400, "A confirmação de senha não confere.")
                domain = email.rsplit("@", 1)[1]
                with connect() as db:
                    allowed = db.execute("SELECT id FROM institutional_domains WHERE domain=? COLLATE NOCASE AND active=1", (domain,)).fetchone()
                    if not allowed: raise APIError(400, "Use seu e-mail institucional. Este domínio não está autorizado.")
                    if db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone(): raise APIError(409, "Já existe uma conta cadastrada com esse e-mail.")
                    salt, digest = hash_password(password)
                    verify = secrets.token_urlsafe(32)
                    expires = (datetime.now() + timedelta(hours=24)).replace(microsecond=0).isoformat()
                    db.execute("INSERT INTO users(name,email,role,salt,password_hash,created_at,status,email_verified,verification_token,verification_expires_at) VALUES(?,?,'Estudante',?, ?,?,'Pendente',0,?,?)",
                               (name, email, salt, digest, now(), verify, expires))
                    uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
                link = f"http://{HOST}:{PORT}/api/verify-email?token={quote(verify)}"
                delivered = send_email(email, "Verifique sua conta do Encontrei", f"Olá, {name}!\n\nPara ativar sua conta, abra o link abaixo em até 24 horas:\n{link}\n\nSe você não solicitou esse cadastro, ignore esta mensagem.")
                message = "Cadastro criado; enviamos o link de verificação para o e-mail informado." if delivered else "Cadastro criado. No modo local, use o link abaixo para verificar a conta; envio SMTP não está configurado ou falhou."
                self.send_json({"message": message, "verification_url": link, "verification_email_sent": delivered, "expires_at": expires, "user_id": uid}, 201); return
            if path == "/api/resend-verification":
                email = text_value(data.get("email"), "e-mail", 6, 190).lower()
                with connect() as db:
                    user = db.execute("SELECT id,status FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
                    if not user: raise APIError(404, "Conta não encontrada.")
                    if user["status"] == "Ativo": raise APIError(400, "Esta conta já está verificada.")
                    token = secrets.token_urlsafe(32); expires = (datetime.now()+timedelta(hours=24)).replace(microsecond=0).isoformat()
                    db.execute("UPDATE users SET verification_token=?,verification_expires_at=? WHERE id=?", (token, expires, user["id"]))
                link = f"http://{HOST}:{PORT}/api/verify-email?token={quote(token)}"
                delivered = send_email(email, "Novo link de verificação do Encontrei", f"Para ativar sua conta, abra este link em até 24 horas:\n{link}")
                message = "Novo link de verificação enviado." if delivered else "Novo link de verificação criado; abra-o manualmente no modo local."
                self.send_json({"message": message, "verification_url": link, "verification_email_sent": delivered, "expires_at": expires}); return
            if path == "/api/login":
                email = str(data.get("email", "")).strip().lower(); password = str(data.get("password", ""))
                client = self.client_address[0] + ":" + email
                attempts = [t for t in LOGIN_ATTEMPTS.get(client, []) if time.time()-t < 60]
                if len(attempts) >= 8: raise APIError(429, "Muitas tentativas de login. Aguarde um minuto e tente novamente.")
                attempts.append(time.time()); LOGIN_ATTEMPTS[client] = attempts
                with connect() as db: user = db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
                if not user: raise APIError(401, "E-mail ou senha incorretos.")
                _, digest = hash_password(password, user["salt"])
                if not hmac.compare_digest(digest, user["password_hash"]): raise APIError(401, "E-mail ou senha incorretos.")
                if not user["email_verified"] or user["status"] == "Pendente": raise APIError(403, "Verifique seu e-mail antes de entrar.")
                if user["status"] != "Ativo": raise APIError(403, "Sua conta está suspensa ou inativa. Procure a moderação.")
                token = secrets.token_urlsafe(32); TOKENS[token] = (user["id"], time.time()+12*60*60)
                self.send_json({"token": token, "user": user_public(user)}); return
            if path == "/api/logout":
                token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip(); TOKENS.pop(token, None)
                self.send_json({"ok": True}); return
            if path == "/api/items":
                user = self.current_user()
                item = self.create_item(data, user, guard_mode=False)
                with connect() as db:
                    matches = find_matches(db, db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.id=?", (item["id"],)).fetchone())
                    # Publicação de um achado notifica os donos de itens perdidos compatíveis; de um perdido, devolve sugestões.
                    for m in matches:
                        if item["type"] == "Achado":
                            add_notification(db, m["owner_id"], "correspondencia", "Possível correspondência", f"O item '{item['title']}' pode corresponder a um anúncio seu.", item["id"])
                        else:
                            add_notification(db, user["id"], "correspondencia", "Possíveis correspondências", f"Encontramos anúncios que podem corresponder a '{item['title']}'.", item["id"])
                self.send_json({"message": "Anúncio publicado com sucesso!", "item": item, "matches": matches}, 201); return
            if path == "/api/guard-points/items":
                user = self.current_user(); self.require_moderator(user)
                item = self.create_item(data, user, guard_mode=True)
                self.send_json({"message": "Item registrado no ponto de guarda.", "item": item}, 201); return
            match = re.fullmatch(r"/api/items/(\d+)/claims", path)
            if match:
                item_id = int(match.group(1)); user = self.current_user(); response = norm(data.get("answer", ""))
                if not response: raise APIError(400, "Responda à pergunta de verificação.")
                with connect() as db:
                    item = self.item_row(db, item_id)
                    if item["owner_id"] == user["id"]: raise APIError(403, "Você não pode reivindicar seu próprio anúncio.")
                    if item["type"] != "Achado" or item["status"] not in ("Aberto", "No ponto de guarda"): raise APIError(400, "Este item não aceita reivindicações.")
                    approved = db.execute("SELECT 1 FROM claims WHERE item_id=? AND status='Aprovada' LIMIT 1", (item_id,)).fetchone()
                    if approved: raise APIError(409, "Este item já possui uma reivindicação aprovada.")
                    if not item["verification_question"] or not item["verification_answer"]: raise APIError(400, "Este item não tem verificação configurada.")
                    if norm(item["verification_answer"]) != response: raise APIError(400, "Resposta não confere. Confira os detalhes e tente novamente.")
                    routed = int(item["guard_point_id"] is not None)
                    try:
                        cur = db.execute("INSERT INTO claims(item_id,claimant_id,answer,status,routed_to_moderation,created_at,updated_at) VALUES(?,?,?,'Pendente',?,?,?)",
                                         (item_id,user["id"],str(data.get("answer",""))[:250],routed,now(),now()))
                    except sqlite3.IntegrityError: raise APIError(409, "Você já possui uma reivindicação ativa para este item.")
                    claim_id = cur.lastrowid
                    add_notification(db, item["owner_id"], "reivindicacao", "Nova reivindicação", f"Há uma nova solicitação para '{item['title']}'.", item_id, claim_id)
                    if routed: notify_moderators(db, "reivindicacao", "Reivindicação de item guardado", f"Analise a solicitação de '{item['title']}'.", item_id, claim_id)
                self.send_json({"message": "Reivindicação enviada para análise.", "claim_id": claim_id}, 201); return
            match = re.fullmatch(r"/api/claims/(\d+)/decision", path)
            if match:
                claim_id = int(match.group(1)); user = self.current_user(); decision = data.get("decision"); note = str(data.get("note", "")).strip()
                if decision not in ("Aprovada", "Recusada"): raise APIError(400, "Decisão inválida.")
                if decision == "Recusada" and len(note) < 5: raise APIError(400, "Informe uma justificativa de pelo menos 5 caracteres para recusar.")
                with connect() as db:
                    claim = db.execute("SELECT c.*,i.owner_id,i.title,i.guard_point_id FROM claims c JOIN items i ON i.id=c.item_id WHERE c.id=?", (claim_id,)).fetchone()
                    if not claim: raise APIError(404, "Reivindicação não encontrada.")
                    self.require_moderator(user) if claim["guard_point_id"] is not None else None
                    if user["id"] != claim["owner_id"] and user["role"] not in ("Moderador", "Administrador"): raise APIError(403, "Somente o publicador ou a moderação pode decidir.")
                    if claim["status"] != "Pendente": raise APIError(409, "Esta reivindicação já foi respondida.")
                    if decision == "Aprovada":
                        other_approved = db.execute("SELECT 1 FROM claims WHERE item_id=? AND status='Aprovada' AND id<>? LIMIT 1", (claim["item_id"], claim_id)).fetchone()
                        if other_approved: raise APIError(409, "Já existe uma reivindicação aprovada para este item.")
                    try:
                        db.execute("UPDATE claims SET status=?,updated_at=?,decision_by=?,decision_note=? WHERE id=?", (decision,now(),user["id"],note[:500],claim_id))
                    except sqlite3.IntegrityError:
                        raise APIError(409, "Já existe uma reivindicação aprovada para este item.")
                    if decision == "Aprovada":
                        db.execute("UPDATE claims SET status='Cancelada',updated_at=? WHERE item_id=? AND id<>? AND status='Pendente'", (now(),claim["item_id"],claim_id))
                        add_notification(db, claim["claimant_id"], "reivindicacao", "Reivindicação aprovada", f"Sua solicitação para '{claim['title']}' foi aprovada. A conversa interna está liberada.", claim["item_id"], claim_id)
                    else:
                        add_notification(db, claim["claimant_id"], "reivindicacao", "Reivindicação recusada", f"Sua solicitação para '{claim['title']}' foi recusada. Motivo: {note[:250]}", claim["item_id"], claim_id)
                    if claim["guard_point_id"] is not None:
                        db.execute("INSERT INTO moderation_actions(moderator_id,item_id,action,justification,created_at) VALUES(?,?,?,?,?)", (user["id"],claim["item_id"],"Decisão de reivindicação: "+decision,note or "Análise de item guardado.",now()))
                self.send_json({"message": "Reivindicação " + ("aprovada" if decision=="Aprovada" else "recusada") + " com sucesso."}); return
            match = re.fullmatch(r"/api/items/(\d+)/resolve", path)
            if match:
                item_id = int(match.group(1)); user = self.current_user()
                with connect() as db:
                    item = self.item_row(db, item_id)
                    if user["id"] != item["owner_id"] and user["role"] not in ("Moderador","Administrador"): raise APIError(403,"Você não pode encerrar este anúncio.")
                    if item["status"] not in ("Aberto", "No ponto de guarda"): raise APIError(409, "Este anúncio já está encerrado.")
                    db.execute("UPDATE items SET status='Resolvido',updated_at=?,resolved_at=? WHERE id=?", (now(),now(),item_id))
                    write_history(db,item_id,user["id"],"Anúncio resolvido","Encerrado pelo publicador ou moderação.")
                    add_notification(db,item["owner_id"],"item","Anúncio resolvido",f"O anúncio '{item['title']}' foi encerrado.",item_id)
                self.send_json({"message":"Anúncio marcado como resolvido."}); return
            match = re.fullmatch(r"/api/claims/(\d+)/returned", path)
            if match:
                claim_id = int(match.group(1)); user = self.current_user()
                with connect() as db:
                    claim = db.execute("SELECT c.*,i.owner_id,i.title,i.guard_point_id,i.status AS item_status FROM claims c JOIN items i ON i.id=c.item_id WHERE c.id=?", (claim_id,)).fetchone()
                    if not claim: raise APIError(404, "Reivindicação não encontrada.")
                    if user["id"] != claim["owner_id"] and user["role"] not in ("Moderador","Administrador"): raise APIError(403,"Apenas o publicador ou a moderação pode confirmar a devolução.")
                    if claim["guard_point_id"] is not None: self.require_moderator(user)
                    if claim["status"] != "Aprovada": raise APIError(409,"Apenas uma reivindicação aprovada pode ser devolvida.")
                    db.execute("UPDATE claims SET returned_at=?,updated_at=? WHERE id=?",(now(),now(),claim_id))
                    db.execute("UPDATE items SET status='Resolvido',resolved_at=?,updated_at=? WHERE id=(SELECT item_id FROM claims WHERE id=?)",(now(),now(),claim_id))
                    write_history(db,claim["item_id"],user["id"],"Devolução confirmada",f"Reivindicação #{claim_id}; responsável: {user['name']}.")
                    add_notification(db,claim["claimant_id"],"devolucao","Devolução registrada",f"A devolução de '{claim['title']}' foi registrada.",claim["item_id"],claim_id)
                self.send_json({"message":"Devolução registrada no histórico."}); return
            match = re.fullmatch(r"/api/items/(\d+)/reports", path)
            if match:
                item_id = int(match.group(1)); user = self.current_user(); reason = text_value(data.get("reason"), "motivo da denúncia", 5, 500)
                with connect() as db:
                    item = self.item_row(db,item_id)
                    if item["owner_id"] == user["id"]: raise APIError(400, "Você não pode denunciar seu próprio anúncio.")
                    try: db.execute("INSERT INTO reports(item_id,reporter_id,reason,created_at) VALUES(?,?,?,?)", (item_id,user["id"],reason,now()))
                    except sqlite3.IntegrityError: raise APIError(409,"Você já denunciou este anúncio.")
                    count = db.execute("SELECT COUNT(DISTINCT reporter_id) FROM reports WHERE item_id=? AND status='Pendente'",(item_id,)).fetchone()[0]
                    if count >= 3:
                        db.execute("UPDATE items SET status='Oculto',updated_at=? WHERE id=?",(now(),item_id))
                        write_history(db,item_id,None,"Ocultação automática","Três denúncias de usuários distintos aguardam revisão.")
                        add_notification(db,item["owner_id"],"moderacao","Anúncio ocultado",f"O anúncio '{item['title']}' foi ocultado automaticamente para revisão.",item_id)
                        notify_moderators(db,"denuncia","Anúncio ocultado automaticamente",item["title"],item_id)
                self.send_json({"message":"Denúncia registrada. Obrigado por ajudar a manter a comunidade segura."},201); return
            match = re.fullmatch(r"/api/users/(\d+)/reports", path)
            if match:
                target_id = int(match.group(1)); user = self.current_user(); reason = text_value(data.get("reason"), "motivo da denúncia", 5, 500)
                if target_id == user["id"]: raise APIError(400, "Você não pode denunciar sua própria conta.")
                with connect() as db:
                    target = db.execute("SELECT id,status FROM users WHERE id=?", (target_id,)).fetchone()
                    if not target: raise APIError(404, "Usuário não encontrado.")
                    try: db.execute("INSERT INTO profile_reports(target_user_id,reporter_id,reason,created_at) VALUES(?,?,?,?)",(target_id,user["id"],reason,now()))
                    except sqlite3.IntegrityError: raise APIError(409,"Você já denunciou este usuário.")
                    add_notification(db,target_id,"moderacao","Denúncia de perfil registrada","Uma denúncia sobre sua conta foi encaminhada à moderação.")
                    notify_moderators(db,"denuncia","Denúncia de perfil recebida",f"Uma conta recebeu uma denúncia: usuário #{target_id}.")
                self.send_json({"message":"Denúncia de perfil registrada."},201); return
            match = re.fullmatch(r"/api/reports/(\d+)/decision", path)
            if match:
                user = self.current_user(); self.require_moderator(user); report_id = int(match.group(1)); decision = data.get("decision"); note = text_value(data.get("note"), "justificativa", 5, 1000)
                if decision not in ("Manter anúncio", "Ocultar anúncio"): raise APIError(400,"Selecione uma ação válida.")
                with connect() as db:
                    report = db.execute("SELECT r.*,i.owner_id,i.title,i.status AS item_status FROM reports r JOIN items i ON i.id=r.item_id WHERE r.id=?",(report_id,)).fetchone()
                    if not report: raise APIError(404,"Denúncia não encontrada.")
                    if report["status"] != "Pendente": raise APIError(409,"Esta denúncia já foi analisada.")
                    status = "Oculto" if decision == "Ocultar anúncio" else "Improcedente"
                    db.execute("UPDATE reports SET status=?,decision_by=?,decision_note=?,decided_at=? WHERE id=?",("Procedente" if decision=="Ocultar anúncio" else "Improcedente",user["id"],note,now(),report_id))
                    if decision == "Ocultar anúncio":
                        db.execute("UPDATE items SET status='Oculto',updated_at=? WHERE id=?",(now(),report["item_id"]))
                    elif report["item_status"] == "Oculto":
                        pending = db.execute("SELECT COUNT(*) FROM reports WHERE item_id=? AND status='Pendente'",(report["item_id"],)).fetchone()[0]
                        if pending == 0: db.execute("UPDATE items SET status='Aberto',updated_at=? WHERE id=?",(now(),report["item_id"]))
                    db.execute("INSERT INTO moderation_actions(moderator_id,item_id,report_id,action,justification,created_at) VALUES(?,?,?,?,?,?)",(user["id"],report["item_id"],report_id,decision,note,now()))
                    write_history(db,report["item_id"],user["id"],"Denúncia analisada",f"{decision}: {note}")
                    add_notification(db,report["owner_id"],"moderacao","Denúncia analisada",f"Uma denúncia sobre '{report['title']}' foi analisada.",report["item_id"])
                    if decision == "Ocultar anúncio":
                        upheld = db.execute("SELECT COUNT(*) FROM reports r JOIN items i ON i.id=r.item_id WHERE i.owner_id=? AND r.status='Procedente'",(report["owner_id"],)).fetchone()[0]
                        if upheld >= 3:
                            db.execute("UPDATE users SET status='Suspenso' WHERE id=?",(report["owner_id"],))
                            for key,val in list(TOKENS.items()):
                                if val[0] == report["owner_id"]: TOKENS.pop(key,None)
                            add_notification(db,report["owner_id"],"moderacao","Conta suspensa", "Sua conta foi suspensa após três denúncias procedentes.", report["item_id"])
                self.send_json({"message":"Análise de moderação registrada."}); return
            match = re.fullmatch(r"/api/profile-reports/(\d+)/decision", path)
            if match:
                user = self.current_user(); self.require_moderator(user); report_id=int(match.group(1)); decision=data.get("decision"); note=text_value(data.get("note"),"justificativa",5,1000)
                if decision not in ("Procedente","Improcedente"): raise APIError(400,"Decisão inválida.")
                with connect() as db:
                    report=db.execute("SELECT * FROM profile_reports WHERE id=?",(report_id,)).fetchone()
                    if not report: raise APIError(404,"Denúncia de perfil não encontrada.")
                    if report["status"]!="Pendente": raise APIError(409,"Esta denúncia já foi analisada.")
                    db.execute("UPDATE profile_reports SET status=?,decision_by=?,decision_note=?,decided_at=? WHERE id=?",(decision,user["id"],note,now(),report_id))
                    db.execute("INSERT INTO moderation_actions(moderator_id,action,justification,created_at) VALUES(?,?,?,?)",(user["id"],f"Denúncia de perfil #{report_id}: {decision}",note,now()))
                    if decision == "Procedente":
                        target=report["target_user_id"]
                        count=db.execute("SELECT COUNT(*) FROM profile_reports WHERE target_user_id=? AND status='Procedente'",(target,)).fetchone()[0]
                        item_count=db.execute("SELECT COUNT(*) FROM reports r JOIN items i ON i.id=r.item_id WHERE i.owner_id=? AND r.status='Procedente'",(target,)).fetchone()[0]
                        if count+item_count >= 3:
                            db.execute("UPDATE users SET status='Suspenso' WHERE id=?",(target,))
                            for key,val in list(TOKENS.items()):
                                if val[0] == target: TOKENS.pop(key,None)
                            add_notification(db,target,"moderacao","Conta suspensa","Sua conta foi suspensa após três denúncias procedentes.")
                self.send_json({"message":"Denúncia de perfil analisada."}); return
            if path == "/api/notifications/read-all":
                user=self.current_user()
                with connect() as db: db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",(user["id"],))
                self.send_json({"message":"Notificações marcadas como lidas."}); return
            if path == "/api/admin/categories":
                user=self.current_user(); self.require_admin(user); name=text_value(data.get("name"),"nome da categoria",2,80)
                requires=int(bool(data.get("requires_guard",False)))
                with connect() as db:
                    try: cur=db.execute("INSERT INTO categories(name,requires_guard,active,created_at) VALUES(?,?,1,?)",(name,requires,now()))
                    except sqlite3.IntegrityError: raise APIError(409,"Já existe uma categoria com esse nome.")
                    cid=cur.lastrowid
                self.send_json({"message":"Categoria criada.","id":cid},201); return
            if path == "/api/admin/locations":
                user=self.current_user(); self.require_admin(user); name=text_value(data.get("name"),"nome do local",2,120); block=str(data.get("block_name","")).strip()[:80]
                with connect() as db:
                    try: cur=db.execute("INSERT INTO locations(name,block_name,active,created_at) VALUES(?,?,1,?)",(name,block or extract_block(name),now()))
                    except sqlite3.IntegrityError: raise APIError(409,"Já existe um local com esse nome.")
                self.send_json({"message":"Local criado.","id":cur.lastrowid},201); return
            if path == "/api/admin/guard-points":
                user=self.current_user(); self.require_admin(user); name=text_value(data.get("name"),"nome do ponto de guarda",2,120); loc_id=data.get("location_id"); ref=str(data.get("reference","")).strip()[:255]
                try: retention=int(data.get("retention_days",90))
                except (ValueError,TypeError): raise APIError(400,"Prazo de guarda inválido.")
                if not 30 <= retention <= 365: raise APIError(400,"O prazo de guarda deve estar entre 30 e 365 dias.")
                with connect() as db:
                    if not db.execute("SELECT 1 FROM locations WHERE id=? AND active=1",(loc_id,)).fetchone(): raise APIError(400,"Selecione um local ativo.")
                    try: cur=db.execute("INSERT INTO guard_points(name,location_id,reference,retention_days,active,created_at) VALUES(?,?,?,?,1,?)",(name,int(loc_id),ref,retention,now()))
                    except sqlite3.IntegrityError: raise APIError(409,"Já existe esse ponto de guarda nesse local.")
                self.send_json({"message":"Ponto de guarda criado.","id":cur.lastrowid},201); return
            if path == "/api/admin/domains":
                user=self.current_user(); self.require_admin(user); domain=text_value(data.get("domain"),"domínio",3,190).lower().lstrip("@").strip()
                if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}",domain): raise APIError(400,"Informe um domínio válido, sem @ ou endereço completo.")
                with connect() as db:
                    try: cur=db.execute("INSERT INTO institutional_domains(domain,active,created_at) VALUES(?,1,?)",(domain,now()))
                    except sqlite3.IntegrityError: raise APIError(409,"Domínio já cadastrado.")
                self.send_json({"message":"Domínio institucional adicionado.","id":cur.lastrowid},201); return
            if path.startswith("/api/claims/") and path.endswith("/messages"):
                match=re.fullmatch(r"/api/claims/(\d+)/messages",path)
                if not match: raise APIError(404,"Rota não encontrada.")
                claim_id=int(match.group(1)); user=self.current_user(); body=text_value(data.get("body"),"mensagem",1,500)
                with connect() as db:
                    claim=db.execute("SELECT c.*,i.owner_id,i.title FROM claims c JOIN items i ON i.id=c.item_id WHERE c.id=?",(claim_id,)).fetchone()
                    if not claim: raise APIError(404,"Reivindicação não encontrada.")
                    if user["id"] not in (claim["owner_id"],claim["claimant_id"]): raise APIError(403,"Você não participa desta conversa.")
                    if claim["status"]!="Aprovada": raise APIError(400,"A conversa é liberada após a aprovação da reivindicação.")
                    db.execute("INSERT INTO messages(claim_id,sender_id,body,created_at) VALUES(?,?,?,?)",(claim_id,user["id"],body,now()))
                    other = claim["claimant_id"] if user["id"] == claim["owner_id"] else claim["owner_id"]
                    add_notification(db,other,"mensagem","Nova mensagem",f"Você recebeu uma mensagem sobre '{claim['title']}'.",claim_id=claim_id)
                self.send_json({"message":"Mensagem enviada."},201); return
            raise APIError(404,"Rota não encontrada.")
        except APIError as e:
            self.send_json({"error":e.message},e.status)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:
            print("ERRO POST:",repr(e)); self.send_json({"error":"Erro interno. Confira o terminal para detalhes."},500)

    def create_item(self, data, user, guard_mode=False):
        title=text_value(data.get("title"),"título",3,100)
        typ=data.get("type")
        if typ not in ("Achado","Perdido"): raise APIError(400,"Selecione se o item foi achado ou perdido.")
        category=text_value(data.get("category"),"categoria",2,80)
        description=text_value(data.get("description"),"descrição",5,1200)
        location=text_value(data.get("location"),"local",2,160)
        event_date=valid_date(data.get("event_date"),"data do item")
        question=str(data.get("verification_question","")).strip()
        answer=norm(data.get("verification_answer",""))
        photos=data.get("photos",[])
        if not isinstance(photos,list) or len(photos)>3: raise APIError(400,"Você pode enviar no máximo 3 fotos.")
        if typ=="Achado" and not photos: raise APIError(400,"Itens achados precisam de pelo menos uma foto.")
        if typ=="Achado" and (len(question)<8 or len(question)>250 or not answer or len(answer)>250): raise APIError(400,"Itens achados precisam de pergunta (8 a 250 caracteres) e resposta de verificação (até 250 caracteres).")
        if typ=="Perdido": question=answer=""
        prepared=[]
        for image in photos:
            if not isinstance(image,dict): raise APIError(400,"Formato de foto inválido.")
            mime=image.get("mime",""); raw=image.get("data","")
            if mime not in ("image/jpeg","image/png","image/webp"): raise APIError(400,"Use fotos JPG, PNG ou WEBP.")
            if not isinstance(raw,str) or "," not in raw: raise APIError(400,"Uma foto enviada está inválida.")
            try: binary=base64.b64decode(raw.split(",",1)[1],validate=True)
            except Exception: raise APIError(400,"Uma foto enviada está inválida.")
            if not binary or len(binary)>MAX_PHOTO: raise APIError(400,"Cada foto deve ter conteúdo e no máximo 5 MB.")
            signatures={"image/jpeg":binary.startswith(b"\xff\xd8\xff"),"image/png":binary.startswith(b"\x89PNG\r\n\x1a\n"),"image/webp":len(binary)>=12 and binary[:4]==b"RIFF" and binary[8:12]==b"WEBP"}
            if not signatures[mime]: raise APIError(400,"O conteúdo da foto não corresponde ao formato informado.")
            prepared.append((mime,binary))
        with connect() as db:
            open_count=db.execute("SELECT COUNT(*) FROM items WHERE owner_id=? AND status IN ('Aberto','No ponto de guarda')",(user["id"],)).fetchone()[0]
            day_count=db.execute("SELECT COUNT(*) FROM items WHERE owner_id=? AND substr(created_at,1,10)=?",(user["id"],date.today().isoformat())).fetchone()[0]
            if open_count>=10: raise APIError(409,"Você já tem 10 anúncios abertos. Resolva algum antes de publicar outro.")
            if day_count>=5: raise APIError(409,"Limite de 5 anúncios por dia atingido.")
            cat_row=db.execute("SELECT * FROM categories WHERE name=? COLLATE NOCASE AND active=1",(category,)).fetchone()
            if cat_row and cat_row["requires_guard"] and typ=="Achado" and not guard_mode:
                raise APIError(400,"Esta categoria deve ser cadastrada por um moderador no ponto de guarda da instituição.")
            guard_id=None; status="Aberto"
            if guard_mode:
                if user["role"] not in ("Moderador","Administrador"): raise APIError(403,"Somente a moderação pode registrar item guardado.")
                if typ!="Achado": raise APIError(400,"O ponto de guarda recebe somente itens encontrados.")
                try: guard_id=int(data.get("guard_point_id"))
                except (TypeError,ValueError): raise APIError(400,"Selecione o ponto de guarda.")
                point=db.execute("SELECT g.*,l.name AS location_name,l.id AS locid FROM guard_points g JOIN locations l ON l.id=g.location_id WHERE g.id=? AND g.active=1 AND l.active=1",(guard_id,)).fetchone()
                if not point: raise APIError(400,"O ponto de guarda selecionado não existe ou está inativo.")
                if norm(location)!=norm(point["location_name"]): raise APIError(400,"O local do anúncio precisa corresponder ao local do ponto de guarda.")
                status="No ponto de guarda"
            category_id,location_id=catalog_ids(db,category,location)
            photo_urls=[]
            for mime,binary in prepared:
                ext={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}[mime]
                filename=secrets.token_hex(16)+ext
                (UPLOAD_DIR/filename).write_bytes(binary)
                photo_urls.append("/uploads/"+filename)
            stamp=now()
            cur=db.execute("""INSERT INTO items(title,type,category,category_id,description,location,location_id,event_date,status,owner_id,guard_point_id,
                       verification_question,verification_answer,photos_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (title,typ,category,category_id,description,location,location_id,event_date,status,user["id"],guard_id,question or None,answer or None,json.dumps(photo_urls),stamp,stamp))
            item_id=cur.lastrowid
            write_history(db,item_id,user["id"],"Anúncio publicado",f"Tipo: {typ}; status: {status}.")
            row=db.execute("SELECT i.*,u.name AS owner_name FROM items i JOIN users u ON u.id=i.owner_id WHERE i.id=?",(item_id,)).fetchone()
            return item_public(row)

    def do_PATCH(self):
        try:
            path=urlparse(self.path).path; data=self.body_json(); self.api_start(); user=self.current_user()
            match=re.fullmatch(r"/api/items/(\d+)",path)
            if match:
                item_id=int(match.group(1))
                old_photo_urls=[]
                with connect() as db:
                    item=self.item_row(db,item_id)
                    if item["owner_id"]!=user["id"]: raise APIError(403,"Somente o publicador pode editar este anúncio.")
                    if item["status"]!="Aberto": raise APIError(409,"Somente anúncios abertos podem ser editados.")
                    title=text_value(data.get("title",item["title"]),"título",3,100)
                    description=text_value(data.get("description",item["description"]),"descrição",5,1200)
                    category=text_value(data.get("category",item["category"]),"categoria",2,80)
                    location=text_value(data.get("location",item["location"]),"local",2,160)
                    event_date=valid_date(data.get("event_date",item["event_date"]),"data do item")
                    target_category=db.execute("SELECT requires_guard FROM categories WHERE name=? COLLATE NOCASE AND active=1",(category,)).fetchone()
                    if not target_category: raise APIError(400,"Selecione uma categoria ativa cadastrada no sistema.")
                    if item["type"]=="Achado" and target_category["requires_guard"] and item["guard_point_id"] is None:
                        raise APIError(400,"Esta categoria deve ser cadastrada por um moderador no ponto de guarda da instituição.")
                    photos_in=data.get("photos",None)
                    photo_urls=json.loads(item["photos_json"] or "[]")
                    if photos_in is not None:
                        if not isinstance(photos_in,list) or len(photos_in)>3: raise APIError(400,"Você pode manter no máximo 3 fotos.")
                        if item["type"]=="Achado" and not photos_in: raise APIError(400,"Itens achados precisam manter pelo menos uma foto.")
                        old_photo_urls = photo_urls
                        photo_urls = []
                        prepared=[]
                        for image in photos_in:
                            mime=image.get("mime",""); raw=image.get("data","")
                            if mime not in ("image/jpeg","image/png","image/webp") or not isinstance(raw,str) or "," not in raw: raise APIError(400,"Uma foto enviada está inválida.")
                            try: binary=base64.b64decode(raw.split(",",1)[1],validate=True)
                            except Exception: raise APIError(400,"Uma foto enviada está inválida.")
                            if len(binary)>MAX_PHOTO: raise APIError(400,"Cada foto deve ter no máximo 5 MB.")
                            if not ((mime=="image/jpeg" and binary.startswith(b"\xff\xd8\xff")) or (mime=="image/png" and binary.startswith(b"\x89PNG\r\n\x1a\n")) or (mime=="image/webp" and len(binary)>=12 and binary[:4]==b"RIFF" and binary[8:12]==b"WEBP")):
                                raise APIError(400,"O conteúdo da foto não corresponde ao formato informado.")
                            ext={"image/jpeg":".jpg","image/png":".png","image/webp":".webp"}[mime]; filename=secrets.token_hex(16)+ext; (UPLOAD_DIR/filename).write_bytes(binary); photo_urls.append("/uploads/"+filename)
                        if len(photo_urls)>3: raise APIError(400,"Você pode manter no máximo 3 fotos no total.")
                    category_id,location_id=catalog_ids(db,category,location)
                    db.execute("UPDATE items SET title=?,description=?,category=?,category_id=?,location=?,location_id=?,event_date=?,photos_json=?,updated_at=? WHERE id=?",(title,description,category,category_id,location,location_id,event_date,json.dumps(photo_urls),now(),item_id))
                    write_history(db,item_id,user["id"],"Anúncio editado","Título, descrição, categoria, local, data e/ou fotos atualizados.")
                for old_url in old_photo_urls:
                    try:
                        if old_url.startswith("/uploads/"):
                            (UPLOAD_DIR / Path(old_url).name).unlink(missing_ok=True)
                    except OSError:
                        pass
                self.send_json({"message":"Anúncio atualizado com sucesso."}); return
            match=re.fullmatch(r"/api/notifications/(\d+)/read",path)
            if match:
                notif_id=int(match.group(1))
                with connect() as db:
                    cur=db.execute("UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",(notif_id,user["id"]))
                    if cur.rowcount==0: raise APIError(404,"Notificação não encontrada.")
                self.send_json({"message":"Notificação marcada como lida."}); return
            match=re.fullmatch(r"/api/admin/categories/(\d+)",path)
            if match:
                self.require_admin(user); cid=int(match.group(1))
                with connect() as db:
                    row=db.execute("SELECT * FROM categories WHERE id=?",(cid,)).fetchone()
                    if not row: raise APIError(404,"Categoria não encontrada.")
                    name=text_value(data.get("name",row["name"]),"nome",2,80); guard=int(bool(data.get("requires_guard",row["requires_guard"]))); active=int(bool(data.get("active",row["active"])))
                    try: db.execute("UPDATE categories SET name=?,requires_guard=?,active=? WHERE id=?",(name,guard,active,cid))
                    except sqlite3.IntegrityError: raise APIError(409,"Já existe categoria com esse nome.")
                self.send_json({"message":"Categoria atualizada."}); return
            match=re.fullmatch(r"/api/admin/locations/(\d+)",path)
            if match:
                self.require_admin(user); lid=int(match.group(1))
                with connect() as db:
                    row=db.execute("SELECT * FROM locations WHERE id=?",(lid,)).fetchone()
                    if not row: raise APIError(404,"Local não encontrado.")
                    name=text_value(data.get("name",row["name"]),"nome",2,120); block=str(data.get("block_name",row["block_name"])).strip()[:80]; active=int(bool(data.get("active",row["active"])))
                    try: db.execute("UPDATE locations SET name=?,block_name=?,active=? WHERE id=?",(name,block,active,lid))
                    except sqlite3.IntegrityError: raise APIError(409,"Já existe local com esse nome.")
                self.send_json({"message":"Local atualizado."}); return
            match=re.fullmatch(r"/api/admin/guard-points/(\d+)",path)
            if match:
                self.require_admin(user); gid=int(match.group(1))
                with connect() as db:
                    row=db.execute("SELECT * FROM guard_points WHERE id=?",(gid,)).fetchone()
                    if not row: raise APIError(404,"Ponto de guarda não encontrado.")
                    name=text_value(data.get("name",row["name"]),"nome",2,120)
                    try: loc=int(data.get("location_id",row["location_id"])); retention=int(data.get("retention_days",row["retention_days"]))
                    except (TypeError,ValueError): raise APIError(400,"Local ou prazo inválido.")
                    if not db.execute("SELECT 1 FROM locations WHERE id=? AND active=1",(loc,)).fetchone(): raise APIError(400,"Selecione um local ativo.")
                    if not 30<=retention<=365: raise APIError(400,"O prazo deve estar entre 30 e 365 dias.")
                    active=int(bool(data.get("active",row["active"])))
                    db.execute("UPDATE guard_points SET name=?,location_id=?,reference=?,retention_days=?,active=? WHERE id=?",(name,loc,str(data.get("reference",row["reference"])).strip()[:255],retention,active,gid))
                self.send_json({"message":"Ponto de guarda atualizado."}); return
            match=re.fullmatch(r"/api/admin/domains/(\d+)",path)
            if match:
                self.require_admin(user); did=int(match.group(1)); active=data.get("active")
                if active not in (True,False,0,1): raise APIError(400,"Informe active como booleano.")
                with connect() as db:
                    cur=db.execute("UPDATE institutional_domains SET active=? WHERE id=?",(int(bool(active)),did))
                    if cur.rowcount==0: raise APIError(404,"Domínio não encontrado.")
                self.send_json({"message":"Domínio atualizado."}); return
            match=re.fullmatch(r"/api/admin/users/(\d+)/(role|status)",path)
            if match:
                self.require_admin(user); uid=int(match.group(1)); field=match.group(2)
                with connect() as db:
                    target=db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
                    if not target: raise APIError(404,"Usuário não encontrado.")
                    if field=="role":
                        role=data.get("role")
                        if role not in ("Estudante","Moderador","Administrador"): raise APIError(400,"Perfil inválido.")
                        if uid==user["id"] and role!="Administrador": raise APIError(400,"Não é permitido remover seu próprio perfil administrativo nesta sessão.")
                        db.execute("UPDATE users SET role=? WHERE id=?",(role,uid))
                    else:
                        status=data.get("status")
                        if status not in ("Ativo","Suspenso"): raise APIError(400,"Status inválido.")
                        if uid==user["id"] and status!="Ativo": raise APIError(400,"Não suspenda sua própria conta durante a sessão.")
                        db.execute("UPDATE users SET status=? WHERE id=?",(status,uid))
                        if status=="Suspenso":
                            for key,val in list(TOKENS.items()):
                                if val[0]==uid: TOKENS.pop(key,None)
                        elif target["email_verified"]:
                            add_notification(db,uid,"conta","Conta reativada","Sua conta foi reativada pela administração.")
                self.send_json({"message":"Usuário atualizado."}); return
            if path=="/api/me/preferences":
                value=data.get("email_notifications")
                if value not in (True,False,0,1): raise APIError(400,"Informe email_notifications como booleano.")
                with connect() as db: db.execute("UPDATE users SET email_notifications=? WHERE id=?",(int(bool(value)),user["id"]))
                self.send_json({"message":"Preferências salvas. O envio real de e-mail exige configurar um serviço SMTP.","email_notifications":bool(value)}); return
            raise APIError(404,"Rota não encontrada.")
        except APIError as e:
            self.send_json({"error":e.message},e.status)
        except (BrokenPipeError,ConnectionResetError):
            return
        except Exception as e:
            print("ERRO PATCH:",repr(e)); self.send_json({"error":"Erro interno. Confira o terminal para detalhes."},500)

    def do_DELETE(self):
        try:
            path=urlparse(self.path).path; self.api_start(); user=self.current_user()
            match=re.fullmatch(r"/api/items/(\d+)",path)
            if not match: raise APIError(404,"Rota não encontrada.")
            item_id=int(match.group(1))
            with connect() as db:
                item=self.item_row(db,item_id)
                if item["owner_id"]!=user["id"] and user["role"]!="Administrador": raise APIError(403,"Somente o publicador ou a administração pode excluir o anúncio.")
                child_count=db.execute("SELECT COUNT(*) FROM claims WHERE item_id=?",(item_id,)).fetchone()[0]
                report_count=db.execute("SELECT COUNT(*) FROM reports WHERE item_id=?",(item_id,)).fetchone()[0]
                if child_count or report_count: raise APIError(409,"Este anúncio possui histórico de reivindicação ou denúncia. Marque-o como resolvido para preservar a auditoria.")
                photos=json.loads(item["photos_json"] or "[]")
                db.execute("DELETE FROM notifications WHERE item_id=?",(item_id,))
                db.execute("DELETE FROM item_history WHERE item_id=?",(item_id,))
                db.execute("DELETE FROM items WHERE id=?",(item_id,))
            for url in photos:
                try:
                    if url.startswith("/uploads/"): (UPLOAD_DIR/Path(url).name).unlink(missing_ok=True)
                except OSError: pass
            self.send_json({"message":"Anúncio excluído."}); return
        except APIError as e:
            self.send_json({"error":e.message},e.status)
        except Exception as e:
            print("ERRO DELETE:",repr(e)); self.send_json({"error":"Erro interno. Confira o terminal para detalhes."},500)


def main():
    init_db()
    maintenance(force=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("\n==============================================")
    print("  ENCONTREI - ACHADOS E PERDIDOS")
    print(f"  Aplicação: http://{HOST}:{PORT}")
    print(f"  Banco local: {DB_PATH}")
    print("  Para encerrar, volte aqui e pressione Ctrl+C")
    print("==============================================\n")
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    maintenance_stop = threading.Event()
    maintenance_thread = threading.Thread(
        target=maintenance_worker, args=(maintenance_stop, 60),
        name="encontrei-maintenance", daemon=True
    )
    maintenance_thread.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor encerrado.")
    finally:
        maintenance_stop.set()
        maintenance_thread.join(timeout=2)
        server.server_close()

if __name__ == "__main__":
    main()
