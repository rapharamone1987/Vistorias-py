import streamlit as st
from google import genai
from google.genai.errors import APIError
from PIL import Image
import tempfile
import time
import os
from fpdf import FPDF
import pypdf # Usado para extrair texto de PDFs da imobiliária

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Contestação de Vistoria Imobiliária",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Auxiliar de Contestação de Vistoria Imobiliária")
st.write("Compare o laudo oficial com fotos e vídeos reais do imóvel para gerar uma contestação fundamentada.")

# ---------------------------------------------------------
# AUTENTICAÇÃO / OBTENÇÃO DA API KEY
# ---------------------------------------------------------
api_key = None

if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
elif "gemini_api_key" in st.secrets:
    api_key = st.secrets["gemini_api_key"]

if not api_key:
    api_key = st.sidebar.text_input("Insira sua Gemini API Key:", type="password")

if api_key:
    client = genai.Client(api_key=api_key)
    st.sidebar.success("API Key carregada com sucesso!")
else:
    st.warning("⚠️ Insira sua API Key do Google AI Studio para começar.")
    st.stop()

# Inicializa o armazenamento de fotos tiradas na hora
if 'fotos_camera' not in st.session_state:
    st.session_state['fotos_camera'] = []

# ---------------------------------------------------------
# FUNÇÃO AUXILIAR PARA EXTRAIR TEXTO DE PDF/TXT
# ---------------------------------------------------------
def extrair_texto_arquivo(arquivo):
    if arquivo.name.endswith('.pdf'):
        try:
            pdf_reader = pypdf.PdfReader(arquivo)
            texto = ""
            for page in pdf_reader.pages:
                texto += page.extract_text() + "\n"
            return texto
        except Exception as e:
            return f"Erro ao ler PDF: {e}"
    elif arquivo.name.endswith('.txt'):
        return arquivo.read().decode('utf-8', errors='ignore')
    return ""

# ---------------------------------------------------------
# FUNÇÃO AUXILIAR PARA GERAÇÃO DO PDF FINAL
# ---------------------------------------------------------
def gerar_pdf(texto_analise):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Laudo de Contestacao de Vistoria Imobiliaria", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=10)
    linhas = texto_analise.encode('latin-1', 'replace').decode('latin-1').split('\n')
    for linha in linhas:
        pdf.multi_cell(0, 6, linha)
        
    return pdf.output(dest='S').encode('latin-1')

# ---------------------------------------------------------
# INTERFACE PRINCIPAL - ENTRADA DE DADOS
# ---------------------------------------------------------
st.header("1. Documentação e Evidências")
col1, col2 = st.columns(2)

# --- COLUNA 1: LAUDO DA IMOBILIÁRIA ---
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
    
    # Consolida o texto do laudo (Prioriza arquivo se enviado)
    texto_laudo_final = ""
    if arquivo_laudo:
        texto_extraido = extrair_texto_arquivo(arquivo_laudo)
        if texto_extraido:
            texto_laudo_final = texto_extraido
            st.info("✅ Texto do arquivo de vistoria extraído com sucesso!")
    elif laudo_texto_manual:
        texto_laudo_final = laudo_texto_manual

# --- COLUNA 2: EVIDÊNCIAS DO INQUILINO ---
with col2:
    st.subheader("📸 Evidências do Inquilino")
    
    # Upload de fotos existentes
    fotos_upload = st.file_uploader(
        "Carregue fotos salvas do imóvel (JPEG/PNG):",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )
    
    # Captura de múltiplas fotos pela câmera
    st.write("**Tirar fotos na hora:**")
    foto_capturada = st.camera_input("Tire uma foto de um defeito/cômodo")
    
    if foto_capturada:
        # Abre a imagem e salva na sessão se ainda não tiver sido salva
        img_temp = Image.open(foto_capturada)
        # Evita duplicar a mesma foto no clique do re-render
        if img_temp not in st.session_state['fotos_camera']:
            st.session_state['fotos_camera'].append(img_temp)
            st.toast(f"Foto {len(st.session_state['fotos_camera'])} adicionada!")

    # Exibe contador e botão de limpar galeria da câmera
    if st.session_state['fotos_camera']:
        st.write(f"📷 Fotos tiradas na hora: **{len(st.session_state['fotos_camera'])}**")
        if st.button("🗑️ Limpar fotos tiradas na hora"):
            st.session_state['fotos_camera'] = []
            st.rerun()

    # Upload de Vídeo
    video_file = st.file_uploader(
        "Ou envie um vídeo percorrendo o imóvel (MP4, MOV):",
        type=["mp4", "mov", "avi"]
    )

