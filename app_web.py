import os
import json
import tempfile
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from pypdf import PdfReader
from audio_recorder_streamlit import audio_recorder


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

st.set_page_config(
    page_title="Policía IA - Poio",
    page_icon="🚓",
    layout="wide",
)


# =========================================================
# UTILIDADES DE ARCHIVO
# =========================================================

def asegurar_carpeta(nombre_carpeta: str) -> None:
    if not os.path.exists(nombre_carpeta):
        os.makedirs(nombre_carpeta)


def guardar_txt(documento: str, prefijo: str) -> str:
    asegurar_carpeta("informes")
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join("informes", f"{prefijo}_{marca_tiempo}.txt")
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write(documento)
    return ruta


def guardar_json(datos: dict, prefijo: str) -> str:
    asegurar_carpeta("datos")
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join("datos", f"{prefijo}_{marca_tiempo}.json")
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=4)
    return ruta


def guardar_txt_con_nombre(documento: str, nombre: str) -> str:
    asegurar_carpeta("informes")
    ruta = os.path.join("informes", f"{nombre}.txt")
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write(documento)
    return ruta


def limpiar_espacios(texto: str) -> str:
    return " ".join((texto or "").split())


def capitalizar_si_corresponde(campo: str, valor: str) -> str:
    valor = limpiar_espacios(valor)
    if not valor:
        return valor

    campos_sensibles = {
        "vehículo a",
        "vehículo b",
        "agentes actuantes (nip)",
        "agentes",
        "agentes actuantes",
        "prueba de alcoholemia (indicar resultado o 'no procede')",
        "prueba de drogas (indicar resultado o 'no procede')",
    }

    if campo.lower() in campos_sensibles:
        return valor

    if "matrícula" in campo.lower():
        return valor.upper()

    return valor[0].upper() + valor[1:] if valor else valor


def normalizar_datos(diccionario: dict) -> dict:
    return {k: capitalizar_si_corresponde(k, v) for k, v in diccionario.items()}


def construir_bloque_usuario(datos: dict) -> str:
    return "\n".join([f"{k}: {v}" for k, v in datos.items() if str(v).strip()])


# =========================================================
# OPENAI
# =========================================================

@st.cache_resource(show_spinner=False)
def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def generar_texto_con_ia(api_key: str, prompt_sistema: str, datos_usuario: str) -> str:
    client = get_client(api_key)
    respuesta = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.15,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": datos_usuario},
        ],
    )
    return respuesta.choices[0].message.content or ""


def transcribir_audio_con_openai(api_key: str, audio_bytes: bytes) -> str:
    client = get_client(api_key)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            transcripcion = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
            )
        return getattr(transcripcion, "text", "") or ""
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# =========================================================
# PDF / BASES LEGALES
# =========================================================

@st.cache_data(show_spinner=False)
def extraer_texto_pdf_path(ruta_pdf: str) -> str:
    if not ruta_pdf or not os.path.exists(ruta_pdf):
        return ""
    try:
        lector = PdfReader(ruta_pdf)
        paginas = []
        for pagina in lector.pages:
            texto = pagina.extract_text()
            if texto:
                paginas.append(texto)
        return "\n".join(paginas)
    except Exception:
        return ""


@st.cache_data(show_spinner=False)
def extraer_texto_pdf_upload(archivo_pdf) -> str:
    if archivo_pdf is None:
        return ""
    try:
        lector = PdfReader(archivo_pdf)
        paginas = []
        for pagina in lector.pages:
            texto = pagina.extract_text()
            if texto:
                paginas.append(texto)
        return "\n".join(paginas)
    except Exception:
        return ""


def obtener_texto_base(ruta_local: str, archivo_subido) -> str:
    texto_local = extraer_texto_pdf_path(ruta_local) if ruta_local else ""
    texto_subido = extraer_texto_pdf_upload(archivo_subido) if archivo_subido is not None else ""
    return texto_subido or texto_local


def mostrar_estado_base(nombre: str, texto_base: str):
    if texto_base:
        st.success(f"Base cargada: {nombre}")
    else:
        st.warning(f"No se ha podido cargar la base: {nombre}")


# =========================================================
# RUTAS PDF
# =========================================================

RUTA_DOCS = "documentos"
RUTA_CODIFICADO_DGT = os.path.join(RUTA_DOCS, "codificado_dgt.pdf")
RUTA_LEY_SC = os.path.join(RUTA_DOCS, "ley_organica_4_2015.pdf")
RUTA_LEY_ANIMAL = os.path.join(RUTA_DOCS, "ley_4_2017_bienestar_animal.pdf")


# =========================================================
# MODOS DE REDACCIÓN
# =========================================================

