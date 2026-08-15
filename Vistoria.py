import streamlit as st
from groq import Groq
import pypdf
import pandas as pd
from datetime import datetime
import tempfile
import os
import io
import json
import time
import re
from PIL import Image

# ReportLab para layout e formatação profissional de PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ==========================================
# 1. INICIALIZAÇÃO DE SESSÃO
# ==========================================
if "items_vistoria" not in st.session_state: st.session_state.items_vistoria = []
if "cabecalho_vistoria" not in st.session_state: 
    st.session_state.cabecalho_vistoria = {
        "imobiliaria": "", 
        "locatario": "", 
        "endereco": "", 
        "contrato": "", 
        "data_vistoria": datetime.now().strftime("%d/%m/%Y")
    }
if "registros_fotos" not in st.session_state: st.session_state.registros_fotos = {}
if "contestados_status" not in st.session_state: st.session_state.contestados_status = {}
if "camera_ativa" not in st.session_state: st.session_state.camera_ativa = None
if "texto_vistoria_bruto" not in st.session_state: st.session_state.texto_vistoria_bruto = ""

# CONFIGURAÇÃO DA GROQ API KEY
key = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
client = Groq(api_key=key) if key else None

# ==========================================
# 2. FUNÇÕES AUXILIARES DE IA E TRATAMENTO
# ==========================================
def limpar_json_ia(texto):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        return json.loads(match.group(0)) if match else json.loads(texto)
    except:
        return None

def extrair_itens_vistoria_ia(texto_entrada):
    """Lê o laudo da imobiliária e fragmenta em itens individuais de checklist por cômodo/elemento."""
    prompt = (
        "Você é um Perito em Vistorias Imobiliárias. "
        "Analise o texto do laudo de vistoria e extraia os apontamentos divididos por cômodos/elementos. "
        "Ignore cláusulas padrão de contrato. Responda APENAS em formato JSON válido:\n"
        '{\n'
        '  "imobiliaria": "nome da imobiliária ou vacio",\n'
        '  "locatario": "nome do inquilino ou vazio",\n'
        '  "endereco": "endereço do imóvel ou vazio",\n'
        '  "checklist": [\n'
        '     "Sala: Paredes com pintura nova em tinta látex branca sem manchas",\n'
        '     "Cozinha: Torneira da pia com leve vazamento na base",\n'
        '     "Quarto 1: Piso laminado com risco de 10cm próximo à janela"\n'
        '  ]\n'
        '}'
    )
    if client:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=[{"role": "user", "content": prompt + "\n\nTexto do laudo:\n" + texto_entrada[:4000]}], 
            temperature=0.1
        )
        return limpar_json_ia(res.choices[0].message.content)
    return None

def purificar_texto_para_pdf(texto_bruto):
    if not texto_bruto: return ""
    linhas = texto_bruto.split('\n')
    linhas_processadas = []
    for l in linhas:
        l_str = l.strip()
        if not l_str:
            linhas_processadas.append("")
            continue
        l_str = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', l_str)
        l_str = re.sub(r'\*(.*?)\*', r'<i>\1</i>', l_str)
        l_str = re.sub(r'^#+\s*', '', l_str)
        if l_str.startswith("- ") or l_str.startswith("* "):
            l_str = "• " + l_str[2:].strip()
        linhas_processadas.append(l_str)
    return "\n".join(linhas_processadas)

