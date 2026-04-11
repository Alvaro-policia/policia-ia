import osimport pyperclip
import json
from datetime import datetime
from typing import Optional

import streamlit as st
from openai import OpenAI


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

st.set_page_config(
    page_title="Policía IA - Poio",
    page_icon="🚓",
    layout="wide",
)


# =========================================================
# UTILIDADES
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

    return valor[0].upper() + valor[1:]


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


# =========================================================
# CODIFICADO DGT (VERSIÓN TEMPORAL SIN PANDAS)
# =========================================================

def cargar_codificado_excel(archivo_subido):
    return None


def buscar_codificado(df, texto: str, limite: int = 5):
    return None


# =========================================================
# PROMPTS
# =========================================================

PROMPT_ACCIDENTE = (
    "Eres un asistente de redacción policial especializado en informes técnicos de accidentes "
    "para la Policía Local de Poio.\n\n"
    "Debes redactar un INFORME TÉCNICO DE ACCIDENTE con estilo policial real, técnico, formal y objetivo.\n"
    "NO inventes datos. SOLO usa los datos proporcionados por el usuario.\n"
    "Si un dato no ha sido facilitado, no lo menciones.\n\n"
    "ENCABEZADO OBLIGATORIO:\n"
    "Debe comenzar exactamente con:\n"
    "'Los instructores en funciones de Policía Judicial de Tráfico, pertenecientes al Cuerpo de la Policía Local de Poio, hacen constar mediante el presente informe técnico:'\n\n"
    "ESTRUCTURA Y ESTILO:\n"
    "- Utiliza párrafos narrativos que comiencen por 'Que...'\n"
    "- No uses subtítulos como 'Conclusión:'\n"
    "- No uses expresiones como 'según manifiesta' o 'según el relato de los conductores' para reconstruir la dinámica\n"
    "- La reconstrucción debe basarse en daños, posición de los vehículos, configuración de la vía y datos objetivos facilitados\n"
    "- Redacción cohesionada, formal y técnica\n\n"
    "VEHÍCULOS:\n"
    "- Vehículo A y vehículo B deben describirse separados y con este formato:\n"
    "  vehículo marca: X, modelo: X, color: X, matrícula: X\n\n"
    "INTERVINIENTES:\n"
    "- Asocia siempre conductor A con vehículo A y conductor B con vehículo B\n"
    "- Si existen pasajeros, asócialos a su vehículo correspondiente\n"
    "- Si se facilita la posición del pasajero, inclúyela expresamente\n"
    "- Si hay peatones o testigos, recógelos en párrafos diferenciados\n\n"
    "DINÁMICA DEL ACCIDENTE:\n"
    "Debe introducirse con una fórmula similar a:\n"
    "'Que examinados los daños apreciados en los vehículos y la configuración de la vía, se procede a la reconstrucción de la dinámica del accidente.'\n"
    "Después desarrolla la dinámica de forma técnica, explicando maniobras, trayectorias, posiciones y punto de impacto, sin atribuirla literalmente a las manifestaciones de los conductores.\n\n"
    "REPORTAJE FOTOGRÁFICO:\n"
    "- Si en el campo correspondiente pone 'sí', incluye un párrafo indicando que los agentes actuantes realizan reportaje fotográfico de los daños y del entorno del siniestro.\n"
    "- Si pone 'no', no lo menciones.\n\n"
    "ALCOHOLEMIA:\n"
    "- Solo incluir si el campo no dice 'no procede'\n"
    "- Debe integrarse en redacción formal y mencionar que la prueba se realiza conforme al artículo 14 del Real Decreto Legislativo 6/2015\n"
    "- Nunca inventes resultados.\n\n"
    "DROGAS:\n"
    "- Solo incluir si el campo no dice 'no procede'\n"
    "- Debe integrarse en redacción formal y mencionar que la prueba se realiza conforme al artículo 14 del Real Decreto Legislativo 6/2015\n"
    "- Nunca inventes resultados.\n\n"
    "CONCLUSIÓN TÉCNICA:\n"
    "- Debe integrarse en un párrafo que empiece por 'Que a la vista de todo lo expuesto, se concluye que...'\n"
    "- Debe basarse únicamente en la causa técnica del accidente y en los datos facilitados.\n\n"
    "CIERRE OBLIGATORIO:\n"
    "Finalizar exactamente con:\n"
    "'Y para que así conste, se extiende el presente informe técnico policial, que se emite en base a la inspección ocular, manifestaciones recabadas y análisis de las circunstancias concurrentes, quedando sometido a cualquier otro mejor fundado.'"
)

