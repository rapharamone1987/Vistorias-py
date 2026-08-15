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
import base64
import re
from PIL import Image

# ReportLab para layout executivo do PDF
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
        "tipo_vistoria": "Entrada",
        "data_vistoria": datetime.now().strftime("%d/%m/%Y")
    }
if "registros_fotos" not in st.session_state: st.session_state.registros_fotos = {}
if "analises_fotos_editaveis" not in st.session_state: st.session_state.analises_fotos_editaveis = {}
if "divergentes_status" not in st.session_state: st.session_state.divergentes_status = {}
if "camera_ativa" not in st.session_state: st.session_state.camera_ativa = None
if "texto_vistoria_bruto" not in st.session_state: st.session_state.texto_vistoria_bruto = ""
if "parecer_editavel" not in st.session_state: st.session_state.parecer_editavel = ""

# CONFIGURAÇÃO DA GROQ API KEY
key = st.secrets.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
client = Groq(api_key=key, timeout=15.0) if key else None

# ==========================================
# 2. FUNÇÕES AUXILIARES DE IA E LEGISLAÇÃO
# ==========================================
def limpar_json_ia(texto):
    try:
        match = re.search(r'\{.*\}', texto, re.DOTALL)
        return json.loads(match.group(0)) if match else json.loads(texto)
    except:
        return None

def otimizar_bytes_imagem(raw_bytes, max_dim=500):
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.thumbnail((max_dim, max_dim))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65)
        return buf.getvalue()
    except Exception:
        return raw_bytes

def encode_image_to_base64(raw_bytes):
    return base64.b64encode(raw_bytes).decode('utf-8')

def analisar_foto_item_ia(raw_bytes, descricao_item):
    if not client:
        return "Evidência fotográfica registrada para comprovação visual."
    
    bytes_otimizados = otimizar_bytes_imagem(raw_bytes, max_dim=500)
    base64_str = encode_image_to_base64(bytes_otimizados)
    
    prompt_visao = (
        f"Examine a imagem anexada ao item '{descricao_item}'. "
        "Responda DIRETAMENTE em Português do Brasil em 2 frases objetivas. "
        "Descreva o estado do elemento, marcas ou desgastes. "
        "PROIBIDO incluir raciocínios em inglês, tags de pensamento, ou introduções."
    )
    
    content_payload = [
        {"type": "text", "text": prompt_visao},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_str}"}}
    ]
    try:
        res = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[{"role": "user", "content": content_payload}],
            temperature=0.0,
            max_tokens=200
        )
        txt = res.choices[0].message.content
        txt = re.sub(r'<think>.*?</think>', '', txt, flags=re.DOTALL)
        txt = re.sub(r'(?i)(The user|Analyze the image|In this photo|Looking closely).*?\n', '', txt)
        return txt.strip()
    except Exception:
        try:
            res = client.chat.completions.create(
                model="llama-3.2-11b-vision-instruct",
                messages=[{"role": "user", "content": content_payload}],
                temperature=0.0,
                max_tokens=200
            )
            txt = res.choices[0].message.content
            txt = re.sub(r'<think>.*?</think>', '', txt, flags=re.DOTALL)
            return txt.strip()
        except Exception:
            return "Evidência fotográfica registrada para comprovação das condições físicas do elemento."

def extrair_itens_vistoria_ia(texto_entrada, tipo_vistoria):
    prompt = (
        f"Você é um Perito Especialista em Vistorias Imobiliárias (Lei 8.245/91).\n"
        f"Analise o laudo referente a uma VISTORIA DE {tipo_vistoria.upper()}.\n"
        "REGRAS ESTRITAS DE EXTRAÇÃO:\n"
        "1. PROIBIDO criar itens genéricos como 'Sala: Não há informações' ou 'Cozinha: Boas condições'.\n"
        "2. Se um cômodo não tiver elementos específicos detalhados, NÃO inclua esse cômodo.\n"
        "3. Extraia APENAS elementos físicos concretos descritos no laudo (Pintura, Pisos, Aberturas, Metais, Louças, Fechaduras, Elétrica).\n"
        "4. Aponte cada item obrigatoriamente no formato 'Cômodo - Elemento: Estado detalhado'.\n"
        "Responda EXCLUSIVAMENTE em JSON válido neste formato:\n"
        '{\n'
        '  "imobiliaria": "nome da imobiliária",\n'
        '  "locatario": "nome do inquilino",\n'
        '  "endereco": "endereço do imóvel",\n'
        '  "checklist": [\n'
        '     "Sala - Pintura: Parede principal com tinta nova branca",\n'
        '     "Sala - Aberturas: Janela de alumínio com fecho e vidros íntegros",\n'
        '     "Cozinha - Metais: Torneira cromada com marca de uso no manípulo",\n'
        '     "Banheiro - Louças: Vaso sanitário com assento plástico instalado"\n'
        '  ]\n'
        '}'
    )
    if client:
        try:
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=[{"role": "user", "content": prompt + "\n\nTexto do Laudo:\n" + texto_entrada[:4000]}], 
                temperature=0.0,
                max_tokens=1500
            )
            data = limpar_json_ia(res.choices[0].message.content)
            if data and "checklist" in data:
                padroes_genericos = r'(não há informação|sem informação|não informado|boas condições gerais|sem observações|conforme laudo|conforme vistoria)'
                data["checklist"] = [
                    item for item in data["checklist"] 
                    if not re.search(padroes_genericos, item, re.IGNORECASE) and " - " in item
                ]
            return data
        except Exception as e:
            st.warning(f"Aviso na extração por IA: {e}")
    return None