def obtener_instruccion_modo_redaccion(modo_redaccion: str) -> str:
    if modo_redaccion == "Ampliado":
        return (
            "Redacta de forma detallada, desarrollando las actuaciones policiales, la descripción del lugar, "
            "la dinámica y los daños observados, manteniendo un lenguaje técnico policial. "
            "NO inventes datos. Si un dato no consta, omítelo del texto o déjalo en blanco si se trata de un campo."
        )

    return (
        "Redacta con lenguaje técnico, formal y preciso, propio de documentos policiales. "
        "NO inventes datos. Si un dato no consta, omítelo del texto o déjalo en blanco si se trata de un campo."
    )


# =========================================================
# PROMPTS BASE
# =========================================================

REGLAS_COMUNES_NO_INVENTAR = (
    "NO inventes datos en ningún caso. Usa exclusivamente la información facilitada por el usuario. "
    "Si un dato no consta, no lo completes ni lo deduzcas. Omítelo del texto o déjalo en blanco si procede."
)

TRATAMIENTO_PERSONAS_GENERAL = (
    "TRATAMIENTO DE PERSONAS:\n"
    "- En la PRIMERA mención de cada persona física que no sea agente debes indicar 'D.' o 'Dña.' seguido del nombre completo, y añadir DNI y teléfono si constan.\n"
    "- En menciones posteriores, debes indicar únicamente 'D.' o 'Dña.' seguido del nombre o nombre completo, sin repetir DNI ni teléfono.\n"
    "- No repitas la filiación completa más de una vez por persona.\n"
    "- Los agentes deben identificarse exclusivamente por su NIP.\n"
)

TRATAMIENTO_PERSONAS_MUNICIPAL = (
    "TRATAMIENTO DE PERSONAS:\n"
    "- Todas las personas físicas deben figurar como 'D.' o 'Dña.' seguido del nombre completo.\n"
    "- NO se debe incluir en ningún caso DNI ni teléfono.\n"
    "- Esta omisión es obligatoria por motivos de protección de datos.\n"
    "- Los agentes deben identificarse exclusivamente por su NIP.\n"
)