# ==========================================
# 3. GERADOR DE PDF DE CONTESTAÇÃO (REPORTLAB)
# ==========================================
def gerar_pdf_contestacao(cabecalho, itens_lista, status_contestados, fotos_dict, obs_geral, parecer_ia=""):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    AZUL_HEADER = colors.HexColor("#1e3a8a")
    VERMELHO_ALERT = colors.HexColor("#b91c1c")
    VERDE_OK = colors.HexColor("#15803d")
    CINZA_FUNDO = colors.HexColor("#f8fafc")
    CINZA_TEXTO = colors.HexColor("#0f172a")
    CINZA_LINHA = colors.HexColor("#cbd5e1")
    
    style_titulo = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'],
        fontSize=13, leading=16, textColor=colors.HexColor("#ffffff"),
        fontName="Helvetica-Bold", alignment=1
    )
    style_secao = ParagraphStyle(
        'SecTitle', parent=styles['Heading2'],
        fontSize=11, leading=15, textColor=AZUL_HEADER,
        fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4
    )
    style_cell_header = ParagraphStyle(
        'CellHeader', parent=styles['Normal'],
        fontSize=9, leading=12, textColor=AZUL_HEADER, fontName="Helvetica-Bold"
    )
    style_cell_body = ParagraphStyle(
        'CellBody', parent=styles['Normal'],
        fontSize=9, leading=12.5, textColor=CINZA_TEXTO, fontName="Helvetica"
    )
    style_legenda = ParagraphStyle(
        'CapStyle', parent=styles['Normal'],
        fontSize=8, leading=10, textColor=CINZA_TEXTO,
        fontName="Helvetica-Bold", alignment=1
    )

    story = []

    # Banner Superior
    t_banner = Table([[Paragraph("<b>LAUDO TÉCNICO DE CONTESTAÇÃO DE VISTORIA IMOBILIÁRIA</b>", style_titulo)]], colWidths=[540])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), AZUL_HEADER),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 10))

    # Tabela de Identificação
    dados_id = [
        [Paragraph("<b>Locatário / Inquilino:</b>", style_cell_header), Paragraph(cabecalho.get('locatario', '-'), style_cell_body)],
        [Paragraph("<b>Imobiliária / Vistoriador:</b>", style_cell_header), Paragraph(cabecalho.get('imobiliaria', '-'), style_cell_body)],
        [Paragraph("<b>Endereço do Imóvel:</b>", style_cell_header), Paragraph(cabecalho.get('endereco', '-'), style_cell_body)],
        [Paragraph("<b>Contrato / Cód. Vistoria:</b>", style_cell_header), Paragraph(cabecalho.get('contrato', '-'), style_cell_body)],
        [Paragraph("<b>Data da Contestação:</b>", style_cell_header), Paragraph(cabecalho.get('data_vistoria', '-'), style_cell_body)]
    ]
    t_id = Table(dados_id, colWidths=[150, 390])
    t_id.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), CINZA_FUNDO),
        ('GRID', (0, 0), (-1, -1), 0.5, CINZA_LINHA),
        ('BOX', (0, 0), (-1, -1), 1, AZUL_HEADER),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_id)
    story.append(Spacer(1, 10))

    # Parecer da IA (Se houver)
    if parecer_ia:
        story.append(Paragraph("<b>1. PARECER TÉCNICO CONSOLIDADO</b>", style_secao))
        story.append(HRFlowable(width="100%", thickness=1, color=AZUL_HEADER, spaceAfter=6))
        
        texto_purificado = purificar_texto_para_pdf(parecer_ia)
        for l in texto_purificado.split('\n'):
            if l.strip():
                story.append(Paragraph(l, style_cell_body))
                story.append(Spacer(1, 3))
        story.append(Spacer(1, 8))

    # Tabela de Itens Vistoriados e Contestações
    story.append(Paragraph("<b>2. CHECKLIST DE DIVERGÊNCIAS E CONTESTAÇÕES LOCATÍCIAS</b>", style_secao))
    story.append(HRFlowable(width="100%", thickness=1, color=AZUL_HEADER, spaceAfter=6))

    for i, itm in enumerate(itens_lista):
        uid = itm['id']
        eh_contestado = status_contestados.get(uid, False)
        
        status_label = "CONTESTADO / DIVERGENTE" if eh_contestado else "CONCORDA / EM CONFORMIDADE"
        status_cor = VERMELHO_ALERT if eh_contestado else VERDE_OK
        
        style_status = ParagraphStyle(
            'StatusStyle', parent=styles['Normal'],
            fontSize=8.5, leading=11, textColor=status_cor, fontName="Helvetica-Bold"
        )

        item_data = [
            [Paragraph(f"<b>Item {i+1}:</b> {itm['texto']}", style_cell_body), Paragraph(status_label, style_status)]
        ]
        t_item = Table(item_data, colWidths=[380, 160])
        t_item.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CINZA_FUNDO),
            ('BOX', (0, 0), (-1, -1), 0.5, status_cor),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t_item)

        # Se houver foto associada a este item
        if uid in fotos_dict:
            img_bytes = fotos_dict[uid]
            img_io = io.BytesIO(img_bytes)
            rl_img = RLImage(img_io, width=220, height=140)
            legenda = Paragraph(f"Evidência Fotográfica do Item {i+1}", style_legenda)
            
            t_foto = Table([[rl_img], [legenda]], colWidths=[540])
            t_foto.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('PADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_foto)

        story.append(Spacer(1, 6))

    # Observações Finais
    if obs_geral:
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>3. JUSTIFICATIVA E CONSIDERAÇÕES FINAIS DO LOCATÁRIO</b>", style_secao))
        story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_LINHA, spaceAfter=4))
        story.append(Paragraph(obs_geral, style_cell_body))

    # Assinatura
    story.append(Spacer(1, 20))
    story.append(Paragraph("____________________________________________________", style_legenda))
    story.append(Paragraph(f"<b>{cabecalho.get('locatario', 'Locatário Responsável')}</b>", style_legenda))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ==========================================
