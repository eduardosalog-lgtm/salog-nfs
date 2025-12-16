import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="Teste de Vida IA", page_icon="🧪")

st.title("🧪 Diagnóstico de Conexão")

# 1. VERIFICAR SE O STREAMLIT ESTÁ LENDO A SENHA
st.header("Passo 1: Verificando Secrets")

if "api_key_google" in st.secrets:
    chave = st.secrets["api_key_google"]
    # Mostra os 5 primeiros e 5 últimos caracteres para você conferir
    st.success(f"✅ Chave encontrada!")
    st.code(f"Início: {chave[:5]}... Fim: ...{chave[-5:]}")
    
    # Configura a biblioteca
    genai.configure(api_key=chave)
    tem_config = True
else:
    st.error("❌ A chave 'api_key_google' NÃO foi encontrada nos Secrets.")
    st.info("Vá em Settings > Secrets e verifique se o nome está exato: api_key_google")
    tem_config = False

# 2. TESTE DE CONEXÃO REAL (PING)
st.header("Passo 2: Testando o Cérebro da IA")

if tem_config:
    if st.button("Fazer Pergunta para o Google Gemini"):
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content("Responda apenas: CONEXÃO BEM SUCEDIDA")
            
            st.balloons()
            st.success("✅ A IA RESPONDEU:")
            st.write(f"🤖 Resposta: **{response.text}**")
            
        except Exception as e:
            st.error("🔥 A chave existe, mas a conexão falhou!")
            st.warning("Motivo do erro abaixo (mande print disso):")
            st.code(e)