PROMPT_ACCIDENTE = (
    "Eres un asistente de redacción policial especializado en informes técnicos de accidentes para la Policía Local de Poio.\n\n"
    "Debes redactar un INFORME TÉCNICO DE ACCIDENTE con estilo policial real, técnico, formal y objetivo.\n"
    "Debe comenzar exactamente con: 'Los instructores en funciones de Policía Judicial de Tráfico, pertenecientes al Cuerpo de la Policía Local de Poio, hacen constar mediante el presente informe técnico:'\n"
    "Usa párrafos narrativos que comiencen por 'Que...'.\n"
    "Debe integrar hora del aviso y hora de personación si constan.\n"
    "No uses subtítulos como 'Conclusión:'.\n"
    "No atribuyas la dinámica literalmente a lo que dicen los conductores; basa la reconstrucción en datos objetivos facilitados.\n"
    "Describe vehículo A y B con formato técnico.\n"
    "Asocia conductor A con vehículo A y conductor B con vehículo B.\n"
    "Si hay reportaje fotográfico y consta que sí, menciónalo.\n"
    "Si hay alcoholemia o drogas y constan, intégralo conforme al artículo 14 del Real Decreto Legislativo 6/2015.\n"
    "La conclusión debe empezar por 'Que a la vista de todo lo expuesto, se concluye que...'.\n"
    "Finaliza exactamente con: 'Y para que así conste, se extiende el presente informe técnico policial, que se emite en base a la inspección ocular, manifestaciones recabadas y análisis de las circunstancias concurrentes, quedando sometido a cualquier otro mejor fundado.'\n\n"
    + TRATAMIENTO_PERSONAS_GENERAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_ATESTADO_EXPOSICION = (
    "Eres un asistente de redacción policial para la Policía Local de Poio.\n\n"
    "Debes redactar una EXPOSICIÓN DE HECHOS para atestado, en castellano, con tono policial formal, técnico y cronológico.\n"
    "Usa párrafos narrativos que comiencen por 'Que...'.\n"
    "Debe reflejar de forma cronológica la actuación policial.\n"
    "Debe integrar hora del aviso y hora de personación si constan.\n"
    "No incluir manifestaciones literales de las partes salvo que se indique expresamente.\n"
    "No hacer valoraciones jurídicas ni conclusiones.\n"
    "Al inicio, quien llama debe figurar como alertante o requirente, no como denunciante.\n"
    "Cuando hables de los agentes, utiliza la fórmula 'los agentes con NIP...'.\n"
    "Si se facilita indicativo, integra la fórmula 'uniformados reglamentariamente, se desplazan en vehículo oficial rotulado bajo el indicativo ...'.\n"
    "Nunca digas que el requirente es trasladado en vehículo oficial; si procede, indica que se desplaza posteriormente por sus propios medios a dependencias policiales.\n"
    "Si se habla de daños en puerta o cerradura, la valoración detallada se reserva principalmente para la inspección ocular.\n\n"
    + TRATAMIENTO_PERSONAS_GENERAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_ATESTADO_INSPECCION = (
    "Eres un asistente de redacción policial para la Policía Local de Poio.\n\n"
    "Debes redactar una INSPECCIÓN OCULAR para atestado, con lenguaje técnico, descriptivo y objetivo.\n"
    "Usa párrafos que comiencen por 'Que...'.\n"
    "No incluir interpretaciones concluyentes ni manifestaciones del alertante salvo referencia mínima imprescindible.\n"
    "Describir únicamente lo observado.\n"
    "Si existen daños en puerta, cerradura, bombín, marco, ventanas o accesos, descríbelos con precisión material.\n"
    "Usa fórmulas prudentes como 'compatible con un posible acceso no autorizado'.\n"
    "Si se indica reportaje fotográfico, inclúyelo expresamente.\n"
    "No mezclar la inspección ocular con diligencias posteriores ni comparecencias.\n\n"
    + TRATAMIENTO_PERSONAS_GENERAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_INFORME_MUNICIPAL = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. Debes redactar un INFORME MUNICIPAL en castellano, con tono formal, objetivo, técnico y administrativo. "
    "Integra hora del aviso y hora de personación si constan. "
    "Debe ser apto para conflictos entre particulares, incidencias en inmuebles, requerimientos vecinales o incidencias municipales.\n\n"
    + TRATAMIENTO_PERSONAS_MUNICIPAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_PARTE_SERVICIO = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. Debes redactar un PARTE DE SERVICIO interno, en castellano, con tono formal, claro, objetivo y operativo. "
    "Integra hora del aviso y hora de personación si constan.\n\n"
    + TRATAMIENTO_PERSONAS_GENERAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_ANOMALIA = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. Debes redactar una ANOMALÍA o comunicación breve de incidencia en vía pública o elementos urbanos, en castellano, con tono claro, breve, técnico y operativo. "
    "Integra hora del aviso y hora de personación si constan.\n\n"
    + TRATAMIENTO_PERSONAS_GENERAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)


# =========================================================
# CAMPOS
# =========================================================

CAMPOS_ACCIDENTE = [
    "Fecha",
    "Hora del aviso",
    "Hora de personación",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Vehículo A",
    "Conductor A",
    "Pasajeros vehículo A",
    "Vehículo B",
    "Conductor B",
    "Pasajeros vehículo B",
    "Peatones implicados",
    "Testigos",
    "Descripción de la vía",
    "Daños observados",
    "Relato técnico del accidente",
    "Actuaciones realizadas",
    "Reportaje fotográfico (sí/no)",
    "Prueba de alcoholemia (indicar resultado o 'no procede')",
    "Prueba de drogas (indicar resultado o 'no procede')",
    "Conclusión técnica",
    "Observaciones adicionales",
]

CAMPOS_ATESTADO_COMPLETO = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",
    "Motivo del aviso",
    "Relato general de los hechos",
    "Actuaciones realizadas",
    "Descripción del lugar",
    "Accesos",
    "Daños observados",
    "Elementos relevantes",
    "Reportaje fotográfico (sí/no)",
    "Observaciones adicionales",
]

CAMPOS_INFORME_MUNICIPAL = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes",
    "Asunto",
    "Partes implicadas",
    "Versión de la parte A",
    "Versión de la parte B",
    "Observaciones de los agentes",
    "Documentación o imágenes",
    "Análisis técnico o valoración policial",
    "Conclusión o resultado",
    "Observaciones adicionales",
]

CAMPOS_PARTE_SERVICIO = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes",
    "Asunto o motivo",
    "Personas implicadas o comparecientes",
    "Relato libre de lo sucedido o de la gestión realizada",
    "Actuaciones policiales realizadas",
    "Documentación o imágenes adjuntas",
    "Observaciones adicionales",
]

CAMPOS_ANOMALIA = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar exacto",
    "Agentes",
    "Tipo de anomalía",
    "Descripción breve de la incidencia observada",
    "Riesgo o afectación apreciada",
    "Actuaciones realizadas",
    "Servicio o departamento avisado",
    "Observaciones adicionales",
]

CAMPOS_PATRULLA_ACCIDENTE = [
    "Fecha",
    "Hora del aviso",
    "Hora de personación",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Vehículo A",
    "Vehículo B",
    "Daños observados",
    "Relato técnico del accidente",
    "Conclusión técnica",
]

CAMPOS_PATRULLA_ATESTADO = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Motivo del aviso",
    "Relato general de los hechos",
    "Daños observados",
]

CAMPOS_PATRULLA_MUNICIPAL = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes",
    "Asunto",
    "Partes implicadas",
    "Observaciones de los agentes",
    "Conclusión o resultado",
]

CAMPOS_PATRULLA_SERVICIO = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes",
    "Asunto o motivo",
    "Relato libre de lo sucedido o de la gestión realizada",
    "Actuaciones policiales realizadas",
]

CAMPOS_PATRULLA_ANOMALIA = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar exacto",
    "Agentes",
    "Tipo de anomalía",
    "Descripción breve de la incidencia observada",
    "Actuaciones realizadas",
    "Servicio o departamento avisado",
]


# =========================================================
# COMPONENTES UI
# =========================================================