def gerar_parecer_revisao_ia(texto_bruto, tipo_vistoria):
    if not client or not texto_bruto:
        return "Solicitamos a revisão formal dos itens apontados neste laudo nos termos dos Artigos 22 e 23 da Lei nº 8.245/1991, resguardando os direitos do locatário quanto ao estado inicial e ao desgaste decorrente do uso regular do imóvel."
    
    contexto_foco = (
        "registrar vícios ocultos e o estado inicial real recebido (Art. 22, I e IV da Lei 8.245/91) para afastar cobranças futuras indevidas."
        if tipo_vistoria == "Entrada" else
        "ressalvar as deteriorações decorrentes do uso normal e desgaste natural do tempo (Art. 23, III da Lei 8.245/91), rechaçando imposições abusivas ou reformas estruturais."
    )
    
    prompt = (
        f"Você é um Perito Locatício. Elabore um parecer técnico formal em PORTUGUÊS DO BRASIL de REVISÃO DE VISTORIA DE {tipo_vistoria.upper()} (Lei 8.245/1991).\n"
        f"Objetivo: {contexto_foco}\n"
        "REGRAS INVIOLÁVEIS:\n"
        "1. Responda EXCLUSIVAMENTE em Português do Brasil.\n"
        "2. NÃO inclua rascunhos, instruções em inglês ou introduções meta-analíticas.\n"
        "3. Máximo 10 linhas, finalizando a última frase de forma completa."
    )
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt + "\n\nLaudo da Imobiliária:\n" + texto_bruto[:2500]}],
            temperature=0.1,
            max_tokens=500
        )
        return res.choices[0].message.content
    except Exception:
        return "Solicitamos a revisão formal dos itens apontados neste laudo nos termos dos Artigos 22 e 23 da Lei nº 8.245/1991, resguardando os direitos do locatário quanto ao estado inicial e ao desgaste decorrente do uso regular do imóvel."

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
# 3. GERADOR DE PDF (REPORTLAB)
# ==========================================
def gerar_pdf_revisao(cabecalho, itens_lista, status_divergentes, fotos_dict, analises_fotos_dict, obs_geral, parecer_texto):
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
        fontSize=12, leading=15, textColor=colors.HexColor("#ffffff"),
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
    style_analise_ia = ParagraphStyle(
        'IaText', parent=styles['Normal'],
        fontSize=8.5, leading=11.5, textColor=AZUL_HEADER, fontName="Helvetica-Oblique"
    )
    style_legenda = ParagraphStyle(
        'CapStyle', parent=styles['Normal'],
        fontSize=8, leading=10, textColor=CINZA_TEXTO,
        fontName="Helvetica-Bold", alignment=1
    )

    story = []

    # Banner
    titulo_banner = "<b>LAUDO TÉCNICO DE REVISÃO DE VISTORIA — LEI 8.245/1991</b>"
    t_banner = Table([[Paragraph(titulo_banner, style_titulo)]], colWidths=[540])
    t_banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), AZUL_HEADER),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_banner)
    story.append(Spacer(1, 10))

    # Identificação
    dados_id = [
        [Paragraph("<b>Locatário / Inquilino:</b>", style_cell_header), Paragraph(cabecalho.get('locatario', '-'), style_cell_body)],
        [Paragraph("<b>Imobiliária / Vistoriador:</b>", style_cell_header), Paragraph(cabecalho.get('imobiliaria', '-'), style_cell_body)],
        [Paragraph("<b>Endereço do Imóvel:</b>", style_cell_header), Paragraph(cabecalho.get('endereco', '-'), style_cell_body)],
        [Paragraph("<b>Modalidade / Contrato:</b>", style_cell_header), Paragraph(f"Vistoria de {cabecalho.get('tipo_vistoria', 'Entrada')} | Cód: {cabecalho.get('contrato', '-')}", style_cell_body)],
        [Paragraph("<b>Data da Revisão:</b>", style_cell_header), Paragraph(cabecalho.get('data_vistoria', '-'), style_cell_body)]
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

    # Parecer Consolidado
    if parecer_texto:
        story.append(Paragraph("<b>1. PARECER TÉCNICO DE FUNDAMENTAÇÃO LEGAL (LEI Nº 8.245/1991)</b>", style_secao))
        story.append(HRFlowable(width="100%", thickness=1, color=AZUL_HEADER, spaceAfter=6))
        
        texto_purificado = purificar_texto_para_pdf(parecer_texto)
        for l in texto_purificado.split('\n'):
            if l.strip():
                story.append(Paragraph(l, style_cell_body))
                story.append(Spacer(1, 3))
        story.append(Spacer(1, 8))

    # Checklist
    story.append(Paragraph("<b>2. CHECKLIST DE ELEMENTOS E RESSALVAS LOCATÍCIAS</b>", style_secao))
    story.append(HRFlowable(width="100%", thickness=1, color=AZUL_HEADER, spaceAfter=6))

    for i, itm in enumerate(itens_lista):
        uid = itm['id']
        eh_divergente = status_divergentes.get(uid, False)
        
        status_label = "SOLICITA REVISÃO / RESSALVA" if eh_divergente else "EM CONFORMIDADE / CONFIRMADO"
        status_cor = VERMELHO_ALERT if eh_divergente else VERDE_OK
        
        style_status = ParagraphStyle(
            'StatusStyle', parent=styles['Normal'],
            fontSize=8.5, leading=11, textColor=status_cor, fontName="Helvetica-Bold"
        )

        item_data = [
            [Paragraph(f"<b>Item {i+1}:</b> {itm['texto']}", style_cell_body), Paragraph(status_label, style_status)]
        ]
        t_item = Table(item_data, colWidths=[370, 170])
        t_item.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CINZA_FUNDO),
            ('BOX', (0, 0), (-1, -1), 0.5, status_cor),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t_item)

        if uid in fotos_dict:
            img_bytes = fotos_dict[uid]
            img_io = io.BytesIO(img_bytes)
            rl_img = RLImage(img_io, width=220, height=140)
            
            analise_txt = analises_fotos_dict.get(uid, "Evidência fotográfica anexada.")
            cap_text = f"<b>Evidência Fotográfica do Item {i+1}</b><br/><br/><b>Análise da Imagem:</b> {analise_txt}"
            
            legenda = Paragraph(cap_text, style_analise_ia)
            
            t_foto = Table([[rl_img, legenda]], colWidths=[240, 300])
            t_foto.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(t_foto)

        story.append(Spacer(1, 6))

    if obs_geral:
        story.append(Spacer(1, 6))
        story.append(Paragraph("<b>3. CONSIDERAÇÕES FINAIS DO LOCATÁRIO</b>", style_secao))
        story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_LINHA, spaceAfter=4))
        story.append(Paragraph(obs_geral, style_cell_body))

    story.append(Spacer(1, 20))
    story.append(Paragraph("____________________________________________________", style_legenda))
    story.append(Paragraph(f"<b>{cabecalho.get('locatario', 'Locatário Responsável')}</b>", style_legenda))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ==========================================
