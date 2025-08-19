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

# --------- Tema (paleta Yassaka – claro) ----------
def inject_theme():
    # Paleta oficial Yassaka
    ROXO    = "#6C42D3"  # primário
    AMARELO = "#FCC52C"  # destaque
    CINZA_E = "#6C6C6B"  # escuro
    CINZA_M = "#747474"  # médio
    CINZA_C = "#7C7B7B"  # claro

    # Base do tema claro
    BG_APP   = "#F7F7F7"
    BG_CARD  = "#FFFFFF"
    TEXTO    = "#1F2937"   # quase preto
    SUBTEXTO = CINZA_M
    BORDA    = "#E5E7EB"
    HOVER    = "#5C36B7"   # roxo mais escuro pro hover

    st.markdown(f"""
    <style>
      /* Fundo geral e tipografia */
      .stApp {{
        background: {BG_APP} !important;
        color: {TEXTO} !important;
      }}

      header[data-testid="stHeader"] {{
        background: rgba(255,255,255,0.8) !important;
        backdrop-filter: blur(6px);
        border-bottom: 1px solid {BORDA};
      }}

      /* Sidebar clara */
      section[data-testid="stSidebar"] {{
        background: #FAFAFA !important;
        border-right: 1px solid {BORDA};
      }}

      /* Cartões e blocos */
      .card {{
        background: {BG_CARD};
        color: {TEXTO};
        padding: 12px 14px;
        border-radius: 12px;
        margin-bottom: 10px;
        border: 1px solid {BORDA};
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }}

      /* Inputs */
      .stTextInput>div>div>input,
      .stNumberInput>div>div>input,
      textarea,
      .stSelectbox>div div[data-baseweb="select"] {{
        background: #FFFFFF !important;
        color: {TEXTO} !important;
        border: 1px solid {BORDA} !important;
        border-radius: 10px !important;
      }}

      /* Botões */
      .stButton>button {{
        background: {ROXO} !important;
        color: #FFFFFF !important;
        border-radius: 10px !important;
        border: 0 !important;
      }}
      .stButton>button:hover {{
        background: {HOVER} !important;
      }}

      /* Textos auxiliares */
      .stMarkdown, .stText, .stCaption {{
        color: {TEXTO} !important;
      }}
      .stCaption {{
        color: {SUBTEXTO} !important;
      }}

      /* Badges QMF (Quente/Morna/Fria) */
      .badge {{
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
        display: inline-block;
      }}
      /* Quente = Amarelo */
      .badge-q {{
        background: rgba(252,197,44,0.25);
        color: {CINZA_E};
        border: 1px solid rgba(252,197,44,0.55);
      }}
      /* Morna = Roxo */
      .badge-m {{
        background: rgba(108,66,211,0.15);
        color: {ROXO};
        border: 1px solid rgba(108,66,211,0.45);
      }}
      /* Fria = Cinza */
      .badge-f {{
        background: rgba(116,116,116,0.18);
        color: {CINZA_E};
        border: 1px solid rgba(116,116,116,0.40);
      }}

      /* Rodapé claro */
      .yassaka-footer {{
        position: fixed; left: 0; right: 0; bottom: 0;
        text-align: center; padding: 8px 12px;
        font-size: 12px; color: {CINZA_M};
        background: #FFFFFF;
        border-top: 1px solid {BORDA};
        z-index: 999;
      }}
    </style>
    """, unsafe_allow_html=True)

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
      qmf              CHAR(1) NOT NULL DEFAULT 'F',
      criado_em        TIMESTAMP NOT NULL DEFAULT NOW(),
      CONSTRAINT propostas_qmf_chk CHECK (qmf IN ('Q','M','F'))
    );
    """
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(ddl)
        # garante coluna/constraint em bases já existentes
        cur.execute("""ALTER TABLE app.propostas
                       ADD COLUMN IF NOT EXISTS qmf CHAR(1) NOT NULL DEFAULT 'F';""")
        cur.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'propostas_qmf_chk'
              AND conrelid = 'app.propostas'::regclass
          ) THEN
            ALTER TABLE app.propostas
              ADD CONSTRAINT propostas_qmf_chk CHECK (qmf IN ('Q','M','F'));
          END IF;
        END$$;
        """)
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
def registrar_proposta(cliente, produto, valor, turmas, head_responsavel, qmf):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.propostas (cliente, produto, valor, turmas, head_responsavel, qmf)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (cliente, produto, Decimal(valor), int(turmas), head_responsavel, qmf)
        )
    conn.close()

def listar_propostas(usuario_logado, role, limit=50):
    conn = get_connection()
    cur = conn.cursor()
    if role == "admin":
        cur.execute("""
            SELECT id, cliente, produto, valor, turmas, head_responsavel, qmf,
                   (criado_em AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS criado_local
            FROM app.propostas
            ORDER BY id DESC
            LIMIT %s;
        """, (limit,))
    else:
        cur.execute("""
            SELECT id, cliente, produto, valor, turmas, head_responsavel, qmf,
                   (criado_em AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS criado_local
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

# ------------------------------ Utils UI -----------------------------------
def qmf_label_and_class(qmf: str):
    q = (qmf or "F").upper()
    if q == "Q":
        return "Quente", "badge-q"  # Amarelo
    if q == "M":
        return "Morna", "badge-m"   # Roxo
    return "Fria", "badge-f"        # Cinza

# ------------------------------ APP UI -------------------------------------
st.set_page_config(page_title="Propostas", layout="centered")
inject_theme()
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
            qmf_map = {"Quente (Q)": "Q", "Morna (M)": "M", "Fria (F)": "F"}
            qmf_sel = st.selectbox("QMF *", list(qmf_map.keys()), index=1)  # padrão Morna
            qmf_code = qmf_map[qmf_sel]

        if st.button("Salvar Proposta"):
            if not (cliente.strip() and produto.strip() and valor_str.strip() and head_resp.strip() and qmf_code):
                st.error("Preencha todos os campos obrigatórios (*)")
            else:
                try:
                    _ = Decimal(valor_str.replace(",", "."))
                    registrar_proposta(
                        cliente.strip(), produto.strip(),
                        valor_str.replace(",", "."), turmas, head_resp.strip(), qmf_code
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
            for pid, pcl, pprod, pval, ptur, phead, pqmf, pdt in linhas:
                label, klass = qmf_label_and_class(pqmf)
                st.markdown(
                    f"""
                    <div class="card">
                      <div><span class="badge {klass}">{label}</span></div>
                      <div><strong>#{pid}</strong> — {pcl} | {pprod} | R$ {pval:.2f} | turmas: {ptur} | head: {phead} | {pdt:%d/%m/%Y %H:%M}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
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

# --------- Rodapé Yassaka ----------
st.markdown('<div class="yassaka-footer">© Yassaka – Todos os direitos reservados</div>', unsafe_allow_html=True)