def boton_copiar_web(texto: str, clave: str):
    texto_js = json.dumps(texto)
    html = f"""
    <div style="margin-top: 8px; margin-bottom: 8px;">
        <button
            onclick='navigator.clipboard.writeText({texto_js}).then(() => {{
                const msg = document.getElementById("copiado-{clave}");
                if (msg) {{
                    msg.innerText = "Texto copiado";
                    setTimeout(() => msg.innerText = "", 2000);
                }}
            }}).catch(() => {{
                const msg = document.getElementById("copiado-{clave}");
                if (msg) {{
                    msg.innerText = "No se pudo copiar";
                    setTimeout(() => msg.innerText = "", 2000);
                }}
            }});'
            style="width: 100%; min-height: 52px; border: none; border-radius: 12px; background: #1f77b4; color: white; font-size: 16px; font-weight: 600; cursor: pointer;"
        >
            📋 Copiar texto
        </button>
        <div id="copiado-{clave}" style="margin-top:8px; font-size:14px; color:#2e7d32;"></div>
    </div>
    """
    components.html(html, height=90)


def render_form_fields(campos: list[str], key_prefix: str) -> dict:
    datos = {}
    for campo in campos:
        valor = st.text_area(
            campo,
            value=st.session_state.get(f"{key_prefix}_{campo}", ""),
            key=f"widget_{key_prefix}_{campo}",
            height=80,
        )
        st.session_state[f"{key_prefix}_{campo}"] = valor
        datos[campo] = valor
    return normalizar_datos(datos)


def aplicar_datos_a_session_state(datos_extraidos: dict, key_prefix: str):
    for campo, valor in datos_extraidos.items():
        st.session_state[f"{key_prefix}_{campo}"] = valor
        st.session_state[f"widget_{key_prefix}_{campo}"] = valor


def mostrar_resultado(texto: str, datos: dict, prefijo: str):
    st.subheader("Resultado")
    st.text_area("Documento generado", texto, height=450)

    col1, col2, col3 = st.columns(3)
    with col1:
        boton_copiar_web(texto, prefijo)
    with col2:
        st.download_button(
            "Descargar TXT",
            data=texto.encode("utf-8"),
            file_name=f"{prefijo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
        )
    with col3:
        if st.button("Guardar TXT y JSON", key=f"guardar_{prefijo}"):
            ruta_txt = guardar_txt(texto, prefijo)
            ruta_json = guardar_json(datos, prefijo)
            st.success(f"Guardado en: {ruta_txt} y {ruta_json}")

    nombre = st.text_input("Guardar con nombre", key=f"nombre_{prefijo}")
    if st.button("Guardar TXT", key=f"guardar_nombre_{prefijo}"):
        if nombre.strip():
            ruta = guardar_txt_con_nombre(texto, nombre.strip())
            st.success(f"Guardado en: {ruta}")
        else:
            st.warning("Escribe un nombre válido.")


def extraer_campos_desde_dictado(api_key: str, tipo_documento: str, texto_dictado: str, campos_objetivo: list[str]) -> dict:
    client = get_client(api_key)
    esquema = {campo: "" for campo in campos_objetivo}

    prompt = f"""
Eres un asistente policial que extrae datos estructurados desde un dictado libre.

TIPO DE DOCUMENTO:
{tipo_documento}

CAMPOS A RELLENAR:
{json.dumps(campos_objetivo, ensure_ascii=False, indent=2)}

INSTRUCCIONES:
- Devuelve EXCLUSIVAMENTE un objeto JSON válido.
- Usa exactamente como claves los nombres de los campos proporcionados.
- Si un dato no aparece claro, deja su valor como cadena vacía "".
- No inventes datos.
- Si el dictado menciona agentes, horas, lugar, daños o motivo del aviso, colócalos en el campo más adecuado.
- En los campos narrativos amplios, resume fielmente el dictado con lenguaje claro y útil para redacción policial.
- No añadas explicaciones fuera del JSON.

JSON base esperado:
{json.dumps(esquema, ensure_ascii=False, indent=2)}

DICTADO:
"""{texto_dictado}"""
"""

    respuesta = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[
            {"role": "system", "content": "Devuelve solo JSON válido y no inventes datos."},
            {"role": "user", "content": prompt},
        ],
    )

    contenido = respuesta.choices[0].message.content or "{}"

    try:
        datos = json.loads(contenido)
        if not isinstance(datos, dict):
            return esquema
        resultado = {}
        for campo in campos_objetivo:
            valor = datos.get(campo, "")
            resultado[campo] = str(valor).strip() if valor is not None else ""
        return resultado
    except Exception:
        return esquema