# Consolida todas as imagens (Upload + Câmera)
imagens_totais = []
if fotos_upload:
    for f in fotos_upload:
        imagens_totais.append(Image.open(f))
if st.session_state['fotos_camera']:
    imagens_totais.extend(st.session_state['fotos_camera'])

# ---------------------------------------------------------
# PROCESSAMENTO E ANÁLISE COM GEMINI
# ---------------------------------------------------------
st.divider()

if st.button("🔍 Analisar e Comparar Vistoria", type="primary", use_container_width=True):
    if not texto_laudo_final:
        st.error("Por favor, envie o arquivo do laudo ou cole o texto da vistoria.")
    elif not imagens_totais and not video_file:
        st.error("Por favor, envie ou tire ao menos uma foto, ou carregue um vídeo como evidência.")
    else:
        with st.spinner("Analisando evidências e cruzando com o laudo da imobiliária..."):
            prompt_base = f"""
            Você é um perito especialista em vistorias imobiliárias e direito do inquilino.
            Análise o laudo fornecido pela imobiliária e compare rigorosamente com as evidências (fotos/vídeos) enviadas pelo inquilino.

            Texto/Conteúdo da Vistoria da Imobiliária:
            {texto_laudo_final}

            Instruções para a análise:
            1. Avalie detalhadamente o estado das superfícies, pintura, manchas de umidade, arranhões, furos, trincas ou defeitos visíveis nas mídias fornecidas.
            2. Verifique se o laudo da imobiliária descreve com precisão o estado real do imóvel ou se omitiu/descreveu incorretamente algum detalhe.
            3. Identifique onde há discordâncias claras.
            4. Elabore uma contestação formal, técnica e respeitosa para cada ponto divergente, citando o cômodo e o problema identificado para que o inquilino possa protocolar na imobiliária.

            Estruture a resposta de forma clara, dividida por cômodos ou pontos contestados.
            """

            try:
                # CASO 1: Análise por Vídeo
                if video_file:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
                        tmp_file.write(video_file.read())
                        tmp_file_path = tmp_file.name

                    uploaded_video = client.files.upload(file=tmp_file_path)

                    while uploaded_video.state.name == "PROCESSING":
                        time.sleep(3)
                        uploaded_video = client.files.get(name=uploaded_video.name)

                    if uploaded_video.state.name == "FAILED":
                        raise Exception("O processamento do vídeo falhou no servidor do Google.")

                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[uploaded_video, prompt_base]
                    )

                    client.files.delete(name=uploaded_video.name)
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)

                # CASO 2: Análise por Fotos/Imagens
                else:
                    conteudo = [prompt_base] + imagens_totais
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=conteudo
                    )

                st.success("Análise concluída com sucesso!")
                st.subheader("📌 Resultado da Avaliação e Contestação")
                st.markdown(response.text)
                
                st.session_state['resultado_analise'] = response.text

            except APIError as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    st.error("⚠️ Limite da API Gratuita atingido neste minuto. Aguarde cerca de 1 minuto e tente novamente.")
                else:
                    st.error(f"Erro na API do Gemini: {e}")
            except Exception as e:
                st.error(f"Ocorreu um erro ao processar a solicitação: {e}")

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
    
