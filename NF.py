import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="Descobrir Modelos", page_icon="🕵️")
st.title("🕵️ Lista de Modelos Disponíveis")

try:
    # 1. Configura a chave
    if "api_key_google" in st.secrets:
        genai.configure(api_key=st.secrets["api_key_google"])
        st.success("✅ Chave encontrada e configurada.")
    else:
        st.error("❌ Chave não encontrada nos Secrets.")
        st.stop()

    # 2. Lista os modelos
    st.subheader("Modelos que sua conta pode acessar:")
    
    encontrou_algum = False
    modelos = genai.list_models()
    
    for m in modelos:
        # Filtra apenas modelos que geram conteúdo (texto/imagem)
        if 'generateContent' in m.supported_generation_methods:
            st.code(f"{m.name}")
            encontrou_algum = True
            
    if not encontrou_algum:
        st.warning("Nenhum modelo encontrado. Verifique se a API Key tem permissões.")

except Exception as e:
    st.error(f"Erro ao listar modelos: {e}")