# 4. INTERFACE PRINCIPAL DO APP
# ==========================================
st.set_page_config(
    page_title="Contestação de Vistoria — Checklist Tático",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Contestação de Vistoria Imobiliária")
st.caption("Sistema Tático de Mapeamento de Divergências e Evidências Locatícias")
st.markdown("---")

# --- ETAPA 1: CARGA E PROCESSAMENTO INICIAL ---
if not st.session_state.items_vistoria:
    st.subheader("1. Carregar laudo da imobiliária para gerar checklist")
    tabs_carga = st.tabs(["📄 Enviar PDF da Imobiliária", "✍️ Cole o Texto do Laudo", "🖊️ Iniciar do Zero"])
    
    with tabs_carga[0]:
        pdf_file = st.file_uploader("Upload do arquivo PDF de vistoria:", type=["pdf"])
        if pdf_file and st.button("🔍 Extrair Itens do PDF com IA", type="primary"):
            with st.spinner("Extraindo e categorizando apontamentos do laudo..."):
                texto = ""
                try:
                    with pypdf.PdfReader(pdf_file) as reader:
                        for page in reader.pages:
                            texto += page.extract_text() + "\n"
                except Exception as e:
                    st.error(f"Erro ao ler PDF: {e}")
                
                if texto:
                    st.session_state.texto_vistoria_bruto = texto
                    res = extrair_itens_vistoria_ia(texto)
                    if res:
                        st.session_state.cabecalho_vistoria.update({
                            "imobiliaria": res.get("imobiliaria", ""),
                            "locatario": res.get("locatario", ""),
                            "endereco": res.get("endereco", "")
                        })
                        st.session_state.items_vistoria = [
                            {"id": time.time()+i, "texto": txt} for i, txt in enumerate(res.get('checklist', []))
                        ]
                        st.success("Checklist gerado com sucesso!")
                        st.rerun()

    with tabs_carga[1]:
        texto_colado = st.text_area(
            "Cole aqui o texto da vistoria recebida:", 
            height=200, 
            placeholder="Ex:\nSala: Paredes com pintura nova na cor branca.\nCozinha: Armário com porta desalinhada..."
        )
        if st.button("🔍 Gerar Checklist do Texto", type="primary"):
            if texto_colado:
                with st.spinner("Categorizando itens via IA..."):
                    st.session_state.texto_vistoria_bruto = texto_colado
                    res = extrair_itens_vistoria_ia(texto_colado)
                    if res:
                        st.session_state.cabecalho_vistoria.update({
                            "imobiliaria": res.get("imobiliaria", ""),
                            "locatario": res.get("locatario", ""),
                            "endereco": res.get("endereco", "")
                        })
                        st.session_state.items_vistoria = [
                            {"id": time.time()+i, "texto": txt} for i, txt in enumerate(res.get('checklist', []))
                        ]
                        st.rerun()
            else:
                st.warning("Cole o texto do laudo antes de continuar.")

    with tabs_carga[2]:
        if st.button("🖊️ Criar Checklist Manualmente"):
            st.session_state.items_vistoria = [{"id": time.time(), "texto": "Sala: Defeito ou apontamento a descrever"}]
            st.rerun()

# --- ETAPA 2: PAINEL DE CONFERÊNCIA E EVIDÊNCIAS ---
else:
    st.sidebar.subheader("⚙️ Ações")
    if st.sidebar.button("🗑️ Nova Contestação / Limpar"):
        st.session_state.clear()
        st.rerun()

    # Cabeçalho Editável do Imóvel
    with st.expander("📋 Dados do Contrato e Imóvel (Editáveis)", expanded=True):
        c1, c2, c3 = st.columns(3)
        st.session_state.cabecalho_vistoria["locatario"] = c1.text_input("Locatário (Inquilino):", value=st.session_state.cabecalho_vistoria["locatario"])
        st.session_state.cabecalho_vistoria["imobiliaria"] = c2.text_input("Imobiliária / Vistoriador:", value=st.session_state.cabecalho_vistoria["imobiliaria"])
        st.session_state.cabecalho_vistoria["contrato"] = c3.text_input("Cód. Contrato / Vistoria:", value=st.session_state.cabecalho_vistoria["contrato"])
        st.session_state.cabecalho_vistoria["endereco"] = st.text_input("Endereço do Imóvel:", value=st.session_state.cabecalho_vistoria["endereco"])

    st.subheader("✅ Itens de Conferência da Vistoria")
    st.caption("Marque a caixa **'CONTESTAR'** nos itens que contêm divergências ou avarias e adicione a foto correspondente.")

    for i, itm in enumerate(st.session_state.items_vistoria):
        uid = itm["id"]
        with st.container(border=True):
            col_ch, col_tx, col_ex = st.columns([0.2, 0.7, 0.1])
            
            # Checkbox de Contestação
            st.session_state.contestados_status[uid] = col_ch.checkbox(
                "🚨 CONTESTAR", 
                key=f"ch_{uid}", 
                value=st.session_state.contestados_status.get(uid, False)
            )
            
            # Texto da descrição do item
            itm["texto"] = col_tx.text_input(f"Item {i+1}", itm["texto"], key=f"in_{uid}", label_visibility="collapsed")
            
            # Botão excluir
            if col_ex.button("🗑️", key=f"del_{uid}"): 
                st.session_state.items_vistoria.pop(i)
                st.rerun()
            
            # Mídia do Item (Câmera ou Upload)
            if uid not in st.session_state.registros_fotos:
                t1, t2 = st.tabs(["📸 Câmera", "📁 Galeria de Fotos"])
                with t1:
                    if st.session_state.camera_ativa == uid:
                        f = st.camera_input("Tire a foto da avaria:", key=f"cam_{uid}")
                        if f:
                            img = Image.open(f)
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG", quality=70)
                            st.session_state.registros_fotos[uid] = buf.getvalue()
                            st.session_state.camera_ativa = None
                            st.rerun()
                    elif st.button("Abrir Câmera", key=f"btn_c_{uid}"):
                        st.session_state.camera_ativa = uid
                        st.rerun()
                with t2:
                    up = st.file_uploader("Upload da foto do item:", type=["jpg", "jpeg", "png"], key=f"up_{uid}")
                    if up:
                        img = Image.open(up)
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=70)
                        st.session_state.registros_fotos[uid] = buf.getvalue()
                        st.rerun()
            else:
                st.image(st.session_state.registros_fotos[uid], width=200, caption=f"Foto Anexada ao Item {i+1}")
                if st.button("Remover Foto", key=f"rm_{uid}"):
                    del st.session_state.registros_fotos[uid]
                    st.rerun()

    if st.button("➕ Adicionar Novo Item de Vistoria"):
        st.session_state.items_vistoria.append({"id": time.time(), "texto": "Cômodo: Novo elemento a contestar"})
        st.rerun()

    st.markdown("---")
    
    # Campo de justificativa final e síntese
    obs_geral = st.text_area(
        "Justificativa Legal / Observações Gerais do Locatário:",
        placeholder="Ex: Solicito a reavaliação dos itens apontados acima, considerando que as avarias foram registradas na entrega das chaves..."
    )

    # --- GERADOR DO PDF DE CONTESTAÇÃO ---
    if st.button("🚀 GERAR LAUDO DE CONTESTAÇÃO EM PDF", type="primary", use_container_width=True):
        if not st.session_state.cabecalho_vistoria["locatario"]:
            st.error("Por favor, preencha o nome do Locatário (Inquilino) nos dados do imóvel.")
        else:
            with st.spinner("Compilando dados e gerando documento em PDF via ReportLab..."):
                try:
                    # Opcional: Redação sintética de apoio via Llama 3.3
                    parecer_ia = ""
                    if client and st.session_state.texto_vistoria_bruto:
                        prompt_parecer = (
                            "Com base nos itens do checklist e na vistoria recebida, elabore um parágrafo "
                            "resumido, formal e técnico em Português contestando formalmente o laudo perante a imobiliária."
                        )
                        res_ia = client.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=[{"role": "user", "content": prompt_parecer + "\n\nTexto:\n" + st.session_state.texto_vistoria_bruto[:2000]}],
                            temperature=0.2,
                            max_tokens=300
                        )
                        parecer_ia = res_ia.choices[0].message.content

                    # Geração do PDF
                    pdf_bytes = gerar_pdf_contestacao(
                        cabecalho=st.session_state.cabecalho_vistoria,
                        itens_lista=st.session_state.items_vistoria,
                        status_contestados=st.session_state.contestados_status,
                        fotos_dict=st.session_state.registros_fotos,
                        obs_geral=obs_geral,
                        parecer_ia=parecer_ia
                    )

                    st.success("Laudo em PDF gerado com sucesso!")
                    st.download_button(
                        label="📄 Baixar Laudo de Contestação (PDF Oficial)",
                        data=pdf_bytes,
                        file_name=f"Contestacao_Vistoria_{datetime.now().strftime('%d%m%Y')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar o PDF:
