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
    return "postgresql://neondb_owner:troque_aqui@ep-xxxx.../neondb?sslmode=require"

NEON_URL = _get_neon_url()

# --------------------------- Conexão / Schema ------------------------------
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

# --------------------------- Autenticação ----------------------------------
def autenticar_usuario(username, password):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        "SELECT username, senha_hash, role FROM app.usuarios WHERE username=%s AND is_active=TRUE;",
        (username,)
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    if row and bcrypt.checkpw(password.encode("utf-8"), row["senha_hash"].encode("utf-8")):
        return {"username": row["username"], "role": row["role"]}
    return None

# --------------------------- Propostas -------------------------------------
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

def listar_propostas(usuario_logado, role, limit=50):
    conn = get_connection()
    cur = conn.cursor()
    if role == "admin":
        cur.execute("""
            SELECT id, cliente, produto, valor, turmas, head_responsavel, criado_em
            FROM app.propostas
            ORDER BY id DESC
            LIMIT %s;
        """, (limit,))
    else:
        cur.execute("""
            SELECT id, cliente, produto, valor, turmas, head_responsavel, criado_em
            FROM app.propostas
            WHERE head_responsavel = %s
            ORDER BY id DESC
            LIMIT %s;
        """, (usuario_logado, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

# --------------------------- Admin: Usuários --------------------------------
def criar_usuario(username, senha, role):
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO app.usuarios (username, senha_hash, role, is_active, must_change)
            VALUES (%s, %s, %s, TRUE, FALSE)
            ON CONFLICT (username) DO NOTHING;
        """, (username, senha_hash, role))
    conn.close()

def set_user_active(username, active: bool):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("UPDATE app.usuarios SET is_active=%s WHERE username=%s;", (active, username))
    conn.close()

def resetar_senha(username, nova_senha):
    senha_hash = bcrypt.hashpw(nova_senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("UPDATE app.usuarios SET senha_hash=%s, must_change=FALSE WHERE username=%s;",
                    (senha_hash, username))
    conn.close()

def renomear_usuario(antigo, novo):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("UPDATE app.usuarios SET username=%s WHERE username=%s;", (novo, antigo))
    conn.close()

def listar_usuarios():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""SELECT id, username, role, is_active FROM app.usuarios ORDER BY username;""")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

# ------------------------------ APP UI -------------------------------------
st.set_page_config(page_title="Propostas", layout="centered")
ensure_schema()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "role" not in st.session_state:
    st.session_state.role = "user"

st.title("📋 Propostas")

# --------- Login ---------
if not st.session_state.autenticado:
    st.subheader("Login")
    user = st.text_input("Usuário")
    pwd = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        auth = autenticar_usuario(user, pwd)
        if auth:
            st.session_state.autenticado = True
            st.session_state.usuario = auth["username"]
            st.session_state.role = auth["role"]
            st.success(f"Bem-vindo, {auth['username']}!")
            st.rerun()
        else:
            st.error("Usuário ou senha inválidos")

# --------- Área autenticada ---------
else:
    st.sidebar.write(f"👤 Usuário: {st.session_state.usuario} ({st.session_state.role})")

    abas = ["Propostas"]
    if st.session_state.role == "admin":
        abas.append("Admin: Usuários")
    aba = st.sidebar.radio("Navegação", abas)

    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()

    # ----- Aba Propostas -----
    if aba == "Propostas":
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
                    registrar_proposta(
                        cliente.strip(), produto.strip(),
                        valor_str.replace(",", "."), turmas, head_resp.strip()
                    )
                    st.success("✅ Proposta registrada com sucesso!")
                except InvalidOperation:
                    st.error("Valor inválido. Use números (ex: 1234.56).")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

        st.markdown("### Últimas propostas")

        # listar com filtro (admin vê tudo; user vê só as suas)
        linhas = listar_propostas(
            st.session_state.usuario,
            st.session_state.get("role", "user"),
        )

        # badge informativo
        if st.session_state.get("role") == "admin":
            st.caption("🟢 Exibindo **todas** as propostas (admin).")
        else:
            st.caption(f"🟡 Exibindo **apenas suas** propostas: {st.session_state.usuario}.")

        if linhas:
            for pid, pcl, pprod, pval, ptur, phead, pdt in linhas:
                st.write(f"• **#{pid}** — {pcl} | {pprod} | R$ {pval:.2f} | turmas: {ptur} | head: {phead} | {pdt:%Y-%m-%d %H:%M}")
        else:
            st.info("Nenhuma proposta cadastrada ainda.")

    # ----- Aba Admin: Usuários -----
    elif aba == "Admin: Usuários":
        st.subheader("👑 Administração de Usuários")

        st.markdown("#### Criar novo usuário")
        c1, c2, c3 = st.columns(3)
        with c1:
            nu_user = st.text_input("Username (ex: Nome.Sobrenome)")
        with c2:
            nu_role = st.selectbox("Role", ["user", "admin"])
        with c3:
            nu_pass = st.text_input("Senha inicial", type="password")

        if st.button("Criar usuário"):
            if nu_user.strip() and nu_pass.strip():
                try:
                    criar_usuario(nu_user.strip(), nu_pass.strip(), nu_role)
                    st.success(f"Usuário {nu_user} criado.")
                except Exception as e:
                    st.error(f"Erro ao criar: {e}")
            else:
                st.error("Preencha username e senha.")

        st.markdown("---")
        st.markdown("#### Ações rápidas")

        c1, c2, c3 = st.columns(3)
        with c1:
            tgt_user1 = st.text_input("Ativar/Desativar - usuário")
            ativar = st.toggle("Ativar", value=True, key="ativar_user")
            if st.button("Aplicar ativação/desativação"):
                if tgt_user1.strip():
                    try:
                        set_user_active(tgt_user1.strip(), ativar)
                        st.success("Status atualizado.")
                    except Exception as e:
                        st.error(f"Erro: {e}")
                else:
                    st.error("Informe o usuário.")

        with c2:
            tgt_user2 = st.text_input("Resetar senha - usuário")
            nova_senha = st.text_input("Nova senha", type="password")
            if st.button("Aplicar reset de senha"):
                if tgt_user2.strip() and nova_senha.strip():
                    try:
                        resetar_senha(tgt_user2.strip(), nova_senha.strip())
                        st.success("Senha atualizada.")
                    except Exception as e:
                        st.error(f"Erro: {e}")
                else:
                    st.error("Informe usuário e nova senha.")

        with c3:
            antigo = st.text_input("Renomear - atual")
            novo = st.text_input("Renomear - novo")
            if st.button("Aplicar renome"):
                if antigo.strip() and novo.strip():
                    try:
                        renomear_usuario(antigo.strip(), novo.strip())
                        st.success("Username atualizado.")
                    except Exception as e:
                        st.error(f"Erro: {e}")
                else:
                    st.error("Informe os dois nomes.")

        st.markdown("---")
        st.markdown("#### Usuários cadastrados")
        try:
            rows = listar_usuarios()
            if rows:
                for uid, uname, urole, active in rows:
                    st.write(f"• #{uid} — **{uname}** — role: {urole} — ativo: {active}")
            else:
                st.info("Nenhum usuário encontrado.")
        except Exception as e:
            st.error(f"Erro ao listar: {e}")
