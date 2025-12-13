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

# =========================================================
# 1. CONFIGURAÇÕES E SETUP
# =========================================================
st.set_page_config(page_title="Salog Express", page_icon="🚛", layout="centered")

if platform.system() == "Windows":
    caminho_tesseract = r"C:\Users\eduardo.costa\Tesseract-OCR\tesseract.exe"
    try: pytesseract.pytesseract.tesseract_cmd = caminho_tesseract
    except: pass

# --- BLOCO DE SEGURANÇA (SEM SENHAS NO CÓDIGO) ---
try:
    SEU_EMAIL = st.secrets["email_remetente"]
    SUA_SENHA = st.secrets["senha_email"]
    EMAIL_FATURAMENTO = st.secrets["email_destino"]
except:
    st.error("❌ ERRO DE CONFIGURAÇÃO: Segredos (Secrets) não encontrados.")
    st.info("Configure as senhas no painel 'Secrets' do Streamlit Cloud.")
    st.stop()

# =========================================================
# 2. VALIDAÇÃO MATEMÁTICA (MODULO 11 - NFe)
# =========================================================
def validar_chave(chave):
    try:
        # 1. Validações básicas de formato
        if not chave or len(chave) != 44 or not chave.isdigit(): return False
        
        # 2. Valida UF (Estado)
        codigos_uf = ['11','12','13','14','15','16','17','21','22','23','24','25','26','27','28','29','31','32','33','35','41','42','43','50','51','52','53']
        if chave[:2] not in codigos_uf: return False

        # 3. Cálculo do Dígito Verificador (Matemática da Receita)
        corpo = chave[:43]
        dv_informado = int(chave[43])
        pesos = [4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2,9,8,7,6,5,4,3,2]
        
        soma = sum(int(corpo[i]) * pesos[i] for i in range(43))
        resto = soma % 11
        dv_calculado = 0 if resto < 2 else 11 - resto
        
        return dv_calculado == dv_informado
    except: return False

# =========================================================
# 3. PROCESSAMENTO DE IMAGEM (COM FILTRO PARA PONTILHADO)
# =========================================================
def processar_imagem(img):
    # --- TENTATIVA 1: CÓDIGO DE BARRAS ---
    try:
        imagens_teste = [img]
        # Versão reduzida para performance
        if img.width > 2000:
            ratio = 2000 / float(img.width)
            new_h = int(float(img.height) * float(ratio))
            imagens_teste.append(img.resize((2000, new_h)))
        # Versão preto e branco direta
        img_gray_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
        imagens_teste.append(Image.fromarray(img_gray_cv))

        for imagem_atual in imagens_teste:
            codigos = decode(imagem_atual)
            for c in codigos:
                txt = c.data.decode('utf-8')
                if validar_chave(txt): return txt, txt[25:34]
    except: pass

    # --- TENTATIVA 2: OCR "RAIO-X" (CORRIGE IMPRESSÃO FALHADA) ---
    try:
        img_np = np.array(img)
        if len(img_np.shape) == 3: gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else: gray = img_np
        
        # Aumenta contraste (Preto fica mais preto, Branco mais branco)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # FILTRO MÁGICO: DILATAÇÃO (Engrossa os números pontilhados)
        kernel = np.ones((2, 2), np.uint8)
        dilated = cv2.erode(thresh, kernel, iterations=1) 
        
        img_pil = Image.fromarray(dilated)
        
        # Configuração Rígida: Proíbe letras, aceita só números (whitelist)
        config_ocr = "--psm 6 -c tessedit_char_whitelist=0123456789 outputbase digits"
        
        txt = pytesseract.image_to_string(img_pil, config=config_ocr)
        txt_limpo = re.sub(r'[^0-9]', '', txt)
        
        # Busca a chave de 44 dígitos
        match = re.search(r'\d{44}', txt_limpo)
        if match:
            chave = match.group(0)
            if validar_chave(chave): return chave, chave[25:34]
    except: pass
    
    return None, None

def enviar_email_com_anexos(texto_final, dados_viagem, lista_notas):
    try:
        motorista = dados_viagem['mot']
        pv = dados_viagem['pv']
        categoria = dados_viagem['categoria']
        obs = dados_viagem['obs']
        
        # Assunto já vem com a categoria para facilitar pro Faturamento
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
        ----------------
        Motorista: {motorista}
        PV: {pv}
        Rota: {dados_viagem['orig']} -> {dados_viagem['dest']}
        
        OBSERVAÇÕES:
        {obs if obs else "Nenhuma observação."}
        
        RESUMO:
        -------
        Qtd Notas: {len(lista_notas)}
        
        LEITURAS REALIZADAS:
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
# 4. INTERFACE
# =========================================================