def bloque_dictado_a_campos(api_key: str, key_prefix: str, tipo_documento: str, campos_objetivo: list[str]):
    st.subheader("🎤 Dictado inteligente")
    st.caption("Graba un relato libre y la app intentará rellenar automáticamente los campos.")

    audio_bytes = audio_recorder(
        text="Pulsa para grabar",
        recording_color="#d32f2f",
        neutral_color="#1976d2",
        icon_name="microphone",
        icon_size="2x",
        key=f"audio_campos_{key_prefix}",
    )

    texto_guardado = st.session_state.get(f"dictado_campos_{key_prefix}", "")

    if audio_bytes:
        if st.button("Transcribir dictado", key=f"transcribir_campos_{key_prefix}"):
            with st.spinner("Transcribiendo audio..."):
                texto = transcribir_audio_con_openai(api_key, audio_bytes)
            st.session_state[f"dictado_campos_{key_prefix}"] = texto
            texto_guardado = texto
            st.success("Dictado transcrito.")

    texto_guardado = st.text_area(
        "Texto dictado",
        value=texto_guardado,
        height=140,
        key=f"texto_dictado_{key_prefix}",
    )

    st.session_state[f"dictado_campos_{key_prefix}"] = texto_guardado

    if st.button("Rellenar campos desde dictado", key=f"rellenar_campos_{key_prefix}"):
        if not texto_guardado.strip():
            st.warning("Primero graba o escribe un dictado.")
        else:
            with st.spinner("Extrayendo campos desde el dictado..."):
                datos_extraidos = extraer_campos_desde_dictado(
                    api_key=api_key,
                    tipo_documento=tipo_documento,
                    texto_dictado=texto_guardado,
                    campos_objetivo=campos_objetivo,
                )
            aplicar_datos_a_session_state(datos_extraidos, key_prefix)
            st.success("Campos rellenados automáticamente. Revisa y corrige lo que haga falta.")
            st.rerun()


def selector_modo_redaccion(clave: str) -> str:
    return st.selectbox(
        "Modo de redacción",
        ["Técnico", "Ampliado"],
        index=0,
        key=clave,
    )


# =========================================================
# PÁGINAS DOCUMENTALES
# =========================================================

def pagina_accidente(api_key: str):
    st.header("Informe técnico de accidente")
    modo_redaccion = selector_modo_redaccion("modo_accidente")
    campos_accidente = CAMPOS_PATRULLA_ACCIDENTE if modo_patrulla else CAMPOS_ACCIDENTE

    bloque_dictado_a_campos(api_key, "accidente", "Informe técnico de accidente", campos_accidente)
    datos = render_form_fields(campos_accidente, "accidente")

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar informe técnico")
    with col2:
        regenerar = st.button("Regenerar informe")

    if generar or regenerar:
        prompt_final = PROMPT_ACCIDENTE + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando informe..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_accidente"] = texto
        st.session_state["datos_accidente"] = datos

    if st.session_state.get("resultado_accidente"):
        mostrar_resultado(st.session_state["resultado_accidente"], st.session_state.get("datos_accidente", {}), "accidente")


def pagina_atestado(api_key: str):
    st.header("Atestado completo")
    modo_redaccion = selector_modo_redaccion("modo_atestado")
    campos_atestado = CAMPOS_PATRULLA_ATESTADO if modo_patrulla else CAMPOS_ATESTADO_COMPLETO

    bloque_dictado_a_campos(api_key, "atestado", "Atestado completo", campos_atestado)
    datos = render_form_fields(campos_atestado, "atestado")

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar atestado completo")
    with col2:
        regenerar = st.button("Regenerar atestado")

    if generar or regenerar:
        bloque = construir_bloque_usuario(datos)
        instruccion = obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando exposición e inspección ocular..."):
            exposicion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_EXPOSICION + "\n\n" + instruccion, bloque)
            inspeccion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_INSPECCION + "\n\n" + instruccion, bloque)
            documento = "===== EXPOSICIÓN DE HECHOS =====\n\n" + exposicion + "\n\n===== INSPECCIÓN OCULAR =====\n\n" + inspeccion
        st.session_state["resultado_atestado"] = documento
        st.session_state["datos_atestado"] = datos

    if st.session_state.get("resultado_atestado"):
        mostrar_resultado(st.session_state["resultado_atestado"], st.session_state.get("datos_atestado", {}), "atestado_completo")


def pagina_informe_municipal(api_key: str):
    st.header("Informe municipal")
    modo_redaccion = selector_modo_redaccion("modo_municipal")
    campos_municipal = CAMPOS_PATRULLA_MUNICIPAL if modo_patrulla else CAMPOS_INFORME_MUNICIPAL

    bloque_dictado_a_campos(api_key, "municipal", "Informe municipal", campos_municipal)
    datos = render_form_fields(campos_municipal, "municipal")

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar informe municipal")
    with col2:
        regenerar = st.button("Regenerar informe municipal")

    if generar or regenerar:
        prompt_final = PROMPT_INFORME_MUNICIPAL + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando informe..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_municipal"] = texto
        st.session_state["datos_municipal"] = datos

    if st.session_state.get("resultado_municipal"):
        mostrar_resultado(st.session_state["resultado_municipal"], st.session_state.get("datos_municipal", {}), "informe_municipal")


