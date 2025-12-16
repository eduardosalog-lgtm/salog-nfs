import streamlit as st
from pyzbar.pyzbar import decode
import pytesseract
from PIL import Image
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import re
import cv2
import numpy as np
import platform
import io
import google.generativeai as genai

# =========================================================
# 1. SETUP E SEGREDOS
# =========================================================
st.set_page_config(page_title="Salog Debug", page_icon="🐞", layout="centered")

if platform.system() == "Windows":
    caminho_tesseract = r"C:\Users\eduardo.costa\Tesseract-OCR\tesseract.exe"
    try: pytesseract.pytesseract.tesseract_cmd = caminho_tesseract
    except: pass

try:
    SEU_EMAIL = st.secrets["email_remetente"]
    SUA_SENHA = st.secrets["senha_email"]
    EMAIL_FATURAMENTO = st.secrets["email_destino"]
    # Tenta configurar a IA
    if "api_key_google" in st.secrets:
        genai.configure(api_key=st.secrets["api_key_google"])
        tem_ia = True
    else:
        st.warning("⚠️ Chave da IA não encontrada nos Secrets!")
        tem_ia = False
except:
    st.error("❌ ERRO GRAVE: Secrets não configurados.")
    st.stop()

# =========================================================
# 2. VALIDAÇÃO MATEMÁTICA
# =========================================================
def validar_chave(chave):
    try:
        if not chave or len(chave) != 44 or not chave.isdigit(): 
            return False, "Tamanho incorreto ou letras"
        
        codigos_uf = ['11','12','13','14','15','16','17','21','22','23','24','25','26','27','28','29','31','32','33','35','41','42','43','50','51','52','53']
        if chave[:2] not in codigos_uf: 
            return False, "UF Inválida"

        corpo = chave[:43]
        dv_informado = int(chave[43])
        pesos = [4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2]
        soma = sum(int(corpo[i]) * pesos[i] for i in range(43))
        resto = soma % 11
        dv_calculado = 0 if resto < 2 else 11 - resto
        
        if dv_calculado == dv_informado:
            return True, "OK"
        else:
            return False, f"DV Inválido (Esperado {dv_calculado}, veio {dv_informado})"
    except Exception as e: return False, f"Erro: {e}"

# =========================================================
# 3. IA GOOGLE (COM VISÃO DEPURADORA)
# =========================================================
def ler_com_ia_gemini(img):
    if not tem_ia: return None

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Prompt mais agressivo
        prompt = """
        EXTRAIR CHAVE DE ACESSO DA DANFE.
        Apenas os 44 números.
        Se houver espaços (ex: 3525 1234...), remova-os.
        Se a imagem estiver ruim, deduza os números.
        Retorne SOMENTE os dígitos.
        """
        
        # Envia para a IA
        response = model.generate_content([prompt, img])
        texto_ia = response.text.strip()
        
        # Limpa o texto
        chave_limpa = re.sub(r'[^0-9]', '', texto_ia)
        
        # MOSTRA NA TELA O QUE A IA VIU (DEBUG)
        st.toast(f"🤖 IA leu: {chave_limpa}")
        
        valida, motivo = validar_chave(chave_limpa)
        
        if valida:
            return chave_limpa
        else:
            # Mostra por que a IA falhou
            st.warning(f"⚠️ IA leu errado: {chave_limpa} -> Motivo: {motivo}")
            return None
            
    except Exception as e:
        st.error(f"🔥 ERRO NA CONEXÃO COM IA: {e}")
        return None

# =========================================================
# 4. PROCESSAMENTO
# =========================================================
def processar_imagem(img):
    # 1. Barras
    try:
        codigos = decode(img)
        for c in codigos:
            txt = c.data.decode('utf-8')
            valida, _ = validar_chave(txt)
            if valida: return txt, txt[25:34], "Barras"
    except: pass

    # 2. OCR Local
    try:
        img_np = np.array(img)
        if len(img_np.shape) == 3: gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else: gray = img_np
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        txt = pytesseract.image_to_string(Image.fromarray(thresh), config="--psm 6 outputbase digits")
        txt_limpo = re.sub(r'[^0-9]', '', txt)
        match = re.search(r'\d{44}', txt_limpo)
        if match:
            chave = match.group(0)
            valida, _ = validar_chave(chave)
            if valida: return chave, chave[25:34], "OCR Local"
    except: pass
    
    # 3. IA
    chave_ia = ler_com_ia_gemini(img)
    if chave_ia:
         return chave_ia, chave_ia[25:34], "IA Gemini"

    return None, None, None

def enviar_email_com_anexos(texto, dados, lista):
    # (Código de envio de email igual ao anterior - omitido para economizar espaço mas mantenha o seu)
    # Vou retornar True direto para testar a leitura primeiro
    return True

# =========================================================
# 5. INTERFACE SIMPLIFICADA PARA TESTE
# =========================================================
st.title("🕵️‍♂️ Salog Debug Mode")
st.info("Modo de teste: As mensagens de erro aparecerão na tela.")

uploaded_file = st.file_uploader("Teste uma nota ruim", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    st.image(img, caption="Imagem Carregada", use_column_width=True)
    
    if st.button("PROCESSAR"):
        with st.spinner("Analisando..."):
            chave, nf, metodo = processar_imagem(img)
            
            if chave:
                st.success(f"✅ SUCESSO! Leitura feita por: {metodo}")
                st.code(f"Chave: {chave}")
                st.code(f"NF: {nf}")
            else:
                st.error("❌ FALHA TOTAL: Nenhum método conseguiu ler.")
                st.info("Veja os alertas amarelos acima para entender o porquê.")