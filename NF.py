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
st.set_page_config(page_title="Salog Enfio de NF", page_icon="🚛", layout="centered")

# Configuração Tesseract (Windows vs Linux/Cloud)
if platform.system() == "Windows":
    caminho_tesseract = r"C:\Users\eduardo.costa\Tesseract-OCR\tesseract.exe"
    try: pytesseract.pytesseract.tesseract_cmd = caminho_tesseract
    except: pass

# =========================================================
# 2. SEGURANÇA DE E-MAILS
# =========================================================
# Tenta pegar dos segredos da nuvem ou local
try:
    SEU_EMAIL = st.secrets["email_remetente"]
    SUA_SENHA = st.secrets["senha_email"]
    EMAIL_FATURAMENTO = st.secrets["email_destino"]
except FileNotFoundError:
    st.error("Erro: Segredos não configurados. Configure no Streamlit Cloud.")
    st.stop()

# =========================================================
# 2. FUNÇÕES DO SISTEMA (OCR E EMAIL)
# =========================================================
def processar_imagem(img):
    # 1. Tenta Código de Barras
    try:
        if img.width > 2000:
            ratio = 2000 / float(img.width)
            new_h = int(float(img.height) * float(ratio))
            img_red = img.resize((2000, new_h))
        else: img_red = img
        codigos = decode(img_red)
        for c in codigos:
            txt = c.data.decode('utf-8')
            if len(txt) == 44 and txt.isdigit(): return txt, txt[25:34]
    except: pass

    # 2. Tenta OCR Turbinado
    try:
        img_np = np.array(img)
        if len(img_np.shape) == 3: gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        else: gray = img_np
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        img_pil = Image.fromarray(thresh)
        txt = pytesseract.image_to_string(img_pil, config="--psm 6 outputbase digits")
        txt_limpo = re.sub(r'[^0-9]', '', txt)
        match = re.search(r'\d{44}', txt_limpo)
        if match:
            chave = match.group(0)
            return chave, chave[25:34]
    except: pass
    return None, None