PROMPT_ATESTADO_EXPOSICION = (
    "Eres un asistente de redacción policial para la Policía Local de Poio.\n\n"
    "Debes redactar una EXPOSICIÓN DE HECHOS para atestado, en castellano, con tono policial formal, técnico y cronológico.\n"
    "NO inventes datos. SOLO usa la información facilitada.\n\n"
    "IMPORTANTE:\n"
    "- Redacta en formato narrativo con párrafos que comiencen por 'Que...'\n"
    "- Debe reflejar de forma cronológica la actuación policial\n"
    "- No incluir manifestaciones literales de las partes salvo que se indique expresamente\n"
    "- No hacer valoraciones jurídicas ni conclusiones\n"
    "- Al inicio, la persona que llama debe figurar como alertante o requirente, no como denunciante\n"
    "- Si se facilita identidad telefónica, utiliza fórmulas como: 'dice ser e identificarse verbalmente como D...., con DNI..., y teléfono...'\n"
    "- Cuando hables de los agentes, utiliza la fórmula 'los agentes con NIP...'\n"
    "- Si se facilita indicativo, integra la fórmula 'uniformados reglamentariamente, se desplazan en vehículo oficial rotulado bajo el indicativo ...'\n"
    "- Nunca digas que el requirente o denunciante es trasladado en vehículo oficial; si procede, indica que se desplaza posteriormente por sus propios medios a dependencias policiales\n"
    "- Si se habla de daños en puerta o cerradura, la valoración detallada debe reservarse principalmente para la inspección ocular\n\n"
    "ESTILO:\n"
    "- Lenguaje claro, técnico y profesional\n"
    "- Redacción continua, sin listas\n"
    "- Uso de expresiones tipo: 'Que siendo las...', 'Que en el teléfono oficial de la Jefatura...', 'Que una vez en el lugar...'\n\n"
    "Debe ser un texto válido para incorporar directamente a un atestado policial."
)

PROMPT_ATESTADO_INSPECCION = (
    "Eres un asistente de redacción policial para la Policía Local de Poio.\n\n"
    "Debes redactar una INSPECCIÓN OCULAR para atestado, con lenguaje técnico, descriptivo y objetivo.\n"
    "NO inventes datos. SOLO usa la información facilitada.\n\n"
    "IMPORTANTE:\n"
    "- Redacta en párrafos que comiencen por 'Que...'\n"
    "- No incluir interpretaciones concluyentes ni manifestaciones del alertante, salvo referencia mínima imprescindible\n"
    "- Describir únicamente lo observado\n"
    "- Si existen daños en puerta, cerradura, bombín, marco, ventanas o accesos, descríbelos con precisión material\n"
    "- Si el usuario aporta detalle, concreta ubicación del daño, tipo de fractura o marcas compatibles con útil empleado\n"
    "- Usa fórmulas prudentes como 'podría ser compatible con un posible acceso no autorizado'\n"
    "- Si se indica reportaje fotográfico, inclúyelo expresamente\n"
    "- No mezclar la inspección ocular con inicio de diligencias ni con comparecencias en sede policial\n\n"
    "ESTILO:\n"
    "- Técnico, claro y objetivo\n"
    "- Preciso y sin adornos\n"
    "- Apto para diligencias policiales"
)

