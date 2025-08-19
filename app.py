import streamlit as st
import psycopg2
import psycopg2.extras
import bcrypt
import os
from decimal import Decimal, InvalidOperation

# --------- Config: pega a URL do Neon dos Secrets ou do ambiente ----------
def _get_neon_url():
    try:
        if "NEON_URL" in st.secrets:
            return st.secrets["NEON_URL"]
    except Exception:
        pass
    if os.getenv("NEON_URL"):
        return os.getenv("NEON_URL")
    # fallback opcional (troque se quiser rodar local sem secrets)
    return "postgresql://neondb_owner:npg_cs0o6BDZfKVl@ep-twilight-tooth-acz22735-pooler.sa-east-1.aws.neon.tech/neondb?sslmode=require"

NEON_URL = _get_neon_url()

# --------------------------- Funções de DB ---------------------------------
def get_connection():
    return psycopg2.connect(NEON_URL)

def ensure_schema():
    ddl = """
    CREATE SCHEMA IF NOT EXISTS app;

    CREATE TABLE IF NOT EXISTS app.usuarios (
      id           SERIAL PRIMARY KEY,
      username     VARCHAR(100) UNIQUE NOT NULL,
      senha_hash   TEXT NOT NULL,
      role         VARCHAR(20) NOT NULL DEFAULT 'user',
      is_active    BOOLEAN NOT NULL DEFAULT TRUE,
      must_change  BOOLEAN NOT NULL DEFAULT FALSE,
      created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
      updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
      CONSTRAINT usuarios_role_chk CHECK (role IN ('user','admin'))
    );

    CREATE TABLE IF NOT EXISTS app.propostas (
      id               SERIAL PRIMARY KEY,
      cliente          VARCHAR(150) NOT NULL,
      produto          VARCHAR(120) NOT NULL,
      valor            NUMERIC(18,2) NOT NULL DEFAULT 0,
      turmas           INTEGER NOT NULL DEFAULT 1,
      head_responsavel VARCHAR(100) NOT NULL,
      criado_em        TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(ddl)
    conn.close()

def autenticar_usuario(username, password):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT senha_hash FROM app.usuarios WHERE username=%s AND is_active=TRUE;", (username,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return bool(row and bcrypt.checkpw(password.encode("utf-8"), row["senha_hash"].encode("utf-8")))

def registrar_proposta(cliente, produto, valor, turmas, head_responsavel):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.propostas (cliente, produto, valor, turmas, head_responsavel)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (cliente, produto, Decimal(valor), int(turmas), head_responsavel)
        )
    conn.close()

def listar_propostas(limit=50):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, cliente, produto, valor, turmas, head_responsavel, criado_em
        FROM app.propostas
        ORDER BY id DESC
        LIMIT %s;
    """, (limit,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

# ------------------------------ APP ----------------------------------------
st.set_page_config(page_title="Propostas", layout="centered")
ensure_schema()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = None

st.title("📋 Propostas")

if not st.session_state.autenticado:
    st.subheader("Login")
    user = st.text_input("Usuário")
    pwd = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if autenticar_usuario(user, pwd):
            st.session_state.autenticado = True
            st.session_state.usuario = user
            st.success(f"Bem-vindo, {user}!")
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")

else:
    st.sidebar.write(f"👤 Usuário: {st.session_state.usuario}")
    if st.sidebar.button("Sair"):
        st.session_state.autenticado = False
        st.session_state.usuario = None
        st.rerun()

    st.subheader("Nova Proposta")

    c1, c2 = st.columns(2)
    with c1:
        cliente = st.text_input("Cliente *")
        produto = st.text_input("Produto *")
        valor_str = st.text_input("Valor (ex: 1234.56) *")
    with c2:
        turmas = st.number_input("Turmas *", min_value=1, step=1, value=1)
        head_resp = st.text_input("Head Responsável *", value=st.session_state.usuario or "")

    if st.button("Salvar Proposta"):
        if not (cliente.strip() and produto.strip() and valor_str.strip() and head_resp.strip()):
            st.error("Preencha todos os campos obrigatórios (*)")
        else:
            try:
                _ = Decimal(valor_str.replace(",", "."))
                registrar_proposta(cliente.strip(), produto.strip(), valor_str.replace(",", "."), turmas, head_resp.strip())
                st.success("✅ Proposta registrada com sucesso!")
            except InvalidOperation:
                st.error("Valor inválido. Use números (ex: 1234.56).")
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    st.markdown("### Últimas propostas")
    linhas = listar_propostas()
    if linhas:
        for pid, pcl, pprod, pval, ptur, phead, pdt in linhas:
            st.write(f"• **#{pid}** — {pcl} | {pprod} | R$ {pval:.2f} | turmas: {ptur} | head: {phead} | {pdt:%Y-%m-%d %H:%M}")
    else:
        st.info("Nenhuma proposta cadastrada ainda.")
