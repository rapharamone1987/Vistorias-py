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
st.write("Compare o laudo oficial com fotos do imóvel para gerar uma contestação fundamentada via **Groq (Llama 3.2 Vision)**.")

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

# Inicializa o armazenamento de fotos tiradas na hora
if 'fotos_camera' not in st.session_state:
    st.session_state['fotos_camera'] = []

# ---------------------------------------------------------
# FUNÇÕES AUXILIARES
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

def encode_image_to_base64(pil_image):
    buffered = io.BytesIO()
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")
    pil_image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

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

# Consolida todas as imagens
imagens_totais = []
if fotos_upload:
    for f in fotos_upload:
        imagens_totais.append(Image.open(f))
if st.session_state['fotos_camera']:
    imagens_totais.extend(st.session_state['fotos_camera'])

# ---------------------------------------------------------
# PROCESSAMENTO E ANÁLISE COM GROQ
# ---------------------------------------------------------
st.divider()

if st.button("🔍 Analisar e Comparar Vistoria (Groq)", type="primary", use_container_width=True):
    if not texto_laudo_final:
        st.error("Por favor, envie o arquivo do laudo ou cole o texto da vistoria.")
    elif not imagens_totais:
        st.error("Por favor, envie ou tire ao menos uma foto como evidência.")
    else:
        with st.spinner("Analisando imagens e comparando com o laudo via Groq (Llama 3.2 90B Vision)..."):
            try:
                # Prompt de instrução técnica
                prompt_text = f"""
                Você é um perito especialista em vistorias imobiliárias e direito do inquilino.
                Análise o laudo fornecido pela imobiliária e compare rigorosamente com as evidências (fotos) enviadas pelo inquilino.

                Texto/Conteúdo da Vistoria da Imobiliária:
                {texto_laudo_final}

                Instruções para a análise:
                1. Avalie detalhadamente o estado das superfícies, pintura, manchas de umidade, arranhões, furos, trincas ou defeitos visíveis nas imagens.
                2. Verifique se o laudo da imobiliária descreve com precisão o estado real do imóvel ou se omitiu/descreveu incorretamente algum detalhe.
                3. Identifique onde há discordâncias claras.
                4. Elabore uma contestação formal, técnica e respeitosa para cada ponto divergente, citando o cômodo e o problema identificado para que o inquilino possa protocolar na imobiliária.

                Estruture a resposta de forma clara, dividida por cômodos ou pontos contestados.
                """

                # Monta a estrutura da mensagem com texto e imagens em Base64
                content_payload = [
                    {
                        "type": "text",
                        "text": prompt_text
                    }
                ]

                # Adiciona as imagens preparadas para o Llama 3.2 Vision
                for img in imagens_totais:
                    base64_str = encode_image_to_base64(img)
                    content_payload.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_str}"
                        }
                    })

                # Chamada para o modelo visual avançado de 90B da Groq
                completion = client.chat.completions.create(
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    messages=[
                        {
                            "role": "user",
                            "content": content_payload
                        }
                    ],
                    temperature=0.2,
                    max_tokens=2048
                )

                resultado_texto = completion.choices[0].message.content

                st.success("Análise concluída com sucesso!")
                st.subheader("📌 Resultado da Avaliação e Contestação")
                st.markdown(resultado_texto)
                
                st.session_state['resultado_analise'] = resultado_texto

            except Exception as e:
                st.error(f"Erro ao processar a solicitação na Groq: {e}")

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
