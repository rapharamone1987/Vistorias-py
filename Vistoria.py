import streamlit as st
from groq import Groq
from PIL import Image
import pypdf
import base64
import io
import re

# ReportLab para layout e formatação profissional de PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Contestação de Vistoria Imobiliária (Groq)",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Auxiliar de Contestação de Vistoria Imobiliária")
st.write("Compare o laudo oficial com fotos do imóvel para gerar uma contestação fundamentada.")

# ---------------------------------------------------------
# AUTENTICAÇÃO / OBTENÇÃO DA GROQ API KEY
# ---------------------------------------------------------
api_key = None

if "GROQ_API_KEY" in st.secrets:
    api_key = st.secrets["GROQ_API_KEY"]
elif "groq_api_key" in st.secrets:
    api_key = st.secrets["groq_api_key"]

if not api_key:
    api_key = st.sidebar.text_input("Insira sua Groq API Key (gsk_...):", type="password")

if api_key:
    client = Groq(api_key=api_key)
    st.sidebar.success("Groq API Key carregada com sucesso!")
else:
    st.warning("⚠️ Insira sua API Key da Groq (console.groq.com) para começar.")
    st.stop()

# Armazenamento de fotos tiradas pela câmera
if 'fotos_camera' not in st.session_state:
    st.session_state['fotos_camera'] = []

# ---------------------------------------------------------
# FUNÇÕES AUXILIARES
# ---------------------------------------------------------
def extrair_texto_arquivo(arquivo, max_caracteres=3500):
    texto = ""
    if arquivo.name.endswith('.pdf'):
        try:
            pdf_reader = pypdf.PdfReader(arquivo)
            for page in pdf_reader.pages:
                texto += page.extract_text() + "\n"
        except Exception as e:
            return f"Erro ao ler PDF: {e}"
    elif arquivo.name.endswith('.txt'):
        texto = arquivo.read().decode('utf-8', errors='ignore')
    
    if len(texto) > max_caracteres:
        texto = texto[:max_caracteres] + "\n...[texto truncado]..."
    return texto

def otimizar_imagem_para_bytes(pil_image, max_size=(600, 600), quality=70):
    """Gera bytes comprimidos da imagem para uso na API e no ReportLab."""
    buffered = io.BytesIO()
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)
    pil_image.save(buffered, format="JPEG", quality=quality)
    return buffered.getvalue()

def encode_image_to_base64(raw_bytes):
    return base64.b64encode(raw_bytes).decode('utf-8')

def purificar_texto_para_pdf(texto_bruto):
    """Remove marcações Markdown (###, **, -) e converte para tags HTML aceitas pelo ReportLab."""
    if not texto_bruto:
        return ""
    
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

