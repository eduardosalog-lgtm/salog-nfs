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
# 1. CONFIGURAÇÕES E SETUP
# =========================================================
st.set_page_config(page_title="Salog Express", page_icon="🚛", layout="centered")

if platform.system() == "Windows":
    caminho_tesseract = r"C:\Users\eduardo.costa\Tesseract-OCR\tesseract.exe"
    try: pytesseract.pytesseract.tesseract_cmd = caminho_tesseract
    except: pass

# --- SEGREDOS ---
try:
    SEU_EMAIL = st.secrets["email_remetente"]
    SUA_SENHA = st.secrets["senha_email"]
    EMAIL_FATURAMENTO = st.secrets["email_destino"]
    genai.configure(api_key=st.secrets["api_key_google"])
except:
    st.error("❌ ERRO: Configure os Secrets (E-mail e API do Google).")
    st.stop()

# =========================================================
# 2. VALIDAÇÃO MATEMÁTICA
# =========================================================
def validar_chave(chave):
    try:
        if not chave or len(chave) != 44 or not chave.isdigit(): return False
        codigos_uf = ['11','12','13','14','15','16','17','21','22','23','24','25','26','27','28','29','31','32','33','35','41','42','43','50','51','52','53']
        if chave[:2] not in codigos_uf: return False
        corpo = chave[:43]
        dv_informado = int(chave[43])
        pesos = [4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2]
        soma = sum(int(corpo[i]) * pesos[i] for i in range(43))
        resto = soma % 11
        dv_calculado = 0 if resto < 2 else 11 - resto
        return dv_calculado == dv_informado
    except: return False

# =========================================================
# 3. FUNÇÃO IA (ATUALIZADA PARA VERSÃO 2.5)
# =========================================================
def ler_com_ia_gemini(img):
    try:
        # ATUALIZADO: Usando o modelo que sua conta tem acesso
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Desativa bloqueios para ler documentos
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        prompt = """
        Atue como um leitor de código de barras e OCR profissional.
        Analise a imagem desta Nota Fiscal (DANFE).
        Encontre a CHAVE DE ACESSO de 44 dígitos numéricos.
        Geralmente está no canto superior direito ou abaixo do código de barras.
        Retorne APENAS os 44 números. Remova espaços ou pontos.
        """
        
        response = model.generate_content([prompt, img], safety_settings=safety_settings)
        texto_ia = response.text.strip()
        
        chave_limpa = re.sub(r'[^0-9]', '', texto_ia)
        
        if validar_chave(chave_limpa):
            return chave_limpa
        else:
            print(f"IA leu inválido: {chave_limpa}")
            return None
    except Exception as e:
        st.error(f"Erro na IA: {e}")
        return None

# =========================================================
# 4. PROCESSAMENTO CASCATA
# =========================================================
def processar_imagem(img):
    # 1. BARRAS
    try:
        imagens_teste = [img]
        if img.width > 2000:
            ratio = 2000 / float(img.width)
            new_h = int(float(img.height) * float(ratio))
            imagens_teste.append(img.resize((2000, new_h)))
        img_gray_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        imagens_teste.append(Image.fromarray(img_gray_cv))

        for imagem_atual in imagens_teste:
            codigos = decode(imagem_atual)
            for c in codigos:
                txt = c.data.decode('utf-8')
                if validar_chave(txt): return txt, txt[25:34], "Código de Barras"
    except: pass

    # 2. OCR LOCAL
    try:
        img_np = np.array(img)
        if len(img_np.shape) == 3: gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else: gray = img_np
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.ones((2, 2), np.uint8)
        dilated = cv2.erode(thresh, kernel, iterations=1) 
        img_pil = Image.fromarray(dilated)
        config_ocr = "--psm 6 -c tessedit_char_whitelist=0123456789 outputbase digits"
        txt = pytesseract.image_to_string(img_pil, config=config_ocr)
        txt_limpo = re.sub(r'[^0-9]', '', txt)
        match = re.search(r'\d{44}', txt_limpo)
        if match:
            chave = match.group(0)
            if validar_chave(chave): return chave, chave[25:34], "OCR Local"
    except: pass
    
    # 3. IA GEMINI 2.5
    chave_ia = ler_com_ia_gemini(img)
    if chave_ia:
         return chave_ia, chave_ia[25:34], "IA Gemini 2.5 🤖"

    return None, None, None

