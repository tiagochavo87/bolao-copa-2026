"""Bolão Copa 2026 — backend v2"""
import datetime, hashlib, hmac, os, secrets, smtplib, sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Response, Depends, Cookie
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH      = os.environ.get("BOLAO_DB", "./bolao.db")
SECRET       = os.environ.get("BOLAO_SECRET", "troque-isso")
ADMIN_USER   = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS   = os.environ.get("ADMIN_PASS", "admin123")
GMAIL_USER   = os.environ.get("GMAIL_USER", "")
GMAIL_APP    = os.environ.get("GMAIL_APP", "")
PRECO_BRASIL = float(os.environ.get("PRECO_BRASIL", "5"))
PRECO_GRUPOS = float(os.environ.get("PRECO_GRUPOS", "10"))

app = FastAPI(title="Bolão Copa 2026")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        pw_hash TEXT NOT NULL,
        role TEXT DEFAULT 'pending',
        first_login INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        phase TEXT NOT NULL,
        group_name TEXT,
        home TEXT NOT NULL,
        away TEXT NOT NULL,
        kickoff TEXT NOT NULL,
        home_score INTEGER,
        away_score INTEGER,
        status TEXT DEFAULT 'upcoming'
    );
    CREATE TABLE IF NOT EXISTS tips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        match_id TEXT NOT NULL,
        home_tip INTEGER NOT NULL,
        away_tip INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, match_id)
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at TEXT NOT NULL
    );
    """)
    cur = conn.execute("SELECT id FROM users WHERE username=?", (ADMIN_USER,))
    if not cur.fetchone():
        conn.execute(
            "INSERT INTO users(username,email,pw_hash,role,first_login) VALUES(?,?,?,'admin',0)",
            (ADMIN_USER, GMAIL_USER or "admin@bolao.local", _hash(ADMIN_PASS)))
    conn.commit()
    conn.close()
    _seed_matches()

def _seed_matches():
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]:
        conn.close()
        return
    # Dados 100% oficiais — PDF FIFA Copa 2026
    # Horários em UTC (horário de Brasília = UTC-3, então 16h BRT = 19h UTC)
    jogos = [
        # GRUPO A
        ("GA1","grupos","A","México","África do Sul","2026-06-11 19:00"),        # 16h BRT
        ("GA2","grupos","A","Coreia do Sul","Rep. Tcheca","2026-06-12 02:00"),   # 23h BRT
        ("GA3","grupos","A","Rep. Tcheca","África do Sul","2026-06-18 16:00"),   # 13h BRT
        ("GA4","grupos","A","México","Coreia do Sul","2026-06-18 01:00"),        # 22h BRT
        ("GA5","grupos","A","Rep. Tcheca","México","2026-06-25 01:00"),          # 22h BRT
        ("GA6","grupos","A","África do Sul","Coreia do Sul","2026-06-25 01:00"), # 22h BRT
        # GRUPO B
        ("GB1","grupos","B","Canadá","Bósnia e Herz.","2026-06-12 19:00"),      # 16h BRT
        ("GB2","grupos","B","Catar","Suíça","2026-06-13 19:00"),                # 16h BRT
        ("GB3","grupos","B","Suíça","Bósnia e Herz.","2026-06-18 19:00"),       # 16h BRT
        ("GB4","grupos","B","Canadá","Catar","2026-06-19 22:00"),               # 19h BRT
        ("GB5","grupos","B","Suíça","Canadá","2026-06-24 19:00"),               # 16h BRT
        ("GB6","grupos","B","Bósnia e Herz.","Catar","2026-06-24 19:00"),       # 16h BRT
        # GRUPO C
        ("GC1","grupos","C","Brasil","Marrocos","2026-06-13 22:00"),            # 19h BRT
        ("GC2","grupos","C","Haiti","Escócia","2026-06-14 01:00"),              # 22h BRT
        ("GC3","grupos","C","Escócia","Marrocos","2026-06-19 22:00"),           # 19h BRT
        ("GC4","grupos","C","Brasil","Haiti","2026-06-20 00:30"),               # 21h30 BRT
        ("GC5","grupos","C","Escócia","Brasil","2026-06-24 22:00"),             # 19h BRT
        ("GC6","grupos","C","Marrocos","Haiti","2026-06-24 22:00"),             # 19h BRT
        # GRUPO D
        ("GD1","grupos","D","Estados Unidos","Paraguai","2026-06-13 01:00"),    # 22h BRT (dia 12)
        ("GD2","grupos","D","Austrália","Turquia","2026-06-14 04:00"),          # 01h BRT
        ("GD3","grupos","D","Turquia","Paraguai","2026-06-20 03:00"),           # 00h BRT
        ("GD4","grupos","D","Estados Unidos","Austrália","2026-06-19 19:00"),   # 16h BRT
        ("GD5","grupos","D","Turquia","Estados Unidos","2026-06-25 02:00"),     # 23h BRT
        ("GD6","grupos","D","Paraguai","Austrália","2026-06-25 02:00"),         # 23h BRT
        # GRUPO E
        ("GE1","grupos","E","Alemanha","Curaçao","2026-06-14 17:00"),           # 14h BRT
        ("GE2","grupos","E","Costa do Marfim","Equador","2026-06-14 23:00"),    # 20h BRT
        ("GE3","grupos","E","Alemanha","Costa do Marfim","2026-06-20 20:00"),   # 17h BRT
        ("GE4","grupos","E","Equador","Curaçao","2026-06-21 00:00"),            # 21h BRT
        ("GE5","grupos","E","Equador","Alemanha","2026-06-25 20:00"),           # 17h BRT
        ("GE6","grupos","E","Curaçao","Costa do Marfim","2026-06-25 20:00"),    # 17h BRT
        # GRUPO F
        ("GF1","grupos","F","Holanda","Japão","2026-06-14 20:00"),              # 17h BRT
        ("GF2","grupos","F","Suécia","Tunísia","2026-06-15 02:00"),             # 23h BRT
        ("GF3","grupos","F","Tunísia","Japão","2026-06-21 04:00"),              # 01h BRT
        ("GF4","grupos","F","Holanda","Suécia","2026-06-20 23:00"),             # 20h BRT
        ("GF5","grupos","F","Japão","Suécia","2026-06-25 23:00"),               # 20h BRT
        ("GF6","grupos","F","Tunísia","Holanda","2026-06-25 23:00"),            # 20h BRT
        # GRUPO G
        ("GG1","grupos","G","Bélgica","Egito","2026-06-15 19:00"),              # 16h BRT
        ("GG2","grupos","G","Irã","Nova Zelândia","2026-06-16 01:00"),          # 22h BRT
        ("GG3","grupos","G","Bélgica","Irã","2026-06-21 19:00"),               # 16h BRT
        ("GG4","grupos","G","Nova Zelândia","Egito","2026-06-22 01:00"),        # 22h BRT
        ("GG5","grupos","G","Egito","Irã","2026-06-27 03:00"),                  # 00h BRT
        ("GG6","grupos","G","Nova Zelândia","Bélgica","2026-06-27 03:00"),      # 00h BRT
        # GRUPO H
        ("GH1","grupos","H","Espanha","Cabo Verde","2026-06-15 16:00"),         # 13h BRT
        ("GH2","grupos","H","Arábia Saudita","Uruguai","2026-06-15 22:00"),     # 19h BRT
        ("GH3","grupos","H","Espanha","Arábia Saudita","2026-06-21 16:00"),     # 13h BRT
        ("GH4","grupos","H","Uruguai","Cabo Verde","2026-06-21 22:00"),         # 19h BRT
        ("GH5","grupos","H","Cabo Verde","Arábia Saudita","2026-06-26 00:00"),  # 21h BRT
        ("GH6","grupos","H","Uruguai","Espanha","2026-06-26 00:00"),            # 21h BRT
        # GRUPO I
        ("GI1","grupos","I","França","Senegal","2026-06-16 19:00"),             # 16h BRT
        ("GI2","grupos","I","Iraque","Noruega","2026-06-16 22:00"),             # 19h BRT
        ("GI3","grupos","I","França","Iraque","2026-06-21 21:00"),              # 18h BRT
        ("GI4","grupos","I","Noruega","Senegal","2026-06-23 00:00"),            # 21h BRT
        ("GI5","grupos","I","Noruega","França","2026-06-26 19:00"),             # 16h BRT
        ("GI6","grupos","I","Senegal","Iraque","2026-06-26 19:00"),             # 16h BRT
        # GRUPO J
        ("GJ1","grupos","J","Argentina","Argélia","2026-06-16 17:00"),          # 14h BRT
        ("GJ2","grupos","J","Áustria","Jordânia","2026-06-17 04:00"),           # 01h BRT
        ("GJ3","grupos","J","Argentina","Áustria","2026-06-22 17:00"),          # 14h BRT
        ("GJ4","grupos","J","Jordânia","Argélia","2026-06-23 03:00"),           # 00h BRT
        ("GJ5","grupos","J","Argélia","Áustria","2026-06-27 02:00"),            # 23h BRT
        ("GJ6","grupos","J","Jordânia","Argentina","2026-06-27 02:00"),         # 23h BRT
        # GRUPO K
        ("GK1","grupos","K","Portugal","R.D. Congo","2026-06-14 17:00"),        # 14h BRT
        ("GK2","grupos","K","Uzbequistão","Colômbia","2026-06-17 20:00"),       # 17h BRT
        ("GK3","grupos","K","Portugal","Uzbequistão","2026-06-23 17:00"),       # 14h BRT
        ("GK4","grupos","K","Colômbia","R.D. Congo","2026-06-23 22:00"),        # 19h BRT
        ("GK5","grupos","K","Colômbia","Portugal","2026-06-27 23:30"),          # 20h30 BRT
        ("GK6","grupos","K","R.D. Congo","Uzbequistão","2026-06-27 23:30"),     # 20h30 BRT
        # GRUPO L
        ("GL1","grupos","L","Inglaterra","Croácia","2026-06-17 20:00"),         # 17h BRT
        ("GL2","grupos","L","Gana","Panamá","2026-06-17 23:00"),                # 20h BRT
        ("GL3","grupos","L","Inglaterra","Gana","2026-06-23 20:00"),            # 17h BRT
        ("GL4","grupos","L","Panamá","Croácia","2026-06-23 23:00"),             # 20h BRT
        ("GL5","grupos","L","Panamá","Inglaterra","2026-06-27 21:00"),          # 18h BRT
        ("GL6","grupos","L","Croácia","Gana","2026-06-27 21:00"),               # 18h BRT
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO matches(id,phase,group_name,home,away,kickoff) VALUES(?,?,?,?,?,?)",
        jogos)
    conn.commit()
    conn.close()

def _hash(pw):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 260000)
    return f"{salt}${dk.hex()}"

def _verify(pw, stored):
    try:
        salt, dk = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 260000)
        return hmac.compare_digest(check.hex(), dk)
    except Exception:
        return False

def get_current_user(bolao_session: Optional[str] = Cookie(None)):
    if not bolao_session:
        raise HTTPException(401, "não autenticado")
    conn = get_db()
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
        "WHERE s.token=? AND s.expires_at > datetime('now')", (bolao_session,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(401, "sessão expirada")
    return dict(row)

def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "acesso restrito")
    return user

def calc_preco(tips):
    # valor FIXO por categoria — R$5 se palpitou qualquer jogo do Brasil, R$10 se palpitou qualquer grupo
    tem_brasil = any(t.get("home") == "Brasil" or t.get("away") == "Brasil" for t in tips)
    tem_grupos = any(t.get("home") != "Brasil" and t.get("away") != "Brasil" and t.get("phase") == "grupos" for t in tips)
    return {
        "tem_brasil": tem_brasil, "tem_grupos": tem_grupos,
        "preco_brasil": PRECO_BRASIL, "preco_grupos": PRECO_GRUPOS,
        "total_devido": (PRECO_BRASIL if tem_brasil else 0) + (PRECO_GRUPOS if tem_grupos else 0),
        "palpites_brasil": 1 if tem_brasil else 0,
        "palpites_grupos": 1 if tem_grupos else 0,
    }

def send_email(to, subject, html):
    if not GMAIL_USER or not GMAIL_APP:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Bolão Copa 2026 <{GMAIL_USER}>"
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_APP)
            s.sendmail(GMAIL_USER, to, msg.as_string())
        return True
    except Exception as e:
        print(f"[email error] {e}")
        return False

def email_aprovacao(user):
    html = f"""<div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto">
      <div style="background:#2d5c3e;padding:24px;border-radius:10px 10px 0 0">
        <h1 style="color:white;margin:0;font-size:20px">⚽ Bolão Copa 2026</h1>
      </div>
      <div style="background:#f7f9f8;padding:24px;border-radius:0 0 10px 10px;border:1px solid #d4ddd7;border-top:none">
        <p>Olá, <strong>{user['username']}</strong>!</p>
        <p style="color:#4e6356">Sua conta foi aprovada. Agora você pode entrar e fazer seus palpites.</p>
      </div>
    </div>"""
    return send_email(user["email"], "✅ Conta aprovada — Bolão Copa 2026", html)

def email_recibo(user, tips):
    now = datetime.datetime.now().strftime("%d/%m/%Y às %H:%M")
    preco = calc_preco(tips)
    total_pts = sum(4 for t in tips if t["status"] == "finished"
                    and t["home_tip"] == t["home_score"] and t["away_tip"] == t["away_score"])
    rows = ""
    for t in tips:
        finished = t["status"] == "finished"
        hit = finished and t["home_tip"] == t["home_score"] and t["away_tip"] == t["away_score"]
        pts = "+4" if hit else ("0" if finished else "–")
        cor = "#2e7d32" if hit else "#555"
        result = f"{t['home_score']} × {t['away_score']}" if finished else "–"
        is_brasil = t["home"] == "Brasil" or t["away"] == "Brasil"
        pj = f"R$ {PRECO_BRASIL:.0f}" if is_brasil else f"R$ {PRECO_GRUPOS:.0f}"
        rows += f"<tr><td style='padding:8px;border-bottom:1px solid #eef2f0'>{t['home']} × {t['away']}</td><td style='padding:8px;border-bottom:1px solid #eef2f0;text-align:center'>Grupo {t['group_name']}</td><td style='padding:8px;border-bottom:1px solid #eef2f0;text-align:center;font-weight:600'>{t['home_tip']} × {t['away_tip']}</td><td style='padding:8px;border-bottom:1px solid #eef2f0;text-align:center'>{result}</td><td style='padding:8px;border-bottom:1px solid #eef2f0;text-align:center;font-weight:600;color:{cor}'>{pts}</td><td style='padding:8px;border-bottom:1px solid #eef2f0;text-align:center;color:#2d5c3e;font-weight:600'>{pj}</td></tr>"
    html = f"""<div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto">
      <div style="background:#2d5c3e;padding:24px;border-radius:10px 10px 0 0">
        <h1 style="color:white;margin:0;font-size:20px">⚽ Bolão Copa 2026</h1>
        <p style="color:#a5c9b0;margin:4px 0 0;font-size:13px">Recibo de palpites — {now}</p>
      </div>
      <div style="background:#f7f9f8;padding:24px;border-radius:0 0 10px 10px;border:1px solid #d4ddd7;border-top:none">
        <p>Olá, <strong>{user['username']}</strong>!</p>
        <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;border:1px solid #d4ddd7">
          <thead><tr style="background:#e8f2eb">
            <th style="padding:8px;text-align:left;font-size:11px;color:#2d5c3e;text-transform:uppercase">Partida</th>
            <th style="padding:8px;font-size:11px;color:#2d5c3e;text-transform:uppercase">Grupo</th>
            <th style="padding:8px;font-size:11px;color:#2d5c3e;text-transform:uppercase">Palpite</th>
            <th style="padding:8px;font-size:11px;color:#2d5c3e;text-transform:uppercase">Resultado</th>
            <th style="padding:8px;font-size:11px;color:#2d5c3e;text-transform:uppercase">Pts</th>
            <th style="padding:8px;font-size:11px;color:#2d5c3e;text-transform:uppercase">Valor</th>
          </tr></thead>
          <tbody>{rows}</tbody>
        </table>
        <div style="margin-top:16px;background:#e8f2eb;border-radius:8px;padding:16px">
          <div style="font-size:13px;color:#4e6356;margin-bottom:4px">🇧🇷 Brasil: {'participando' if preco['tem_brasil'] else 'não participando'} = R$ {PRECO_BRASIL:.0f if preco['tem_brasil'] else '0.00'}</div>
          <div style="font-size:13px;color:#4e6356;margin-bottom:12px">⚽ Grupos: {'participando' if preco['tem_grupos'] else 'não participando'} = R$ {PRECO_GRUPOS:.0f if preco['tem_grupos'] else '0.00'}</div>
          <div style="display:flex;justify-content:space-between">
            <span style="font-weight:600;color:#2d5c3e">Pontos: {total_pts} pts</span>
            <span style="font-weight:700;color:#2d5c3e;font-size:18px">Total: R$ {preco['total_devido']:.2f}</span>
          </div>
        </div>
      </div>
    </div>"""
    return send_email(user["email"], "⚽ Seus palpites — Bolão Copa 2026", html)

class RegisterBody(BaseModel):
    username: str
    password: str
    email: str

class LoginBody(BaseModel):
    username: str
    password: str

class TipBody(BaseModel):
    match_id: str
    home_tip: int
    away_tip: int

class ResultBody(BaseModel):
    match_id: str
    home_score: int
    away_score: int

class RoleBody(BaseModel):
    role: str

@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(Path("index.html").read_text(encoding="utf-8"))

@app.get("/flags/{name}")
def get_flag(name: str):
    p = Path("flags") / name
    if not p.exists() or p.suffix != ".svg":
        raise HTTPException(404, "não encontrado")
    return FileResponse(str(p), media_type="image/svg+xml")

@app.post("/api/auth/register")
def register(body: RegisterBody):
    if len(body.username.strip()) < 2:
        raise HTTPException(400, "usuário precisa ter ao menos 2 caracteres")
    if len(body.password) < 6:
        raise HTTPException(400, "senha precisa ter ao menos 6 caracteres")
    if "@" not in body.email or "." not in body.email:
        raise HTTPException(400, "email inválido")
    conn = get_db()
    try:
        conn.execute("INSERT INTO users(username,email,pw_hash) VALUES(?,?,?)",
                     (body.username.strip(), body.email.strip().lower(), _hash(body.password)))
        conn.commit()
    except sqlite3.IntegrityError as e:
        msg = "email já cadastrado" if "email" in str(e) else "nome de usuário já em uso"
        raise HTTPException(409, msg)
    finally:
        conn.close()
    return {"ok": True}

@app.post("/api/auth/login")
def login(body: LoginBody, response: Response):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username=?", (body.username.strip(),)).fetchone()
    conn.close()
    if not row or not _verify(body.password, row["pw_hash"]):
        raise HTTPException(401, "usuário ou senha inválidos")
    if row["role"] == "pending":
        raise HTTPException(403, "conta aguardando aprovação do administrador")
    if row["role"] == "banned":
        raise HTTPException(403, "conta suspensa")
    token = secrets.token_urlsafe(32)
    exp = (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat()
    conn = get_db()
    conn.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)", (token, row["id"], exp))
    conn.commit()
    conn.close()
    response.set_cookie("bolao_session", token, httponly=True, samesite="lax", secure=False, max_age=86400*30)
    return {"ok": True, "username": row["username"], "role": row["role"],
            "email": row["email"], "first_login": bool(row["first_login"])}

@app.post("/api/auth/logout")
def logout(response: Response, bolao_session: Optional[str] = Cookie(None)):
    if bolao_session:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token=?", (bolao_session,))
        conn.commit()
        conn.close()
    response.delete_cookie("bolao_session")
    return {"ok": True}

@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    return {"username": user["username"], "role": user["role"],
            "email": user["email"], "first_login": bool(user["first_login"])}

@app.post("/api/auth/first-login-seen")
def first_login_seen(user=Depends(get_current_user)):
    conn = get_db()
    conn.execute("UPDATE users SET first_login=0 WHERE id=?", (user["id"],))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/matches")
def matches(phase: Optional[str] = None, group: Optional[str] = None, user=Depends(get_current_user)):
    conn = get_db()
    sql = "SELECT * FROM matches WHERE 1=1"
    params = []
    if phase:
        sql += " AND phase=?"; params.append(phase)
    if group:
        sql += " AND group_name=?"; params.append(group)
    sql += " ORDER BY kickoff"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    tips = {r["match_id"]: dict(r) for r in conn.execute(
        "SELECT * FROM tips WHERE user_id=?", (user["id"],)).fetchall()}
    for r in rows:
        t = tips.get(r["id"])
        r["my_tip"] = {"home": t["home_tip"], "away": t["away_tip"]} if t else None
    conn.close()
    return rows

def _is_open(kickoff_str):
    ko = datetime.datetime.fromisoformat(kickoff_str)
    return datetime.datetime.utcnow() < ko - datetime.timedelta(hours=1)

@app.post("/api/tip")
def save_tip(body: TipBody, user=Depends(get_current_user)):
    conn = get_db()
    match = conn.execute("SELECT * FROM matches WHERE id=?", (body.match_id,)).fetchone()
    if not match:
        raise HTTPException(404, "partida não encontrada")
    if match["status"] == "finished":
        raise HTTPException(400, "partida já encerrada")
    if not _is_open(match["kickoff"]):
        raise HTTPException(400, "prazo encerrado — palpites fecham 1 hora antes do jogo")
    conn.execute(
        "INSERT INTO tips(user_id,match_id,home_tip,away_tip) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id,match_id) DO UPDATE SET "
        "home_tip=excluded.home_tip, away_tip=excluded.away_tip, created_at=datetime('now')",
        (user["id"], body.match_id, body.home_tip, body.away_tip))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/my-tips")
def my_tips(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT t.*, m.home, m.away, m.kickoff, m.phase, m.group_name, "
        "m.home_score, m.away_score, m.status "
        "FROM tips t JOIN matches m ON m.id=t.match_id "
        "WHERE t.user_id=? ORDER BY m.kickoff", (user["id"],)).fetchall()
    conn.close()
    tips = [dict(r) for r in rows]
    return {"tips": tips, "preco": calc_preco(tips)}

@app.post("/api/my-tips/email")
def send_tips_email(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT t.*, m.home, m.away, m.kickoff, m.phase, m.group_name, "
        "m.home_score, m.away_score, m.status "
        "FROM tips t JOIN matches m ON m.id=t.match_id "
        "WHERE t.user_id=? ORDER BY m.kickoff", (user["id"],)).fetchall()
    conn.close()
    tips = [dict(r) for r in rows]
    if not tips:
        raise HTTPException(400, "você ainda não tem palpites registrados")
    ok = email_recibo(dict(user), tips)
    if not ok:
        raise HTTPException(500, "falha ao enviar email — verifique as configurações SMTP")
    return {"ok": True}

@app.get("/api/ranking")
def ranking(user=Depends(get_current_user)):
    conn = get_db()
    users = conn.execute("SELECT id, username FROM users WHERE role IN ('user','admin')").fetchall()
    result = []
    for u in users:
        tips = conn.execute(
            "SELECT t.home_tip, t.away_tip, m.home_score, m.away_score, m.home, m.away, m.phase "
            "FROM tips t JOIN matches m ON m.id=t.match_id WHERE t.user_id=?", (u["id"],)).fetchall()
        tips_list = [dict(t) for t in tips]

        def is_brasil(t): return t.get("home") == "Brasil" or t.get("away") == "Brasil"
        def is_hit(t): return t["home_tip"] == t["home_score"] and t["away_tip"] == t["away_score"]
        def is_done(t): return t.get("home_score") is not None

        finished       = [t for t in tips_list if is_done(t)]
        fin_brasil     = [t for t in finished if is_brasil(t)]
        fin_grupos     = [t for t in finished if not is_brasil(t) and t.get("phase") == "grupos"]

        pts            = sum(4 for t in finished   if is_hit(t))
        exact          = sum(1 for t in finished   if is_hit(t))
        pts_brasil     = sum(4 for t in fin_brasil if is_hit(t))
        exact_brasil   = sum(1 for t in fin_brasil if is_hit(t))
        pts_grupos     = sum(4 for t in fin_grupos if is_hit(t))
        exact_grupos   = sum(1 for t in fin_grupos if is_hit(t))

        preco = calc_preco(tips_list)
        result.append({
            "username": u["username"], "is_self": u["id"] == user["id"],
            "tips_count": len(tips_list),
            # geral
            "points": pts, "exact": exact,
            # brasil
            "pts_brasil": pts_brasil, "exact_brasil": exact_brasil,
            "tips_brasil": len([t for t in tips_list if is_brasil(t)]),
            # grupos (sem brasil)
            "pts_grupos": pts_grupos, "exact_grupos": exact_grupos,
            "tips_grupos": len([t for t in tips_list if not is_brasil(t) and t.get("phase") == "grupos"]),
            # financeiro (inalterado)
            "total_devido": preco["total_devido"],
            "palpites_brasil": preco["palpites_brasil"],
            "palpites_grupos": preco["palpites_grupos"],
        })

    # rank geral
    result.sort(key=lambda x: (-x["points"], -x["exact"]))
    for i, r in enumerate(result, 1):
        r["rank"] = i

    # rank brasil (posição independente)
    for i, r in enumerate(sorted(result, key=lambda x: (-x["pts_brasil"], -x["exact_brasil"])), 1):
        r["rank_brasil"] = i

    # rank grupos (posição independente)
    for i, r in enumerate(sorted(result, key=lambda x: (-x["pts_grupos"], -x["exact_grupos"])), 1):
        r["rank_grupos"] = i

    conn.close()
    return result

@app.get("/api/admin/users")
def admin_users(admin=Depends(require_admin)):
    conn = get_db()
    rows = conn.execute("SELECT id,username,email,role,created_at FROM users ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/admin/users/{uid}/role")
def set_role(uid: int, body: RoleBody, admin=Depends(require_admin)):
    if body.role not in ("admin", "user", "pending", "banned"):
        raise HTTPException(400, "papel inválido")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        raise HTTPException(404, "usuário não encontrado")
    conn.execute("UPDATE users SET role=? WHERE id=?", (body.role, uid))
    conn.commit()
    conn.close()
    if body.role == "user":
        email_aprovacao(dict(user))
    return {"ok": True}

@app.post("/api/admin/result")
def set_result(body: ResultBody, admin=Depends(require_admin)):
    conn = get_db()
    conn.execute("UPDATE matches SET home_score=?, away_score=?, status='finished' WHERE id=?",
                 (body.home_score, body.away_score, body.match_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.on_event("startup")
def startup():
    init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