PROMPT_INFORME_MUNICIPAL = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. "
    "Debes redactar un INFORME MUNICIPAL o de incidencia para el concello, en castellano, con tono formal, objetivo, técnico y administrativo. "
    "No inventes datos. Usa solo la información facilitada. "
    "La redacción debe ser apta para conflictos entre particulares, incidencias en inmuebles, requerimientos vecinales, constancias o incidencias municipales."
)

PROMPT_PARTE_SERVICIO = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. "
    "Debes redactar un PARTE DE SERVICIO interno, en castellano, con tono formal, claro, objetivo y operativo. "
    "No inventes datos. Usa solo la información proporcionada por el usuario."
)

PROMPT_ANOMALIA = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. "
    "Debes redactar una ANOMALÍA o comunicación breve de incidencia en vía pública o elementos urbanos, "
    "en castellano, con tono claro, breve, técnico y operativo. "
    "No inventes datos. Usa solo la información proporcionada."
)

PROMPT_SANCIONADOR_GENERAL = (
    "Eres un asistente sancionador policial. Analiza el supuesto y devuelve SIEMPRE en este formato:\n\n"
    "NORMA:\n"
    "ARTÍCULO:\n"
    "APARTADO:\n"
    "OPCIÓN:\n"
    "CALIFICACIÓN:\n"
    "PUNTOS:\n"
    "CUANTÍA:\n"
    "CUANTÍA REDUCIDA:\n"
    "RESPONSABLE:\n"
    "HECHO DENUNCIADO:\n"
    "OBSERVACIONES:\n\n"
    "Si no encaja claramente, indícalo con prudencia y explica el mejor encaje posible."
)


# =========================================================
# CAMPOS
# =========================================================

CAMPOS_ACCIDENTE = [
    "Fecha",
    "Hora del aviso",
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
    "Lugar exacto",
    "Agentes",
    "Tipo de anomalía",
    "Descripción breve de la incidencia observada",
    "Riesgo o afectación apreciada",
    "Actuaciones realizadas",
    "Servicio o departamento avisado",
    "Observaciones adicionales",
]


# =========================================================
# COMPONENTES UI
# =========================================================

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


def mostrar_resultado(texto: str, datos: dict, prefijo: str):
    st.subheader("Resultado")
    st.text_area("Documento generado", texto, height=450)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("📋 Copiar texto", key=f"copiar_{prefijo}"):
            try:
                pyperclip.copy(texto)
                st.success("Texto copiado al portapapeles.")
            except Exception:
                st.warning("No se pudo copiar automáticamente.")

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

    with col4:
        nombre = st.text_input("Guardar con nombre", key=f"nombre_{prefijo}")
        if st.button("Guardar TXT", key=f"guardar_nombre_{prefijo}"):
            if nombre.strip():
                ruta = guardar_txt_con_nombre(texto, nombre.strip())
                st.success(f"Guardado en: {ruta}")
            else:
                st.warning("Escribe un nombre válido.")


# =========================================================
# PÁGINAS
# =========================================================

def pagina_accidente(api_key: str):
    st.header("Informe técnico de accidente")
    datos = render_form_fields(CAMPOS_ACCIDENTE, "accidente")

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar informe técnico")
    with col2:
        regenerar = st.button("Regenerar con mismos datos")

    if generar or regenerar:
        with st.spinner("Generando informe..."):
            texto = generar_texto_con_ia(api_key, PROMPT_ACCIDENTE, construir_bloque_usuario(datos))
        st.session_state["resultado_accidente"] = texto
        st.session_state["datos_accidente"] = datos

    if st.session_state.get("resultado_accidente"):
        mostrar_resultado(
            st.session_state["resultado_accidente"],
            st.session_state.get("datos_accidente", {}),
            "accidente",
        )