def enviar_email_com_anexos(texto_final, dados_viagem, lista_notas):
    try:
        motorista = dados_viagem['mot']
        pv = dados_viagem['pv']
        categoria = dados_viagem['categoria']
        obs = dados_viagem['obs']
        
        assunto = f"[{categoria}] PV {pv} - {motorista}"
        msg = MIMEMultipart()
        msg['Subject'] = assunto
        msg['From'] = SEU_EMAIL
        msg['To'] = EMAIL_FATURAMENTO
        
        corpo = f"""
        ENTREGA DE NOTAS - APP LOGÍSTICA
        ================================
        CATEGORIA: {categoria}
        DADOS DA VIAGEM:
        Motorista: {motorista} | PV: {pv}
        Rota: {dados_viagem['orig']} -> {dados_viagem['dest']}
        OBSERVAÇÕES: {obs if obs else "Nenhuma."}
        
        LEITURAS:
        {texto_final}
        """
        msg.attach(MIMEText(corpo, 'plain'))
        
        for i, item in enumerate(lista_notas):
            try:
                img_byte_arr = io.BytesIO()
                item['img'].save(img_byte_arr, format='JPEG', quality=85)
                img_byte_arr = img_byte_arr.getvalue()
                part = MIMEBase('application', "octet-stream")
                part.set_payload(img_byte_arr)
                encoders.encode_base64(part)
                nome_arq = f"NF_{item['nf']}.jpg" if item['nf'] != "MANUAL" else f"FOTO_MANUAL_{i+1}.jpg"
                part.add_header('Content-Disposition', f'attachment; filename="{nome_arq}"')
                msg.attach(part)
            except: pass

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SEU_EMAIL, SUA_SENHA)
        server.sendmail(SEU_EMAIL, EMAIL_FATURAMENTO, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return False

# =========================================================
# 5. INTERFACE
# =========================================================

st.title("🚛 Salog Express Web")

if 'etapa' not in st.session_state: st.session_state.etapa = 'dados'
if 'notas_processadas' not in st.session_state: st.session_state.notas_processadas = []

if st.session_state.etapa == 'dados':
    st.info("Olá Motorista! Preencha os dados da viagem.")
    categoria = st.selectbox("Tipo de Veículo / Contratação *", ["FROTA", "AGREGADO", "TERCEIRO"], index=0)
    st.markdown("---")
    c1, c2 = st.columns(2)
    mot = c1.text_input("Nome do Motorista *", placeholder="Seu nome completo")
    pv = c2.text_input("Número da PV *", placeholder="Ex: 12345")
    c3, c4 = st.columns(2)
    orig = c3.text_input("Origem", placeholder="Cidade Coleta")
    dest = c4.text_input("Destino", placeholder="Cidade Entrega")
    obs = st.text_area("Observações (Opcional)")
    
    if st.button("Continuar ➡️", type="primary"):
        if mot and pv:
            st.session_state.dados = {'categoria': categoria, 'mot': mot, 'pv': pv, 'orig': orig, 'dest': dest, 'obs': obs}
            st.session_state.etapa = 'fotos'
            st.rerun()
        else: st.error("⚠️ Preencha seu Nome e o número da PV.")

elif st.session_state.etapa == 'fotos':
    d = st.session_state.dados
    st.caption(f"Motorista: {d['mot']} ({d['categoria']}) | PV: {d['pv']}")
    
    qtd = len(st.session_state.notas_processadas)
    if qtd > 0:
        st.success(f"✅ {qtd} notas lidas")
        with st.expander("Ver lista"):
            for n in st.session_state.notas_processadas:
                metodo = f" ({n.get('metodo', 'Manual')})" if n['nf'] != "MANUAL" else ""
                st.text(f"- NF: {n['nf']}{metodo}")
    
    st.markdown("---")
    st.subheader("📸 Tirar Fotos das Notas")
    uploads = st.file_uploader("Toque aqui para abrir a Câmera ou Galeria", type=['jpg', 'png', 'jpeg'], accept_multiple_files=True)
    
    if uploads:
        if st.button("🔍 Processar Fotos", type="primary"):
            novos = 0
            progresso = st.progress(0)
            status_text = st.empty()
            total = len(uploads)
            
            for i, u in enumerate(uploads):
                status_text.text(f"Analisando nota {i+1}/{total} (Isso pode levar alguns segundos)...")
                progresso.progress((i)/total)
                img_u = Image.open(u)
                chave, nf, metodo = processar_imagem(img_u)
                
                if chave:
                    st.session_state.notas_processadas.append({'chave': chave, 'nf': nf, 'img': img_u, 'metodo': metodo})
                    novos += 1
                else:
                    st.session_state.notas_processadas.append({'chave': "VER ANEXO", 'nf': "MANUAL", 'img': img_u, 'metodo': "Falha"})
                    novos += 1
            
            progresso.progress(1.0)
            status_text.text("Concluído!")
            if novos > 0: st.rerun()

    st.markdown("---")
    c_v, c_a = st.columns(2)
    if c_v.button("⬅️ Corrigir Dados"):
        st.session_state.etapa = 'dados'
        st.rerun()
    if c_a.button("Finalizar Envio ➡️", type="primary"):
        if qtd > 0:
            st.session_state.etapa = 'envio'
            st.rerun()
        else: st.error("Tire foto de pelo menos uma nota.")

elif st.session_state.etapa == 'envio':
    st.subheader("🚀 Conferir e Enviar")
    texto = ""
    for item in st.session_state.notas_processadas:
        icone = "✅" if item['nf'] != "MANUAL" else "⚠️"
        metodo = f"[{item.get('metodo', 'Manual')}]" if item['nf'] != "MANUAL" else ""
        texto += f"{icone} NF:{item['nf']} {metodo} - CHAVE: {item['chave']}\n"
    
    st.text_area("Resumo:", value=texto, height=200, disabled=True)
    if st.button("✈️ ENVIAR AGORA", type="primary"):
        with st.spinner("Enviando..."):
            if enviar_email_com_anexos(texto, st.session_state.dados, st.session_state.notas_processadas):
                st.balloons()
                st.success("Sucesso! E-mail enviado.")
                st.session_state.notas_processadas = []
                st.session_state.etapa = 'dados'
                if st.button("Nova Viagem"): st.rerun()
            else: st.error("Erro no envio do e-mail.")
    if st.button("⬅️ Voltar"):
        st.session_state.etapa = 'fotos'
        st.rerun()