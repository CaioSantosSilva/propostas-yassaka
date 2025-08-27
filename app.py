# app.py — Yassaka | Propostas + (novo) Painel Educadores | Streamlit + Neon
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

import bcrypt
import psycopg2
import psycopg2.extras
import streamlit as st

# ---------------------------------------------------------------------------
# Config: pega a URL do Neon dos Secrets ou do ambiente
# ---------------------------------------------------------------------------
def _get_neon_url():
    try:
        if "NEON_URL" in st.secrets:
            return st.secrets["NEON_URL"]
    except Exception:
        pass
    if os.getenv("NEON_URL"):
        return os.getenv("NEON_URL")
    return "postgresql://neondb_owner:troque_aqui@ep-xxxx.../neondb?sslmode=require"

NEON_URL = _get_neon_url()

def _validate_url(url: str):
    assert url, "NEON_URL está vazio / não carregou."
    parsed = urlparse(url)
    assert parsed.scheme in {"postgresql", "postgres"}, "Scheme inválido (use postgresql://)."
    assert parsed.hostname, "Hostname ausente na URL."
    return parsed

# ---------------------------------------------------------------------------
# Tema (paleta Yassaka – claro)
# ---------------------------------------------------------------------------
def inject_theme():
    ROXO = "#6C42D3"
    AMARELO = "#FCC52C"
    CINZA_M = "#747474"

    BG_APP = "#F4F2FB"
    BG_CARD = "#FFFFFF"
    TEXTO = "#1F1F1F"

    st.markdown(
        f"""
    <style>
      .stApp {{
        background: linear-gradient(180deg, {BG_APP} 0%, #ffffff 100%) !important;
        color: {TEXTO} !important;
      }}

      /* cabeçalho */
      header[data-testid="stHeader"] {{
        background: {ROXO} !important;
        color: white !important;
        border-bottom: 3px solid {AMARELO};
      }}

      /* sidebar */
      section[data-testid="stSidebar"] {{
        background: #FAFAFA !important;
        border-right: 2px solid {ROXO};
      }}

      /* títulos */
      h1, h2, h3, h4, h5, h6 {{
        color: {ROXO} !important;
        font-weight: 700 !important;
      }}
      h1::after, h2::after {{
        content: '';
        display: block;
        width: 60px;
        border-bottom: 3px solid {AMARELO};
        margin-top: 4px;
      }}

      /* cards */
      .card {{
        background: {BG_CARD};
        color: {TEXTO};
        padding: 14px 16px;
        border-radius: 14px;
        margin-bottom: 14px;
        border: 1px solid {ROXO};
        box-shadow: 0 2px 6px rgba(108,66,211,0.15);
      }}

      /* inputs – base */
      .stTextInput input,
      .stPassword input,
      .stNumberInput input,
      .stDateInput input,
      textarea,
      .stSelectbox [data-baseweb="select"] input {{
        border: 2px solid #ddd !important;
        border-radius: 10px !important;
        padding: 6px !important;
        box-shadow: none !important;
        outline: none !important;
        background: #FFFFFF !important;
        color: #1F1F1F !important;
      }}

      /* foco */
      .stTextInput input:focus,
      .stPassword input:focus,
      .stNumberInput input:focus,
      .stDateInput input:focus,
      textarea:focus {{
        border: 2px solid {ROXO} !important;
        box-shadow: 0 0 4px {AMARELO} !important;
        outline: none !important;
      }}

      /* invalid */
      .stTextInput input:invalid,
      .stPassword input:invalid,
      .stNumberInput input:invalid,
      .stDateInput input:invalid,
      textarea:invalid,
      .stSelectbox [data-baseweb="select"] input:invalid,
      .stTextInput input[aria-invalid="true"],
      .stPassword input[aria-invalid="true"],
      .stNumberInput input[aria-invalid="true"],
      .stDateInput input[aria-invalid="true"] {{
        border: 2px solid #ddd !important;
        box-shadow: none !important;
        outline: none !important;
      }}

      /* focus visible */
      .stTextInput input:focus-visible,
      .stPassword input:focus-visible,
      .stNumberInput input:focus-visible,
      .stDateInput input:focus-visible,
      textarea:focus-visible {{
        outline: none !important;
        box-shadow: 0 0 4px {AMARELO} !important;
      }}

      /* botões */
      .stButton>button {{
        background: {ROXO} !important;
        color: white !important;
        border-radius: 10px !important;
        border: none !important;
        font-weight: 600 !important;
        transition: all 0.3s ease-in-out;
      }}
      .stButton>button:hover {{
        background: {AMARELO} !important;
        color: {ROXO} !important;
        transform: translateY(-2px);
      }}

      /* badges (usadas no histórico) */
      .badge {{
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 700;
        display: inline-block;
      }}
      .badge-q {{ background: {AMARELO}; color: {ROXO}; }}
      .badge-m {{ background: {ROXO}; color: white; }}
      .badge-f {{ background: {CINZA_M}; color: white; }}

      /* rodapé */
      .yassaka-footer {{
        position: fixed;
        left: 0; right: 0; bottom: 0;
        text-align: center;
        padding: 8px 12px;
        font-size: 12px;
        color: white;
        background: {ROXO};
        border-top: 3px solid {AMARELO};
        z-index: 999;
      }}
    </style>
    """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Conexão / Schema
# ---------------------------------------------------------------------------
def get_connection():
    _validate_url(NEON_URL)
    return psycopg2.connect(NEON_URL)

def ensure_schema():
    conn = get_connection()
    with conn, conn.cursor() as cur:
        # schema base
        cur.execute("CREATE SCHEMA IF NOT EXISTS app;")

        # ------------------ usuários (mantido) ------------------
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app.usuarios (
              id           SERIAL PRIMARY KEY,
              username     VARCHAR(100) UNIQUE NOT NULL,
              senha_hash   TEXT NOT NULL,
              role         VARCHAR(20) NOT NULL DEFAULT 'user',
              is_active    BOOLEAN NOT NULL DEFAULT TRUE,
              must_change  BOOLEAN NOT NULL DEFAULT FALSE,
              created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
              updated_at   TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute("ALTER TABLE app.usuarios DROP CONSTRAINT IF EXISTS usuarios_role_chk;")
        cur.execute(
            """ALTER TABLE app.usuarios
               ADD CONSTRAINT usuarios_role_chk CHECK (role IN ('user','admin','educador'));"""
        )

        # ------------------ propostas (mantido) ------------------
        cur.execute(
            """
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
        )
        cur.execute(
            """ALTER TABLE app.propostas
               ADD COLUMN IF NOT EXISTS qmf CHAR(1) NOT NULL DEFAULT 'F';"""
        )

        # ------------------ NOVAS TABELAS DO PAINEL ------------------
        # Reuniões efetivadas
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app.reunioes_efetivadas (
              id              SERIAL PRIMARY KEY,
              owner_username  VARCHAR(100) NOT NULL,
              data            DATE NOT NULL,
              cliente         VARCHAR(200) NOT NULL,
              responsavel     VARCHAR(150) NOT NULL,
              criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
        # Atestados
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app.atestados_educadores (
              id                    SERIAL PRIMARY KEY,
              owner_username        VARCHAR(100) NOT NULL,
              mes                   DATE NOT NULL,          -- guardamos como dia 1 do mês
              cliente               VARCHAR(200) NOT NULL,
              projeto_finalizado    TEXT NOT NULL,
              atestado_conquistado  TEXT NOT NULL,
              criado_em             TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
    conn.close()

# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------
def autenticar_usuario(username, password):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        "SELECT username, senha_hash, role, is_active FROM app.usuarios WHERE username=%s;",
        (username,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row or not row["is_active"]:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row["senha_hash"].encode("utf-8")):
        return {"username": row["username"], "role": row["role"]}
    return None

# ---------------------------------------------------------------------------
# Propostas (mantido)
# ---------------------------------------------------------------------------
def _parse_valor_brl(txt: str) -> Decimal | None:
    if not txt:
        return None
    clean = txt.strip().replace("R$", "").replace(" ", "")
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    try:
        return Decimal(clean).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None

def registrar_proposta(cliente, produto, valor, turmas, head_responsavel, qmf):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.propostas (cliente, produto, valor, turmas, head_responsavel, qmf)
            VALUES (%s, %s, %s, %s, %s, %s);
            """,
            (cliente, produto, Decimal(valor), int(turmas), head_responsavel, qmf),
        )
    conn.close()

def listar_propostas(usuario_logado, role, limit=50):
    conn = get_connection()
    cur = conn.cursor()
    if role == "admin":
        cur.execute(
            """
            SELECT id, cliente, produto, valor, turmas, head_responsavel, qmf,
                   criado_em AT TIME ZONE 'America/Sao_Paulo' AS criado_local
            FROM app.propostas
            ORDER BY id DESC
            LIMIT %s;
        """,
            (limit,),
        )
    else:
        cur.execute(
            """
            SELECT id, cliente, produto, valor, turmas, head_responsavel, qmf,
                   criado_em AT TIME ZONE 'America/Sao_Paulo' AS criado_local
            FROM app.propostas
            WHERE head_responsavel = %s
            ORDER BY id DESC
            LIMIT %s;
        """,
            (usuario_logado, limit),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# ---------------------------------------------------------------------------
# PAINEL EDUCADORES — operações
# ---------------------------------------------------------------------------
def inserir_reuniao(owner_username: str, data_reuniao: date, cliente: str, responsavel: str):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.reunioes_efetivadas (owner_username, data, cliente, responsavel)
            VALUES (%s, %s, %s, %s);
            """,
            (owner_username, data_reuniao, cliente, responsavel),
        )
    conn.close()

def listar_reunioes(owner_username: str, limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, data, cliente, responsavel,
               criado_em AT TIME ZONE 'America/Sao_Paulo' AS criado_local
        FROM app.reunioes_efetivadas
        WHERE owner_username=%s
        ORDER BY id DESC
        LIMIT %s;
        """,
        (owner_username, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def inserir_atestado(owner_username: str, mes: date, cliente: str,
                     projeto_finalizado: str, atestado_conquistado: str):
    mes_norm = date(mes.year, mes.month, 1)  # primeiro dia do mês
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.atestados_educadores
              (owner_username, mes, cliente, projeto_finalizado, atestado_conquistado)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (owner_username, mes_norm, cliente, projeto_finalizado, atestado_conquistado),
        )
    conn.close()

def listar_atestados(owner_username: str, limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, mes, cliente, projeto_finalizado, atestado_conquistado,
               criado_em AT TIME ZONE 'America/Sao_Paulo' AS criado_local
        FROM app.atestados_educadores
        WHERE owner_username=%s
        ORDER BY id DESC
        LIMIT %s;
        """,
        (owner_username, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------
def format_brl(d: Decimal | None) -> str:
    if d is None:
        return "-"
    s = f"{d:.2f}".replace(".", ",")
    return f"R$ {s}"

def qmf_label_and_class(qmf: str):
    q = (qmf or "F").upper()
    if q == "Q": return "Quente", "badge-q"
    if q == "M": return "Morna", "badge-m"
    return "Fria", "badge-f"

# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------
def page_propostas():
    st.subheader("Nova Proposta")

    c1, c2 = st.columns(2)
    with c1:
        cliente = st.text_input("Cliente *")
        produto = st.text_input("Produto *")
        valor_str = st.text_input("Valor (ex: 1234,56) *")
    with c2:
        turmas = st.number_input("Turmas *", min_value=1, step=1, value=1)
        head_resp = st.text_input("Head Responsável *", value=st.session_state.usuario or "")
        qmf_map = {"Quente (Q)": "Q", "Morna (M)": "M", "Fria (F)": "F"}
        qmf_sel = st.selectbox("QMF *", list(qmf_map.keys()), index=1)
        qmf_code = qmf_map[qmf_sel]

    if st.button("Salvar Proposta"):
        if not (cliente.strip() and produto.strip() and valor_str.strip() and head_resp.strip() and qmf_code):
            st.error("Preencha todos os campos obrigatórios (*)")
        else:
            try:
                dec = _parse_valor_brl(valor_str)
                if dec is None:
                    raise InvalidOperation()
                registrar_proposta(
                    cliente.strip(), produto.strip(), str(dec), turmas, head_resp.strip(), qmf_code
                )
                st.success("✅ Proposta registrada com sucesso!")
            except InvalidOperation:
                st.error("Valor inválido. Use números (ex: 1234,56).")
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")

    st.markdown("### Últimas propostas")
    linhas = listar_propostas(st.session_state.usuario, st.session_state.get("role", "user"))

    if st.session_state.get("role") == "admin":
        st.caption("🟢 Exibindo **todas** as propostas (admin).")
    else:
        st.caption(f"🟡 Exibindo **apenas suas** propostas: {st.session_state.usuario}.")

    if linhas:
        for pid, pcl, pprod, pval, ptur, phead, pqmf, pdt in linhas:
            label, klass = qmf_label_and_class(pqmf)
            try:
                pval_dec = Decimal(pval).quantize(Decimal("0.01"))
            except Exception:
                pval_dec = None
            dt_fmt = pdt.strftime("%d/%m/%Y %H:%M") if hasattr(pdt, "strftime") else str(pdt)
            st.markdown(
                f"""
                <div class="card">
                  <div><span class="badge {klass}">{label}</span></div>
                  <div><strong>#{pid}</strong> — {pcl} | {pprod} | {format_brl(pval_dec)} | turmas: {ptur} | head: {phead} | {dt_fmt}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Nenhuma proposta cadastrada ainda.")

def page_educador():
    """Novo Painel Educadores – conforme layout solicitado."""
    st.subheader("Painel Educadores")
    st.caption(f"Logado como **{st.session_state.usuario}**")

    colA, colB = st.columns(2)

    # ------------------------- Reunião Efetivada -------------------------
    with colA:
        st.markdown("## Reunião Efetivada")
        with st.form("form_reuniao"):
            data_reuniao = st.date_input("Data:", value=date.today(), format="DD/MM/YYYY")
            cliente_r = st.text_input("Cliente:")
            responsavel_r = st.text_input("Responsável:", value=st.session_state.usuario)
            salvar_reuniao = st.form_submit_button("Adicionar Reunião")
        if salvar_reuniao:
            if not (cliente_r.strip() and responsavel_r.strip()):
                st.error("Preencha Cliente e Responsável.")
            else:
                try:
                    inserir_reuniao(st.session_state.usuario, data_reuniao, cliente_r.strip(), responsavel_r.strip())
                    st.success("Reunião registrada!")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

        # lista
        st.markdown("#### Últimas reuniões")
        reunioes = listar_reunioes(st.session_state.usuario, limit=10)
        if not reunioes:
            st.info("Sem reuniões registradas ainda.")
        else:
            for rid, rdata, rcli, rresp, rcriado in reunioes:
                dt = rdata.strftime("%d/%m/%Y") if isinstance(rdata, (date, datetime)) else str(rdata)
                st.markdown(
                    f"""
                    <div class="card">
                      <div><strong>Data:</strong> {dt}</div>
                      <div><strong>Cliente:</strong> {rcli}</div>
                      <div><strong>Responsável:</strong> {rresp}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    # ------------------------------ Atestados -----------------------------
    with colB:
        st.markdown("## Atestados")
        with st.form("form_atestado"):
            mes_a = st.date_input("Mês:", value=date.today().replace(day=1), format="DD/MM/YYYY")
            cliente_a = st.text_input("Cliente:")
            projeto_finalizado = st.text_input("Projeto Finalizado:")
            atestado_conquistado = st.text_input("Atestado Conquistado:")
            salvar_atestado = st.form_submit_button("Adicionar Atestado")

        if salvar_atestado:
            if not (cliente_a.strip() and projeto_finalizado.strip() and atestado_conquistado.strip()):
                st.error("Preencha Cliente, Projeto Finalizado e Atestado Conquistado.")
            else:
                try:
                    inserir_atestado(
                        st.session_state.usuario,
                        mes_a,
                        cliente_a.strip(),
                        projeto_finalizado.strip(),
                        atestado_conquistado.strip(),
                    )
                    st.success("Atestado registrado!")
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")

        # lista
        st.markdown("#### Últimos atestados")
        atestados = listar_atestados(st.session_state.usuario, limit=10)
        if not atestados:
            st.info("Sem atestados registrados ainda.")
        else:
            for aid, ames, acli, aproj, aatest, acriado in atestados:
                mes_fmt = ames.strftime("%m/%Y") if isinstance(ames, (date, datetime)) else str(ames)
                st.markdown(
                    f"""
                    <div class="card">
                      <div><strong>Mês:</strong> {mes_fmt}</div>
                      <div><strong>Cliente:</strong> {acli}</div>
                      <div><strong>Projeto Finalizado:</strong> {aproj}</div>
                      <div><strong>Atestado Conquistado:</strong> {aatest}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

# ---------------------------------------------------------------------------
# Admin: Usuários
# ---------------------------------------------------------------------------
def criar_usuario(username, senha, role):
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app.usuarios (username, senha_hash, role, is_active, must_change)
            VALUES (%s, %s, %s, TRUE, FALSE)
            ON CONFLICT (username) DO NOTHING;
        """,
            (username, senha_hash, role),
        )
    conn.close()

def listar_usuarios():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, is_active FROM app.usuarios ORDER BY username;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

# ---------------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Yassaka", layout="centered")
inject_theme()
ensure_schema()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "role" not in st.session_state:
    st.session_state.role = "user"

# Título (login ou será definido pela aba)
if not st.session_state.autenticado:
    st.title("Yassaka")

# Login
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

# Área autenticada
else:
    role = st.session_state.role
    st.sidebar.write(f"👤 Usuário: {st.session_state.usuario} ({role})")

    if role == "educador":
        # Educador: só a tela dele
        st.title("Painel Educadores")
        if st.sidebar.button("Sair"):
            st.session_state.clear()
            st.rerun()
        page_educador()

    else:
        # Admin/User: abas
        abas = ["Propostas"]
        if role == "admin":
            abas.insert(1, "Educadores")     # admin também vê a tela de educadores
            abas.append("Admin: Usuários")

        aba = st.sidebar.radio("Navegação", abas)

        if st.sidebar.button("Sair"):
            st.session_state.clear()
            st.rerun()

        # título dinâmico por aba
        if aba == "Propostas":
            st.title("Propostas")
            page_propostas()

        elif aba == "Educadores":
            st.title("Painel Educadores")
            page_educador()

        elif aba == "Admin: Usuários":
            st.title("Admin: Usuários")
            st.subheader("👑 Administração de Usuários")
            st.markdown("#### Criar novo usuário")
            c1, c2, c3 = st.columns(3)
            with c1:
                nu_user = st.text_input("Username (ex: Nome.Sobrenome)")
            with c2:
                nu_role = st.selectbox("Role", ["user", "admin", "educador"])
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

# Rodapé
st.markdown(
    '<div class="yassaka-footer">© Yassaka – Todos os direitos reservados</div>',
    unsafe_allow_html=True,
)
