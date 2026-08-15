import streamlit as st
from google import genai
from google.genai.errors import APIError
import tempfile
import time
import os
from fpdf import FPDF

st.set_page_config(page_title="Vistoria Imobiliária - Análise de Vídeo", page_icon="🎥", layout="wide")

st.title("🎥 Vistoria Imobiliária - Contestação com IA")
st.write("Análise gratuita de vídeos e imagens para contestação de vistoria.")

# API Key
api_key = st.sidebar.text_input("Sua Gemini API Key (AI Studio - Grátis):", type="password")

if api_key:
    client = genai.Client(api_key=api_key)

    col1, col2 = st.columns(2)

    with col1:
        laudo_texto = st.text_area("Texto do Laudo da Imobiliária:", height=200)

    with col2:
        video_file = st.file_uploader("Vídeo do Imóvel (Prefira vídeos curtos de até 1 ou 2 min)", type=["mp4", "mov", "avi"])

    if st.button("🔍 Analisar Vídeo Gratuitamente", type="primary"):
        if not laudo_texto or not video_file:
            st.error("Por favor, preencha o laudo e anexe o vídeo.")
        else:
            with st.spinner("Enviando e processando vídeo no Gemini (Plano Gratuito)..."):
                # Salva o arquivo temporário
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
                    tmp_file.write(video_file.read())
                    tmp_file_path = tmp_file.name

                try:
                    # Upload para a API temporária do Gemini
                    uploaded_file = client.files.upload(file=tmp_file_path)

                    # Aguarda o processamento do vídeo
                    while uploaded_file.state.name == "PROCESSING":
                        time.sleep(3)
                        uploaded_file = client.files.get(name=uploaded_file.name)

                    if uploaded_file.state.name == "FAILED":
                        raise Exception("Falha ao processar o vídeo no servidor do Google.")

                    prompt = f"""
                    Você é um perito em vistorias imobiliárias e direito do inquilino.
                    Compare o vídeo gravado com a descrição fornecida no laudo da imobiliária.

                    Laudo da Imobiliária:
                    {laudo_texto}

                    Instruções:
                    1. Identifique manchas de umidade, pintura avariada, furos, arranhões ou problemas estruturais no vídeo.
                    2. Aponta onde o laudo da imobiliária foi omisso ou impreciso.
                    3. Elabore os pontos de contestação formal e técnica para o inquilino.
                    """

                    # Força o uso do modelo gratuito de alta performance
                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=[uploaded_file, prompt]
                    )

                    st.success("Análise concluída com sucesso!")
                    st.subheader("📌 Resultado da Avaliação")
                    st.markdown(response.text)
                    st.session_state['resultado_analise'] = response.text

                    # Limpa o arquivo da nuvem do Gemini para liberar espaço da cota
                    client.files.delete(name=uploaded_file.name)

                except APIError as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        st.error("⚠️ Limite da API Gratuita atingido para este minuto. Aguarde cerca de 1 minuto e tente novamente.")
                    else:
                        st.error(f"Erro na API do Gemini: {e}")
                except Exception as e:
                    st.error(f"Ocorreu um erro: {e}")
                finally:
                    # Deleta o arquivo temporário local
                    if os.path.exists(tmp_file_path):
                        os.remove(tmp_file_path)

    # Exportação em PDF
    if 'resultado_analise' in st.session_state:
        st.divider()
        st.subheader("📄 Gerar Laudo de Contestação")

        def gerar_pdf(texto):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, "Laudo de Contestacao de Vistoria", ln=True, align='C')
            pdf.ln(5)
            pdf.set_font("Arial", size=10)
            
            linhas = texto.encode('latin-1', 'replace').decode('latin-1').split('\n')
            for linha in linhas:
                pdf.multi_cell(0, 6, linha)
                
            return pdf.output(dest='S').encode('latin-1')

        pdf_bytes = gerar_pdf(st.session_state['resultado_analise'])
        
        st.download_button(
            label="Baixar PDF de Contestação",
            data=pdf_bytes,
            file_name="contestacao_vistoria.pdf",
            mime="application/pdf"
        )
else:
    st.warning("Insira sua API Key do Google AI Studio para começar.")
      