def pagina_parte_servicio(api_key: str):
    st.header("Parte de servicio")
    modo_redaccion = selector_modo_redaccion("modo_servicio")
    campos_servicio = CAMPOS_PATRULLA_SERVICIO if modo_patrulla else CAMPOS_PARTE_SERVICIO

    bloque_dictado_a_campos(api_key, "servicio", "Parte de servicio", campos_servicio)
    datos = render_form_fields(campos_servicio, "servicio")

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar parte de servicio")
    with col2:
        regenerar = st.button("Regenerar parte de servicio")

    if generar or regenerar:
        prompt_final = PROMPT_PARTE_SERVICIO + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando parte..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_servicio"] = texto
        st.session_state["datos_servicio"] = datos

    if st.session_state.get("resultado_servicio"):
        mostrar_resultado(st.session_state["resultado_servicio"], st.session_state.get("datos_servicio", {}), "parte_servicio")


def pagina_anomalia(api_key: str):
    st.header("Anomalía")
    modo_redaccion = selector_modo_redaccion("modo_anomalia")
    campos_anomalia = CAMPOS_PATRULLA_ANOMALIA if modo_patrulla else CAMPOS_ANOMALIA

    bloque_dictado_a_campos(api_key, "anomalia", "Anomalía", campos_anomalia)
    datos = render_form_fields(campos_anomalia, "anomalia")

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar anomalía")
    with col2:
        regenerar = st.button("Regenerar anomalía")

    if generar or regenerar:
        prompt_final = PROMPT_ANOMALIA + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando anomalía..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_anomalia"] = texto
        st.session_state["datos_anomalia"] = datos

    if st.session_state.get("resultado_anomalia"):
        mostrar_resultado(st.session_state["resultado_anomalia"], st.session_state.get("datos_anomalia", {}), "anomalia")


# =========================================================
# SANCIONADOR
# =========================================================

def respuesta_dgt_frecuente(caso: str) -> str:
    texto = (caso or "").lower()

    if "sin seguro" in texto or "seguro obligatorio" in texto:
        return (
            "NORMA: SOA\n"
            "ARTÍCULO SANCIONADOR: 002\n"
            "APARTADO / LETRA: 1 / Opc. 5H\n"
            "TEXTO LITERAL DEL PRECEPTO: Circular el vehículo reseñado sin que conste que su propietario tenga suscrito y mantenga en vigor un contrato de seguro que cubra la responsabilidad civil derivada de su circulación.\n"
            "CALIFICACIÓN: Muy grave\n"
            "PUNTOS: No procede\n"
            "CUANTÍA: 1500€\n"
            "CUANTÍA REDUCIDA: 750€\n"
            "RESPONSABLE: Titular\n"
            "HECHO DENUNCIADO: Circular con vehículo sin seguro obligatorio en vigor.\n"
            "OBSERVACIONES: Causa de posible inmovilización y depósito del vehículo."
        )

    if "sin itv" in texto or "itv caducada" in texto or "vehiculo sin itv" in texto or "vehículo sin itv" in texto:
        return (
            "NORMA: VEH\n"
            "ARTÍCULO SANCIONADOR: 010\n"
            "APARTADO / LETRA: 1 / Opc. 5A\n"
            "TEXTO LITERAL DEL PRECEPTO: No haberse sometido el vehículo reseñado a la inspección técnica periódica establecida reglamentariamente.\n"
            "CALIFICACIÓN: Grave\n"
            "PUNTOS: No procede\n"
            "CUANTÍA: 200€\n"
            "CUANTÍA REDUCIDA: 100€\n"
            "RESPONSABLE: Titular\n"
            "HECHO DENUNCIADO: No haber sometido el vehículo a la inspección técnica periódica reglamentaria.\n"
            "OBSERVACIONES: ITV."
        )

    if "stop" in texto:
        return (
            "NORMA: CIR\n"
            "ARTÍCULO SANCIONADOR: 145\n"
            "APARTADO / LETRA: 2-A / Opc. 5B\n"
            "TEXTO LITERAL DEL PRECEPTO: No detenerse en el lugar prescrito por la señal de stop (R-2).\n"
            "CALIFICACIÓN: Grave\n"
            "PUNTOS: 4\n"
            "CUANTÍA: 200€\n"
            "CUANTÍA REDUCIDA: 100€\n"
            "RESPONSABLE: Conductor\n"
            "HECHO DENUNCIADO: No detenerse ante señal de stop.\n"
            "OBSERVACIONES: Obligación de detenerse en línea de detención o antes de la intersección y ceder el paso."
        )

    if "carga y descarga" in texto:
        return (
            "NORMA: CIR\n"
            "ARTÍCULO SANCIONADOR: 091\n"
            "APARTADO / LETRA: 2 / Opc. 5G\n"
            "TEXTO LITERAL DEL PRECEPTO: Estacionar un vehículo en zona reservada a carga y descarga durante las horas de utilización.\n"
            "CALIFICACIÓN: Grave\n"
            "PUNTOS: No procede\n"
            "CUANTÍA: 200€\n"
            "CUANTÍA REDUCIDA: 100€\n"
            "RESPONSABLE: Titular o arrendatario, salvo conductor identificado\n"
            "HECHO DENUNCIADO: Estacionar en zona reservada a carga y descarga en horas de utilización.\n"
            "OBSERVACIONES: Si se identifica conductor en la denuncia, será el responsable."
        )

    if "negligente" in texto or "conduccion negligente" in texto or "conducción negligente" in texto:
        return (
            "NORMA: CIR\n"
            "ARTÍCULO SANCIONADOR: 003\n"
            "APARTADO / LETRA: 1 / Opc. 5C\n"
            "TEXTO LITERAL DEL PRECEPTO: Conducir sin la diligencia, precaución y no distracción necesarios para evitar todo daño propio o ajeno.\n"
            "CALIFICACIÓN: Grave\n"
            "PUNTOS: No procede\n"
            "CUANTÍA: 200€\n"
            "CUANTÍA REDUCIDA: 100€\n"
            "RESPONSABLE: Conductor\n"
            "HECHO DENUNCIADO: Conducir de forma negligente, debiendo detallarse la conducta.\n"
            "OBSERVACIONES: Debe describirse la conducta concreta."
        )

    return ""


