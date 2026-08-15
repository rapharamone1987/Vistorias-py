import streamlit as st
from google import genai
from google.genai.errors import APIError
from PIL import Image
import tempfile
import time
import os
from fpdf import FPDF

# ---------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Contestação de Vistoria Imobiliária",
    page_icon="🏠",
    layout="wide"
)

st.title("🏠 Auxiliar de Contestação de Vistoria Imobiliária")
st.write("Compare a vistoria da imobiliária com fotos e vídeos reais do imóvel para gerar uma contestação fundamentada.")

# ---------------------------------------------------------
# AUTENTICAÇÃO / OBTENÇÃO DA API KEY
# ---------------------------------------------------------
api_key = None

# 1. Tenta carregar a chave salva nos Secrets do Streamlit Cloud
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
elif "gemini_api_key" in st.secrets:
    api_key = st.secrets["gemini_api_key"]

# 2. Se não estiver configurada nos Secrets, exibe o campo na barra lateral (Fallback)
if not api_key:
    api_key = st.sidebar.text_input("Insira sua Gemini API Key:", type="password")

if api_key:
    client = genai.Client(api_key=api_key)
    st.sidebar.success("API Key carregada com sucesso!")
else:
    st.warning("⚠️ Insira sua API Key do Google AI Studio na barra lateral ou configure nos Secrets para começar.")
    st.stop()

# ---------------------------------------------------------
# FUNÇÃO AUXILIAR PARA GERAÇÃO DO PDF
# ---------------------------------------------------------
def gerar_pdf(texto_analise):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Laudo de Contestacao de Vistoria Imobiliaria", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=10)
    # Tratamento simples para codificação de caracteres no FPDF (Latin-1)
    linhas = texto_analise.encode('latin-1', 'replace').decode('latin-1').split('\n')
    for linha in linhas:
        pdf.multi_cell(0, 6, linha)
        
    return pdf.output(dest='S').encode('latin-1')

# ---------------------------------------------------------
# INTERFACE PRINCIPAL - ENTRADA DE DADOS
# ---------------------------------------------------------
st.header("1. Documentação e Evidências")
col1, col2 = st.columns(2)

with col1:
    st.subheader("Laudo da Imobiliária")
    laudo_texto = st.text_area(
        "Cole aqui o texto relevante da vistoria feita pela imobiliária:",
        height=250,
        placeholder="Ex: Sala de estar: Paredes pintadas na cor branca, sem manchas, piso em bom estado de conservacao..."
    )

with col2:
    st.subheader("Evidências do Inquilino")
    fotos = st.file_uploader(
        "Carregue fotos dos cômodos/avarias:",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )
    foto_camera = st.camera_input("Ou tire uma foto agora:")
    video_file = st.file_uploader(
        "Ou envie um vídeo percorrendo o imóvel (MP4, MOV):",
        type=["mp4", "mov", "avi"]
    )

# Consolidação das imagens capturadas/enviadas
imagens_para_analise = []
if fotos:
    for f in fotos:
        imagens_para_analise.append(Image.open(f))
if foto_camera:
    imagens_para_analise.append(Image.open(foto_camera))

# ---------------------------------------------------------
# PROCESSAMENTO E ANÁLISE COM GEMINI
# ---------------------------------------------------------
if st.button("🔍 Analisar e Comparar Vistoria", type="primary"):
    if not laudo_texto:
        st.error("Por favor, forneça o texto da vistoria da imobiliária.")
    elif not imagens_para_analise and not video_file:
        st.error("Por favor, envie ao menos uma foto ou um vídeo como evidência.")
    else:
        with st.spinner("Analisando evidências e cruzando com o laudo da imobiliária..."):
            prompt_base = f"""
            Você é um perito especialista em vistorias imobiliárias e direito do inquilino.
            Análise o laudo fornecido pela imobiliária e compare rigorosamente com as evidências (fotos/vídeos) enviadas pelo inquilino.

            Texto do Laudo da Imobiliária:
            {laudo_texto}

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

                    # Upload para a File API do Gemini
                    uploaded_video = client.files.upload(file=tmp_file_path)

                    # Aguarda o processamento do vídeo no servidor do Google
                    while uploaded_video.state.name == "PROCESSING":
                        time.sleep(3)
                        uploaded_video = client.files.get(name=uploaded_video.name)

                    if uploaded_video.state.name == "FAILED":
                        raise Exception("O processamento do vídeo falhou no servidor do Google.")

                    # Executa a análise do vídeo com o modelo Gemini 2.5 Flash
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[uploaded_video, prompt_base]
                    )

                    # Limpa o arquivo no servidor do Gemini
                    client.files.delete(name=uploaded_video.name)

                    # Deleta o arquivo temporário local
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)

                # CASO 2: Análise por Fotos/Imagens
                else:
                    conteudo = [prompt_base] + imagens_para_analise
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=conteudo
                    )

                st.success("Análise concluída com sucesso!")
                st.subheader("📌 Resultado da Avaliação e Contestação")
                st.markdown(response.text)
                
                # Salva o resultado no estado da sessão do Streamlit
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