def pagina_atestado(api_key: str):
    st.header("Atestado completo")
    datos = render_form_fields(CAMPOS_ATESTADO_COMPLETO, "atestado")

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar atestado completo")
    with col2:
        regenerar = st.button("Regenerar atestado")

    if generar or regenerar:
        with st.spinner("Generando exposición e inspección ocular..."):
            bloque = construir_bloque_usuario(datos)
            exposicion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_EXPOSICION, bloque)
            inspeccion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_INSPECCION, bloque)
            documento = (
                "===== EXPOSICIÓN DE HECHOS =====\n\n"
                + exposicion
                + "\n\n===== INSPECCIÓN OCULAR =====\n\n"
                + inspeccion
            )
        st.session_state["resultado_atestado"] = documento
        st.session_state["datos_atestado"] = datos

    if st.session_state.get("resultado_atestado"):
        mostrar_resultado(
            st.session_state["resultado_atestado"],
            st.session_state.get("datos_atestado", {}),
            "atestado_completo",
        )


def pagina_informe_municipal(api_key: str):
    st.header("Informe municipal")
    datos = render_form_fields(CAMPOS_INFORME_MUNICIPAL, "municipal")
    if st.button("Generar informe municipal"):
        with st.spinner("Generando informe..."):
            texto = generar_texto_con_ia(api_key, PROMPT_INFORME_MUNICIPAL, construir_bloque_usuario(datos))
        st.session_state["resultado_municipal"] = texto
        st.session_state["datos_municipal"] = datos

    if st.session_state.get("resultado_municipal"):
        mostrar_resultado(
            st.session_state["resultado_municipal"],
            st.session_state.get("datos_municipal", {}),
            "informe_municipal",
        )


def pagina_parte_servicio(api_key: str):
    st.header("Parte de servicio")
    datos = render_form_fields(CAMPOS_PARTE_SERVICIO, "servicio")
    if st.button("Generar parte de servicio"):
        with st.spinner("Generando parte..."):
            texto = generar_texto_con_ia(api_key, PROMPT_PARTE_SERVICIO, construir_bloque_usuario(datos))
        st.session_state["resultado_servicio"] = texto
        st.session_state["datos_servicio"] = datos

    if st.session_state.get("resultado_servicio"):
        mostrar_resultado(
            st.session_state["resultado_servicio"],
            st.session_state.get("datos_servicio", {}),
            "parte_servicio",
        )


def pagina_anomalia(api_key: str):
    st.header("Anomalía")
    datos = render_form_fields(CAMPOS_ANOMALIA, "anomalia")
    if st.button("Generar anomalía"):
        with st.spinner("Generando anomalía..."):
            texto = generar_texto_con_ia(api_key, PROMPT_ANOMALIA, construir_bloque_usuario(datos))
        st.session_state["resultado_anomalia"] = texto
        st.session_state["datos_anomalia"] = datos

    if st.session_state.get("resultado_anomalia"):
        mostrar_resultado(
            st.session_state["resultado_anomalia"],
            st.session_state.get("datos_anomalia", {}),
            "anomalia",
        )