def gerar_pdf(texto_analise, fotos_bytes_list):
    """Gera o PDF da contestação incluindo o parecer e a anexo de fotos."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )
    
    styles = getSampleStyleSheet()
    AZUL_HEADER = colors.HexColor("#1e3a8a")
    CINZA_TEXTO = colors.HexColor("#1f2937")
    CINZA_LINHA = colors.HexColor("#cbd5e1")
    
    style_titulo = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'],
        fontSize=14, leading=18, textColor=AZUL_HEADER,
        fontName="Helvetica-Bold", alignment=1, spaceAfter=12
    )
    style_secao = ParagraphStyle(
        'SecTitle', parent=styles['Heading2'],
        fontSize=11, leading=15, textColor=AZUL_HEADER,
        fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4
    )
    style_corpo = ParagraphStyle(
        'BodyTextCustom', parent=styles['Normal'],
        fontSize=9.5, leading=13.5, textColor=CINZA_TEXTO,
        fontName="Helvetica", spaceAfter=5
    )
    style_legenda = ParagraphStyle(
        'CapStyle', parent=styles['Normal'],
        fontSize=8.5, leading=11, textColor=CINZA_TEXTO,
        fontName="Helvetica-Bold", alignment=1
    )

    story = []

    # Cabeçalho Principal
    story.append(Paragraph("LAUDO DE CONTESTAÇÃO DE VISTORIA IMOBILIÁRIA", style_titulo))
    story.append(HRFlowable(width="100%", thickness=1.5, color=AZUL_HEADER, spaceAfter=12))

    # Corpo do Parecer
    texto_limpo = purificar_texto_para_pdf(texto_analise)
    linhas = texto_limpo.split('\n')

    for l in linhas:
        if not l:
            story.append(Spacer(1, 3))
            continue
            
        if re.match(r'^(\d+\.|\bConclusão\b|\bAtenciosamente\b)', l, re.IGNORECASE):
            story.append(Spacer(1, 4))
            story.append(Paragraph(l, style_secao))
            story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_LINHA, spaceAfter=5))
        else:
            story.append(Paragraph(l, style_corpo))

    # Anexo de Evidências Fotográficas
    if fotos_bytes_list:
        story.append(Spacer(1, 10))
        story.append(Paragraph("ANEXO: REGISTROS FOTOGRÁFICOS DE EVIDÊNCIAS", style_secao))
        story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_LINHA, spaceAfter=10))
        
        tabela_fotos_data = []
        linha_atual = []
        
        for i, f_bytes in enumerate(fotos_bytes_list):
            img_io = io.BytesIO(f_bytes)
            rl_img = RLImage(img_io, width=240, height=160)
            legenda = Paragraph(f"Evidência Fotográfica {i+1}", style_legenda)
            celula = [rl_img, Spacer(1, 3), legenda]
            linha_atual.append(celula)
            
            if len(linha_atual) == 2:
                tabela_fotos_data.append(linha_atual)
                linha_atual = []
                
        if linha_atual:
            if len(linha_atual) == 1:
                linha_atual.append("")
            tabela_fotos_data.append(linha_atual)
            
        t_fotos = Table(tabela_fotos_data, colWidths=[250, 250])
        t_fotos.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t_fotos)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ---------------------------------------------------------
# INTERFACE PRINCIPAL - ENTRADA DE DADOS
# ---------------------------------------------------------
st.header("1. Documentação e Evidências")
col1, col2 = st.columns(2)

with col1:
    st.subheader("📄 Laudo da Imobiliária")
    arquivo_laudo = st.file_uploader(
        "Carregue o arquivo do laudo da imobiliária (PDF ou TXT):",
        type=["pdf", "txt"]
    )
    laudo_texto_manual = st.text_area(
        "Ou cole o texto do laudo da imobiliária aqui:",
        height=150,
        placeholder="Ex: Sala de estar: Paredes pintadas na cor branca, sem manchas..."
    )
    
    texto_laudo_final = ""
    if arquivo_laudo:
        texto_extraido = extrair_texto_arquivo(arquivo_laudo)
        if texto_extraido:
            texto_laudo_final = texto_extraido
            st.info("✅ Texto do arquivo extraído com sucesso!")
    elif laudo_texto_manual:
        texto_laudo_final = laudo_texto_manual[:3500]

with col2:
    st.subheader("📸 Evidências do Inquilino")
    fotos_upload = st.file_uploader(
        "Carregue fotos salvas do imóvel (JPEG/PNG):",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )
    
    st.write("**Tirar fotos na hora:**")
    foto_capturada = st.camera_input("Tire uma foto de um defeito/cômodo")
    
    if foto_capturada:
        img_temp = Image.open(foto_capturada)
        if img_temp not in st.session_state['fotos_camera']:
            st.session_state['fotos_camera'].append(img_temp)
            st.toast(f"Foto {len(st.session_state['fotos_camera'])} adicionada!")

    if st.session_state['fotos_camera']:
        st.write(f"📷 Fotos tiradas na hora: **{len(st.session_state['fotos_camera'])}**")
        if st.button("🗑️ Limpar fotos tiradas na hora"):
            st.session_state['fotos_camera'] = []
            st.rerun()

imagens_totais = []
if fotos_upload:
    for f in fotos_upload:
        imagens_totais.append(Image.open(f))
if st.session_state['fotos_camera']:
    imagens_totais.extend(st.session_state['fotos_camera'])

# ---------------------------------------------------------
# PROCESSAMENTO DE ANÁLISE (EVIDÊNCIAS + SÍNTESE)
# ---------------------------------------------------------
st.divider()

if st.button("🔍 Analisar e Comparar Vistoria", type="primary", use_container_width=True):
    if not texto_laudo_final:
        st.error("Por favor, envie o arquivo do laudo ou cole o texto da vistoria.")
    elif not imagens_totais:
        st.error("Por favor, envie ou tire ao menos uma foto como evidência.")
    else:
        with st.spinner("Analisando fotos com modelo de visão e gerando laudo com Llama 3.3 70B..."):
            try:
                content_payload = [
                    {
                        "type": "text",
                        "text": "Analise as imagens e descreva com precisão técnica todas as avarias, sujeiras, furos, riscos, manchas de umidade ou defeitos visíveis:"
                    }
                ]

                # Prepara imagens otimizadas para API e para o PDF
                fotos_bytes_processadas = []
                for img in imagens_totais:
                    img_bytes = otimizar_imagem_para_bytes(img)
                    fotos_bytes_processadas.append(img_bytes)

                # Anexa até 2 imagens na chamada visual da API
                for img_bytes in fotos_bytes_processadas[:2]:
                    base64_str = encode_image_to_base64(img_bytes)
                    content_payload.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_str}"
                        }
                    })

                try:
                    vision_resp = client.chat.completions.create(
                        model="qwen/qwen3.6-27b",
                        messages=[{"role": "user", "content": content_payload}],
                        temperature=0.1,
                        max_tokens=500
                    )
                except Exception:
                    vision_resp = client.chat.completions.create(
                        model="llama-3.2-11b-vision-instruct",
                        messages=[{"role": "user", "content": content_payload}],
                        temperature=0.1,
                        max_tokens=500
                    )
                
                descricao_visual = vision_resp.choices[0].message.content

                prompt_contestacao = f"""
                Você é um perito em vistorias imobiliárias e direito do inquilino.
                Elabore uma contestação formal e bem fundamentada comparando o laudo da imobiliária com as evidências reais das fotos.

                --- LAUDO DA IMOBILIÁRIA ---
                {texto_laudo_final}

                --- DETALHES IDENTIFICADOS NAS FOTOS REALIZADAS ---
                {descricao_visual}

                Instruções:
                1. Aponta as discordâncias técnicas em relação ao laudo fornecido pela imobiliária.
                2. Redija argumentos formais e respeitosos divididos por cômodo/item divergente.
                """

                final_resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt_contestacao}],
                    temperature=0.2,
                    max_tokens=1500
                )

                resultado_texto = final_resp.choices[0].message.content

                st.success("Análise e parecer concluídos com sucesso!")
                st.subheader("📌 Resultado da Avaliação e Contestação")
                st.markdown(resultado_texto)
                
                # Guarda o texto e a lista de bytes das fotos no session_state
                st.session_state['resultado_analise'] = resultado_texto
                st.session_state['fotos_pdf_bytes'] = fotos_bytes_processadas

            except Exception as e:
                st.error(f"Erro na requisição: {e}")

# ---------------------------------------------------------
# GERADOR DE PDF DE CONTESTAÇÃO
# ---------------------------------------------------------
if 'resultado_analise' in st.session_state:
    st.divider()
    st.subheader("2. Gerar Documento de Contestação")

    pdf_bytes = gerar_pdf(
        st.session_state['resultado_analise'],
        st.session_state.get('fotos_pdf_bytes', [])
    )

    st.download_button(
        label="📄 Baixar Laudo de Contestação com Fotos em PDF",
        data=pdf_bytes,
        file_name="contestacao_vistoria_imobiliaria.pdf",
        mime="application/pdf"
    )
    
