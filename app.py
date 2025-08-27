# app.py — Yassaka | Propostas + Painel Educadores | Streamlit + Neon
import os
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlparse

import bcrypt
import psycopg2
import psycopg2.extras
import streamlit as st


# --------- Config: pega a URL do Neon dos Secrets ou do ambiente ----------
def _get_neon_url():
    try:
        if "NEON_URL" in st.secrets:
            return st.secrets["NEON_URL"]
    except Exception:
        pass
    if os.getenv("NEON_URL"):
        return os.getenv("NEON_URL")
    # fallback apenas para dev local
    return "postgresql://neondb_owner:troque_aqui@ep-xxxx.../neondb?sslmode=require"


NEON_URL = _get_neon_url()


def _validate_url(url: str):
    assert url, "NEON_URL está vazio / não carregou."
    parsed = urlparse(url)
    assert parsed.scheme in {"postgresql", "postgres"}, "Scheme inválido (use postgresql://)."
    assert parsed.hostname, "Hostname ausente na URL."
    return parsed


# --------- Tema (paleta Yassaka – claro) ----------
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

      /* badges */
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


# --------------------------- Conexão / Schema ------------------------------
def get_connection():
    _validate_url(NEON_URL)
    return psycopg2.connect(NEON_URL)


def ensure_schema():
    conn = get_connection()
    with conn, conn.cursor() as cur:
        # schema base
        cur.execute("CREATE SCHEMA IF NOT EXISTS app;")

        # usuários
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
        # garante a constraint com 'educador' (idempotente)
        cur.execute("ALTER TABLE app.usuarios DROP CONSTRAINT IF EXISTS usuarios_role_chk;")
        cur.execute(
            """ALTER TABLE app.usuarios
               ADD CONSTRAINT usuarios_role_chk CHECK (role IN ('user','admin','educador'));"""
        )

        # propostas
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
        cur.execute(
            """
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
        """
        )
        cur.execute(
            """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='app' AND table_name='propostas'
              AND column_name='criado_em'
              AND data_type='timestamp without time zone'
          ) THEN
            ALTER TABLE app.propostas
              ALTER COLUMN criado_em TYPE timestamptz
              USING (criado_em AT TIME ZONE 'UTC');
            ALTER TABLE app.propostas
              ALTER COLUMN criado_em SET DEFAULT now();
          END IF;
        END$$;
        """
        )

        # educadores — base + relax NOT NULL
        cur.execute(
            """
        CREATE TABLE IF NOT EXISTS app.educadores (
          id                   SERIAL PRIMARY KEY,
          owner_username       VARCHAR(100) NOT NULL,
          nome                 VARCHAR(150),
          email                VARCHAR(150) UNIQUE,
          telefone             VARCHAR(40),
          area                 VARCHAR(120),
          especialidades       TEXT,
          disponibilidade      TEXT,
          reunioes_efetivadas  INTEGER NOT NULL DEFAULT 0,
          projetos             TEXT,
          atestados            TEXT,
          recomendacoes        TEXT,
          ativo                BOOLEAN NOT NULL DEFAULT TRUE,
          criado_em            TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        )
        # remover NOT NULL de nome/email se houver (idempotente)
        cur.execute(
            """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='app' AND table_name='educadores'
              AND column_name='nome' AND is_nullable='NO'
          ) THEN
            ALTER TABLE app.educadores ALTER COLUMN nome DROP NOT NULL;
          END IF;
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='app' AND table_name='educadores'
              AND column_name='email' AND is_nullable='NO'
          ) THEN
            ALTER TABLE app.educadores ALTER COLUMN email DROP NOT NULL;
          END IF;
        END$$;
        """
        )

        # novos campos do painel
        cur.execute(
            """ALTER TABLE app.educadores
               ADD COLUMN IF NOT EXISTS empresa_reuniao VARCHAR(150);"""
        )
        cur.execute("""ALTER TABLE app.educadores ADD COLUMN IF NOT EXISTS data_reuniao DATE;""")
        cur.execute("""ALTER TABLE app.educadores ADD COLUMN IF NOT EXISTS contato VARCHAR(150);""")
        cur.execute(
            """ALTER TABLE app.educadores
               ADD COLUMN IF NOT EXISTS telefone_contato VARCHAR(30);"""
        )
        cur.execute(
            """ALTER TABLE app.educadores
               ADD COLUMN IF NOT EXISTS valor_projeto NUMERIC(18,2);"""
        )
        cur.execute("""ALTER TABLE app.educadores ADD COLUMN IF NOT EXISTS uf CHAR(2);""")
        cur.execute("""ALTER TABLE app.educadores ADD COLUMN IF NOT EXISTS educador VARCHAR(150);""")
    conn.close()


# --------------------------- Autenticação ----------------------------------
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


# --------------------------- Propostas -------------------------------------
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


# --------------------------- EDUCADORES (CRUD focado) ----------------------
def obter_educador_por_owner(owner_username: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute(
        """
        SELECT *
        FROM app.educadores
        WHERE owner_username=%s
        ORDER BY id DESC
        LIMIT 1;
    """,
        (owner_username,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def _parse_valor_brl(txt: str) -> Decimal | None:
    if not txt:
        return None
    # aceita "1.234,56" ou "1234,56" ou "1234.56"
    clean = txt.strip().replace("R$", "").replace(" ", "")
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    try:
        return Decimal(clean).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


_BR_PHONE_RE = re.compile(r"^[0-9()\-\s+]{8,20}$")


def upsert_educador(
    owner_username: str,
    empresa_reuniao: str,
    data_reuniao: date | None,
    contato: str,
    telefone_contato: str,
    projetos: str,
    valor_projeto_str: str,
    atestados: str,
    uf: str,
    educador: str,
):
    valor_projeto = _parse_valor_brl(valor_projeto_str)
    if valor_projeto_str and valor_projeto is None:
        raise ValueError("Valor do projeto inválido. Use formato 1234,56.")

    if telefone_contato and not _BR_PHONE_RE.match(telefone_contato.strip()):
        raise ValueError("Telefone inválido. Ex: (11) 91234-5678")

    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM app.educadores WHERE owner_username=%s LIMIT 1;", (owner_username,))
        found = cur.fetchone()
        if found:
            cur.execute(
                """
                UPDATE app.educadores
                   SET empresa_reuniao=%s,
                       data_reuniao=%s,
                       contato=%s,
                       telefone_contato=%s,
                       projetos=%s,
                       valor_projeto=%s,
                       atestados=%s,
                       uf=%s,
                       educador=%s
                 WHERE owner_username=%s;
            """,
                (
                    empresa_reuniao or None,
                    data_reuniao,
                    contato or None,
                    (telefone_contato or "").strip() or None,
                    projetos or None,
                    valor_projeto,
                    atestados or None,
                    (uf or "").upper()[:2] or None,
                    educador or owner_username,
                    owner_username,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO app.educadores
                  (owner_username, empresa_reuniao, data_reuniao, contato, telefone_contato,
                   projetos, valor_projeto, atestados, uf, educador)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
                (
                    owner_username,
                    empresa_reuniao or None,
                    data_reuniao,
                    contato or None,
                    (telefone_contato or "").strip() or None,
                    projetos or None,
                    valor_projeto,
                    atestados or None,
                    (uf or "").upper()[:2] or None,
                    educador or owner_username,
                ),
            )
    conn.close()


# ------------------------------ Utils UI -----------------------------------
def qmf_label_and_class(qmf: str):
    q = (qmf or "F").upper()
    if q == "Q":
        return "Quente", "badge-q"
    if q == "M":
        return "Morna", "badge-m"
    return "Fria", "badge-f"


def format_brl(d: Decimal | None) -> str:
    if d is None:
        return "-"
    s = f"{d:.2f}".replace(".", ",")
    return f"R$ {s}"


# ------------------------------ Páginas -------------------------------------
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
        qmf_sel = st.selectbox("QMF *", list(qmf_map.keys()), index=1)  # padrão Morna
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
                    cliente.strip(),
                    produto.strip(),
                    str(dec),
                    turmas,
                    head_resp.strip(),
                    qmf_code,
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


def _dict_row(row: psycopg2.extras.DictRow | None) -> dict:
    """Converte DictRow para dict para usarmos .get com segurança."""
    return dict(row) if row is not None else {}


def obter_educador_resumo(owner_username: str):
    """Renderiza o cartão-resumo do educador (se existir)."""
    row = obter_educador_por_owner(owner_username)
    if not row:
        return
    d = _dict_row(row)
    data_fmt = d.get("data_reuniao").strftime("%d/%m/%Y") if d.get("data_reuniao") else "-"
    valor_fmt = format_brl(d.get("valor_projeto"))
    st.markdown(
        f"""
        <div class="card">
          <div><strong>Educador:</strong> {d.get('educador') or owner_username}</div>
          <div><strong>Empresa:</strong> {d.get('empresa_reuniao') or '-'}</div>
          <div><strong>Data da reunião:</strong> {data_fmt}</div>
          <div><strong>Contato:</strong> {d.get('contato') or '-'}</div>
          <div><strong>Telefone:</strong> {d.get('telefone_contato') or '-'}</div>
          <div><strong>UF:</strong> {d.get('uf') or '-'}</div>
          <div><strong>Projetos:</strong> {(d.get('projetos') or '-').replace('\n','<br>')}</div>
          <div><strong>Valor do projeto:</strong> {valor_fmt}</div>
          <div><strong>Atestados:</strong> {(d.get('atestados') or '-').replace('\n','<br>')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_educador_meu_painel():
    """Painel pessoal do Educador com os campos solicitados."""
    st.subheader("Painel Educadores")
    st.caption(f"Logado como **{st.session_state.usuario}**")

    ficha = obter_educador_por_owner(st.session_state.usuario)
    d = _dict_row(ficha)

    st.markdown("### 📝 Registro")
    with st.form("form_educador"):
        col1, col2 = st.columns(2)
        with col1:
            empresa_reuniao = st.text_input("Reunião efetiva (empresa)", value=d.get("empresa_reuniao", ""))
            data_value = d.get("data_reuniao") or date.today()
            data_reuniao = st.date_input("Data da reunião", value=data_value, format="DD/MM/YYYY")
            contato = st.text_input("Contato da empresa (nome)", value=d.get("contato", ""))
            telefone_contato = st.text_input(
                "Telefone do contato (BR)",
                value=d.get("telefone_contato", ""),
                placeholder="(11) 91234-5678",
            )
        with col2:
            projetos = st.text_area("Projetos", value=d.get("projetos", ""))
            valor_projeto_str = st.text_input(
                "Valor do projeto",
                value=(format_brl(d.get("valor_projeto")) if d.get("valor_projeto") is not None else ""),
                placeholder="Ex: 1.234,56 ou 1234,56",
            )
            atestados = st.text_area("Atestados", value=d.get("atestados", ""))
            uf = st.text_input("UF", max_chars=2, value=d.get("uf", "") or "")
        _ = st.text_input("Educador", value=st.session_state.usuario, disabled=True)
        salvar = st.form_submit_button("Salvar")

    if salvar:
        try:
            upsert_educador(
                owner_username=st.session_state.usuario,
                empresa_reuniao=empresa_reuniao.strip(),
                data_reuniao=data_reuniao,
                contato=contato.strip(),
                telefone_contato=telefone_contato.strip(),
                projetos=projetos.strip(),
                valor_projeto_str=valor_projeto_str.strip(),
                atestados=atestados.strip(),
                uf=(uf or "").strip().upper()[:2],
                educador=st.session_state.usuario,
            )
            st.success("Registro salvo/atualizado!")
            st.rerun()
        except ValueError as ve:
            st.error(str(ve))
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

    # Cartão-resumo
    obter_educador_resumo(st.session_state.usuario)


# --------------------------- Admin: Usuários (helpers banco) ---------------
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


def set_user_active(username, active: bool):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("UPDATE app.usuarios SET is_active=%s WHERE username=%s;", (active, username))
    conn.close()


def resetar_senha(username, nova_senha):
    senha_hash = bcrypt.hashpw(nova_senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE app.usuarios SET senha_hash=%s, must_change=FALSE WHERE username=%s;",
            (senha_hash, username),
        )
    conn.close()


def renomear_usuario(antigo, novo):
    conn = get_connection()
    with conn, conn.cursor() as cur:
        cur.execute("UPDATE app.usuarios SET username=%s WHERE username=%s;", (novo, antigo))
    conn.close()


def listar_usuarios():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, is_active FROM app.usuarios ORDER BY username;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


# ------------------------------ APP ----------------------------------------
st.set_page_config(page_title="Yassaka", layout="centered")
inject_theme()
ensure_schema()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "role" not in st.session_state:
    st.session_state.role = "user"

# --------- Título por contexto ---------
if not st.session_state.autenticado:
    st.title("Yassaka")
else:
    if st.session_state.role == "educador":
        st.title("Painel Educadores")
    else:
        st.title("Propostas")

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
    role = st.session_state.role
    st.sidebar.write(f"👤 Usuário: {st.session_state.usuario} ({role})")

    if role == "educador":
        if st.sidebar.button("Sair"):
            st.session_state.clear()
            st.rerun()
        page_educador_meu_painel()
    else:
        abas = ["Propostas"]
        if role == "admin":
            abas.append("Admin: Usuários")
        aba = st.sidebar.radio("Navegação", abas)

        if st.sidebar.button("Sair"):
            st.session_state.clear()
            st.rerun()

        if aba == "Propostas":
            page_propostas()
        elif aba == "Admin: Usuários":
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

# --------- Rodapé ----------
st.markdown(
    '<div class="yassaka-footer">© Yassaka – Todos os direitos reservados</div>',
    unsafe_allow_html=True,
)