def pagina_sancionador(api_key: str):
    st.header("Asistente sancionador")

    tipo = st.selectbox(
        "Materia",
        [
            "Tráfico / DGT",
            "Seguridad ciudadana LO 4/2015",
            "Bienestar animal Galicia",
        ],
    )

    texto_base = ""
    archivo_pdf = None

    if tipo == "Tráfico / DGT":
        st.subheader("Base: Codificado DGT")
        archivo_pdf = st.file_uploader(
            "Sube el PDF del codificado DGT si quieres sustituir el de la app",
            type=["pdf"],
            key="codificado_dgt_pdf",
        )
        texto_base = obtener_texto_base(RUTA_CODIFICADO_DGT, archivo_pdf)
        mostrar_estado_base("Codificado DGT", texto_base)

    elif tipo == "Seguridad ciudadana LO 4/2015":
        st.subheader("Base: Ley Orgánica 4/2015")
        archivo_pdf = st.file_uploader(
            "Sube el PDF de seguridad ciudadana si quieres sustituir el de la app",
            type=["pdf"],
            key="ley_sc_pdf",
        )
        texto_base = obtener_texto_base(RUTA_LEY_SC, archivo_pdf)
        mostrar_estado_base("LO 4/2015", texto_base)

    elif tipo == "Bienestar animal Galicia":
        st.subheader("Base: Ley 4/2017 Galicia")
        archivo_pdf = st.file_uploader(
            "Sube el PDF de bienestar animal si quieres sustituir el de la app",
            type=["pdf"],
            key="ley_animal_pdf",
        )
        texto_base = obtener_texto_base(RUTA_LEY_ANIMAL, archivo_pdf)
        mostrar_estado_base("Ley 4/2017 Galicia", texto_base)

    caso = st.text_area("Describe el caso", height=140)

    if st.button("Analizar con IA"):
        if tipo == "Tráfico / DGT":
            frecuente = respuesta_dgt_frecuente(caso)
            if frecuente:
                st.session_state["resultado_sancionador"] = frecuente
                st.session_state["datos_sancionador"] = {"tipo": tipo, "caso": caso}
            else:
                prompt = (
                    "Eres un asistente experto en el codificado de infracciones de tráfico DGT en España.\n\n"
                    "Devuelve SIEMPRE en este formato:\n"
                    "NORMA:\n"
                    "ARTÍCULO SANCIONADOR:\n"
                    "APARTADO / LETRA:\n"
                    "TEXTO LITERAL DEL PRECEPTO:\n"
                    "CALIFICACIÓN:\n"
                    "PUNTOS:\n"
                    "CUANTÍA:\n"
                    "CUANTÍA REDUCIDA:\n"
                    "RESPONSABLE:\n"
                    "HECHO DENUNCIADO:\n"
                    "OBSERVACIONES:\n\n"
                    "Debes usar prioritariamente la base DGT aportada. No inventes datos. Si no encuentras encaje claro, dilo expresamente."
                )
                entrada = f"SUPUESTO:\n{caso}\n\nBASE NORMATIVA DGT:\n{texto_base[:20000] if texto_base else 'No consta base cargada.'}"
                with st.spinner("Analizando supuesto..."):
                    texto = generar_texto_con_ia(api_key, prompt, entrada)
                st.session_state["resultado_sancionador"] = texto
                st.session_state["datos_sancionador"] = {"tipo": tipo, "caso": caso}

        elif tipo == "Seguridad ciudadana LO 4/2015":
            prompt = (
                "Eres un asistente experto en la Ley Orgánica 4/2015 de protección de la seguridad ciudadana.\n\n"
                "Debes distinguir entre artículos materiales y artículos sancionadores.\n"
                "Debes buscar primero la conducta en los artículos 35, 36 o 37, y la cuantía en el artículo 39.\n"
                "No tomes como artículo principal uno que solo describa principios generales o actuaciones policiales.\n\n"
                "Devuelve SIEMPRE en este formato:\n"
                "NORMA:\n"
                "ARTÍCULO SANCIONADOR:\n"
                "APARTADO / LETRA:\n"
                "TEXTO LITERAL DEL PRECEPTO:\n"
                "CALIFICACIÓN:\n"
                "PUNTOS:\n"
                "CUANTÍA:\n"
                "CUANTÍA REDUCIDA:\n"
                "RESPONSABLE:\n"
                "HECHO DENUNCIADO:\n"
                "OBSERVACIONES:\n\n"
                "En 'RESPONSABLE' debe figurar siempre el responsable de la infracción. "
                "Cuando un dato no proceda, indica 'No procede' o 'No consta'. No inventes datos."
            )
            entrada = f"SUPUESTO:\n{caso}\n\nBASE LEGAL:\n{texto_base[:24000] if texto_base else 'No consta base cargada.'}"
            with st.spinner("Analizando supuesto..."):
                texto = generar_texto_con_ia(api_key, prompt, entrada)
            st.session_state["resultado_sancionador"] = texto
            st.session_state["datos_sancionador"] = {"tipo": tipo, "caso": caso}

        elif tipo == "Bienestar animal Galicia":
            prompt = (
                "Eres un asistente experto en la Ley 4/2017 de Galicia de protección y bienestar animal.\n\n"
                "Debes distinguir entre artículos que imponen obligaciones materiales y artículos sancionadores.\n"
                "Debes identificar primero el artículo sancionador correcto, normalmente en los artículos 38, 39 o 40, y después la cuantía en el artículo 41.\n"
                "No debes devolver como artículo principal el de la obligación material si existe un artículo sancionador específico que tipifique la conducta.\n\n"
                "Devuelve SIEMPRE en este formato:\n"
                "NORMA:\n"
                "ARTÍCULO SANCIONADOR:\n"
                "APARTADO / LETRA:\n"
                "TEXTO LITERAL DEL PRECEPTO:\n"
                "CALIFICACIÓN:\n"
                "PUNTOS:\n"
                "CUANTÍA:\n"
                "CUANTÍA REDUCIDA:\n"
                "RESPONSABLE:\n"
                "HECHO DENUNCIADO:\n"
                "OBSERVACIONES:\n\n"
                "En 'RESPONSABLE' debe figurar siempre el responsable de la infracción. "
                "Cuando un dato no proceda, indica 'No procede' o 'No consta'. No inventes datos."
            )
            entrada = f"SUPUESTO:\n{caso}\n\nBASE LEGAL:\n{texto_base[:24000] if texto_base else 'No consta base cargada.'}"
            with st.spinner("Analizando supuesto..."):
                texto = generar_texto_con_ia(api_key, prompt, entrada)
            st.session_state["resultado_sancionador"] = texto
            st.session_state["datos_sancionador"] = {"tipo": tipo, "caso": caso}

    if st.session_state.get("resultado_sancionador"):
        mostrar_resultado(st.session_state["resultado_sancionador"], st.session_state.get("datos_sancionador", {}), "sancionador")


