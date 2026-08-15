import streamlit as st
from groq import Groq
from PIL import Image
from fpdf import FPDF
import pypdf
import base64
import io

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

def encode_image_to_base64(pil_image, max_size=(600, 600), quality=60):
    buffered = io.BytesIO()
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    pil_image.thumbnail(max_size, Image.Resampling.LANCZOS)
    pil_image.save(buffered, format="JPEG", quality=quality)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def gerar_pdf(texto_analise):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    # Título principal
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, "Laudo de Contestacao de Vistoria Imobiliaria", ln=True, align='C')
    pdf.ln(5)
    
    # Corpo do texto
    pdf.set_font("Arial", size=10)
    texto_limpo = texto_analise.encode('latin-1', 'replace').decode('latin-1')
    
    for linha in texto_limpo.split('\n'):
        linha_formatada = linha.strip()
        if linha_formatada:
            pdf.multi_cell(190, 6, linha_formatada)
        else:
            pdf.ln(3)
        
    return pdf.output(dest='S').encode('latin-1')

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
                # ETAPA 1: Processamento de Visão Computacional
                content_payload = [
                    {
                        "type": "text",
                        "text": "Analise as imagens e descreva com precisão técnica todas as avarias, sujeiras, furos, riscos, manchas de umidade ou defeitos visíveis:"
                    }
                ]

                for img in imagens_totais[:2]:
                    base64_str = encode_image_to_base64(img)
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

                # ETAPA 2: Redação da Contestação Técnica (Llama 3.3 70B Versatile)
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
                
                st.session_state['resultado_analise'] = resultado_texto

            except Exception as e:
                st.error(f"Erro na requisição: {e}")

# ---------------------------------------------------------
# GERADOR DE PDF DE CONTESTAÇÃO
# ---------------------------------------------------------
if 'resultado_analise' in st.session_state:
    st.divider()
    st.subheader("2. Gerar Documento de Contestação")

    pdf_bytes = gerar_pdf(st.session_state['resultado_analise'])

    st.download_button(
        label="📄 Baixar Laudo de Contestação em PDF",
        data=pdf_bytes,
        file_name="contestacao_vistoria_imobiliaria.pdf",
        mime="application/pdf"
    )
    