def pagina_sancionador(api_key: str):
    st.header("Asistente sancionador")

    st.subheader("Codificado DGT")
    st.info(
        "La lectura directa del Excel DGT queda desactivada temporalmente en esta versión por un bloqueo de seguridad de Windows con pandas/numpy."
    )
    df_codificado = None

    tipo = st.selectbox(
        "Materia",
        [
            "Tráfico / DGT",
            "Seguridad ciudadana LO 4/2015",
            "Bienestar animal Galicia",
            "Ordenanzas municipales",
        ],
    )

    caso = st.text_area("Describe el caso", height=120)

    col1, col2 = st.columns(2)
    with col1:
        buscar_excel = st.button("Buscar en codificado DGT")
    with col2:
        analizar = st.button("Analizar con IA")

    if buscar_excel and tipo == "Tráfico / DGT":
        st.warning("La búsqueda directa en Excel está desactivada temporalmente en esta versión.")

    if analizar:
        prompt = PROMPT_SANCIONADOR_GENERAL
        if tipo == "Tráfico / DGT":
            prompt = (
                "Eres un asistente experto en el codificado de infracciones de tráfico DGT en España.\n\n"
                "Tu función es identificar la infracción exacta a partir de un supuesto descrito por el usuario.\n"
                "Devuelve SIEMPRE en este formato: NORMA, ARTÍCULO, APARTADO, OPCIÓN, CALIFICACIÓN, PUNTOS, CUANTÍA, CUANTÍA REDUCIDA, RESPONSABLE, HECHO DENUNCIADO y OBSERVACIONES.\n"
                "Si no tienes codificado cargado, razona con prudencia y ofrece el encaje más ajustado posible."
            )
        elif tipo == "Seguridad ciudadana LO 4/2015":
            prompt = (
                "Eres un asistente experto en la Ley Orgánica 4/2015 de protección de la seguridad ciudadana.\n"
                "Analiza el supuesto y devuelve SIEMPRE: NORMA, ARTÍCULO, APARTADO, OPCIÓN (si no aplica, indícalo), CALIFICACIÓN, PUNTOS (si no procede, indícalo), CUANTÍA, CUANTÍA REDUCIDA (si no procede, indícalo), RESPONSABLE, HECHO DENUNCIADO y OBSERVACIONES.\n"
                "Sé prudente: usa 'podría encajar' cuando el supuesto dependa de matices relevantes."
            )
        elif tipo == "Bienestar animal Galicia":
            prompt = (
                "Eres un asistente experto en la Ley 4/2017 de Galicia de protección y bienestar animal.\n"
                "Analiza el supuesto y devuelve SIEMPRE: NORMA, ARTÍCULO, APARTADO, OPCIÓN (si no aplica), CALIFICACIÓN, PUNTOS (si no procede), CUANTÍA, CUANTÍA REDUCIDA (si no procede), RESPONSABLE, HECHO DENUNCIADO y OBSERVACIONES.\n"
                "Aclara si el encaje puede variar entre leve, grave o muy grave según el perjuicio causado."
            )
        elif tipo == "Ordenanzas municipales":
            prompt = (
                "Eres un asistente experto en ordenanzas municipales.\n"
                "Analiza el supuesto y devuelve SIEMPRE: NORMA, ARTÍCULO, APARTADO, OPCIÓN (si no aplica), CALIFICACIÓN, PUNTOS (si no procede), CUANTÍA, CUANTÍA REDUCIDA (si no procede), RESPONSABLE, HECHO DENUNCIADO y OBSERVACIONES.\n"
                "Si el encaje no es seguro, dilo claramente."
            )

        with st.spinner("Analizando supuesto..."):
            texto = generar_texto_con_ia(api_key, prompt, caso)
        st.session_state["resultado_sancionador"] = texto
        st.session_state["datos_sancionador"] = {"tipo": tipo, "caso": caso}

    if st.session_state.get("resultado_sancionador"):
        mostrar_resultado(
            st.session_state["resultado_sancionador"],
            st.session_state.get("datos_sancionador", {}),
            "sancionador",
        )


# =========================================================
# SIDEBAR / APP PRINCIPAL
# =========================================================

st.sidebar.title("Policía IA")
st.sidebar.caption("Versión web inicial para ordenador y móvil")
modo_patrulla = st.sidebar.toggle("Modo patrulla / móvil", value=True)
if modo_patrulla:
    st.markdown(
        """
        <style>
        .stButton > button {
            width: 100%;
            min-height: 52px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 12px;
        }
        textarea {
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
st.write(
    "Esta es la primera versión web. Se puede usar en ordenador y también en el navegador del móvil."
)

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