# =========================================================
# SIDEBAR / APP PRINCIPAL
# =========================================================

st.sidebar.title("Policía IA")
st.sidebar.caption("Versión web para ordenador y móvil")
modo_patrulla = st.sidebar.toggle("Modo patrulla / móvil", value=True)

if modo_patrulla:
    st.sidebar.success("Modo patrulla activo")
    st.markdown(
        """
        <style>
        .stButton > button {
            width: 100%;
            min-height: 56px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 12px;
        }
        textarea {
            font-size: 17px !important;
        }
        .stTextInput input {
            font-size: 17px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

api_key = st.sidebar.text_input(
    "API key de OpenAI",
    type="password",
    help="Pega aquí tu clave. No se guarda fuera de tu sesión.",
)

pagina = st.sidebar.radio(
    "Módulos",
    [
        "Accidente",
        "Atestado completo",
        "Informe municipal",
        "Parte de servicio",
        "Anomalía",
        "Asistente sancionador",
    ],
)

st.title("🚓 Policía IA - Policía Local de Poio")
st.write("App web operativa para ordenador y móvil, con redacción policial, dictado a campos y asistente sancionador simplificado.")

if not api_key:
    st.info("Introduce tu API key en la barra lateral para empezar.")
    st.stop()

if pagina == "Accidente":
    pagina_accidente(api_key)
elif pagina == "Atestado completo":
    pagina_atestado(api_key)
elif pagina == "Informe municipal":
    pagina_informe_municipal(api_key)
elif pagina == "Parte de servicio":
    pagina_parte_servicio(api_key)
elif pagina == "Anomalía":
    pagina_anomalia(api_key)
elif pagina == "Asistente sancionador":
    pagina_sancionador(api_key)