# 4. INTERFACE PRINCIPAL
# ==========================================
st.set_page_config(
    page_title="Revisão de Vistoria Imobiliária",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Revisão Técnica de Vistoria Imobiliária")
st.caption("Sistema de Conferência e Registro de Evidências com Fundamentação na Lei 8.245/1991")
st.markdown("---")

tipo_vistoria = st.radio(
    "📌 Selecione a Etapa da Vistoria:",
    ["Entrada (Início do Contrato)", "Saída (Devolução do Imóvel)"],
    horizontal=True
)

st.session_state.cabecalho_vistoria["tipo_vistoria"] = "Entrada" if "Entrada" in tipo_vistoria else "Saída"

if not st.session_state.items_vistoria:
    st.subheader(f"1. Carregar laudo da imobiliária para Revisão de {st.session_state.cabecalho_vistoria['tipo_vistoria']}")
    tabs_carga = st.tabs(["📄 Enviar PDF do Laudo", "✍️ Cole o Texto da Vistoria", "🖊️ Iniciar Manualmente"])
    
    with tabs_carga[0]:
        pdf_file = st.file_uploader("Carregue o arquivo PDF do laudo fornecido:", type=["pdf"])
        
        if pdf_file and st.button("🔍 Extrair e Gerar Checklist de Revisão", type="primary"):
            with st.spinner("Analisando laudo e estruturando elementos de conferência..."):
                texto = ""
                try:
                    reader = pypdf.PdfReader(pdf_file)
                    for page in reader.pages:
                        texto += page.extract_text() + "\n"
                except Exception as e:
                    st.error(f"Erro ao ler PDF: {e}")
                
                if texto:
                    st.session_state.texto_vistoria_bruto = texto
                    res = extrair_itens_vistoria_ia(texto, st.session_state.cabecalho_vistoria["tipo_vistoria"])
                    if res:
                        st.session_state.cabecalho_vistoria.update({
                            "imobiliaria": res.get("imobiliaria", ""),
                            "locatario": res.get("locatario", ""),
                            "endereco": res.get("endereco", "")
                        })
                        st.session_state.items_vistoria = [
                            {"id": time.time()+i, "texto": txt} for i, txt in enumerate(res.get('checklist', []))
                        ]
                        st.session_state.parecer_editavel = gerar_parecer_revisao_ia(texto, st.session_state.cabecalho_vistoria["tipo_vistoria"])
                        st.success("Checklist de revisão criado com sucesso!")
                        st.rerun()

    with tabs_carga[1]:
        texto_colado = st.text_area("Cole aqui o texto da vistoria recebida:", height=200)
        if st.button("🔍 Processar Texto para Revisão", type="primary"):
            if texto_colado:
                with st.spinner("Categorizando itens via IA..."):
                    st.session_state.texto_vistoria_bruto = texto_colado
                    res = extrair_itens_vistoria_ia(texto_colado, st.session_state.cabecalho_vistoria["tipo_vistoria"])
                    if res:
                        st.session_state.cabecalho_vistoria.update({
                            "imobiliaria": res.get("imobiliaria", ""),
                            "locatario": res.get("locatario", ""),
                            "endereco": res.get("endereco", "")
                        })
                        st.session_state.items_vistoria = [
                            {"id": time.time()+i, "texto": txt} for i, txt in enumerate(res.get('checklist', []))
                        ]
                        st.session_state.parecer_editavel = gerar_parecer_revisao_ia(texto_colado, st.session_state.cabecalho_vistoria["tipo_vistoria"])
                        st.rerun()

    with tabs_carga[2]:
        if st.button("🖊️ Iniciar Checklist em Branco"):
            st.session_state.items_vistoria = [{"id": time.time(), "texto": "Sala - Pintura: Parede com manchas ou marcas aparentes"}]
            st.rerun()

else:
else:
    st.sidebar.subheader("⚙️ Ações")
    if st.sidebar.button("🗑️ Nova Revisão / Limpar"):
        st.session_state.clear()
        st.rerun()

    with st.expander("📋 Dados do Contrato e Imóvel (Editáveis)", expanded=True):
        c1, c2, c3 = st.columns(3)
        st.session_state.cabecalho_vistoria["locatario"] = c1.text_input("Locatário (Inquilino):", value=st.session_state.cabecalho_vistoria["locatario"])
        st.session_state.cabecalho_vistoria["imobiliaria"] = c2.text_input("Imobiliária / Vistoriador:", value=st.session_state.cabecalho_vistoria["imobiliaria"])
        st.session_state.cabecalho_vistoria["contrato"] = c3.text_input("Cód. Contrato / Vistoria:", value=st.session_state.cabecalho_vistoria["contrato"])
        st.session_state.cabecalho_vistoria["endereco"] = st.text_input("Endereço do Imóvel:", value=st.session_state.cabecalho_vistoria["endereco"])

    st.subheader("✍️ 1. Parecer Técnico de Revisão Locatícia (Lei 8.245/1991)")
    st.caption("Ajuste a fundamentação legal que constará na introdução do laudo emitido.")
    st.session_state.parecer_editavel = st.text_area(
        "Texto do Parecer (Editável):",
        value=st.session_state.parecer_editavel,
        height=140
    )

    st.subheader(f"✅ 2. Conferência dos Itens ({st.session_state.cabecalho_vistoria['tipo_vistoria']})")
    st.caption("Marque **'REVISAR'** nos itens divergentes e anexe a foto da evidência.")

    for i, itm in enumerate(st.session_state.items_vistoria):
        uid = itm["id"]
        with st.container(border=True):
            col_ch, col_tx, col_ex = st.columns([0.25, 0.65, 0.1])
            
            st.session_state.divergentes_status[uid] = col_ch.checkbox(
                "⚠️ REVISAR", 
                key=f"ch_{uid}", 
                value=st.session_state.divergentes_status.get(uid, False)
            )
            
            itm["texto"] = col_tx.text_input(f"Item {i+1}", itm["texto"], key=f"in_{uid}", label_visibility="collapsed")
            
            if col_ex.button("🗑️", key=f"del_{uid}"): 
                st.session_state.items_vistoria.pop(i)
                st.rerun()
            
            if uid not in st.session_state.registros_fotos:
                t1, t2 = st.tabs(["📸 Câmera", "📁 Galeria de Fotos"])
                with t1:
                    if st.session_state.camera_ativa == uid:
                        f = st.camera_input("Tire a foto da avaria/estado:", key=f"cam_{uid}")
                        if f:
                            img = Image.open(f)
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG", quality=70)
                            bytes_img = buf.getvalue()
                            st.session_state.registros_fotos[uid] = bytes_img
                            
                            with st.spinner("IA analisando foto do item..."):
                                st.session_state.analises_fotos_editaveis[uid] = analisar_foto_item_ia(bytes_img, itm["texto"])
                            
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
                        bytes_img = buf.getvalue()
                        st.session_state.registros_fotos[uid] = bytes_img
                        
                        with st.spinner("IA analisando foto do item..."):
                            st.session_state.analises_fotos_editaveis[uid] = analisar_foto_item_ia(bytes_img, itm["texto"])
                        st.rerun()
            else:
                col_img, col_txt_ia = st.columns([0.35, 0.65])
                with col_img:
                    st.image(st.session_state.registros_fotos[uid], width=220, caption=f"Foto Anexada ao Item {i+1}")
                    if st.button("Remover Foto", key=f"rm_{uid}"):
                        del st.session_state.registros_fotos[uid]
                        if uid in st.session_state.analises_fotos_editaveis:
                            del st.session_state.analises_fotos_editaveis[uid]
                        st.rerun()
                
                with col_txt_ia:
                    if uid not in st.session_state.analises_fotos_editaveis or not st.session_state.analises_fotos_editaveis[uid]:
                        st.session_state.analises_fotos_editaveis[uid] = analisar_foto_item_ia(st.session_state.registros_fotos[uid], itm["texto"])
                        
                    st.session_state.analises_fotos_editaveis[uid] = st.text_area(
                        "🔍 Análise Pericial da Foto (Editável):",
                        value=st.session_state.analises_fotos_editaveis[uid],
                        key=f"txt_ia_{uid}",
                        height=100
                    )

    if st.button("➕ Adicionar Item para Conferência"):
        st.session_state.items_vistoria.append({"id": time.time(), "texto": "Cômodo - Elemento: Descrição do estado real"})
        st.rerun()

    st.markdown("---")
    
    obs_geral = st.text_area(
        "Considerações Finais / Ressalvas Gerais do Inquilino:",
        placeholder="Ex: Ressalvo que a umidade nas paredes do quarto decorre de vazamento na fachada externa, de responsabilidade do locador..."
    )

    if st.button("🚀 GERAR LAUDO DE REVISÃO TÉCNICA EM PDF", type="primary", use_container_width=True):
        if not st.session_state.cabecalho_vistoria["locatario"]:
            st.error("Por favor, preencha o nome do Locatário (Inquilino) nos dados do imóvel.")
        else:
            with st.spinner("Compilando relatório de revisão legal..."):
                try:
                    pdf_bytes = gerar_pdf_revisao(
                        cabecalho=st.session_state.cabecalho_vistoria,
                        itens_lista=st.session_state.items_vistoria,
                        status_divergentes=st.session_state.divergentes_status,
                        fotos_dict=st.session_state.registros_fotos,
                        analises_fotos_dict=st.session_state.analises_fotos_editaveis,
                        obs_geral=obs_geral,
                        parecer_texto=st.session_state.parecer_editavel
                    )

                    st.success("Laudo de Revisão gerado com sucesso!")
                    st.download_button(
                        label="📄 Baixar Laudo de Revisão Técnica (PDF Oficial)",
                        data=pdf_bytes,
                        file_name=f"Revisao_Vistoria_{st.session_state.cabecalho_vistoria['tipo_vistoria']}_{datetime.now().strftime('%d%m%Y')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Erro ao gerar o PDF: {e}")
                    
    