def enviar_email_com_anexos(texto_final, dados_viagem, lista_notas):
    # Recupera os dados organizados
    usuario_envio = dados_viagem['usuario']
    motorista = dados_viagem['mot']
    pv = dados_viagem['pv']
    obs = dados_viagem['obs']
    
    assunto = f"PV {pv} - {motorista}"
    
    msg = MIMEMultipart()
    msg['Subject'] = assunto
    msg['From'] = SEU_EMAIL
    msg['To'] = EMAIL_FATURAMENTO
    
    # Monta o corpo do e-mail
    corpo = f"""
    ENTREGA DE NOTAS - APP LOGÍSTICA
    ================================
    ENVIADO POR: {usuario_envio}
    
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
    
    # Anexa as fotos
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

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SEU_EMAIL, SUA_SENHA)
        server.sendmail(SEU_EMAIL, EMAIL_FATURAMENTO, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        return False

# =========================================================
# 3. APLICAÇÃO PRINCIPAL (SEM LOGIN)
# =========================================================

st.title("🚛 Salog Express Web")

if 'etapa' not in st.session_state: st.session_state.etapa = 'dados'
if 'notas_processadas' not in st.session_state: st.session_state.notas_processadas = []

# --- ETAPA 1: DADOS ---
if st.session_state.etapa == 'dados':
    st.info("Preencha os dados da viagem.")
    
    # CAMPO 1: QUEM ESTÁ ENVIANDO (OBRIGATÓRIO)
    usuario_envio = st.text_input("👤 Quem está enviando? (Seu Nome) *", placeholder="Ex: Eduardo Costa")
    
    st.markdown("---")
    
    c1, c2 = st.columns(2)
    mot = c1.text_input("Motorista *", placeholder="Nome do Motorista")
    pv = c2.text_input("PV *", placeholder="Número PV")
    
    c3, c4 = st.columns(2)
    orig = c3.text_input("Origem", placeholder="Cidade Coleta")
    dest = c4.text_input("Destino", placeholder="Cidade Entrega")
    
    # CAMPO OBS (OPCIONAL)
    obs = st.text_area("📝 Observações (Opcional)", placeholder="Ex: Nota com rasura, vidro quebrado, falta canhoto...")
    
    if st.button("Continuar ➡️", type="primary"):
        # Validação: Usuário, Motorista e PV são cruciais
        if usuario_envio and mot and pv:
            st.session_state.dados = {
                'usuario': usuario_envio,
                'mot': mot, 
                'pv': pv, 
                'orig': orig, 
                'dest': dest,
                'obs': obs
            }
            st.session_state.etapa = 'fotos'
            st.rerun()
        else:
            st.error("⚠️ Faltando: Seu Nome, Motorista ou PV.")

# --- ETAPA 2: FOTOS ---
elif st.session_state.etapa == 'fotos':
    d = st.session_state.dados
    st.caption(f"Enviado por: {d['usuario']} | PV: {d['pv']}")
    
    qtd = len(st.session_state.notas_processadas)
    if qtd > 0:
        st.success(f"✅ {qtd} notas na cesta")
        with st.expander("Ver lista"):
            for n in st.session_state.notas_processadas:
                status = n['nf'] if n['nf'] != "MANUAL" else "⚠️ ANÁLISE HUMANA"
                st.text(f"- {status}")
    
    st.markdown("---")
    st.subheader("📸 Nova Nota")
    
    foto = st.camera_input("Tirar Foto")
    
    if foto:
        col_verif, col_forcar = st.columns(2)
        with col_verif:
            if st.button("🔍 Verificar", type="primary"):
                with st.spinner("Lendo..."):
                    img_pil = Image.open(foto)
                    chave, nf = processar_imagem(img_pil)
                    if chave:
                        st.session_state.notas_processadas.append({'chave': chave, 'nf': nf, 'img': img_pil})
                        st.toast(f"NF {nf} lida!", icon="✅")
                        st.rerun()
                    else:
                        st.error("❌ Não leu.")
                        st.session_state.falha_leitura = True
        
        if 'falha_leitura' in st.session_state:
            if st.button("⚠️ Anexar para Análise Humana"):
                img_pil = Image.open(foto)
                st.session_state.notas_processadas.append({'chave': "FALHA LEITURA", 'nf': "MANUAL", 'img': img_pil})
                del st.session_state['falha_leitura']
                st.rerun()

    with st.expander("📂 Upload da Galeria"):
        uploads = st.file_uploader("Arquivos", accept_multiple_files=True)
        if uploads:
            if st.button("Processar Arquivos"):
                for u in uploads:
                    img_u = Image.open(u)
                    chave_u, nf_u = processar_imagem(img_u)
                    if chave_u:
                        st.session_state.notas_processadas.append({'chave': chave_u, 'nf': nf_u, 'img': img_u})
                    else:
                        st.session_state.notas_processadas.append({'chave': "VER ANEXO", 'nf': "MANUAL", 'img': img_u})
                st.rerun()
    
    st.markdown("---")
    c_v, c_a = st.columns(2)
    if c_v.button("⬅️ Voltar"):
        st.session_state.etapa = 'dados'
        st.rerun()
    if c_a.button("Finalizar Envio ➡️", type="primary"):
        if qtd > 0:
            st.session_state.etapa = 'envio'
            st.rerun()
        else: st.error("Adicione nota.")

# --- ETAPA 3: ENVIO ---
elif st.session_state.etapa == 'envio':
    st.subheader("🚀 Conferência Final")
    texto = ""
    for item in st.session_state.notas_processadas:
        icone = "✅" if item['nf'] != "MANUAL" else "⚠️"
        texto += f"{icone} NF:{item['nf']} - CHAVE: {item['chave']}\n"
    
    st.text_area("Resumo:", value=texto, height=200, disabled=True)
    
    if st.session_state.dados['obs']:
        st.info(f"📝 Obs: {st.session_state.dados['obs']}")

    if st.button("✈️ ENVIAR TUDO", type="primary"):
        d = st.session_state.dados
        with st.spinner("Enviando..."):
            ok = enviar_email_com_anexos(texto, d, st.session_state.notas_processadas)
            if ok:
                st.balloons()
                st.success("Enviado com sucesso!")
                st.session_state.notas_processadas = []
                st.session_state.etapa = 'dados'
                if st.button("Nova Viagem"): st.rerun()
            else:
                st.error("Erro no envio.")
    
    if st.button("⬅️ Voltar"):
        st.session_state.etapa = 'fotos'
        st.rerun()