st.title("🚛 Salog Express Web")

if 'etapa' not in st.session_state: st.session_state.etapa = 'dados'
if 'notas_processadas' not in st.session_state: st.session_state.notas_processadas = []

# ETAPA 1: DADOS
if st.session_state.etapa == 'dados':
    st.info("Olá Motorista! Preencha os dados da viagem.")
    
    categoria = st.selectbox(
        "Tipo de Veículo / Contratação *",
        ["FROTA", "AGREGADO", "TERCEIRO"],
        index=0
    )
    
    st.markdown("---")
    
    c1, c2 = st.columns(2)
    mot = c1.text_input("Nome do Motorista *", placeholder="Seu nome completo")
    pv = c2.text_input("Número da PV *", placeholder="Ex: 12345")
    
    c3, c4 = st.columns(2)
    orig = c3.text_input("Origem", placeholder="Cidade Coleta")
    dest = c4.text_input("Destino", placeholder="Cidade Entrega")
    
    obs = st.text_area("Observações (Opcional)", placeholder="Ex: Avaria, falta canhoto, atraso...")
    
    if st.button("Continuar ➡️", type="primary"):
        if mot and pv:
            st.session_state.dados = {
                'categoria': categoria, 'mot': mot, 'pv': pv, 
                'orig': orig, 'dest': dest, 'obs': obs
            }
            st.session_state.etapa = 'fotos'
            st.rerun()
        else:
            st.error("⚠️ Preencha seu Nome e o número da PV.")

# ETAPA 2: FOTOS
elif st.session_state.etapa == 'fotos':
    d = st.session_state.dados
    st.caption(f"Motorista: {d['mot']} ({d['categoria']}) | PV: {d['pv']}")
    
    qtd = len(st.session_state.notas_processadas)
    if qtd > 0:
        st.success(f"✅ {qtd} notas lidas")
        with st.expander("Ver lista"):
            for n in st.session_state.notas_processadas:
                status = n['nf'] if n['nf'] != "MANUAL" else "⚠️ ANÁLISE HUMANA"
                st.text(f"- {status}")
    
    st.markdown("---")
    st.subheader("📸 Tirar Fotos das Notas")
    
    uploads = st.file_uploader(
        "Toque aqui para abrir a Câmera ou Galeria", 
        type=['jpg', 'png', 'jpeg'],
        accept_multiple_files=True,
        label_visibility="visible"
    )
    
    if uploads:
        if st.button("🔍 Processar Fotos", type="primary"):
            novos = 0
            for u in uploads:
                img_u = Image.open(u)
                chave_u, nf_u = processar_imagem(img_u)
                
                if chave_u:
                    st.session_state.notas_processadas.append({'chave': chave_u, 'nf': nf_u, 'img': img_u})
                    novos += 1
                else:
                    st.session_state.notas_processadas.append({'chave': "VER ANEXO", 'nf': "MANUAL", 'img': img_u})
                    novos += 1
            
            if novos > 0:
                st.success(f"{novos} fotos adicionadas!")
                st.rerun()

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

# ETAPA 3: ENVIO
elif st.session_state.etapa == 'envio':
    st.subheader("🚀 Conferir e Enviar")
    
    texto = ""
    for item in st.session_state.notas_processadas:
        icone = "✅" if item['nf'] != "MANUAL" else "⚠️"
        texto += f"{icone} NF:{item['nf']} - CHAVE: {item['chave']}\n"
    
    st.text_area("Resumo das Notas:", value=texto, height=200, disabled=True)
    
    if st.session_state.dados['obs']:
        st.info(f"Obs: {st.session_state.dados['obs']}")

    if st.button("✈️ ENVIAR AGORA", type="primary"):
        d = st.session_state.dados
        with st.spinner("Enviando..."):
            ok = enviar_email_com_anexos(texto, d, st.session_state.notas_processadas)
            if ok:
                st.balloons()
                st.success("Enviado com sucesso! Boa viagem.")
                st.session_state.notas_processadas = []
                st.session_state.etapa = 'dados'
                if st.button("Nova Viagem"): st.rerun()
            else:
                st.error("Erro no envio.")
    
    if st.button("⬅️ Voltar"):
        st.session_state.etapa = 'fotos'
        st.rerun()