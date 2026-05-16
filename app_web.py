import os
import re
import json
import tempfile
from datetime import datetime, date
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

st.set_page_config(
    page_title="Policía Local IA",
    page_icon="🚓",
    layout="wide",
)


# =========================================================
# UTILIDADES DE ARCHIVO
# =========================================================

def asegurar_carpeta(nombre_carpeta: str) -> None:
    if not os.path.exists(nombre_carpeta):
        os.makedirs(nombre_carpeta)

def get_reset_version(key_prefix: str) -> int:
    return st.session_state.get(f"_reset_version_{key_prefix}", 0)


def bump_reset_version(key_prefix: str) -> None:
    st.session_state[f"_reset_version_{key_prefix}"] = get_reset_version(key_prefix) + 1

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


def guardar_log_generacion(modulo: str, datos_form: dict, bloque_ia: str, resultado: str) -> None:
    asegurar_carpeta("logs")
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = os.path.join("logs", f"{modulo}_{marca_tiempo}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({
            "modulo": modulo,
            "timestamp": marca_tiempo,
            "datos_formulario": datos_form,
            "bloque_enviado_ia": bloque_ia,
            "resultado_generado": resultado,
        }, f, ensure_ascii=False, indent=2)


def guardar_txt_con_nombre(documento: str, nombre: str) -> str:
    asegurar_carpeta("informes")
    ruta = os.path.join("informes", f"{nombre}.txt")
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write(documento)
    return ruta


PREFIJO_A_CARPETA = {
    "accidente": "accidentes",
    "atestado_completo": "atestados",
    "informe_municipal": "informes_municipales",
    "parte_servicio": "partes_servicio",
    "anomalia": "anomalias",
    "informe_juzgado": "informes_juzgado",
    "denuncia_administrativa": "denuncias_administrativas",
}

PREFIJO_A_TIPO_DOC = {
    "accidente": "Informe técnico de accidente",
    "atestado_completo": "Atestado completo",
    "informe_municipal": "Informe municipal",
    "parte_servicio": "Parte de servicio",
    "anomalia": "Anomalía",
    "informe_juzgado": "Informe personas",
    "denuncia_administrativa": "Denuncia administrativa",
}


def guardar_ejemplo_ia(texto: str, prefijo: str) -> str:
    carpeta_modulo = PREFIJO_A_CARPETA.get(prefijo, prefijo)
    ruta_carpeta = os.path.join("conocimiento_policial", carpeta_modulo, "ejemplos_ia")
    asegurar_carpeta(ruta_carpeta)
    ahora = datetime.now()
    fecha = ahora.strftime("%Y-%m-%d")
    hora_nombre = ahora.strftime("%H-%M")
    hora_display = ahora.strftime("%H:%M")
    tipo_doc = PREFIJO_A_TIPO_DOC.get(prefijo, prefijo)
    nombre_archivo = f"{fecha}_{hora_nombre}_{carpeta_modulo}_ia.md"
    ruta = os.path.join(ruta_carpeta, nombre_archivo)
    cabecera = (
        f"# EJEMPLO IA\n\n"
        f"Módulo: {tipo_doc}\n"
        f"Fecha: {fecha}\n"
        f"Hora: {hora_display}\n"
        f"Generado por: GPT-4o-mini\n"
        f"Aplicación: Policía IA\n\n"
        f"---\n\n"
    )
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(cabecera + texto)
    return ruta


def anonimizar_texto(texto: str) -> str:
    # DNIs completos (8 dígitos + letra); los ya anonimizados (***XXXX**) no hacen match
    texto = re.sub(r'\b\d{8}[A-Za-z]\b', '***XXXX**', texto)
    # Teléfonos de 9 dígitos empezando por 6 o 7
    texto = re.sub(r'\b[67]\d{8}\b', '6XXXXXXXX', texto)
    # Matrículas actuales: NNNNLLL
    texto = re.sub(r'\b\d{4}[A-Z]{3}\b', 'XXXX000', texto)
    # Matrículas antiguas: LNNNNLL
    texto = re.sub(r'\b[A-Z]\d{4}[A-Z]{2}\b', 'XXXX000', texto)
    # NIPs de 6 dígitos tras "NIP"
    texto = re.sub(r'\bNIP\s+\d{6}\b', 'NIP XXXXXX', texto)
    # Nombres precedidos de Dña. (primero, más específico)
    texto = re.sub(
        r'Dña\.\s+[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ]+){0,3}',
        'Dña. [NOMBRE]',
        texto,
    )
    # Nombres precedidos de D.
    texto = re.sub(
        r'\bD\.\s+[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ]+){0,3}',
        'D. [NOMBRE]',
        texto,
    )
    return texto


def limpiar_espacios(texto: str) -> str:
    return " ".join((texto or "").split())


# =========================================================
# UTILIDADES DE FECHA
# =========================================================

def parsear_fecha(valor: Any) -> date | None:
    if not valor:
        return None

    if isinstance(valor, date):
        return valor

    if isinstance(valor, str):
        texto = valor.strip()
        for formato in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                pass

    if hasattr(valor, "year") and hasattr(valor, "month") and hasattr(valor, "day"):
        try:
            return date(valor.year, valor.month, valor.day)
        except Exception:
            return None

    return None


def formatear_fecha(valor: Any) -> str:
    fecha = parsear_fecha(valor)
    return fecha.strftime("%d/%m/%Y") if fecha else ""


# =========================================================
# UTILIDADES DE NORMALIZACIÓN
# =========================================================

def capitalizar_si_corresponde(campo: str, valor: str) -> str:
    valor = limpiar_espacios(valor)
    if not valor:
        return valor

    # ✅ FORZAR MAYÚSCULAS EN INDICATIVO
    if "indicativo policial" in campo.lower():
        return valor.upper()

    campos_sensibles = {
        "agentes actuantes (nip)",
        "agentes",
        "agentes actuantes",
        "indicativo policial",
        "vehículo a - clase y matrícula",
        "vehículo b - clase y matrícula",
        "vehículo c - clase y matrícula",
        "prueba de alcoholemia (indicar resultado)",
        "prueba de drogas (signos, indicar resultado)",
    }

    if campo.lower() in campos_sensibles or "dni" in campo.lower() or "teléfono" in campo.lower():
        return valor

    # En textos muy largos es mejor no tocar demasiado
    if len(valor) > 120:
        return valor

    return valor[0].upper() + valor[1:] if valor else valor

def formatear_nips(nips_raw: str) -> str:
    if not nips_raw:
        return ""

    # Separar por espacios, comas, etc.
    lista = re.split(r"[,\s]+", nips_raw.strip())

    # Limpiar vacíos
    lista = [nip for nip in lista if nip]

    if not lista:
        return ""

    if len(lista) == 1:
        return f"NIP {lista[0]}"

    if len(lista) == 2:
        return f"NIP {lista[0]} y NIP {lista[1]}"

    # Más de 2 → coma + y final
    return ", ".join(f"NIP {nip}" for nip in lista[:-1]) + f" y NIP {lista[-1]}"

def normalizar_datos(diccionario: dict) -> dict:
    return {k: capitalizar_si_corresponde(k, str(v)) for k, v in diccionario.items()}

def limpiar_json_respuesta(contenido: str) -> str:
    contenido = (contenido or "").strip()

    if contenido.startswith("```json"):
        contenido = contenido[7:]
    elif contenido.startswith("```"):
        contenido = contenido[3:]

    if contenido.endswith("```"):
        contenido = contenido[:-3]

    contenido = contenido.strip()

    # Rescate extra por si el modelo mete texto fuera del JSON
    inicio = contenido.find("{")
    fin = contenido.rfind("}")
    if inicio != -1 and fin != -1 and fin > inicio:
        contenido = contenido[inicio:fin + 1]

    return contenido.strip()


def normalizar_valor_select(campo: str, valor: str) -> str:
    valor_limpio = (valor or "").strip().lower()

    if not valor_limpio:
        return ""

    if campo == "Tipo de accidente":
        if "simple" in valor_limpio:
            return "Simple"
        if "complej" in valor_limpio:
            return "Complejo"
        if "multip" in valor_limpio:
            return "Múltiple"
        return ""

    if campo == "Reportaje fotográfico (sí/no)":
        if valor_limpio in {"si", "sí", "s", "hay", "con reportaje", "se realiza", "realizado"}:
            return "Sí"
        if valor_limpio in {"no", "n", "sin reportaje", "no se realiza", "no realizado"}:
            return "No"
        if "sí" in valor_limpio or "si" in valor_limpio:
            return "Sí"
        if "no" in valor_limpio:
            return "No"
        return ""

    if campo == "Condiciones meteorológicas":
        if any(x in valor_limpio for x in ["despejado", "despejada"]):
            return "Despejado"
        if any(x in valor_limpio for x in ["soleado", "soleada", "sol"]):
            return "Soleado"
        if any(x in valor_limpio for x in ["nublado", "nublada", "cubierto"]):
            return "Nublado"
        if any(x in valor_limpio for x in ["lluvia", "lloviendo", "llueve", "chubasco"]):
            return "Lluvia"
        if any(x in valor_limpio for x in ["niebla", "neblina"]):
            return "Niebla"
        if any(x in valor_limpio for x in ["viento", "ventoso", "ventosa"]):
            return "Viento"
        return "Otra"

    if campo == "Tipo de anomalía":
        mapa_anomalias = {
            "alcantarilla": "Alcantarilla",
            "cable": "Cable caído",
            "farola": "Farola dañada",
            "socavón": "Socavón",
            "socavon": "Socavón",
            "señal": "Señalización dañada",
            "senal": "Señalización dañada",
            "árbol": "Árbol o ramas",
            "arbol": "Árbol o ramas",
            "rama": "Árbol o ramas",
            "bache": "Bache",
            "agua": "Fuga de agua",
            "obstáculo": "Obstáculo en calzada",
            "obstaculo": "Obstáculo en calzada",
        }

        for clave, resultado in mapa_anomalias.items():
            if clave in valor_limpio:
                return resultado
        return "Otra"

    if campo == "Tipo de informe al juzgado":
        if "no localiz" in valor_limpio or "notificación negativa" in valor_limpio or "notificacion negativa" in valor_limpio:
            return "No localización / notificación negativa"
        if "localización permanente" in valor_limpio or "localizacion permanente" in valor_limpio:
            return "Incumplimiento de localización permanente"
        return ""

    return valor.strip()


def ajustar_datos_accidente_por_tipo(datos: dict) -> dict:
    tipo = (datos.get("Tipo de accidente", "") or "").strip().lower()

    if tipo == "simple":
        campos_a_vaciar = [
            "Vehículo B - clase y matrícula",
            "Vehículo B - marca",
            "Vehículo B - modelo",
            "Vehículo B - color",
            "Conductor vehículo B",
            "DNI conductor vehículo B",
            "Teléfono conductor vehículo B",
            "Pasajeros vehículo B (indicar posición)",
            "DNI pasajeros vehículo B",
            "Teléfono pasajeros vehículo B",
            "Vehículo C - clase y matrícula",
            "Vehículo C - marca",
            "Vehículo C - modelo",
            "Vehículo C - color",
            "Conductor vehículo C",
            "DNI conductor vehículo C",
            "Teléfono conductor vehículo C",
            "Pasajeros vehículo C (indicar posición)",
            "DNI pasajeros vehículo C",
            "Teléfono pasajeros vehículo C",
            "Más implicados (si hubiere)",
            "DNI más implicados",
            "Teléfono más implicados",
        ]
        for campo in campos_a_vaciar:
            datos[campo] = ""

    elif tipo == "complejo":
        campos_a_vaciar = [
            "Vehículo C - matrícula",
            "Vehículo C - marca",
            "Vehículo C - modelo",
            "Vehículo C - color",
            "Conductor vehículo C",
            "DNI conductor vehículo C",
            "Teléfono conductor vehículo C",
            "Pasajeros vehículo C (indicar posición)",
            "DNI pasajeros vehículo C",
            "Teléfono pasajeros vehículo C",
            "Más implicados (si hubiere)",
            "DNI más implicados",
            "Teléfono más implicados",
        ]
        for campo in campos_a_vaciar:
            datos[campo] = ""

    elif tipo == "múltiple" or tipo == "multiple":
        pass

    return datos


def construir_bloque_usuario_con_contexto(
    datos: dict,
    origen_actuacion: str,
    intervencion_presencial: str,
    orden_autoridad: str = "",
) -> str:
    if not isinstance(datos, dict):
        datos = {}

    bloque = [
        f"Origen de la actuación: {origen_actuacion}",
        f"Intervención presencial en el lugar: {intervencion_presencial}",
    ]

    if origen_actuacion == "Orden jerárquica" and orden_autoridad.strip():
        bloque.append(f"Orden jerárquica (autoridad que la dicta): {orden_autoridad.strip()}")

    bloque.extend([f"{k}: {v}" for k, v in datos.items() if str(v).strip()])

    nips = datos.get("Agentes actuantes (NIP)", "").strip()
    indicativo = datos.get("Indicativo policial", "").strip()

    # 👉 FORMATEAR NIPS
    nips_formateados = formatear_nips(nips)

    if intervencion_presencial == "Sí" and nips_formateados:
        frase_personacion = f"Que los agentes con {nips_formateados}, uniformados reglamentariamente"

        if indicativo:
            frase_personacion += f", se personan en el lugar en vehículo oficial rotulado bajo el indicativo policial {indicativo}."
        else:
            frase_personacion += ", se personan en el lugar en vehículo oficial."

        bloque.append(frase_personacion)

    if datos.get("DNI del alertante o requirente"):
        bloque.append("Alertante identificado previamente: Sí")
    else:
        bloque.append("Alertante identificado previamente: No")

    return "\n".join(bloque)


# =========================================================
# OPENAI
# =========================================================

@st.cache_resource(show_spinner=False)
def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def generar_texto_con_ia(
    api_key: str,
    prompt_sistema: str,
    datos_usuario: str,
    bloque_fidelidad: str | None = "",
) -> str:
    client = get_client(api_key)

    if bloque_fidelidad is None:
        prompt_final = prompt_sistema
    else:
        prompt_final = prompt_sistema + "\n\n" + (bloque_fidelidad or BLOQUE_FIDELIDAD_Y_EXTENSION)

    respuesta = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.05,
        messages=[
            {"role": "system", "content": prompt_final},
            {"role": "user", "content": datos_usuario},
        ],
    )

    return respuesta.choices[0].message.content or ""


# =========================================================
# PROMPTS BASE
# =========================================================


REGLAS_COMUNES_NO_INVENTAR = (
    "NO inventes datos en ningún caso. Usa exclusivamente la información facilitada por el usuario. "
    "Si un dato no consta, no lo completes ni lo deduzcas. Omítelo del texto o déjalo en blanco si procede."
)

BLOQUE_FIDELIDAD_Y_EXTENSION = (
    "TEXTO BASE Y FIDELIDAD AL CONTENIDO:\n"
    "- Debes respetar al máximo el texto base y los datos introducidos por el usuario.\n"
    "- No debes resumir ni reformular en exceso si con ello se pierden matices relevantes.\n"
    "- Debes conservar el sentido, el orden y el contenido material de los datos facilitados.\n"
    "- Si en el texto base o en los campos aparece una formulación técnica válida, debes mantenerla o reproducirla de forma muy próxima.\n"
    "- No debes sustituir expresiones concretas del usuario por fórmulas más genéricas o más pobres.\n\n"

    "EXTENSIÓN Y DESARROLLO:\n"
    "- Debes desarrollar suficientemente todos los apartados del documento sin inventar datos.\n"
    "- Debes evitar redacciones escuetas o excesivamente resumidas.\n"
    "- Debes dar al texto una extensión adecuada propia de un documento policial completo.\n"
    "- El mayor desarrollo debe lograrse explicando mejor los datos existentes, no inventando hechos nuevos.\n\n"
)

BLOQUE_FIDELIDAD_ATESTADO_EXPOSICION = (
    "FIDELIDAD ESPECÍFICA PARA EXPOSICIÓN DE HECHOS DE ATESTADO:\n"
    "- Debes respetar los datos de INTELCOPS y las pinceladas del agente, pero no debes copiar literalmente las actas.\n"
    "- Si la comparecencia o declaración principal del denunciante/perjudicado contiene el núcleo de los hechos, debes desarrollar ese relato en la exposición de hechos con una redacción policial nueva, equivalente en contenido, pero no literal.\n"
    "- Si existen actas secundarias de testigos, denunciantes adicionales o personas complementarias, normalmente se dejan como diligencias adjuntas y se resumen de forma operativa.\n"
    "- Está prohibido copiar párrafos enteros de una declaración con la misma redacción; debes reformular, ordenar y dar estilo de exposición policial.\n"
    "- Las respuestas de interrogatorio posteriores a 'PREGUNTADO/PREGUNTADA' pueden trasladarse si completan el relato principal, identifican pruebas, documentos, archivos, testigos o gestiones, o explican un extremo relevante de los hechos.\n"
    "- No traslades detalles claramente accesorios del interrogatorio si no aportan contexto, prueba o relevancia al relato policial.\n"
    "- Debes priorizar la secuencia de actuaciones policiales: entrada por registro, llamadas, citaciones, comparecencias, tomas de declaración, recepción de archivos, remisiones, anexos, comprobaciones y traslado final, solo si constan.\n"
    "- El texto debe ser suficientemente completo en actuaciones y diligencias, y debe desarrollar el relato fáctico principal cuando sea necesario para entender el atestado.\n"
    "- Los campos 'Inicio' y 'Fin' dentro de un acta son metadatos de esa acta, no la finalización del atestado completo.\n"
    "- No inventes gestiones, anexos, vídeos, correos, antecedentes ni cierre si no constan en los datos facilitados.\n\n"
)

BLOQUE_CONTEXTO_JEFATURA = (
    "CONTEXTO DE ACTUACIÓN:\n"
    "- Debes atender a los campos 'Origen de la actuación' e 'Intervención presencial en el lugar'.\n"
    "- El origen de la actuación puede ser comparecencia en jefatura, registro electrónico del Concello, aviso telefónico, aviso por WhatsApp, aviso en la calle, actuación de oficio u orden jerárquica.\n"
    "- Debes identificar correctamente el tipo de origen y adaptar la redacción al mismo sin mezclar escenarios.\n"
    "- Aunque la actuación se inicie por comparecencia en jefatura, puede existir después intervención presencial en vía pública.\n"
    "- Debes reflejar correctamente ambas fases si constan: inicio en dependencias y posterior intervención policial en el lugar.\n"
    "- Si el origen es comparecencia en jefatura y además existe intervención presencial, primero debes reflejar la comparecencia y después la personación de los agentes.\n"
    "- Si el origen es llamada o aviso telefónico, debes iniciar con fórmulas tipo 'Que se recibe llamada...' o 'Que se recibe aviso...'.\n"
    "- Si existe intervención presencial en el lugar, es OBLIGATORIO incluir la personación de los agentes.\n"
    "- Debes utilizar una fórmula técnica equivalente a:\n"
    "  'Que los agentes con NIP XXXX y NIP XXXX, uniformados reglamentariamente, se personan en el lugar en vehículo oficial rotulado bajo el indicativo policial XXXX...'\n"
    "- Si en los datos consta el campo 'Indicativo policial', debes incluirlo expresamente en esa frase.\n"
    "- Está prohibido omitir el indicativo policial cuando conste en los datos.\n"
    "- El indicativo policial debe integrarse exactamente en la frase de personación.\n"
    "- No mezclar escenarios de forma incoherente ni inventar actuaciones no facilitadas.\n\n"
)

BLOQUE_TIEMPO_PRESENTE = (
    "TIEMPO VERBAL (CRÍTICO — SIN EXCEPCIONES):\n"
    "- Toda la redacción debe realizarse en tiempo presente narrativo policial.\n"
    "- Está PROHIBIDO el uso de cualquier forma de pasado: pretérito perfecto simple ('se observó', 'se realizó'), pretérito perfecto compuesto ('se han observado', 'no se han encontrado', 'se ha realizado') y pretérito imperfecto.\n"
    "- Ejemplos correctos: 'se recibe aviso', 'se personan los agentes', 'se observa', 'se realiza', 'no se observan', 'no se localizan'.\n"
    "- Ejemplos incorrectos (prohibidos): 'se observó', 'se ha observado', 'no se han observado', 'se personó', 'se realizaron'.\n"
)

BLOQUE_PERSONACION_OBLIGATORIA = (
    "PERSONACIÓN POLICIAL (OBLIGATORIO):\n"
    "- Si existe intervención presencial en el lugar, debes reflejar la personación de los agentes.\n"
    "- Si en los datos aparece una 'FRASE DE PERSONACIÓN OBLIGATORIA', debes integrarla obligatoriamente.\n"
    "- Debes reproducirla de forma literal o muy próxima.\n"
    "- Está prohibido omitirla si está presente.\n"
    "- FÓRMULA ESTÁNDAR DE PERSONACIÓN (obligatoria en todos los módulos): cuando los agentes acuden a un lugar, debes usar una fórmula equivalente a:\n"
    "  'Que los agentes con NIP [NIP1] y NIP [NIP2], uniformados reglamentariamente, se personan en el lugar en vehículo oficial rotulado bajo el indicativo policial [indicativo].'\n"
    "- Si no consta el indicativo, omitir esa parte pero mantener el resto.\n"
    "- Está prohibido describir la personación sin mencionar los NIPs y la condición de uniformados reglamentariamente.\n\n"
)

BLOQUE_ORDEN_JERARQUICA = (
    "ORDEN JERÁRQUICA:\n"
    "- Si el origen de la actuación es 'Orden jerárquica', está prohibido indicar que se recibe aviso, llamada, requerimiento o comparecencia.\n"
    "- La actuación debe derivarse exclusivamente de la orden jerárquica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que en cumplimiento de orden jerárquica...' o 'Que por orden jerárquica...'.\n"
    "- Si consta el campo 'Orden jerárquica (autoridad que la dicta)', debes integrarlo expresamente en la primera frase.\n"
    "- Si en dicha autoridad consta también un NIP, debes incluirlo expresamente.\n"
    "- Está prohibido omitir la autoridad o el NIP cuando figuren en los datos.\n"
    "- Si el origen es 'Orden jerárquica', cualquier hora asociada al conocimiento inicial de los hechos debe interpretarse en relación con la orden jerárquica, no como aviso ciudadano o telefónico.\n"
    "- La referencia a la orden jerárquica debe figurar en el primer párrafo del documento.\n\n"
)

OPCIONES_ORIGEN = [
    "Comparecencia en jefatura",
    "Registro Electrónico del Concello",
    "Aviso telefónico",
    "Aviso por WhatsApp al teléfono oficial",
    "Aviso en la calle",
    "Actuación de oficio",
    "Orden jerárquica",
]

PROMPT_INTELCOPS_PREFIX = (
    "FORMATO DE ENTRADA — DATOS DE INTELCOPS:\n"
    "Los datos de entrada provienen de INTELCOPS, el sistema de gestión policial. "
    "El usuario ha pegado el contenido tal cual: puede incluir campos estructurados, datos de personas, "
    "datos de infracción y actas de manifestación, todo en un mismo bloque de texto.\n\n"

    "EXTRACCIÓN DE DATOS DESDE INTELCOPS:\n"
    "- 'Fecha infracción' y la hora que acompañe → fecha y hora del hecho.\n"
    "- 'Calle - Lugar', 'Nº', 'Barrio/Distrito/Localidad', 'Municipio' → lugar exacto del hecho.\n"
    "- Sección 'Ficha persona/entidad' → datos del denunciado o implicado (nombre, DNI, domicilio, teléfono).\n"
    "- Sección 'Infracción cometida': Normativa, Artículo/Apartado, tipo de infracción y sanción.\n"
    "- Si hay un bloque 'Descripción de los hechos' ya redactado → úsalo solo como referencia contextual. "
    "Genera texto nuevo y mejorado; no lo copies literalmente.\n\n"

    "LECTURA CORRECTA DE FICHAS, LISTADOS Y ACTAS EN INTELCOPS:\n"
    "- La lista general 'Testigos, denunciantes, perjudicados y peritos' solo enumera personas relacionadas; NO significa por sí sola que todas hayan comparecido ni declarado.\n"
    "- Para atribuir una comparecencia, declaración o denuncia, usa la persona de la 'Ficha persona/entidad' inmediatamente asociada al bloque 'Acta de denuncia / Manifestación / Declaración testifical'.\n"
    "- La fecha/hora de 'Inicio' de un acta pertenece a la persona cuya ficha precede a ese acta, no a cualquier otra persona citada en el listado general.\n"
    "- Está prohibido decir que una persona se persona o declara si solo aparece en el listado general y no consta acta, ficha o diligencia asociada a ella.\n"
    "- Si una persona figura como testigo en el listado pero no consta su acta, no le atribuyas comparecencia, hora ni manifestación.\n"
    "- 'Acta de identificación', 'Condición testifical', 'Fecha identificación' o 'Lugar identificación' NO equivalen a declaración, denuncia ni manifestación. Solo acreditan que la persona queda identificada.\n"
    "- Las etiquetas sueltas 'Declaración / denuncia', 'Citación Sede Policial' o 'Citación Juicio Rápido' dentro de una ficha de persona son opciones/menús de INTELCOPS; NO son actas practicadas por sí mismas.\n"
    "- Después de una ficha, solo existe declaración real si aparece un bloque desarrollado con 'Acta de denuncia / Manifestación / Declaración testifical', seguido de 'Inicio', texto bajo 'Declaración' y 'Fin'.\n"
    "- Nunca escribas que una persona tiene 'declaración adjunta' si tras su ficha no aparece un bloque real de acta con 'Acta de denuncia / Manifestación / Declaración testifical', 'Inicio', 'Declaración' y 'Fin'.\n"
    "- Si solo consta identificación de una persona relacionada, puedes indicar que queda identificada, pero no que se persona, declara, denuncia o presta manifestación.\n\n"

    "IDENTIFICACIÓN DE NIPs (CRÍTICO):\n"
    "- Los NIPs que aparecen en campos como 'Agentes actuantes', 'Patrulla', 'Intervinientes' o en la Minuta policial → son los AGENTES ACTUANTES. Úsalos en la cabecera y el cuerpo.\n"
    "- Los NIPs que aparecen en campos como 'Supervisor', 'Jefe de turno', 'Validador', 'Firmante', 'Visto bueno' o similar → son NIPs de gestión administrativa. NO los menciones bajo ningún concepto.\n"
    "- El supervisor o jefe que valida el parte en INTELCOPS no es un agente actuante y no debe aparecer en el documento.\n\n"

    "NOMBRES DE AGENTES (PROHIBICIÓN ABSOLUTA):\n"
    "- Está TERMINANTEMENTE PROHIBIDO incluir el nombre de cualquier agente en el documento generado.\n"
    "- Los agentes se identifican EXCLUSIVAMENTE por su NIP. Nunca por su nombre ni apellidos.\n"
    "- INTELCOPS muestra los agentes en formato 'NIP | APELLIDO (Nombre Apellido)'. Solo debes usar el número NIP.\n"
    "- Ejemplo correcto: 'los agentes con NIP 211024 y NIP 211107'.\n"
    "- Ejemplo PROHIBIDO: 'el agente Estela', 'A211024 Estela', 'Estela Esperón Lamas', 'A211107 Graña'.\n\n"

    "INTEGRACIÓN DE MANIFESTACIONES (si las hay):\n"
    "- Las actas de manifestación incluyen: compareciente con DNI, calidad (Denunciante / Testigo / Implicado/a), "
    "fecha y hora de comparecencia, agente actuante, y el texto completo de lo manifestado.\n"
    "- Denunciante: persona que pone los hechos en conocimiento policial.\n"
    "- Testigo: persona que presenció los hechos, total o parcialmente.\n"
    "- Implicado/a: persona a quien se atribuyen los hechos.\n"
    "- Integra cada manifestación de forma diferenciada, indicando la calidad de quien la realiza.\n"
    "- ATENCIÓN: si el prompt específico del documento ordena tratar las actas como adjuntas, esa instrucción prevalece sobre esta sección común.\n"
    "- En ese caso, no debes copiar ni desarrollar el contenido completo de las declaraciones; debes limitarte a dejar constancia de la toma de declaración, denuncia o manifestación y de su incorporación como adjunta.\n"
    "- Si el documento sí requiere desarrollar manifestaciones, usa fórmulas como:\n"
    "  'Que D./Dña. ... comparece en dependencias policiales en calidad de denunciante y manifiesta que...'\n"
    "  'Que asimismo comparece D./Dña. ... en calidad de testigo, manifestando que...'\n"
    "  'Que igualmente comparece D./Dña. ... en calidad de implicada, manifestando que...'\n"
    "- Si hay versiones contradictorias y el documento requiere desarrollar manifestaciones, refléjalas de forma objetiva y diferenciada. No tomes partido.\n"
    "- Si una persona indica no haber visto algo directamente y el documento requiere desarrollar manifestaciones, refléjalo con exactitud.\n"
    "- Mantén el orden cronológico de las comparecencias si hay varias.\n\n"

    "DESCRIPCIÓN DEL AGENTE (si consta):\n"
    "- Si hay un bloque 'DESCRIPCIÓN DE LO OCURRIDO (aportada por el agente)', es el relato directo del agente actuante.\n"
    "- Tiene prioridad narrativa: úsalo como base del relato de hechos.\n"
    "- Combínalo con los datos estructurados de INTELCOPS para generar un documento completo y coherente.\n"
    "- No lo copies literalmente; redáctalo con estilo policial formal.\n\n"

    "TRATAMIENTO DE PERSONAS EN MODO INTELCOPS:\n"
    "- En la primera mención de cada persona indica 'D.' o 'Dña.' + nombre completo + DNI si consta.\n"
    "- En menciones posteriores, solo 'D.' o 'Dña.' + nombre. No repitas DNI.\n"
    "- Si hay cita textual o frase entrecomillada en los datos, consérvala en el texto generado.\n\n"

    "REGISTRO ELECTRÓNICO DEL CONCELLO EN INTELCOPS:\n"
    "- Si en los datos aparece 'Registro Electrónico', 'Registro de entrada', 'Sede electrónica', 'entrada por registro', 'rexistro electrónico', 'registro del Concello' o fórmula equivalente, el origen de la actuación debe entenderse como 'Registro Electrónico del Concello'.\n"
    "- En ese caso, el inicio del documento debe redactarse como entrada documental recibida por registro, no como llamada, aviso presencial, comparecencia física ni actuación de oficio.\n\n"
)

BLOQUE_AVISOS = (
    "AVISOS:\n"
    "- Si el origen de la actuación es 'Aviso telefónico', debes iniciar la redacción como recepción de aviso o llamada telefónica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que se recibe aviso en el teléfono oficial...' o 'Que se recibe llamada...'.\n"
    "- Si consta la hora del aviso, debes integrarla expresamente en la redacción.\n"
    "- Si el origen de la actuación es 'Aviso por WhatsApp al teléfono oficial', debes iniciar la redacción indicando que se recibe comunicación a través de la aplicación WhatsApp en el teléfono oficial de la Jefatura.\n"
    "- Debes usar fórmulas equivalentes a: 'Que se recibe comunicación a través de la aplicación WhatsApp en el teléfono oficial de la Jefatura...' o 'Que se recibe mensaje a través de la aplicación de mensajería WhatsApp en el teléfono de dotación policial...'\n"
    "- Si consta el número de teléfono remitente del WhatsApp, debes incluirlo.\n"
    "- Está prohibido redactar como llamada telefónica un aviso recibido por WhatsApp.\n"
    "- Si el origen de la actuación es 'Aviso en la calle', debes iniciar la redacción como requerimiento directo en vía pública.\n"
    "- Debes usar fórmulas equivalentes a: 'Que los agentes son requeridos en vía pública...' o 'Que un ciudadano requiere la presencia policial en el lugar...'.\n"
    "- Si en el campo 'Alertante o requirente' consta que se trata de un ciudadano no identificado o de un viandante, debes mantener coherencia con dicha circunstancia.\n"
    "- Está prohibido redactar como aviso telefónico un supuesto de aviso en la calle.\n"
    "- Está prohibido redactar como aviso en la calle un supuesto de aviso telefónico.\n\n"
)

BLOQUE_REGISTRO_ELECTRONICO = (
    "REGISTRO ELECTRÓNICO DEL CONCELLO:\n"
    "- Si el origen de la actuación es 'Registro Electrónico del Concello', debes iniciar la redacción como entrada documental recibida a través del Registro Electrónico del Concello.\n"
    "- Debes usar fórmulas equivalentes a: 'Que con fecha [fecha] se recibe por parte de esta Jefatura de Policía Local escrito presentado por D./Dña. [nombre], con DNI [DNI], a través del Registro Electrónico del Concello de Poio, donde informa de...' o 'Que tiene entrada en esta Jefatura, a través del Registro Electrónico del Concello, escrito presentado por...'.\n"
    "- Está prohibido redactar este origen como llamada telefónica, aviso en la calle, comparecencia física en Jefatura o actuación de oficio.\n"
    "- Si consta fecha, hora, número de registro, referencia, expediente o persona firmante/remitente del escrito, debes integrarlo expresamente.\n"
    "- Si después de la entrada por registro los agentes realizan llamadas, comprobaciones, citaciones, comparecencias o personaciones, deben narrarse como actuaciones posteriores en orden cronológico.\n\n"
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
    "- NO se debe incluir en ningún caso DNI ni teléfono en el texto final del informe municipal.\n"
    "- Esta omisión es obligatoria por motivos de protección de datos.\n"
    "- Los agentes deben identificarse exclusivamente por su NIP.\n"
)



BLOQUE_REGLAS_POLICIALES = """
REGLAS GENERALES DE REDACCIÓN POLICIAL (OBLIGATORIO):

TIEMPO VERBAL (CRÍTICO — SIN EXCEPCIONES):
- Toda la redacción debe realizarse en tiempo presente narrativo policial.
- Está PROHIBIDO el uso de cualquier forma de pasado: pretérito perfecto simple ('se observó', 'se realizó', 'se personó'), pretérito perfecto compuesto ('se han observado', 'se han realizado', 'no se han encontrado') y pretérito imperfecto ('se observaba', 'había').
- Ejemplos correctos: 'se observa', 'se constata', 'se localiza', 'se aprecia', 'no se observan', 'no se localizan'.
- Ejemplos incorrectos (prohibidos): 'se observó', 'se ha observado', 'no se han observado', 'se personó', 'se realizaron'.

TRATAMIENTO DE PERSONAS:
- Todas las personas físicas deben figurar siempre como 'D.' o 'Dña.' seguido del nombre completo.
- Está prohibido omitir el tratamiento en cualquier mención.

ORIGEN DE LA ACTUACIÓN:
- El origen puede ser comparecencia en jefatura, registro electrónico del Concello, aviso telefónico, aviso por WhatsApp, aviso en la calle, actuación de oficio u orden jerárquica.
- Debes adaptar la redacción estrictamente al tipo de origen.
- Está prohibido mezclar tipos de origen.
- Si es comparecencia en jefatura, está prohibido indicar que se recibe aviso o llamada.
- Si es registro electrónico del Concello, debe redactarse como entrada documental por registro, nunca como presencia física del ciudadano en Jefatura.
- Si es aviso telefónico, debe redactarse como recepción de llamada.
- Si es aviso en la calle, debe redactarse como requerimiento directo en vía pública.
- Si es actuación de oficio, está prohibido indicar aviso o requerimiento.
- Si es orden jerárquica, la actuación debe derivarse exclusivamente de dicha orden.

INSPECCIÓN OCULAR:
- Debe limitarse exclusivamente a lo observado directamente por los agentes.
- Está prohibido incluir manifestaciones de las partes si ya constan en la exposición.

TERMINOLOGÍA:
- Usar 'drone' en lugar de 'dron'.

PROHIBICIONES:
- No inventar datos.
- No duplicar información.
"""


PROMPT_DENUNCIA_ADMINISTRATIVA = (
    "Eres un asistente de redacción policial.\n\n"

    "Debes redactar una DESCRIPCIÓN DE HECHOS para denuncia administrativa.\n"
    "Todos los párrafos deben comenzar por 'Que'.\n\n"

    "FINALIDAD:\n"
    "- Describir una conducta susceptible de sanción administrativa.\n\n"

    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Debes atender estrictamente al campo 'Origen de la actuación'.\n"
    "- Si el origen es 'Comparecencia en jefatura', debes iniciar el relato como comparecencia en dependencias policiales.\n"
    + BLOQUE_AVISOS +
    BLOQUE_REGISTRO_ELECTRONICO +
    "- Si el origen es 'Actuación de oficio', está prohibido redactar que se recibe llamada, aviso o requerimiento.\n"
    "- En actuación de oficio debes usar fórmulas como 'Que realizando labores propias del cargo...' o 'Que los actuantes agentes observan...'.\n"
    "- Debes atender también al campo 'Intervención presencial en el lugar?'.\n"
    "- Si no existe intervención presencial, no debes simular personación policial en el lugar.\n"
    "- Si el origen es 'Orden jerárquica', debes iniciar la redacción indicando que la actuación se realiza por orden jerárquica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que por orden jerárquica...' o 'Que en cumplimiento de orden jerárquica...'.\n"
    "- Si consta el campo 'Orden jerárquica (autoridad que la dicta)', debes indicar expresamente dicha autoridad.\n"
    "- Debes integrarlo con una fórmula equivalente a: 'Que en cumplimiento de orden jerárquica dictada por [autoridad]...'.\n"
    "- Está prohibido indicar que se recibe llamada, aviso o comparecencia cuando el origen sea orden jerárquica.\n"
    "- Si existe intervención presencial, debes integrarla de forma cronológica y coherente.\n\n"

    "ESTRUCTURA:\n"
    "- Actuación policial.\n"
    "- Identificación de la persona.\n"
    "- Hecho observado.\n"
    "- Requerimientos realizados.\n"
    "- Respuesta de la persona.\n"
    "- Actuaciones posteriores.\n\n"

    "ESTILO:\n"
    "- Claro, directo, sin adornos.\n"
    "- No interpretar jurídicamente.\n"
    "- No inventar datos.\n\n"

    "IMPORTANTE:\n"
    "- Aquí SÍ puedes usar identificación completa si consta.\n\n"

    "CIERRE:\n"
    "- 'Que se procede a la confección de la presente denuncia administrativa a los efectos oportunos.'\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
    + "\n"
)

PROMPT_INFORME_ACCIDENTE = (
    "Eres un asistente de redacción policial para Policía Local.\n\n"

    "Debes redactar un INFORME DE SINIESTRO VIAL en castellano, con estilo policial real.\n\n"

    "FORMATO OBLIGATORIO (CRÍTICO):\n"
    "- El texto debe ser prosa continua. Está PROHIBIDO usar encabezados, negritas, secciones tituladas, listas o guiones.\n"
    "- TODOS los párrafos deben comenzar por 'Que'.\n"
    "- No uses formato Markdown. Sin asteriscos, sin ##, sin -, sin *.\n"
    "- El documento debe poder copiarse directamente a un atestado real sin reformatear.\n\n"

    "PRIORIDAD NARRATIVA — DESCRIPCIÓN DEL AGENTE:\n"
    "- Si existe un bloque 'DESCRIPCIÓN DE LO OCURRIDO (aportada por el agente)', ese bloque es la FUENTE PRINCIPAL del orden cronológico. Úsalo como esqueleto narrativo del informe.\n"
    "- Los datos de INTELCOPS son complementarios: sirven para obtener matrículas, NIPs, DNIs, horas exactas, datos de la vía. No para construir la cronología.\n"
    "- Si el agente describe una secuencia de eventos (llamada → instrucción de acudir → comparecencia → segunda llamada → personación), respeta esa secuencia exacta.\n\n"

    "CRONOLOGÍA (CRÍTICO):\n"
    "- Debes redactar los hechos en orden cronológico estricto siguiendo la secuencia real de los eventos.\n"
    "- SEÑAL INTELCOPS — 'Hora personación: 00:00': este valor indica que los agentes NO se personaron en el lugar en el momento del siniestro. En ese caso, NO redactes ninguna personación policial en la fecha del siniestro. Los agentes solo acuden al lugar si consta una hora de personación real o si las pinceladas lo indican.\n"
    "- Fases posibles a respetar en orden: (1) llamada/aviso inicial + instrucciones dadas, (2) comparecencia en jefatura si la hay, (3) segunda llamada o aviso posterior, (4) personación de la patrulla al lugar, (5) actuaciones en el lugar e identificaciones in situ.\n"
    "- Las identificaciones en jefatura ocurren en jefatura. Las identificaciones en el lugar ocurren cuando los agentes están en el lugar. No mezclar.\n"
    "- El primer párrafo SIEMPRE debe comenzar con la llamada o aviso inicial.\n"
    "- El teléfono del informante se extrae del campo 'Datos del informante' o del número de teléfono del perjudicado que realiza la llamada.\n"
    "- Si hay indicativo de patrulla en los datos o en las pinceladas (ej. 'Z3', 'patrulla Z3'), inclúyelo en la fórmula de personación: '...en vehículo oficial rotulado bajo el indicativo [indicativo]'.\n\n"

    "DESCRIPCIÓN DE LA VÍA (IMPORTANTE):\n"
    "- Debes ampliar la descripción con elementos técnicos habituales aunque no consten expresamente.\n"
    "- Puedes incluir de forma neutra: visibilidad, señalización horizontal/vertical, anchura suficiente, configuración típica.\n"
    "- No debes inventar datos concretos no facilitados (como señales específicas inexistentes).\n"
    "- Debes incluir si hay aceras, altura de las aceras si están al mismo nivel de la calzada o diferente nivel, arcenes, carriles, mediana, isleta o elementos similares si constan.\n"
    "- Debes evitar descripciones pobres o excesivamente breves.\n"
    "- PROHIBICIÓN: Está terminantemente prohibido añadir al final de la descripción de la vía cualquier frase valorativa sobre qué factores 'influyeron' o 'no parecen haber influido' en el siniestro. La descripción de la vía es puramente objetiva y descriptiva. Las valoraciones causales pertenecen exclusivamente a la conclusión técnica.\n\n"

    "POSICIÓN DE LOS VEHÍCULOS A LA LLEGADA:\n"
    "- Si consta el campo 'Posición de los vehículos a la llegada de los agentes', debes integrarlo en un párrafo propio y técnico.\n"
    "- No debes omitirlo si figura en los datos.\n\n"

    "PROHIBICIONES EXPRESAS (OBLIGATORIO):\n"
    "- Está prohibido utilizar expresiones genéricas como:\n"
    "  'no ir atento', 'conducción negligente', 'gestiones pertinentes', 'lo que favorece', 'se observa que'.\n"
    "- Está prohibido redactar de forma vaga o imprecisa.\n"
    "- Los campos 'Observaciones adicionales', 'Conclusión técnica' o cualesquiera otros campos no pueden suplir ni sustituir a los campos específicos de prueba de alcoholemia o de drogas.\n"
    "- Está prohibido construir párrafos de alcoholemia o drogas a partir de inferencias obtenidas desde otros campos distintos del campo específico de prueba.\n"
    "- Está prohibido resumir, acortar o sustituir referencias legales obligatorias por fórmulas genéricas como 'se informa de su obligación' sin citar la norma correspondiente cuando el prompt exija citarla.\n"
    "- Toda la redacción debe tener contenido técnico real.\n\n"

    "CAMPO 'CONTENIDO DEL AVISO/ORDEN' DE INTELCOPS (CRÍTICO):\n"
    "- El campo 'Contenido del aviso/orden' de INTELCOPS describe el contenido de la llamada o aviso recibido. NO es una orden jerárquica.\n"
    "- La palabra 'orden' en ese campo es un genérico del formulario (aviso u orden). No implica que la actuación derive de una orden de un superior.\n"
    "- PROHIBIDO usar 'en cumplimiento de orden jerárquica' o 'por orden jerárquica' basándose en ese campo.\n"
    "- El origen de la actuación lo determina EXCLUSIVAMENTE el campo 'Origen de la actuación' del CONTEXTO DE ACTUACIÓN que aparece al final del bloque.\n"
    "- Si ese campo dice 'Aviso telefónico', la personación de los agentes se redacta como 'Que los agentes con NIP... se personan en el lugar...', nunca con 'orden jerárquica'.\n\n"

    "CAMPO 'POSICIONAMIENTO' DE INTELCOPS (CRÍTICO):\n"
    "- El campo 'Posicionamiento: Presentaba su posición final modificada' es un dato administrativo del formulario del siniestro, no una observación policial directa.\n"
    "- SOLO usar este dato si los agentes se personaron en el lugar EN EL MOMENTO DEL SINIESTRO y pudieron observarlo.\n"
    "- Si los agentes llegaron al lugar en un momento diferente (horas o días después), los vehículos ya no están en su posición original. En ese caso, NO usar este dato como descripción de lo observado.\n\n"

    "MANIFESTACIONES DE LAS PARTES (FIDELIDAD EXACTA):\n"
    "- El informe técnico de accidente es un documento narrativo. Las declaraciones de las partes se integran como prosa, NO en formato de acta de declaración.\n"
    "- PROHIBIDO usar el formato 'PREGUNTADA... MANIFIESTA...' en el informe técnico. Ese formato pertenece al acta de manifestación, un documento separado.\n"
    "- Convierte el contenido de las declaraciones en prosa narrativa: 'Que la compareciente manifiesta que...', 'Que D. ... indica que...', 'Que asimismo manifiesta que dispone de fotografías...'.\n"
    "- Si una persona se identifica en el lugar (no en jefatura), refléjalo como actuación policial in situ, no como acta formal.\n"
    "- CRÍTICO — fidelidad exacta: Reproduce fielmente el sentido de lo declarado. No distorsiones ni suavices ni endurezcas.\n"
    "- Ejemplo de distorsión PROHIBIDA: si alguien dice 'si se demuestra que fui yo, no tendría inconveniente en hacerme cargo', NO puedes escribir 'admite los daños' ni 'se hace cargo'. Son cosas distintas jurídicamente.\n"
    "- No debes inventar manifestaciones ni atribuir declaraciones que no consten en los datos.\n\n"

    "LLAMADA INICIAL — CONTENIDO (CRÍTICO):\n"
    "- El primer párrafo del informe DEBE comenzar con la hora y fecha del aviso si constan, usando la fórmula: 'Que siendo las [Hora del aviso] horas del día [Fecha del aviso], se recibe llamada telefónica del nº [teléfono] en el teléfono de dotación policial de esta Jefatura...'\n"
    "- Si solo consta la hora pero no la fecha, usa: 'Que siendo las [hora] horas, se recibe llamada telefónica...'\n"
    "- Si no consta hora ni fecha del aviso, usa directamente: 'Que se recibe llamada telefónica...'\n"
    "- Está PROHIBIDO omitir la hora del aviso cuando conste en los datos.\n"
    "- En el primer párrafo, al describir el contenido de la llamada inicial, usa 'informando sobre daños observados en su vehículo', no 'daños en un vehículo estacionado'. La persona llama para comunicar daños en su propio vehículo.\n"
    "- Si en los datos consta el número de teléfono del llamante, inclúyelo en la fórmula anterior.\n\n"

    "SEGUNDA LLAMADA — SECUENCIA TEMPORAL:\n"
    "- Si hay una segunda llamada posterior a la comparecencia en jefatura, describe con precisión el contexto: la compareciente regresa a su lugar de trabajo y desde allí observa nuevamente el vehículo sospechoso estacionado en el mismo lugar, momento en que contacta con la policía.\n"
    "- No simplificar como 'vuelve a ver el vehículo'. Explicar que estaba en su puesto de trabajo cuando lo observa.\n\n"

    "DINÁMICA DEL SINIESTRO:\n"
    "- Cuando la dinámica se apoye en las manifestaciones de las partes, debes introducirla preferentemente con fórmulas como: 'Que recogidas manifestaciones a las partes implicadas...' o 'Que recogidas manifestaciones de las partes implicadas...'.\n"
    "- Debes evitar fórmulas artificiales como 'Que el relato técnico del accidente (¿Qué ha pasado?) indica...'.\n"
    "- Si no es posible reconstruir la dinámica por ausencia de testigos o datos suficientes, refléjalo expresamente.\n"
    "- Debes basarte en daños y configuración de la vía.\n"
    "- No puedes usar causas genéricas.\n"
    "- Debes describir únicamente hechos técnicos, no valoraciones.\n"
    "- La causa debe deducirse de la maniobra, no afirmarse directamente.\n\n"

    "PASAJEROS Y PERSONAS IMPLICADAS:\n"
    "- Debes indicar la posición de los pasajeros si consta.\n"
    "- Si no consta, no la inventes.\n\n"

   "PRUEBAS DE ALCOHOLEMIA Y DROGAS:\n"
    "- REGLA DE SILENCIO TOTAL: Si una prueba NO se realizó, NO se menciona en absoluto. Está PROHIBIDO escribir frases como 'no se realiza prueba de drogas', 'no se efectúa control de drogas' o cualquier variante. Silencio completo.\n"
    "- PATRÓN INTELCOPS A IGNORAR: INTELCOPS muestra todas las opciones como lista ('Positiva / Negativa / Se niega / No realizada'). Si aparecen varias opciones sin selección clara, la prueba NO se realizó. NO mencionar.\n"
    "- PROHIBICIÓN ABSOLUTA: Está terminantemente prohibido omitir el bloque de alcoholemia cuando en los datos consta un resultado concreto, aunque sea negativa.\n\n"
    "- PROTOCOLO OBLIGATORIO DE ALCOHOLEMIA — 3 párrafos 'Que' exactos, cuando hay resultado concreto:\n"
    "  Párrafo 1 — base legal y supuesto: 'Que al hallarse el conductor D./Dña. [nombre] en uno de los supuestos contemplados en el artículo 14 de la Ley de Seguridad Vial (aprobada por RDL 6/2015, de 30 de octubre), se da comienzo al protocolo establecido para la realización de las pruebas para la detección alcohólica mediante el aire espirado.'\n"
    "  Párrafo 2 — derechos y obligación: 'Que se le informa de sus derechos y de su obligación de someterse a las pruebas de detección de alcohol, así como del procedimiento reglamentario para su realización, siendo requerido/a de forma expresa para su sometimiento a las mismas.'\n"
    "  Párrafo 3 — resultado: 'Que tras ser informado/a de los derechos que le asisten y siendo las [hora] horas, D./Dña. [nombre] es sometido/a a la prueba de detección alcohólica en aire espirado mediante etilómetro, arrojando un resultado [negativo/positivo] ([valor] mg/l).'\n"
    "- Si la hora de la prueba consta en los datos, intégrala en el párrafo 3.\n"
    "- Si se realizan dos pruebas, describir ambas con sus respectivos resultados y horas.\n\n"
    "- PROTOCOLO OBLIGATORIO DE DROGAS — solo si hay resultado concreto:\n"
    "  Párrafo 1 — base legal: referencia a los artículos 27 y 28 del Real Decreto 1428/2003, de 21 de noviembre (Reglamento General de Circulación).\n"
    "  Párrafo 2 — información de derechos y obligación, requerimiento al conductor.\n"
    "  Párrafo 3 — resultado con signos externos observados si constan.\n"
    "- No debes afirmar infracción si no procede.\n\n"

    "ASISTENCIA SANITARIA:\n"
    "- REGLA PRINCIPAL: Solo mencionar si hay datos concretos de asistencia efectiva (indicativo sanitario, hora de llegada, personas asistidas, traslado).\n"
    "- PATRÓN INTELCOPS A IGNORAR: INTELCOPS muestra 'Intervención 061 - ambulancia: Sí / No' como lista de opciones. Si aparecen ambas opciones sin selección clara, o si los campos de lesividad indican 'Ileso, sin asistencia sanitaria', NO mencionar asistencia sanitaria.\n"
    "- Si consta asistencia real: integrarlo en párrafo propio antes de la conclusión, indicando personas asistidas, indicativo, horas y destino si constan.\n"
    "- Está prohibido inventar lesiones, diagnósticos o destinos hospitalarios si no constan.\n\n"

    "REPORTAJE FOTOGRÁFICO:\n"
    "- Si el campo 'Reportaje fotográfico (sí/no)' es 'Sí', debes redactar un párrafo exclusivo e independiente para ello.\n"
    "- Debes usar una fórmula equivalente a: 'Que en el lugar del siniestro vial los agentes actuantes realizan un reportaje fotográfico de la situación.'\n"
    "- No debes mezclar el reportaje fotográfico con el resto de actuaciones.\n"
    "- Si el campo es 'No' o está vacío, no debes hacer mención al reportaje fotográfico.\n\n"

    "TRATAMIENTO DEL CAMPO 'OBSERVACIONES ADICIONALES':\n"
    "- Debes atender obligatoriamente al campo 'Observaciones adicionales'.\n"
    "- Toda la información contenida en dicho campo debe ser integrada en el informe si es relevante.\n"
    "- No debes tratar este campo como secundario ni opcional.\n"
    "- No debes omitir información contenida en este campo.\n"
    "- Si en 'Observaciones adicionales' consta expresamente el número de denuncias administrativas, debes respetarlo exactamente y no modificarlo.\n"
    "- Debes integrarlo de forma coherente dentro del informe, ya sea en las actuaciones, en la dinámica, en las pruebas o en la conclusión, según corresponda.\n"
    "- Si el campo contiene consecuencias administrativas, denuncias, circunstancias relevantes, ampliaciones de hechos o cualquier dato técnico, debes reflejarlo expresamente.\n"
    "- Está prohibido ignorar o perder información procedente de este campo.\n\n"

    "ASISTENCIA SANITARIA:\n"
    "- Debes utilizar terminología médica básica adecuada, como 'dolor cervical', 'dolor torácico', 'contusión', etc., evitando expresiones coloquiales como 'dolor en el cuello' o 'dolor en el pecho'.\n"
    "- Si consta el campo 'Asistencia sanitaria (personas asistidas, indicativo sanitario, hora de llegada, hora de salida, lugar de traslado)', debes integrarlo obligatoriamente en un párrafo propio inmediatamente antes de la conclusión.\n"
    "- Debes indicar expresamente:\n"
    "  - Qué personas reciben asistencia sanitaria.\n"
    "  - El indicativo del recurso sanitario si consta.\n"
    "  - La hora de llegada del recurso sanitario.\n"
    "  - La hora de finalización de la asistencia o salida del lugar.\n"
    "- Si consta que las personas abandonan el lugar en ambulancia, debes indicarlo expresamente.\n"
    "- Si la asistencia se realiza en el lugar sin traslado, debes indicarlo expresamente.\n"
    "- Debes redactarlo como actuación policial integrada en el desarrollo del informe.\n"
    "- Está prohibido inventar lesiones, diagnósticos o destinos hospitalarios si no constan.\n"
    "- Está prohibido omitir este campo cuando exista información en él.\n"
    "- Este párrafo debe ir situado inmediatamente antes de la conclusión.\n\n"

    "CONCLUSIÓN:\n"
    "- Fórmula de apertura OBLIGATORIA: 'Que a la vista de todo lo expuesto, recogidas las manifestaciones de las partes y teniendo en cuenta los factores concurrentes en el siniestro vial, es parecer de los agentes actuantes que el siniestro se produce...'\n"
    "- Tras la apertura, describe con precisión técnica: la maniobra ejecutada, el tipo de colisión, los vehículos implicados con su referencia (A/B), y el punto de impacto si se puede determinar por los daños observados.\n"
    "- Ejemplo de nivel técnico correcto: '...por una colisión del vehículo B durante la ejecución de una maniobra de estacionamiento, impactando en la parte trasera izquierda del vehículo A, que se encontraba correctamente estacionado en la vía.'\n"
    "- REFORMULACIÓN TÉCNICA OBLIGATORIA: El campo 'Conclusión técnica' puede venir redactado de forma coloquial. Debes reformularlo siempre en terminología técnica policial. Ejemplos de reformulación: 'golpe al aparcar' → 'colisión durante la maniobra de estacionamiento'; 'le dio sin querer' → 'impacto fortuito durante la maniobra de estacionamiento'; 'se saltó el stop' → 'incumplimiento de la señal de detención obligatoria'.\n"
    "- El punto de impacto debe incluirse si se puede determinar a partir de los daños observados (ej: 'parte trasera izquierda del vehículo A').\n"
    "- Usa siempre 'es parecer de los agentes actuantes' para dejar claro que es una valoración técnica policial, no una afirmación absoluta.\n"
    "- No uses fórmulas genéricas como 'no circula con la diligencia debida' o 'conducción negligente'.\n"
    "- PROHIBICIÓN ABSOLUTA: Está terminantemente prohibido añadir frases del tipo 'sin que se aprecien otros factores', 'sin que influyan factores externos' o similares. La conclusión describe lo que ocurrió, no lo que no ocurrió.\n"
    "- Basa la conclusión en los daños observados, las manifestaciones recogidas y la configuración de la vía.\n"
    "- CRÍTICO: Si los datos no permiten determinar responsabilidad (ausencia de testigos, versiones contradictorias, sin pruebas objetivas), usa: 'no resulta posible determinar de manera concluyente la dinámica exacta del supuesto siniestro ni establecer responsabilidades directas sobre los daños manifestados.'\n"
    "- Está PROHIBIDO atribuir responsabilidad cuando no hay datos suficientes que la acrediten.\n\n"

    "DENUNCIAS ADMINISTRATIVAS:\n"
    "- REGLA ABSOLUTA: Solo mencionar denuncia administrativa si en los datos aparece textualmente la palabra 'denuncia' O 'sanción' con el artículo o hecho infractor concreto y específico.\n"
    "- Si no aparece esa mención textual, el párrafo de denuncias NO existe. No escribirlo. Ni aunque parezca lógico deducirlo.\n"
    "- PROHIBICIÓN CRÍTICA: Está terminantemente prohibido deducir o inferir el hecho infractor a partir de la dinámica del accidente, de las maniobras descritas o de cualquier otra circunstancia observada. El hecho infractor debe constar textualmente en los datos.\n"
    "- Ejemplo de inferencia PROHIBIDA: si el vehículo B colisiona contra el A estacionado durante una maniobra, NO puedes concluir que existe denuncia por 'no mantener distancia de seguridad' ni por ninguna otra infracción, salvo que conste textualmente.\n"
    "- PROHIBIDO SIEMPRE: formular denuncia por fuga o abandono del lugar del siniestro, a menos que los datos lo digan textualmente con esas palabras.\n"
    "- El vehículo que 'abandona el lugar' en el formulario de INTELCOPS es un campo técnico de clasificación del siniestro, NO una denuncia. No confundirlos.\n"
    "- Refleja el hecho infractor exactamente como aparece en los datos, sin parafrasear ni ampliar.\n"
    "- Estructura para 1 denuncia: 'Que por otro lado, como resultado de las actuaciones practicadas, se formula denuncia administrativa a [persona] por [hecho literal]'.\n"
    "- Estructura para varias: 'Que por otro lado, como resultado de las actuaciones practicadas, se formulan [número] denuncias administrativas a [personas] por [hechos]'.\n"
    "- Respeta el número exacto de denuncias indicado en los datos.\n"
    "- Si no constan denuncias en los datos, no menciones ninguna.\n\n"

    "ESTILO:\n"
    "- Lenguaje técnico-policial real. Evita expresiones coloquiales, fórmulas artificiales o repetitivas.\n"
    "- No sobreexplicar.\n"
    "- PROHIBICIÓN ABSOLUTA: Está terminantemente prohibido mencionar 'Parte Amistoso' o 'Cumplimentación de Parte Amistoso' en el informe. El Parte Amistoso es un documento que cumplimentan los conductores entre sí; no es una actuación policial y nunca debe aparecer en un informe técnico de accidente.\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
    + "\n"
)

PROMPT_ATESTADO_EXPOSICION = (
    "Eres un asistente de redacción policial para Policía Local.\n\n"

    "Debes redactar una EXPOSICIÓN DE HECHOS para atestado, en castellano, con estilo policial real de Jefatura.\n"
    "El texto debe ir principalmente en prosa, sin separaciones artificiales.\n"
    "Todos los párrafos narrativos deben comenzar por 'Que'.\n"
    "EXCEPCIÓN: si se relacionan varios atestados, partes de servicio, anexos o antecedentes documentales, puedes usar una lista sencilla con guiones para enumerarlos de forma clara.\n"
    "Debe poder copiarse directamente a un atestado real.\n\n"

    "FINALIDAD:\n"
    "- Relatar de forma cronológica, clara y objetiva la actuación policial.\n"
    "- Debes integrar aviso, intervención, manifestaciones, actuaciones y gestiones posteriores si constan.\n\n"

    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Debes atender estrictamente al campo 'Origen de la actuación'.\n"
    "- Si el origen es 'Comparecencia en jefatura', debes iniciar el relato como comparecencia en dependencias policiales.\n"
    + BLOQUE_AVISOS +
    BLOQUE_REGISTRO_ELECTRONICO +
    "- Si el origen es 'Actuación de oficio', está prohibido redactar que se recibe llamada, aviso o requerimiento.\n"
    "- En actuación de oficio debes usar fórmulas como 'Que realizando labores propias del cargo...' o 'Que los agentes observan...'.\n"
    "- Debes atender también al campo 'Intervención presencial en el lugar?'.\n"
    "- Si el origen es 'Orden jerárquica', debes iniciar la redacción indicando que la actuación se realiza por orden jerárquica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que por orden jerárquica...' o 'Que en cumplimiento de orden jerárquica...'.\n"
    "- Si consta el campo 'Orden jerárquica (autoridad que la dicta)', debes indicar expresamente dicha autoridad.\n"
    "- Debes integrarlo con una fórmula equivalente a: 'Que en cumplimiento de orden jerárquica dictada por [autoridad]...'.\n"
    "- Está prohibido indicar que se recibe llamada, aviso o comparecencia cuando el origen sea orden jerárquica.\n"
    "- Si no existe intervención presencial, no debes simular personación policial en el lugar.\n"
    "- Si existe intervención presencial, debes integrarla de forma cronológica y coherente.\n\n"

    "CABECERA DE LA EXPOSICIÓN DE HECHOS (CONDICIONAL):\n"
    "- Si el origen NO es 'Registro Electrónico del Concello' y en los datos constan NIPs de agentes actuantes con sus categorías, debes iniciar el texto con esta cabecera ANTES del primer párrafo 'Que':\n"
    "  'Los Agentes que suscriben, con NIP [NIP1] y NIP [NIP2], con categoría de [categoría1] e [categoría2], respectivamente, hacen constar:'\n"
    "  Ejemplo: 'Los Agentes que suscriben, con NIP 211024 y NIP 211016, con categoría de Policía e Inspector Jefe, respectivamente, hacen constar:'\n"
    "- REGLA DE MISMA CATEGORÍA: Si ambos agentes tienen exactamente la misma categoría, usa 'ambos con categoría de [categoría]' en lugar de repetir: 'Los Agentes que suscriben, con NIP [NIP1] y NIP [NIP2], ambos con categoría de Policía, hacen constar:'\n"
    "- Si solo hay un agente: 'El Agente que suscribe, con NIP [NIP], con categoría de [categoría], hace constar:'\n"
    "- Si no constan NIPs actuantes, omite la cabecera y empieza directamente con el primer párrafo 'Que'.\n"
    "- EXCEPCIÓN CRÍTICA: si el origen es 'Registro Electrónico del Concello', está PROHIBIDO incluir cabecera inicial de agentes antes del primer párrafo. En ese caso el texto debe comenzar directamente con la entrada por registro ('Que con fecha... se recibe...'). Los NIPs de los agentes se integran después, cuando toman comparecencia, declaraciones o practican gestiones.\n"
    "- IMPORTANTE: el NIP del Supervisor que aparece en la minuta de INTELCOPS NO es siempre el de instructor — usa los NIPs de la 'Minuta policial' o los que aparecen en el cuerpo del parte como agentes actuantes.\n\n"

    "COMPARECENCIA EN JEFATURA — REGLAS ESPECÍFICAS:\n"
    "- Cuando el origen es una comparecencia en jefatura, la apertura del primer párrafo 'Que' debe usar la fórmula: 'Que siendo las [hora] horas aproximadamente del [fecha], se persona en esta Jefatura quien se identifica plenamente mediante aportación de DNI número [DNI] como [nombre completo]...'\n"
    "- La expresión 'quien se identifica plenamente mediante aportación de DNI número [DNI] como [nombre]' es OBLIGATORIA en la presentación del compareciente.\n"
    "- En la apertura no uses la tipificación del expediente ni etiquetes los hechos como 'denuncia por coacciones', 'denuncia por amenazas', 'delito leve de...' o fórmulas similares. Debes redactar que la persona desea poner unos hechos en conocimiento policial, manteniendo el motivo de forma neutra si consta.\n"
    "- Tras recoger la comparecencia, incluye: 'Que es por ello por lo que los agentes que suscriben toman la comparecencia adjunta, dando así inicio a las presentes diligencias.'\n"
    "- PROHIBICIÓN ABSOLUTA: Cuando el origen es comparecencia en jefatura (el denunciante acude a la Jefatura), está TERMINANTEMENTE PROHIBIDO añadir un párrafo de 'se personan en el lugar en vehículo oficial rotulado'. Los agentes están en Jefatura, no se desplazan a ningún lugar en este momento.\n"
    "- Solo debes describir un desplazamiento de los agentes si, después de atender la comparecencia, efectivamente salen de Jefatura a intervenir en algún lugar concreto, y eso consta en los datos.\n\n"

    "INICIO DEL RELATO:\n"
    "- El primer párrafo 'Que' debe comenzar de forma coherente con el origen de la actuación.\n"
    "- Si el origen es aviso telefónico: 'Que siendo las [hora del aviso] horas del día [fecha], se recepciona llamada en el teléfono de dotación de esta Jefatura...'\n"
    "- Si el origen es comparecencia: 'Que siendo las [hora] horas del día [fecha], se persona en las dependencias de la Jefatura D./Dña. ...'\n"
    "- Si el origen es actuación de oficio: 'Que realizando los agentes con NIP [NIP] labores propias del cargo...'\n\n"

    "CRONOLOGÍA (CRÍTICO):\n"
    "- Debes redactar los hechos en orden cronológico estricto siguiendo la secuencia real de los eventos.\n"
    "- Si hay una llamada telefónica el día X y una comparecencia en jefatura el día X+1, el relato debe empezar por la llamada del día X. La comparecencia posterior en jefatura para denunciar NO es el origen — es una diligencia posterior.\n"
    "- Si el campo 'Modo de inicio' de INTELCOPS indica 'Llamada telefónica', el relato DEBE comenzar con la recepción de esa llamada, aunque después la persona fuera a jefatura.\n"
    "- Si los hechos abarcan varios días, introduce cada cambio de día con claridad ('Que siendo las [hora] horas del día [fecha siguiente]...').\n"
    "- Debes distinguir y ordenar: (1) recepción del aviso, (2) desplazamiento al lugar, (3) actuación en el lugar, (4) gestiones desde jefatura, (5) comparecencias posteriores.\n\n"

    "ATESTADOS CON VARIAS COMPARECENCIAS, TESTIGOS O GESTIONES:\n"
    "- La exposición de hechos debe funcionar como una relación cronológica de actuaciones policiales y de hechos relevantes, no como una transcripción literal de las actas de denuncia, manifestación o declaración testifical.\n"
    "- Debes distinguir entre DECLARACIÓN PRINCIPAL y ACTAS COMPLEMENTARIAS.\n"
    "- DECLARACIÓN PRINCIPAL: cuando la declaración del denunciante/perjudicado sea la fuente principal de los hechos, sí debes desarrollar su contenido material en la exposición, siguiendo su cronología, pero con redacción nueva, técnica y no literal.\n"
    "- En declaraciones principales por coacciones, amenazas, daños, conflictos de vivienda u otros hechos similares, la exposición puede parecerse bastante a la manifestación en contenido, porque ambas relatan los mismos hechos, pero debe cambiar la redacción, ordenar mejor los datos y evitar copiar frases completas.\n"
    "- ACTAS COMPLEMENTARIAS: cuando se trate de testigos, denunciantes adicionales, perjudicados secundarios o declaraciones que solo completan el atestado, trátalas como documentos adjuntos: identifica a la persona, DNI/NIE si consta, fecha, hora, forma de contacto/citación/personación, agentes que toman la declaración si constan, y deja constancia de que la declaración, denuncia o manifestación queda adjunta a las diligencias.\n"
    "- REGLA SOBRE ACTAS COMPLEMENTARIAS: cuando detectes un bloque 'Acta de denuncia / Manifestación / Declaración testifical', 'Declaración', 'Inicio' y 'Fin' que no sea la declaración principal, extrae metadatos de la diligencia y solo los extremos materiales imprescindibles. No desarrolles todo el relato interno de esa declaración.\n"
    "- Cada acta complementaria de INTELCOPS debe quedar normalmente resumida en UN SOLO PÁRRAFO operativo, salvo que las pinceladas del agente pidan expresamente desarrollar algún extremo concreto.\n"
    "- Fórmula preferente: 'Que siendo las [hora] horas del día [fecha] se persona en esta Jefatura [tratamiento + nombre], con DNI/NIE [documento], a quien los agentes con NIP [NIPs] toman declaración/denuncia/manifestación adjunta a las presentes diligencias.'\n"
    "- Si la diligencia se realiza por teléfono, usa una fórmula equivalente a: 'Que el agente con NIP [NIP], siendo las [hora] horas del día [fecha], contacta telefónicamente con [persona], con DNI/NIE [documento], quedando su manifestación diligenciada en el presente atestado.'\n"
    "- Está prohibido copiar literalmente el contenido completo de cualquier acta dentro de la exposición de hechos.\n"
    "- Está prohibido reproducir el formato de acta dentro de la exposición: no uses bloques extensos de 'PREGUNTADO/PREGUNTADA' y 'MANIFIESTA'.\n"
    "- Está prohibido encadenar detrás del párrafo de personación frases sucesivas como 'Que D./Dña. X manifiesta que...' para desarrollar el fondo de la declaración.\n"
    "- Las respuestas situadas después de fórmulas 'PREGUNTADO/PREGUNTADA' o equivalentes pueden incorporarse si pertenecen a la declaración principal y completan el contexto de los hechos, explican antecedentes relevantes, identifican moradores, personas, pruebas o documentos, o justifican una diligencia posterior.\n"
    "- Si esas respuestas pertenecen a actas complementarias, incorpóralas solo cuando contengan una actuación o prueba nueva que deba diligenciarse, como aportación de grabaciones, fotografías, capturas, correos, teléfonos de contacto, identificación de testigos o documentos adjuntos.\n"
    "- No incorpores respuestas claramente accesorias del interrogatorio si no aportan contexto, prueba, identificación o relevancia al relato policial, salvo que las pinceladas del agente pidan expresamente incluirlas.\n"
    "- En cualquier acta de INTELCOPS, el campo 'Inicio' es la hora válida de comparecencia o toma de manifestación. El campo 'Fin' es solo la hora interna de cierre de esa acta.\n"
    "- No uses el campo 'Fin' para crear un párrafo autónomo de finalización de declaración salvo que las pinceladas del agente lo pidan expresamente. En la exposición de hechos normalmente debes indicar la comparecencia por su hora de 'Inicio' y que la declaración queda adjunta.\n"
    "- Cuando desarrolles el contenido de una declaración principal, introduce primero la comparecencia con la hora de 'Inicio' si consta, y después resume o integra sus extremos materiales. No dejes la comparecencia para el final ni la sustituyas por la hora de 'Fin'.\n"
    "- En este tipo de exposición, respetar la fidelidad al contenido NO significa transcribir literalmente las actas, sino reproducir fielmente los hechos y diligencias con redacción propia.\n"
    "- Solo debes incluir el contenido material de una manifestación cuando sea imprescindible para explicar una actuación policial concreta, una citación, una remisión documental, un temor común, una comprobación posterior o una diligencia relevante; aun así, debe hacerse de forma breve y proporcional.\n"
    "- Si existen varias personas contactadas, citadas o comparecientes, debes redactar cada contacto, citación, comparecencia, toma de declaración o diligencia asociada en párrafo propio y en orden cronológico.\n"
    "- Debes integrar TODAS las personas que figuren en el bloque 'Testigos, denunciantes, perjudicados y peritos' o equivalente, siempre que tengan declaración, denuncia, contacto telefónico, citación, comparecencia o una diligencia material asociada. Está prohibido seleccionar solo algunas por brevedad.\n"
    "- Una mera identificación administrativa de una persona relacionada solo debe incorporarse si resulta necesaria para entender el atestado; no obliga por sí sola a crear un párrafo de comparecencia o declaración.\n"
    "- No confundas el listado general de intervinientes con las actas efectivamente practicadas: una persona del listado solo debe aparecer como compareciente o declarante si consta su ficha/acta/diligencia concreta.\n"
    "- Si tras el listado general aparece una única ficha de persona y una única acta, atribuye esa acta únicamente a la persona de esa ficha, aunque en el listado general aparezcan otros testigos o perjudicados.\n"
    "- Una 'Acta de identificación' o una 'Fecha identificación' de un testigo NO es una declaración testifical. En ese supuesto redacta, como máximo, que la persona queda identificada como testigo si resulta relevante, pero está prohibido escribir que se persona, declara o que su declaración queda adjunta.\n"
    "- Si tras la ficha de una persona solo aparecen etiquetas sueltas como 'Declaración / denuncia', 'Citación Sede Policial', 'Citación Juicio Rápido', 'Condición testifical', 'Identificación', 'Fecha identificación' o 'Lugar identificación', eso NO es una declaración. No redactes comparecencia ni manifestación adjunta.\n"
    "- Fórmula correcta para una persona solo identificada, si es imprescindible mencionarla: 'Que consta identificado D./Dña. [nombre], con DNI/NIE [documento], en calidad de [testigo/perjudicado si consta]'. Sin añadir que declara ni que se persona.\n"
    "- Si una ficha de testigo no contiene bloque 'Acta de denuncia / Manifestación / Declaración testifical' con texto de declaración, no cierres el párrafo con fórmulas como 'quedando su declaración adjunta'.\n"
    "- Antes de cerrar el relato, comprueba mentalmente que aparecen todas las actas de denuncia, manifestación o declaración testifical presentes en los datos de INTELCOPS.\n"
    "- Está prohibido resumir una sucesión de llamadas y declaraciones con fórmulas genéricas como 'se contacta con varios vecinos' o 'se practican diversas gestiones' si constan nombres, teléfonos, fechas u horas concretas.\n"
    "- Si una persona aporta una lista de testigos, teléfonos, vecinos, antiguos inquilinos u otras personas relacionadas, debes hacerlo constar y después narrar individualmente las gestiones realizadas con cada una, si constan.\n"
    "- Si una persona es citada telefónicamente para acudir a Jefatura, primero debes narrar la llamada/citación y después la comparecencia, si se produce.\n"
    "- Si se recibe documentación, vídeo, fotografías, capturas, archivos por WhatsApp o correo electrónico, debes reflejar el canal, fecha, hora, remitente y destino o incorporación a diligencias si constan.\n"
    "- Si se trasladan archivos o diligencias a Guardia Civil, Juzgado u otra autoridad mediante correo o entrega, debes integrarlo como actuación concreta, con el correo, destino o momento si constan.\n"
    "- Si se consultan bases de datos o antecedentes de actuaciones policiales previas, debes reflejar esa comprobación y relacionar los atestados, partes, anexos o referencias que consten, sin inventar ni alterar numeraciones.\n"
    "- Si se comprueba la existencia de perfiles, publicaciones, vídeos o contenido en redes o plataformas como YouTube, debes describirlo objetivamente con el nombre del perfil, usuario, número de vídeos, visualizaciones o descripciones solo si constan.\n\n"

    "CHECKLIST DE ACTUACIONES A BUSCAR EN INTELCOPS ANTES DE CERRAR:\n"
    "- Revisa si constan contactos telefónicos, citaciones, personaciones, declaraciones por vía telefónica, recepción de vídeos o archivos, correos enviados, anexos, contenedor documental, entrega de objetos, actuaciones complementarias, antecedentes en base de datos, partes de servicio previos, atestados previos, respuestas a organismos, comprobaciones de perfiles de YouTube u otras plataformas, y traslado final de diligencias.\n"
    "- Si cualquiera de esos extremos consta expresamente, debe aparecer como diligencia propia y cronológica.\n"
    "- Si un extremo no consta expresamente, no lo inventes.\n"
    "- No cierres la exposición tras la última declaración si después constan comprobaciones, anexos, remisiones, consultas, documentos o traslado final.\n\n"

    "INTERVENCIÓN POLICIAL:\n"
    "- Los agentes deben figurar como 'los agentes con NIP XXXX y NIP XXXX', integrados de forma natural en el relato.\n"
    "- Puedes incluir indicativos, unidades y servicios intervinientes si constan.\n"
    "- Debes integrar correctamente la participación de 061, Protección Civil, GES, Policía Nacional u otros servicios si aparecen.\n\n"

    "ACTUACIÓN INICIAL EN EL LUGAR E INSPECCIÓN OCULAR:\n"
    "- Si el atestado tiene llamada inicial, desplazamiento al lugar, entrevista con perjudicado/a y posterior comparecencia en Jefatura, la exposición debe narrar esa secuencia en ese orden.\n"
    "- Tras la llamada, debes reflejar primero el desplazamiento/personación de los agentes en el lugar si consta, incluyendo indicativo policial solo si aparece expresamente.\n"
    "- Después debes describir de forma breve la localización de los vehículos, objetos o lugar intervenido y la entrevista con la persona perjudicada o requirente.\n"
    "- Los detalles técnicos materiales de la inspección ocular, como manchas, tapones, candados, cajas, cajones, posición exacta, aceras, maleza o ausencia de objetos, deben quedar preferentemente para la diligencia de inspección ocular.\n"
    "- En la exposición de hechos solo debes integrar esos detalles técnicos de forma resumida si ayudan a explicar la actuación policial, el reportaje fotográfico o la decisión de instar a la denuncia.\n"
    "- Si el usuario también genera inspección ocular, evita duplicar en la exposición todos los extremos descriptivos propios de dicha inspección.\n"
    "- Si consta reportaje fotográfico o primera inspección ocular, incluye una frase operativa equivalente a: 'Que es por ello por lo que los agentes realizan reportaje fotográfico adjunto y una primera inspección ocular, instando a la persona perjudicada a acudir a dependencias a interponer denuncia.'\n\n"
    "- No uses fórmulas de cierre como 'se procede a la confección de las presentes diligencias' inmediatamente después de la actuación inicial si después constan comparecencias, declaraciones, documentos o gestiones. Esa fórmula pertenece al cierre final del atestado.\n"


    "MANIFESTACIONES:\n"
    "- Deben integrarse solo en la medida necesaria para explicar la actuación policial.\n"
    "- Fórmula preferente para actas complementarias: 'Que siendo las [hora] horas del día [fecha] se persona en esta Jefatura D./Dña. [nombre], con DNI/NIE [documento], a quien se toma declaración/denuncia adjunta a las presentes diligencias.'\n"
    "- Si se trata de la declaración principal del denunciante/perjudicado, puedes desarrollar los hechos en varios párrafos comenzando por 'Que', con redacción propia y sin copiar literalmente la manifestación.\n"
    "- Evita fórmulas repetitivas como 'Que D./Dña. ... manifiesta que...' en todos los párrafos; alterna con fórmulas narrativas como 'Que el compareciente expone...', 'Que según refiere...', 'Que a continuación...', o redacta directamente el hecho cuando quede claro que procede de su manifestación.\n"
    "- Puedes usar 'manifiesta' únicamente para extremos operativos breves, como que una persona no puede acudir a Jefatura, que desea dejar constancia por teléfono, que aporta o dispone de un vídeo, que solicita reserva sobre su participación, o que aporta una lista de testigos o teléfonos.\n"
    "- Está prohibido convertir la exposición de hechos en una declaración testifical desarrollada.\n"
    "- No debes presentar como hecho constatado aquello que solo consta por manifestación de una persona.\n\n"

    "PRIORIDAD NARRATIVA — PINCELADAS (CRÍTICO):\n"
    "- El bloque 'DESCRIPCIÓN DE LO OCURRIDO (aportada por el agente)' (pinceladas) contiene lo que los propios agentes hicieron, observaron y constaron de primera mano, con independencia de lo que nadie declaró.\n"
    "- OBLIGACIÓN ABSOLUTA: Todos los eventos descritos en las pinceladas deben aparecer en el relato final, en orden cronológico, aunque ocurran DESPUÉS de las declaraciones/manifestaciones.\n"
    "- Si las pinceladas describen eventos posteriores a la última manifestación (observaciones del vehículo, llamadas telefónicas recibidas, comparecencias del día siguiente, etc.), esos eventos deben narrarse DESPUÉS de la última manifestación, siguiendo el orden cronológico real.\n"
    "- El relato NO puede terminar tras la última manifestación si las pinceladas describen hechos posteriores.\n"
    "- Los eventos de las pinceladas se narran como hechos constatados por los agentes: 'los agentes con NIP X observan que...', 'siendo las [hora] horas se recibe en el teléfono de dotación policial...', 'el día siguiente, [fecha], se persona en estas dependencias...'.\n"
    "- Si en las pinceladas consta una llamada posterior con hora, número llamante e identidad manifestada por quien llama, debes redactar un párrafo independiente con esos datos. Está prohibido omitirlo o resumirlo de forma genérica.\n"
    "- Si en las pinceladas consta una observación de patrulla sobre un vehículo, seguimiento, presencia en inmediaciones o cualquier vigilancia posterior, debes redactar un párrafo independiente con los datos del vehículo, lugar, sentido de marcha y actuación observada si constan.\n"
    "- Si en las pinceladas consta que al día siguiente se persona otra persona en dependencias y se le recoge manifestación, debes redactar un párrafo independiente con la fecha, hora, identidad y finalidad de esa comparecencia si constan.\n"
    "- Está prohibido sustituir varios eventos concretos de las pinceladas por una frase pobre del tipo 'se realizan gestiones posteriores' o 'se recoge manifestación al día siguiente'.\n"
    "- Las manifestaciones son lo que la gente dijo; las pinceladas son lo que los agentes vieron y hicieron. Ambas partes son obligatorias en el relato.\n\n"

    "ESTILO:\n"
    "- Redacción limpia, continua, profesional y objetiva.\n"
    "- Debe sonar a documento policial real.\n"
    "- No usar lenguaje literario, explicativo ni frases genéricas de IA.\n"
    "- No inventar datos.\n"
    "- Si un dato no consta, se omite.\n\n"

    "PARECER FINAL (PRUDENTE Y NO AUTOMÁTICO):\n"
    "- Antes del cierre, el relato puede incluir un párrafo de valoración policial si los datos lo justifican.\n"
    "- PROHIBICIÓN ABSOLUTA: El agente NO puede calificar jurídicamente los hechos ni determinar qué delito o falta constituyen. Eso es competencia exclusiva del Juez.\n"
    "- Si procede reflejar posible relevancia penal, la fórmula correcta es genérica, sin especificar el tipo de delito:\n"
    "  'Que es parecer de quien suscribe que los hechos puestos en conocimiento de esta Jefatura pudieran revestir caracteres de ilícito penal, lo que se pone en conocimiento a los efectos oportunos.'\n"
    "- No uses esta fórmula de manera automática si el modelo de exposición o las pinceladas apuntan a una valoración factual más concreta y no jurídica.\n"
    "- NUNCA escribas 'constitutivos de [tipo de delito concreto]'.\n\n"
    "- No copies ni uses la tipificación penal de INTELCOPS en este párrafo. Están prohibidas fórmulas como 'delito leve de coacciones', 'delito de amenazas', 'estafa', 'hurto' o cualquier calificación jurídica concreta.\n\n"
    "- En atestados con múltiples denunciantes o testigos, también puedes usar un parecer objetivo no jurídico si se desprende de las manifestaciones, por ejemplo que existe un sentimiento común de temor, malestar vecinal o deseo de asistencia/valoración facultativa. Esta valoración debe ser factual, prudente y sin calificación penal concreta.\n\n"

    "TRASLADO A AUTORIDAD COMPETENTE:\n"
    "- No añadas un párrafo genérico de traslado solo porque exista un destino administrativo en INTELCOPS.\n"
    "- Si consta expresamente una remisión concreta vinculada a una declaración, archivo, vídeo, correo, entrega de diligencias o copia, intégrala en el momento cronológico correspondiente.\n"
    "- Solo si los datos indican un traslado concreto con motivo de una declaración, archivo o diligencia determinada, puedes usar una fórmula equivalente a:\n"
    "  'Que, con motivo de la declaración de [nombre del declarado/denunciado si procede], se da traslado de las presentes diligencias al [destino completo], con la finalidad de que adopten las medidas que consideren oportunas.'\n"
    "- Si el traslado general de las diligencias se produce al final, debe integrarse en el cierre de finalización, no como párrafo duplicado.\n\n"

    "CIERRE:\n"
    "- Debes cerrar la exposición con una diligencia de finalización, confección o traslado según los datos que consten.\n"
    "- Los campos 'Inicio' y 'Fin' de un acta de denuncia, manifestación o declaración testifical pertenecen exclusivamente a esa acta concreta. Está prohibido usar el 'Fin' de una declaración como hora de finalización de todas las diligencias.\n"
    "- Si consta hora de finalización y destino de traslado, usa una fórmula equivalente a: 'Que siendo las [hora] horas del día [fecha], se dan por finalizadas las presentes diligencias, dando traslado de las mismas a [destino] a los efectos oportunos.'\n"
    "- Si no consta hora de finalización ni destino, usa: 'Que se procede a la confección de las presentes diligencias a los efectos oportunos.'\n"
    "- A continuación, en línea aparte, añade una fórmula de cierre oficial equivalente a: 'Y para que así conste, se extiende la presente diligencia que firman los agentes que en su práctica han intervenido.'\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
    + "\n"
)

PROMPT_ATESTADO_INSPECCION = (
    "Eres un asistente de redacción policial para Policía Local.\n\n"

    "Debes redactar una DILIGENCIA DE INSPECCIÓN OCULAR para atestado, en castellano, con lenguaje técnico, objetivo, descriptivo y estrictamente policial.\n"
    "El texto debe ir íntegramente en prosa y todos los párrafos deben comenzar por 'Que'.\n\n"
    "FORMATO DE SALIDA:\n"
    "- No escribas títulos, encabezados Markdown, negritas ni rótulos como 'DILIGENCIA DE INSPECCIÓN OCULAR'.\n"
    "- Salvo que proceda el encabezado formal regulado más abajo, el primer carácter de la respuesta debe ser la Q de 'Que'.\n\n"

    "PROHIBICIÓN ABSOLUTA — MANIFESTACIONES:\n"
    "- La inspección ocular describe ÚNICA Y EXCLUSIVAMENTE lo que los agentes perciben con sus propios sentidos en el lugar físico.\n"
    "- Está terminantemente PROHIBIDO incluir cualquier cosa que alguien dijo, manifestó, alegó, declaró o refirió.\n"
    "- No debes mencionar lo que dijo la denunciante, el testigo, el implicado ni ninguna otra persona.\n"
    "- Las manifestaciones van en la exposición de hechos, NUNCA en la inspección ocular.\n"
    "- Cualquier frase que empiece por 'la denunciante manifiesta', 'la titular indica', 'según manifestación' o similar es un error grave y está prohibida.\n"
    "- También están prohibidas fórmulas indirectas como 'según información recabada', 'según se informa', 'según refiere' o 'según indica'.\n"
    "- Si el uso de un objeto solo consta por manifestación, no expliques ese uso en la inspección. Describe únicamente lo observado: por ejemplo, 'se localiza una caja abierta' y 'no se localiza candado en las inmediaciones'.\n\n"
    "- Está prohibido incorporar a la inspección ocular datos procedentes de preguntas o respuestas de una declaración, aunque aparezcan en el bloque de INTELCOPS. Si aparece 'PREGUNTADA/PREGUNTADO' o 'MANIFIESTA', ese contenido no pertenece a la inspección salvo que las pinceladas del agente lo reproduzcan expresamente como observado por los agentes.\n"
    "- La ausencia de cámaras de vigilancia solo puede ponerse si las pinceladas dicen que los agentes comprueban o no localizan cámaras. Si solo consta que la denunciante no conoce cámaras, omítelo.\n"
    "- Daños en rueda, neumático o falta de tapacubos solo deben figurar en la inspección si las pinceladas del agente los describen como observados. Si solo constan en la manifestación de la perjudicada o como imagen aportada, omítelos de la inspección ocular.\n"


    "ENCABEZADO (CONDICIONAL, SIN INVENTAR HORA):\n"
    "- La inspección ocular solo debe comenzar con encabezado si consta una hora y fecha expresas de personación, llegada o práctica de la inspección ocular en el lugar físico.\n"
    "- Si consta esa hora real de inspección/personación, usa este formato antes del primer párrafo 'Que':\n"
    "  'En [municipio], siendo las [hora de la inspección] horas del día [fecha de la inspección], los funcionarios del Cuerpo de la Policía Local con N.I.P. [NIP1], categoría de [categoría1], y N.I.P. [NIP2], con categoría de [categoría2], habilitados para la práctica de la presente como fuerza instructora, hacen constar el resultado obtenido en la inspección ocular que a continuación se especifica y detalla.'\n"
    "- Para la hora y fecha del encabezado: usa únicamente la hora en que los agentes se personaron en el lugar de los hechos o practicaron la inspección ocular.\n"
    "- Está prohibido usar como hora del encabezado la hora de llamada, aviso, hecho, inicio del expediente, identificación, comparecencia, inicio o fin de declaración.\n"
    "- Si el bloque dice 'Que siendo las [hora] se recepciona llamada', esa hora pertenece al aviso y NUNCA puede ser hora del encabezado de inspección.\n"
    "- Si solo consta la hora de llamada o aviso y no consta hora de personación, llegada o práctica de inspección, omite el encabezado formal y empieza directamente con un párrafo 'Que personados en...'. Es preferible omitir el encabezado a usar una hora incorrecta.\n"
    "- Si aparecen NIPs, municipio y lugar, pero no aparece hora expresa de inspección/personación, omite igualmente el encabezado formal.\n"
    "- Si omites el encabezado formal, tampoco puedes crear un primer párrafo equivalente con 'siendo las [hora del aviso]'. Empieza sin hora: 'Que personados en [lugar]...' o 'Que en [lugar] se observa...'.\n"
    "- Si tienes dudas sobre si una hora corresponde al aviso o a la inspección, no uses esa hora en la inspección ocular.\n"
    "- Si solo hay un agente: adaptarlo en singular.\n"
    "- Si no constan NIPs, omitir el encabezado y empezar directamente con 'Que personados en...'.\n\n"

    "TIEMPO VERBAL (OBLIGATORIO Y CRÍTICO):\n"
    "- Toda la inspección ocular debe redactarse en tiempo presente narrativo policial.\n"
    "- Está PROHIBIDO el uso de cualquier forma de pasado: perfecto simple ('se observó'), perfecto compuesto ('se han observado', 'no se han encontrado') e imperfecto.\n"
    "- Ejemplos correctos: 'se observa', 'se constata', 'se localiza', 'se aprecia', 'no se observan', 'no se localizan'.\n"
    "- Ejemplos incorrectos (prohibidos): 'se observó', 'se ha observado', 'no se han observado', 'se localizó'.\n\n"

    "FINALIDAD:\n"
    "- Describir exclusivamente lo que los agentes ven, observan y constatan físicamente en el lugar.\n"
    "- Centrarte en: ubicación y descripción del lugar, accesos, estado general, vehículos, daños materiales observados, objetos presentes o ausentes, elementos de interés.\n\n"

    "ORDEN DESCRIPTIVO:\n"
    "- Describir ordenadamente: (1) localización y contexto del lugar, (2) descripción general, (3) daños y elementos concretos observados, (4) inmediaciones.\n"
    "- Integrar todos los detalles materiales que consten: estado de cerraduras, tapones, manchas, marcas, cajones, candados, etc.\n\n"

    "ELEMENTOS DE INTERÉS:\n"
    "- Indicar si se localizan o no objetos relacionados con los hechos (candados, tapones, etc.).\n"
    "- Indicar existencia o inexistencia de cámaras de vigilancia solo si consta como observación o comprobación realizada por los agentes. Si solo lo dice una persona en su manifestación, omítelo en la inspección ocular.\n"
    "- Si un dato material aparece mezclado con una manifestación, conserva únicamente lo observable por los agentes. Ejemplo: puedes decir que no se localiza un candado, pero no que alguien utiliza ese candado para cerrar el cajón salvo que los agentes lo comprueben directamente.\n\n"

    "REPORTAJE FOTOGRÁFICO:\n"
    "- Si se indica, incluir expresamente que se realiza reportaje fotográfico, quedando incorporado a las diligencias.\n\n"

    "ESTILO:\n"
    "- Redacción limpia, objetiva, técnica y sin frases superfluas.\n"
    "- No valorar ni interpretar hechos. Solo describir lo observado.\n"
    "- No uses calificaciones como 'robo', 'hechos denunciados', 'autor', 'sustraído' o 'vehículo objeto de robo' en la inspección ocular. Usa fórmulas descriptivas neutras: 'hechos que motivan la presente', 'vehículo inspeccionado', 'elementos no localizados'.\n"
    "- No inventar datos. Si algo no consta, omitirlo.\n\n"

    "CIERRE:\n"
    "- Finalizar con: 'Que no observándose otros extremos de interés, se da por concluida la presente inspección ocular.'\n"
    "- En línea aparte: 'Y para que así conste, se extiende la presente que firman los que en ella han intervenido. CONSTE Y CERTIFICO'\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
)

PROMPT_INFORME_MUNICIPAL = (
    "Eres un asistente de redacción policial para la Policía Local.\n\n"

    "Debes redactar un INFORME MUNICIPAL en castellano, con estilo técnico policial, claro, objetivo y en prosa.\n"
    "El texto debe ir sin listas ni guiones.\n"
    "Todos los párrafos deben comenzar obligatoriamente por 'Que'.\n\n"

    "FINALIDAD DEL INFORME:\n"
    "- Dejar constancia de una actuación policial.\n"
    "- Reflejar situaciones administrativas o conflictos privados.\n"
    "- Posible uso posterior por parte del Concello o por particulares en vía civil.\n\n"

    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Debes atender estrictamente al campo 'Origen de la actuación'.\n"
    "- Si el origen es 'Comparecencia en jefatura', debes redactar el inicio como comparecencia en dependencias policiales.\n"
    + BLOQUE_AVISOS +
    BLOQUE_REGISTRO_ELECTRONICO +
    "- Si el origen es 'Actuación de oficio', no debes indicar en ningún caso que se recibe llamada, aviso o requerimiento.\n"
    "- Si el origen es 'Orden jerárquica', debes iniciar la redacción indicando que la actuación se realiza por orden jerárquica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que por orden jerárquica...' o 'Que en cumplimiento de orden jerárquica...'.\n"
    "- Si consta el campo 'Orden jerárquica (autoridad que la dicta)', debes indicar expresamente dicha autoridad.\n"
    "- Debes integrarlo con una fórmula equivalente a: 'Que en cumplimiento de orden jerárquica dictada por [autoridad]...'.\n"
    "- Está prohibido indicar que se recibe llamada, aviso o comparecencia cuando el origen sea orden jerárquica.\n"
    "- En los supuestos de actuación de oficio, debes usar fórmulas como: 'Que realizando labores propias del cargo...' o 'Que los agentes actuantes observan...'.\n"
    "- No debes mezclar 'actuación de oficio' con 'se recibe aviso'.\n\n"

    "ESTRUCTURA:\n"
    "- Inicio con recepción de aviso o actuación directa.\n"
    "- Personación de la patrulla.\n"
    "- Identificación de la situación.\n"
    "- Manifestaciones de las partes implicadas (si las hay).\n"
    "- Actuaciones realizadas.\n"
    "- Situación final o medidas adoptadas.\n\n"

    "ESTILO:\n"
    "- Redacción objetiva, sin valoraciones personales.\n"
    "- Lenguaje claro y profesional.\n"
    "- No inventar datos.\n"
    "- Si un dato no consta, se omite.\n"
    "- No escribir 'No consta'.\n"
    "- Debes usar terminología correcta en castellano técnico.\n"
    "- Ejemplo: 'drone' en lugar de 'dron'.\n"
    "- No usar expresiones como 'Se observa que', usar siempre 'Que'.\n\n"

    "IDENTIFICACIÓN DE PERSONAS:\n"
    "- No debes incluir datos personales en el texto (DNI, teléfonos, direcciones completas).\n"
    "- Siempre que se mencione a una persona por su nombre, debe ir precedido obligatoriamente de 'D.' o 'Dña.' según corresponda.\n"
    "- Está prohibido mencionar nombres sin dicho tratamiento.\n"
    "- Debes referirte a las personas como:\n"
    "  - 'Filiado A', 'Filiado B', 'Filiado C' (hombres)\n"
    "  - 'Filiada A', 'Filiada B', 'Filiada C' (mujeres)\n"
    "- Debes asignar las letras en orden de aparición.\n"
    "- Debes mantener la misma referencia durante todo el informe.\n"
    "- No mezclar nombres reales con filiaciones.\n\n"

    "MANIFESTACIONES:\n"
    "- Usar formato técnico:\n"
    "  'Que PREGUNTADO...', 'MANIFIESTA que...'\n"
    "- No mezclar versiones.\n\n"

    "ACTUACIONES POLICIALES:\n"
    "- Incluir actuaciones reales si aparecen:\n"
    "  - identificación\n"
    "  - entrevistas\n"
    "  - traslado\n"
    "  - aviso a servicios\n"
    "  - reportaje fotográfico\n\n"

    "CIERRE:\n"
    "- Finalizar obligatoriamente con:\n"
    "  'Que se procede a la elaboración del presente informe a los efectos oportunos.'\n\n"

    "IMPORTANTE:\n"
    "- No incluir firmas.\n"
    "- No incluir nombres de agentes.\n"
    "- No añadir información que no esté en los datos proporcionados.\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
    + "\n"
)

PROMPT_PARTE_SERVICIO = (
    "Eres un asistente de redacción policial para la Policía Local.\n\n"

    "Debes redactar un PARTE DE SERVICIO en castellano, en estilo técnico, claro, objetivo y en prosa continua.\n"
    "El texto debe ir íntegramente en prosa, sin guiones, sin listas y sin separaciones artificiales.\n"
    "Todos los párrafos del cuerpo deben comenzar obligatoriamente por 'Que' (sin guion, sin punto previo).\n"
    "Está prohibido comenzar cualquier párrafo con '- Que' o con guion.\n\n"

    "FINALIDAD:\n"
    "Dejar constancia de una actuación policial, recogiendo hechos, manifestaciones y actuaciones de forma objetiva.\n\n"

    "CABECERA (elige UNO de estos tres formatos según los datos disponibles):\n\n"

    "  FORMATO A — Agente/s redactores identificados (campo 'NIP del agente redactor' o 'Agentes actuantes' con NIPs concretos):\n"
    "    Si un solo agente: 'En la Jefatura de la Policía Local de [Municipio], el agente con NIP [NIP] hace constar:'\n"
    "    Si varios agentes con misma categoría: 'En la Jefatura de la Policía Local de [Municipio], los agentes con NIP [NIP1] y NIP [NIP2] hacen constar:'\n\n"

    "  FORMATO B — Varios agentes con categorías distintas:\n"
    "    'Los agentes de la Policía Local de [Municipio] con NIP [NIP1] y NIP [NIP2], con categoría de [cat1] y [cat2] respectivamente, hacen constar:'\n\n"

    "  FORMATO C — Sin datos suficientes de agentes actuantes:\n"
    "    No incluir cabecera. Empezar directamente con 'Que siendo las [hora] horas del día [fecha]...'\n\n"

    "  REGLA CRÍTICA SOBRE NIPs:\n"
    "  - Los NIPs de la cabecera deben ser los de los AGENTES ACTUANTES en el servicio.\n"
    "  - En datos de INTELCOPS pueden aparecer NIPs de jefes, supervisores, validadores o firmantes del sistema — NO son los agentes actuantes.\n"
    "  - Si en los datos aparece un NIP en un campo como 'Agente supervisor', 'Jefe de turno', 'Validador', 'Firmante' o similar, NO lo uses en la cabecera ni en el cuerpo como agente actuante.\n"
    "  - Solo usa los NIPs que figuren expresamente como agentes que intervinieron en el servicio.\n"
    "  Si 'Nº de expediente' consta, añádelo como referencia antes o junto a la cabecera.\n\n"

    "PERSONACIÓN EN EL LUGAR (OBLIGATORIO Y CRÍTICO):\n"
    "- Si 'Intervención presencial en el lugar' es 'No': está PROHIBIDO redactar que los agentes se desplazan, se personan o acuden al lugar. La actuación se gestiona desde jefatura.\n"
    "- Si 'Intervención presencial en el lugar' es 'Sí': debes reflejar el desplazamiento y personación de los agentes en el lugar.\n\n"

    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Si el origen es 'Aviso telefónico': indicar hora y medio de recepción.\n"
    "- Si el aviso llega por WhatsApp: indicar expresamente 'a través de la aplicación WhatsApp' con el número si consta.\n"
    "- Si hay varios orígenes (ej: WhatsApp + llamada posterior), narrarlos cronológicamente.\n"
    "- Si el origen es 'Comparecencia en jefatura': iniciar el relato como comparecencia en dependencias policiales.\n"
    + BLOQUE_AVISOS +
    BLOQUE_REGISTRO_ELECTRONICO +
    "- Si el origen es 'Actuación de oficio': prohibido mencionar llamada, aviso o requerimiento.\n"
    "  Usar: 'Que realizando labores propias del cargo...' o 'Que los agentes actuantes observan...'.\n"
    "- Si el origen es 'Orden jerárquica': indicar que la actuación se realiza por orden jerárquica.\n"
    "  Si consta la autoridad que la dicta, mencionarla expresamente.\n\n"

    "VEHÍCULOS (si constan):\n"
    "- Describir el vehículo con tipo, marca, modelo y matrícula.\n"
    "- Si solo hay vehículos y no personas implicadas, no inventar intervinientes.\n\n"

    "PERSONAS IMPLICADAS:\n"
    "- Primera mención: nombre completo y DNI.\n"
    "- Menciones siguientes: 'el identificado', 'la identificada', o por nombre.\n"
    "- Si no hay personas implicadas, no inventar.\n\n"

    "ESTILO Y PROSA:\n"
    "- Redacción en prosa continua, cronológica, en tercera persona y tiempo presente narrativo policial.\n"
    "- Integrar los datos de forma fluida, sin frases cortas aisladas.\n"
    "- No valorar ni interpretar hechos. No inventar datos.\n"
    "- Horas siempre en formato HH:MM horas.\n\n"

    "CIERRE:\n"
    "- Finalizar siempre con: 'Y para que conste, se extiende el presente parte de servicio.'\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
    + "\n"
)

PROMPT_ANOMALIA = (
    "Eres un asistente de redacción policial.\n\n"

    "Debes redactar una ANOMALÍA en castellano, breve, clara y técnica.\n"
    "Todos los párrafos deben comenzar por 'Que'.\n\n"

    "FINALIDAD:\n"
    "- Dejar constancia de una incidencia concreta en vía pública o inmueble.\n"
    "- Reflejar riesgo o problema detectado.\n\n"

    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Debes atender estrictamente al campo 'Origen de la actuación'.\n"
    "- Si el origen es 'Comparecencia en jefatura', debes iniciar el relato como comparecencia en dependencias policiales.\n"
    + BLOQUE_AVISOS +
    BLOQUE_REGISTRO_ELECTRONICO +
    "- Si el origen es 'Actuación de oficio', está prohibido redactar que se recibe llamada, aviso o requerimiento.\n"
    "- En actuación de oficio debes usar fórmulas como 'Que realizando labores propias del cargo...' o 'Que los agentes actuantes observan...'.\n"
    "- Debes atender también al campo 'Intervención presencial en el lugar?'.\n"
    "- Si el origen es 'Orden jerárquica', debes iniciar la redacción indicando que la actuación se realiza por orden jerárquica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que por orden jerárquica...' o 'Que en cumplimiento de orden jerárquica...'.\n"
    "- Si consta el campo 'Orden jerárquica (autoridad que la dicta)', debes indicar expresamente dicha autoridad.\n"
    "- Debes integrarlo con una fórmula equivalente a: 'Que en cumplimiento de orden jerárquica dictada por [autoridad]...'.\n"
    "- Está prohibido indicar que se recibe llamada, aviso o comparecencia cuando el origen sea orden jerárquica.\n"
    "- Si no existe intervención presencial, no debes simular personación policial en el lugar.\n"
    "- Si existe intervención presencial, debes integrarla de forma cronológica y coherente.\n\n"

    "ESTRUCTURA:\n"
    "- Recepción de aviso o detección.\n"
    "- Localización exacta.\n"
    "- Descripción del problema.\n"
    "- Riesgo existente.\n"
    "- Actuaciones realizadas.\n\n"

    "ESTILO:\n"
    "- Muy directo.\n"
    "- Sin narrativa innecesaria.\n"
    "- No inventar.\n\n"

    "TRATAMIENTO DEL CAMPO 'OBSERVACIONES ADICIONALES':\n"
    "- Debes atender obligatoriamente al campo 'Observaciones adicionales'.\n"
    "- Toda la información contenida en ese campo debe integrarse expresamente en el texto final si resulta relevante para la gestión, urgencia, necesidad de actuación o cualquier otra circunstancia de interés.\n"
    "- Está prohibido omitir el contenido de 'Observaciones adicionales' cuando complemente, matice o refuerce la incidencia descrita.\n"
    "- Si en ese campo se indica urgencia o necesidad de actuación rápida, debes reflejarlo de forma expresa con fórmulas equivalentes a: 'requiriéndose actuación a la mayor brevedad posible' o 'requiriéndose tratamiento urgente de la incidencia'.\n\n"

    "CIERRE:\n"
    "- 'Que se pone en conocimiento a los efectos oportunos.'\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
    + "\n"
)

PROMPT_INFORME_JUZGADO = (
    "Eres un asistente de redacción policial para la Policía Local de Poio.\n\n"

    "Debes redactar un INFORME AL JUZGADO en castellano, con tono formal, técnico, objetivo y de estilo judicial-policial.\n"
    "El texto debe redactarse íntegramente en prosa.\n"
    "Debe estructurarse en párrafos que comiencen por 'Que...'.\n"
    "Debe redactarse en tiempo presente narrativo policial.\n"
    "No inventes datos en ningún caso.\n"
    "Debes reflejar con claridad las gestiones practicadas por los agentes, los domicilios visitados, los intentos realizados, las llamadas efectuadas, las comprobaciones en bases de datos y el resultado obtenido.\n"
    "Los agentes deben identificarse exclusivamente por su NIP.\n"
    "Las personas físicas deben figurar como 'D.' o 'Dña.' seguido del nombre completo, añadiendo DNI y teléfono si constan en la primera mención.\n"
    "En menciones posteriores, no repitas la filiación completa.\n"
    "La redacción debe ser sobria, clara y apta para su remisión al órgano judicial.\n\n"

    + BLOQUE_TIEMPO_PRESENTE + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL + "\n"

    "TIPO DE INFORME:\n"
    "- Debes atender al campo 'Tipo de informe al juzgado'.\n"
    "- Si el tipo es 'No localización / notificación negativa', debes dejar constancia de las gestiones realizadas para localizar a la persona o practicar la notificación, así como del resultado negativo de dichas gestiones.\n"
    "- Si el tipo es 'Incumplimiento de localización permanente', debes reflejar las distintas comprobaciones realizadas en el domicilio y la ausencia reiterada de la persona afectada, si así consta.\n\n"

    "CONTENIDO MÍNIMO:\n"
    "- Debes integrar, si constan, el órgano judicial, el procedimiento o asunto, la identidad de la persona afectada, el domicilio principal, otros domicilios consultados, teléfonos contactados, bases de datos consultadas, fechas y horas de los intentos y resultado de las gestiones.\n"
    "- Debes describir las gestiones de forma ordenada y cronológica.\n"
    "- Debes evitar frases coloquiales o imprecisas.\n\n"

    "ESTILO:\n"
    "- Debes utilizar fórmulas como 'se practican gestiones', 'se realizan comprobaciones', 'se efectúa personación', 'sin resultado positivo', 'no siendo localizada la persona'.\n"
    "- Debes evitar lenguaje coloquial.\n"
    "- Puedes cerrar con fórmulas como 'sin que se obtenga resultado positivo' o 'sin que consten más extremos relevantes'.\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
    + "\n"
)


# =========================================================
# CAMPOS
# =========================================================

CAMPOS_ACCIDENTE = [
    # ===== TEMPORAL =====
    "Fecha del accidente",
    "Hora del accidente",
    "Fecha del aviso",
    "Hora del aviso",
    "Hora de comparecencia en jefatura (si procede)",
    "Fecha de personación de los agentes",
    "Hora de personación de los agentes",

    # ===== LUGAR Y ACTUACIÓN =====
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Tipo de accidente",
    "Número de vehículos implicados",

    # ===== REQUIRIMIENTO =====
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",

    # ===== VEHÍCULO A =====
    "Vehículo A - clase y matrícula",
    "Vehículo A - marca",
    "Vehículo A - modelo",
    "Vehículo A - color",
    "Conductor vehículo A",
    "DNI conductor vehículo A",
    "Teléfono conductor vehículo A",
    "Pasajeros vehículo A (indicar posición)",
    "DNI pasajeros vehículo A",
    "Teléfono pasajeros vehículo A",

    # ===== VEHÍCULO B =====
    "Vehículo B - clase y matrícula",
    "Vehículo B - marca",
    "Vehículo B - modelo",
    "Vehículo B - color",
    "Conductor vehículo B",
    "DNI conductor vehículo B",
    "Teléfono conductor vehículo B",
    "Pasajeros vehículo B (indicar posición)",
    "DNI pasajeros vehículo B",
    "Teléfono pasajeros vehículo B",

    # ===== VEHÍCULO C =====
    "Vehículo C - clase y matrícula",
    "Vehículo C - marca",
    "Vehículo C - modelo",
    "Vehículo C - color",
    "Conductor vehículo C",
    "DNI conductor vehículo C",
    "Teléfono conductor vehículo C",
    "Pasajeros vehículo C (indicar posición)",
    "DNI pasajeros vehículo C",
    "Teléfono pasajeros vehículo C",

    # ===== MÁS IMPLICADOS =====
    "Más implicados (si hubiere)",
    "DNI más implicados",
    "Teléfono más implicados",

    # ===== PEATONES =====
    "Peatones (si los hubiere)",
    "DNI peatones",
    "Teléfono peatones",

    # ===== TESTIGOS =====
    "Testigos (si los hubiere)",
    "DNI testigos",
    "Teléfono testigos",

    # ===== VÍA =====
    "Descripción de la vía",
    "Condiciones meteorológicas",

    # ===== HECHOS =====
    "Daños observados",
    "Posición de los vehículos a la llegada de los agentes",
    "Relato técnico del accidente (¿Qué ha pasado?)",
    "Actuaciones realizadas",

    # ===== PRUEBAS =====
    "Reportaje fotográfico (sí/no)",
    "Prueba de alcoholemia (indicar resultado)",
    "Prueba de drogas (signos, indicar resultado)",

    # ===== FINAL =====
    "Asistencia sanitaria (personas asistidas, indicativo sanitario, hora de llegada, hora de salida, lugar de traslado)",
    "Conclusión técnica (¿Por qué ha pasado?)",
    "Observaciones adicionales",
]

CAMPOS_ATESTADO_COMPLETO = [
    "Nº de atestado",
    "Municipio / Jefatura",
    "NIP del instructor",
    "NIP del secretario",
    "Destino (juzgado o unidad receptora)",
    "Delito o hecho imputado",
    "Fecha de inicio de diligencias",
    "Hora de inicio de diligencias",
    "Fecha del hecho",
    "Hora del hecho o franja horaria",
    "Fecha de personación del denunciante en jefatura (si procede)",
    "Hora de personación del denunciante en jefatura (si procede)",
    "Fecha de personación de los agentes en el lugar",
    "Hora de personación de los agentes en el lugar",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",
    "Personas implicadas",
    "DNI personas implicadas",
    "Teléfono personas implicadas",
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
    "Hora del aviso",
    "Hora de personación de los agentes",
    "Hora de personación del requirente/alertante en jefatura (si procede)",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",
    "Partes implicadas",
    "DNI partes implicadas",
    "Teléfono partes implicadas",
    "Asunto",
    "Versión de la parte A",
    "Versión de la parte B",
    "Observaciones de los agentes",
    "Documentación o imágenes",
    "Análisis técnico o valoración policial",
    "Conclusión o resultado",
    "Observaciones adicionales",
]

CAMPOS_PARTE_SERVICIO = [
    "Nº de expediente (si procede)",
    "Municipio / Jefatura",
    "NIP del agente redactor",
    "Categoría de los agentes",
    "Turno de servicio",
    "Fecha",
    "Hora del aviso",
    "Hora de personación de los agentes",
    "Hora de personación del requirente/alertante en jefatura (si procede)",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",
    "Personas implicadas",
    "DNI personas implicadas",
    "Teléfono personas implicadas",
    "Vehículo - matrícula",
    "Vehículo - marca",
    "Vehículo - modelo",
    "Vehículo - titular",
    "Asunto o motivo",
    "Relato libre de lo sucedido o de la gestión realizada",
    "Actuaciones policiales realizadas",
    "Observaciones adicionales",
]

CAMPOS_ANOMALIA = [
    "Fecha",
    "Hora del aviso",
    "Hora de personación de los agentes",
    "Hora de personación del requirente/alertante en jefatura (si procede)",
    "Lugar exacto",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",
    "Personas implicadas",
    "DNI personas implicadas",
    "Teléfono personas implicadas",
    "Tipo de anomalía",
    "Descripción breve de la incidencia observada",
    "Riesgo o afectación apreciada",
    "Actuaciones realizadas",
    "Servicio o departamento avisado",
    "Observaciones adicionales",
]

CAMPOS_INFORME_JUZGADO = [
    "Fecha",
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Tipo de informe al juzgado",
    "Órgano judicial",
    "Procedimiento / asunto",
    "Persona afectada",
    "DNI persona afectada",
    "Teléfono persona afectada",
    "Domicilio principal",
    "Otros domicilios consultados",
    "Teléfonos contactados",
    "Bases de datos consultadas",
    "Número de intentos realizados",
    "Fechas y horas de los intentos",
    "Comprobaciones realizadas",
    "Resultado de las gestiones",
    "Manifestaciones de terceros (si las hubiere)",
    "Observaciones adicionales",
]

CAMPOS_DENUNCIA_ADMINISTRATIVA = [
    "Fecha",
    "Hora",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Origen de la actuación",
    "Persona denunciada / responsable",
    "DNI persona denunciada / responsable",
    "Teléfono persona denunciada / responsable",
    "Norma administrativa aplicada",
    "Precepto o artículo (si se conoce)",
    "Hecho observado",
        "Requerimientos realizados por los agentes",
    "Respuesta o actitud de la persona",
    "Actuaciones policiales realizadas",
    "Testigos (si los hubiere)",
    "Documentación / reportaje fotográfico",
    "Observaciones adicionales",
]

# =========================================================
# OPCIONES DE SELECT
# =========================================================

OPCIONES_SELECT = {
    "Turno de servicio": ["", "Mañana", "Tarde", "Noche"],
    "Tipo de accidente": ["", "Simple", "Complejo", "Múltiple"],
    "Condiciones meteorológicas": ["", "Despejado", "Soleado", "Nublado", "Lluvia", "Niebla", "Viento", "Otra"],
    "Reportaje fotográfico (sí/no)": ["", "Sí", "No"],
    "Origen del aviso (teléfono / jefatura)": ["", "Teléfono", "Jefatura"],
    "Tipo de anomalía": [
        "",
        "Alcantarilla",
        "Cable caído",
        "Farola dañada",
        "Socavón",
        "Señalización dañada",
        "Árbol o ramas",
        "Bache",
        "Fuga de agua",
        "Obstáculo en calzada",
        "Otra",
    ],
    "Tipo de informe al juzgado": [
        "",
        "No localización / notificación negativa",
        "Incumplimiento de localización permanente",
    ],
}

CAMPOS_GRANDES = {
    "Asunto",
    "Relato técnico del accidente (¿Qué ha pasado?)",
    "Actuaciones realizadas",
    "Asistencia sanitaria (personas asistidas, indicativo sanitario, hora de llegada, hora de salida, lugar de traslado)",
    "Conclusión técnica (¿Por qué ha pasado?)",
    "Observaciones adicionales",
    "Relato libre de lo sucedido o de la gestión realizada",
    "Actuaciones policiales realizadas",
    "Relato general de los hechos",
    "Descripción del lugar",
    "Daños observados",
    "Elementos relevantes",
}


# =========================================================
# COMPONENTES UI
# =========================================================
def render_form_fields_grupo(titulo: str, campos: list[str], key_prefix: str) -> dict:
    with st.expander(titulo, expanded=True):
        return render_form_fields(campos, key_prefix)

def selector_contexto_actuacion_general(key_prefix: str) -> tuple[str, str, str]:
    col1, col2 = st.columns(2)

    with col1:
        origen = st.radio(
            "Origen de la actuación",
            OPCIONES_ORIGEN,
            key=f"origen_actuacion_{key_prefix}",
        )

        orden_autoridad = ""
        if origen == "Orden jerárquica":
            orden_autoridad = st.text_input(
                "Autoridad que dicta la orden",
                key=f"orden_autoridad_{key_prefix}",
                placeholder="Ej: Jefatura de Policía Local"
            )

    with col2:
        intervencion = st.radio(
            "¿Hubo intervención presencial en el lugar?",
            ["No", "Sí"],
            key=f"intervencion_presencial_{key_prefix}",
        )

    return origen, intervencion, orden_autoridad


def pagina_informe_municipal(api_key: str):
    key_prefix = "municipal"
    cabecera_modulo("Informe municipal", "🏛️")

    tab_directo, tab_campos = st.tabs(["⚡ Desde INTELCOPS", "📝 Con campos"])

    with tab_directo:
        bloque_generacion_directa(
            api_key=api_key,
            key_prefix=key_prefix,
            tipo_documento="Informe municipal",
            prompt_base=PROMPT_INFORME_MUNICIPAL,
            resultado_key="resultado_municipal",
            datos_key="datos_municipal",
            prefijo_guardado="informe_municipal",
        )

    with tab_campos:
        bloque_texto_a_campos(api_key, "municipal", "Informe municipal", CAMPOS_INFORME_MUNICIPAL)
        origen_actuacion, intervencion_presencial, orden_autoridad = selector_contexto_actuacion_general(key_prefix)

        col_tools_1, col_tools_2 = st.columns(2)
        with col_tools_1:
            if st.button("🧹 Limpiar formulario", key="limpiar_municipal"):
                resetear_formulario("municipal", ["resultado_municipal", "datos_municipal"])
                st.rerun()
        with col_tools_2:
            st.caption("Pega un texto base o rellena los campos manualmente.")

        datos = {}

        datos.update(render_form_fields_grupo(
            "📍 Datos generales",
            [
                "Fecha",
                "Hora del aviso",
                "Hora de personación de los agentes",
                "Hora de personación del requirente/alertante en jefatura (si procede)",
                "Lugar",
                "Agentes actuantes (NIP)",
                "Indicativo policial",
            ],
            key_prefix,
        ))

        datos.update(render_form_fields_grupo(
            "👥 Intervinientes",
            [
                "Alertante o requirente",
                "DNI del alertante o requirente",
                "Teléfono del alertante o requirente",
                "Partes implicadas",
                "DNI partes implicadas",
                "Teléfono partes implicadas",
            ],
            key_prefix,
        ))

        datos.update(render_form_fields_grupo(
            "🧾 Hechos",
            [
                "Asunto",
                "Versión de la parte A",
                "Versión de la parte B",
                "Observaciones de los agentes",
            ],
            key_prefix,
        ))

        datos.update(render_form_fields_grupo(
            "📸 Actuaciones y cierre",
            [
                "Documentación o imágenes",
                "Análisis técnico o valoración policial",
                "Conclusión o resultado",
                "Observaciones adicionales",
            ],
            key_prefix,
        ))

        generar = st.button("Generar informe municipal", key="btn_generar_municipal")

        if generar:
            prompt_final = PROMPT_INFORME_MUNICIPAL

            bloque = construir_bloque_usuario_con_contexto(
                datos,
                origen_actuacion,
                intervencion_presencial,
                orden_autoridad,
            )

            observaciones = datos.get("Observaciones adicionales", "")
            hay_denuncia = "denuncia" in observaciones.lower()
            bloque += f"\nHay denuncia administrativa: {'Sí' if hay_denuncia else 'No'}"

            with st.spinner("Generando informe..."):
                texto = generar_texto_con_ia(api_key, prompt_final, bloque)
            guardar_log_generacion("informe_municipal", datos, bloque, texto)

            st.session_state["resultado_municipal"] = texto
            st.session_state["datos_municipal"] = datos

    if st.session_state.get("resultado_municipal"):
        mostrar_resultado(
            st.session_state["resultado_municipal"],
            st.session_state.get("datos_municipal", {}),
            "informe_municipal",
        )



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
            style="width: 100%; min-height: 52px; border: none; border-radius: 12px; background: #0067b1; color: white; font-size: 16px; font-weight: 600; cursor: pointer;"
        >
            📋 Copiar texto
        </button>
        <div id="copiado-{clave}" style="margin-top:8px; font-size:14px; color:#2e7d32;"></div>
    </div>
    """
    components.html(html, height=90)


def cabecera_modulo(titulo: str, icono: str):
    col_btn, col_titulo = st.columns([1, 5])
    with col_btn:
        if st.button("← Inicio", key=f"volver_{titulo}"):
            st.session_state["pagina_actual"] = "inicio"
            st.rerun()
    with col_titulo:
        st.markdown(
            f"""
            <div class="modulo-header">
                <span class="modulo-header-icon">{icono}</span>
                <span class="modulo-header-titulo">{titulo}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_form_fields(campos: list[str], key_prefix: str) -> dict:
    datos = {}

    for campo in campos:
        clave = f"{key_prefix}_{campo}"
        reset_version = get_reset_version(key_prefix)
        clave_widget = f"widget_{clave}_{reset_version}"
        campo_lower = campo.lower()

        # ===== SELECTS =====
        if campo in OPCIONES_SELECT:
            opciones = OPCIONES_SELECT[campo]
            valor_actual = st.session_state.get(clave_widget, st.session_state.get(clave, ""))
            valor_actual = normalizar_valor_select(campo, str(valor_actual))
            indice = opciones.index(valor_actual) if valor_actual in opciones else 0

            valor = st.selectbox(
                campo,
                opciones,
                index=indice,
                key=clave_widget,
            )

        # ===== CAMPOS GRANDES =====
        elif campo in CAMPOS_GRANDES:
            valor = st.text_area(
                campo,
                value=st.session_state.get(clave_widget, st.session_state.get(clave, "")),
                key=clave_widget,
                height=130,
            )

        # ===== CAMPOS CORTOS FORZADOS =====
        elif campo in {
            "Agentes",
            "Agentes actuantes (NIP)",
            "Persona denunciada / responsable",
        }:
            valor = st.text_input(
                campo,
                value=st.session_state.get(clave_widget, st.session_state.get(clave, "")),
                key=clave_widget,
            )

        # ===== CAMPOS CORTOS =====
        elif any(x in campo_lower for x in [
            "fecha",
            "hora",
            "dni",
            "teléfono",
            "telefono",
            "nip",
            "alertante o requirente",
            "matrícula",
            "matricula",
            "marca",
            "modelo",
            "color",
            "conductor vehículo",
            "conductor vehiculo",
            "número de vehículos implicados",
            "numero de vehiculos implicados",
            "posición de los vehículos a la llegada",
            "posicion de los vehiculos a la llegada",
            "lugar",
            "indicativo",
            "municipio",
            "jefatura",
            "expediente",
            "turno",
            "categoría de los agentes",
            "categoria de los agentes",
            "vehículo - matrícula",
            "vehículo - marca",
            "vehículo - modelo",
            "vehículo - titular",
            "vehiculo - matricula",
            "vehiculo - marca",
            "vehiculo - modelo",
            "vehiculo - titular",
            "órgano judicial",
            "organo judicial",
            "procedimiento",
            "tipo de informe al juzgado",
            "tipo de anomalía",
            "norma administrativa aplicada",
            "precepto o artículo",
            "precepto o articulo",
        ]):
            valor = st.text_input(
                campo,
                value=st.session_state.get(clave_widget, st.session_state.get(clave, "")),
                key=clave_widget,
            )

        # ===== CAMPOS LARGOS / NARRATIVOS =====
        else:
            valor = st.text_area(
                campo,
                value=st.session_state.get(clave_widget, st.session_state.get(clave, "")),
                key=clave_widget,
                height=100,
            )

        st.session_state[clave] = valor
        datos[campo] = valor

    return normalizar_datos(datos)


def aplicar_datos_a_session_state(datos_extraidos: dict, key_prefix: str):
    if not isinstance(datos_extraidos, dict):
        return

    reset_version = get_reset_version(key_prefix)

    for campo, valor in datos_extraidos.items():
        clave_base = f"{key_prefix}_{campo}"
        clave_widget = f"widget_{clave_base}_{reset_version}"

        valor = "" if valor is None else str(valor).strip()

        # Normalizar selects
        if campo in OPCIONES_SELECT:
            valor = normalizar_valor_select(campo, valor)

        # Guardar directamente como texto
        st.session_state[clave_base] = valor
        st.session_state[clave_widget] = valor


def resetear_formulario(key_prefix: str, claves_resultado: list[str] | None = None):
    claves_a_borrar = []

    for clave in list(st.session_state.keys()):
        if (
            clave.startswith(f"{key_prefix}_")
            or clave.startswith(f"widget_{key_prefix}_")
            or clave.startswith(f"audio_campos_{key_prefix}")
            or clave.startswith(f"dictado_campos_{key_prefix}")
            or clave.startswith(f"texto_dictado_{key_prefix}")
            or clave == f"contexto_actuacion_{key_prefix}"
            or clave == f"origen_actuacion_{key_prefix}"
            or clave == f"intervencion_presencial_{key_prefix}"
            or clave == f"orden_autoridad_{key_prefix}"
            or clave == f"nombre_informe_municipal"
            # Modo directo INTELCOPS
            or clave.startswith(f"intelcops_datos_{key_prefix}")
            or clave.startswith(f"intelcops_manifest_{key_prefix}")
            or clave.startswith(f"intelcops_pinceladas_{key_prefix}")
            or clave.startswith(f"origen_actuacion_directo_{key_prefix}")
            or clave.startswith(f"intervencion_presencial_directo_{key_prefix}")
            or clave.startswith(f"orden_autoridad_directo_{key_prefix}")
        ):
            claves_a_borrar.append(clave)

    if claves_resultado:
        claves_a_borrar.extend(claves_resultado)

    for clave in set(claves_a_borrar):
        if clave in st.session_state:
            del st.session_state[clave]

    # Fuerza recreación de widgets con claves nuevas
    bump_reset_version(key_prefix)


def mostrar_resultado(texto: str, datos: dict, prefijo: str):
    orig_key = f"_anon_orig_{prefijo}"
    display_key = f"_anon_display_{prefijo}"

    # Resetear si es una generación nueva (texto cambió)
    if st.session_state.get(orig_key) != texto:
        st.session_state[orig_key] = texto
        st.session_state[display_key] = texto

    texto_mostrado = st.session_state[display_key]
    esta_anonimizado = texto_mostrado != texto

    st.subheader("Resultado")
    st.text_area("Documento generado", texto_mostrado, height=450)

    anon_col, rest_col = st.columns(2)
    with anon_col:
        if st.button("🔒 Anonimizar", key=f"btn_anon_{prefijo}"):
            st.session_state[display_key] = anonimizar_texto(texto)
            st.rerun()
    with rest_col:
        if esta_anonimizado:
            if st.button("↩ Restaurar original", key=f"btn_restaurar_{prefijo}"):
                st.session_state[display_key] = texto
                st.rerun()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        boton_copiar_web(texto_mostrado, prefijo)
    with col2:
        st.download_button(
            "Descargar TXT",
            data=texto_mostrado.encode("utf-8"),
            file_name=f"{prefijo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
        )
    with col3:
        if st.button("Guardar TXT y JSON", key=f"guardar_{prefijo}"):
            ruta_txt = guardar_txt(texto_mostrado, prefijo)
            ruta_json = guardar_json(datos, prefijo)
            st.success(f"Guardado en: {ruta_txt} y {ruta_json}")
    with col4:
        if st.button("Guardar ejemplo IA (.md)", key=f"guardar_md_{prefijo}"):
            ruta_md = guardar_ejemplo_ia(texto_mostrado, prefijo)
            st.success("Ejemplo IA guardado correctamente")

    nombre = st.text_input("Guardar con nombre", key=f"nombre_{prefijo}")
    if st.button("Guardar TXT", key=f"guardar_nombre_{prefijo}"):
        if nombre.strip():
            ruta = guardar_txt_con_nombre(texto_mostrado, nombre.strip())
            st.success(f"Guardado en: {ruta}")
        else:
            st.warning("Escribe un nombre válido.")


# =========================================================
# EXTRACCIÓN DESDE DICTADO
# =========================================================

def extraer_campos_desde_dictado(api_key: str, tipo_documento: str, texto_dictado: str, campos_objetivo: list[str]) -> dict:
    client = get_client(api_key)
    esquema = {campo: "" for campo in campos_objetivo}

    instrucciones_select = """
- Para los campos desplegables, debes usar exactamente uno de estos valores permitidos cuando proceda:
  - "Tipo de accidente": "Simple" o "Complejo"
  - "Reportaje fotográfico (sí/no)": "Sí" o "No"
  - "Condiciones meteorológicas": "Despejado", "Soleado", "Nublado", "Lluvia", "Niebla", "Viento" u "Otra"
  - "Tipo de anomalía": "Alcantarilla", "Cable caído", "Farola dañada", "Socavón", "Señalización dañada", "Árbol o ramas", "Bache", "Fuga de agua", "Obstáculo en calzada" u "Otra"
  - "Tipo de informe al juzgado": "No localización / notificación negativa" o "Incumplimiento de localización permanente"
- No uses variantes como "simple", "si", "lloviendo", "día soleado", "hay fotos", etc.
- Si no está claro, deja cadena vacía "".
"""

    instrucciones_tiempo = """
- Debes diferenciar claramente entre:
  - "Fecha del accidente"
  - "Hora del accidente"
  - "Fecha del aviso"
  - "Hora del aviso"
  - "Fecha de comparecencia en jefatura (si procede)"
  - "Hora de comparecencia en jefatura (si procede)"
  - "Fecha de personación de los agentes"
  - "Hora de personación de los agentes"
- Si la persona comparece en dependencias días después del accidente, NO debes confundir ese momento con la fecha y hora del siniestro.
- Si del relato se desprende que los hechos ocurrieron antes y que posteriormente la persona acude a jefatura a comunicarlo, debes separar correctamente ambos momentos.
- Si el texto menciona expresamente que la persona se persona en jefatura o en dependencias policiales para contar un accidente ocurrido con anterioridad, debes rellenar los campos de comparecencia en jefatura si existen entre los campos objetivo.
- Si el texto menciona que los agentes se personan en el lugar en otro momento distinto, debes rellenar aparte la fecha y hora de personación de los agentes si esos campos existen entre los campos objetivo.
- Si solo consta la hora pero no la fecha, rellena solo la hora.
- Si solo consta la fecha pero no la hora, rellena solo la fecha.
"""

    instrucciones_logica = """
- Debes detectar si el accidente fue:
  - comunicado en el momento,
  - comunicado posteriormente,
  - o puesto en conocimiento mediante comparecencia en jefatura.
- Si el relato indica que los hechos ocurrieron días antes y después se comunican en dependencias, debes reflejar esa lógica temporal correctamente en los campos.
- No debes colocar como "Hora del aviso" la hora del accidente salvo que del relato se desprenda claramente que ambas coinciden.
- No debes colocar como "Hora del accidente" la hora de comparecencia en jefatura.
"""

    instrucciones_vehiculos = """
- En los campos de marca del vehículo, escribe solo la marca real si consta claramente.
- No uses tipos genéricos como "furgoneta", "turismo", "camión" o similares como si fueran marca.
- Si no consta la marca real, deja el campo vacío.
- En los campos de modelo, escribe solo el modelo si consta claramente.
"""

    prompt = f"""
Eres un asistente policial especializado en extraer información estructurada desde textos libres utilizados por agentes de Policía Local en Jefatura.

TIPO DE DOCUMENTO:
{tipo_documento}

CAMPOS A RELLENAR:
{json.dumps(campos_objetivo, ensure_ascii=False, indent=2)}

INSTRUCCIONES GENERALES:
- Devuelve EXCLUSIVAMENTE un objeto JSON válido.
- No escribas texto antes ni después del JSON.
- Usa exactamente como claves los nombres de los campos proporcionados.
- No inventes datos.
- Si un dato no aparece claro, deja su valor como cadena vacía "".

INTERPRETACIÓN POLICIAL DEL TEXTO:
- Debes interpretar el lenguaje natural como lo haría un agente.
- No te limites a copiar texto; debes estructurarlo correctamente.

GÉNERO (MUY IMPORTANTE):
- Detecta si la persona es hombre o mujer por el nombre.
- Si es mujer, usa "Dña." delante del nombre.
- Si es hombre, usa "D." delante del nombre.
- Ejemplo: María → Dña. María

COMPARECENCIAS EN JEFATURA:
- Si el texto indica que alguien acude a dependencias, interprétalo como comparecencia.
- Ejemplo: "vino a jefatura", "se presenta en dependencias", "comparece en Policía Local"

CAMPOS CLAVE:
- "Alertante o requirente" → persona que acude o llama
- "Partes implicadas" → resto de personas mencionadas
- "Asunto" → resumen breve (insultos, daños, discusión, etc.)
- "Versión de la parte A" → lo que dice el alertante
- "Versión de la parte B" → lo que dice la otra parte, si existe

VERSIONES:
- Separa correctamente versiones si hay dos partes.
- Usa lenguaje claro y directo.
- No mezcles versiones.

ACTUACIONES:
- Si se menciona actuación policial (fotos, llamadas, gestiones, personación, comprobaciones, etc.), inclúyelo en el campo correspondiente.
- No inventar actuaciones.
- CRÍTICO: El campo 'Tipo de intervención' de INTELCOPS (Cumplimentación de Parte Amistoso / Parte/Informe a Prevención / Atestado...) es una lista de opciones administrativas del formulario, NO son actuaciones policiales realizadas. No extraigas nada de ese campo para rellenar 'Actuaciones realizadas'.
- 'Cumplimentación de Parte Amistoso' NUNCA es una actuación policial. El Parte Amistoso lo cumplimentan los conductores civiles, no los agentes. No lo incluyas nunca en ningún campo.

ESTILO:
- Resume el texto en lenguaje claro y útil para redacción policial.
- No escribas frases largas innecesarias.

{instrucciones_select}

{instrucciones_tiempo}

{instrucciones_logica}

{instrucciones_vehiculos}

JSON base esperado:
{json.dumps(esquema, ensure_ascii=False, indent=2)}

TEXTO:
{texto_dictado}
"""

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Debes devolver solo un objeto JSON válido, sin explicaciones. "
                        "Usa exactamente las claves pedidas y no inventes datos."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        contenido = (respuesta.choices[0].message.content or "").strip()

        datos = json.loads(contenido)

        if not isinstance(datos, dict):
            return esquema

        resultado = {}
        for campo in campos_objetivo:
            valor = datos.get(campo, "")
            valor = str(valor).strip() if valor is not None else ""

            if campo in OPCIONES_SELECT:
                valor = normalizar_valor_select(campo, valor)

            resultado[campo] = valor

        return resultado

    except Exception as e:
        st.warning(f"No se pudieron extraer campos desde el texto. Error: {e}")
        return esquema

def bloque_texto_a_campos(api_key: str, key_prefix: str, tipo_documento: str, campos_objetivo: list[str]):
    st.subheader("📄 Rellenar campos desde texto")
    st.caption("Pega aquí un texto y la app rellenará automáticamente los campos.")

    reset_version = get_reset_version(key_prefix)
    clave_texto = f"texto_base_{key_prefix}_{reset_version}"

    texto = st.text_area(
        "Texto base",
        height=150,
        key=clave_texto,
    )

    if st.button("Rellenar campos automáticamente", key=f"rellenar_texto_{key_prefix}_{reset_version}"):
        if not texto.strip():
            st.warning("Introduce un texto primero.")
        else:
            with st.spinner("Extrayendo campos desde el texto..."):
                datos_extraidos = extraer_campos_desde_dictado(
                    api_key=api_key,
                    tipo_documento=tipo_documento,
                    texto_dictado=texto,
                    campos_objetivo=campos_objetivo,
                )

            aplicar_datos_a_session_state(datos_extraidos, key_prefix)

            st.success("Campos rellenados automáticamente.")
            # st.rerun()

# =========================================================
# GENERACIÓN DIRECTA DESDE INTELCOPS
# =========================================================

def detectar_contexto_actuacion(api_key: str, texto: str) -> tuple[str, str]:
    """Devuelve (origen_actuacion, intervencion_presencial) detectados del texto."""
    client = get_client(api_key)
    texto_lower = (texto or "").lower()
    origen_forzado = ""
    if any(
        marca in texto_lower
        for marca in [
            "registro electrónico",
            "registro electronico",
            "registro de entrada",
            "sede electrónica",
            "sede electronica",
            "entrada por registro",
            "rexistro electrónico",
            "rexistro electronico",
            "registro del concello",
        ]
    ):
        origen_forzado = "Registro Electrónico del Concello"

    prompt = (
        "Lee el siguiente texto policial de INTELCOPS y determina dos cosas.\n\n"

        "1. ORIGEN DE LA ACTUACIÓN — REGLA CRÍTICA:\n"
        "El origen es el PRIMER evento cronológico que inició la actuación policial, no el primero que aparece en el texto.\n"
        "Señales que indican AVISO TELEFÓNICO (muy comunes, prioridad alta):\n"
        "  - El campo 'Modo de inicio' dice 'Llamada telefónica'.\n"
        "  - El texto dice 'se recepciona llamada', 'se recibe llamada', 'llamada en el teléfono'.\n"
        "  - La declarante/denunciante dice que 'contactó con la policía', 'llamó a la policía', 'avisó a la policía', 'se puso en contacto con la policía'.\n"
        "  - El texto menciona un número de teléfono como origen del aviso.\n"
        "Señales que indican COMPARECENCIA EN JEFATURA:\n"
        "  - La persona fue a jefatura a denunciar SIN que hubiera llamada previa a la policía.\n"
        "  - El primer contacto policial fue en las dependencias.\n"
        "  - ATENCIÓN: El campo 'Modo de inicio: Orden jerárquica' en el PAS/minuta indica cómo el agente fue asignado al servicio por su supervisor, NO cómo llegó el hecho a conocimiento policial. Si la persona acudió físicamente a jefatura sin llamar antes, el origen es 'Comparecencia en jefatura', no 'Orden jerárquica'.\n"
        "Señales que indican REGISTRO ELECTRÓNICO DEL CONCELLO:\n"
        "  - El texto menciona 'Registro Electrónico', 'Registro de entrada', 'Sede electrónica', 'entrada por registro', 'rexistro electrónico' o 'registro del Concello'.\n"
        "  - El hecho llega mediante escrito, instancia, comunicación o documentación remitida por el Concello, no por presencia física de la persona en Jefatura.\n"
        "  - Si el primer conocimiento policial es una entrada documental del Concello, el origen es 'Registro Electrónico del Concello'.\n"
        "Señales que indican ACTUACIÓN DE OFICIO:\n"
        "  - Los agentes detectaron el hecho ellos solos, sin aviso de nadie.\n"
        "  - No hay ningún ciudadano que alertara a la policía.\n"
        "IMPORTANTE: Si la persona avisó a la policía (aunque sea desde la calle o por teléfono) el origen NO es 'Actuación de oficio'.\n"
        "Si hay una llamada el día X y después comparecencia el día X+1, el origen es 'Aviso telefónico'.\n"
        "Si hay una entrada por registro electrónico y después se cita o comparece una persona, el origen sigue siendo 'Registro Electrónico del Concello'.\n"
        "Si alguien paró a los agentes en la calle → 'Aviso en la calle'.\n"
        "Si hubo orden de un superior → 'Orden jerárquica'.\n\n"
        "Elige exactamente una de estas opciones:\n"
        "- Comparecencia en jefatura\n"
        "- Registro Electrónico del Concello\n"
        "- Aviso telefónico\n"
        "- Aviso por WhatsApp al teléfono oficial\n"
        "- Aviso en la calle\n"
        "- Actuación de oficio\n"
        "- Orden jerárquica\n\n"

        "2. INTERVENCIÓN PRESENCIAL. ¿Los agentes se desplazaron físicamente al lugar de los hechos?\n"
        "Responde Sí si el texto indica que los agentes acudieron, se personaron o intervinieron en el lugar.\n"
        "Responde No si la actuación se gestionó solo desde jefatura, por teléfono o sin desplazamiento.\n\n"

        "Responde en este formato exacto (dos líneas):\n"
        "ORIGEN: <opción>\n"
        "PRESENCIAL: <Sí o No>\n\n"
        f"TEXTO:\n{texto[:6000]}"
    )
    origen = origen_forzado or "Actuación de oficio"
    presencial = "No"
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
        )
        resultado = (resp.choices[0].message.content or "").strip()
        for linea in resultado.splitlines():
            if linea.startswith("ORIGEN:"):
                valor = linea.replace("ORIGEN:", "").strip()
                valor_lower = valor.lower()
                if "registro" in valor_lower and ("concello" in valor_lower or "electr" in valor_lower or "entrada" in valor_lower):
                    origen = "Registro Electrónico del Concello"
                    continue
                if not origen_forzado:
                    for opcion in OPCIONES_ORIGEN:
                        if opcion in valor:
                            origen = opcion
                            break
            elif linea.startswith("PRESENCIAL:"):
                valor = linea.replace("PRESENCIAL:", "").strip()
                presencial = "Sí" if "sí" in valor.lower() or valor.lower() == "si" else "No"
    except Exception:
        pass
    if origen_forzado:
        origen = origen_forzado
    return origen, presencial


def _construir_contenido_directo(
    contenido: str,
    origen_actuacion: str,
    intervencion_presencial: str,
    orden_autoridad: str,
    pinceladas: str = "",
    priorizar_pinceladas: bool = False,
) -> str:
    contexto = (
        f"Origen de la actuación: {origen_actuacion}\n"
        f"Intervención presencial en el lugar: {intervencion_presencial}\n"
    )
    if origen_actuacion == "Registro Electrónico del Concello":
        contexto += (
            "Instrucción crítica: si se genera una exposición de hechos, debe empezar directamente "
            "con la entrada por Registro Electrónico del Concello. No incluyas cabecera inicial de agentes antes "
            "del primer párrafo 'Que'.\n"
        )
    if origen_actuacion == "Orden jerárquica" and orden_autoridad.strip():
        contexto += f"Orden jerárquica (autoridad que la dicta): {orden_autoridad.strip()}\n"

    partes = []
    if priorizar_pinceladas and pinceladas.strip():
        partes.append(
            "DESCRIPCIÓN DE LO OCURRIDO (aportada por el agente) — PRIORIDAD NARRATIVA ABSOLUTA:\n"
            f"{pinceladas.strip()}\n\n"
            "REGLA DE USO: cada llamada, observación, seguimiento, comparecencia posterior o gestión descrita en este bloque debe aparecer en el documento final en orden cronológico. "
            "Si este bloque está redactado como exposición de hechos, úsalo como modelo preferente de estructura, extensión y nivel de detalle frente a las actas completas de INTELCOPS."
        )
    if contenido.strip():
        partes.append(f"DATOS DE INTELCOPS:\n{contenido.strip()}")
    if pinceladas.strip() and not priorizar_pinceladas:
        partes.append(f"DESCRIPCIÓN DE LO OCURRIDO (aportada por el agente):\n{pinceladas.strip()}")
    partes.append(f"CONTEXTO DE ACTUACIÓN:\n{contexto}")
    return "\n\n".join(partes)


def bloque_generacion_directa(
    api_key: str,
    key_prefix: str,
    tipo_documento: str,
    prompt_base: str,
    resultado_key: str,
    datos_key: str,
    prefijo_guardado: str,
):
    st.caption("Pega los datos de INTELCOPS y añade un par de frases explicando qué pasó. La IA genera el documento completo.")

    reset_version = get_reset_version(key_prefix)
    clave_contenido = f"intelcops_datos_{key_prefix}_{reset_version}"
    clave_pinceladas = f"intelcops_pinceladas_{key_prefix}_{reset_version}"

    contenido = st.text_area(
        "Datos de INTELCOPS",
        height=260,
        key=clave_contenido,
        placeholder="Pega aquí el contenido copiado de INTELCOPS: datos del parte, manifestaciones, lo que tengas.",
    )

    pinceladas = st.text_area(
        "¿Qué pasó? (2-4 frases)",
        height=100,
        key=clave_pinceladas,
        placeholder="Ej: Actuación por persona agresiva en la calle. Se dirige a los agentes con insultos y tono amenazante. Se le denuncia por Ley de Seguridad Ciudadana.",
    )

    _, intervencion_presencial, orden_autoridad = selector_contexto_actuacion_general(
        f"directo_{key_prefix}"
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        generar_directo = st.button(
            f"Generar {tipo_documento}",
            key=f"btn_directo_{key_prefix}",
        )
    with col2:
        if st.button("🧹 Limpiar", key=f"btn_limpiar_directo_{key_prefix}"):
            resetear_formulario(key_prefix, [resultado_key, datos_key])
            st.rerun()

    if generar_directo:
        if not contenido.strip():
            st.warning("Introduce los datos antes de generar.")
            return

        with st.spinner("Analizando texto..."):
            origen_detectado, presencial_detectado = detectar_contexto_actuacion(
                api_key,
                "\n\n".join(parte for parte in [pinceladas, contenido] if parte.strip()),
            )

        st.info(f"Origen detectado: **{origen_detectado}** · Personación en el lugar: **{presencial_detectado}**")

        bloque = _construir_contenido_directo(
            contenido, origen_detectado, presencial_detectado, orden_autoridad, pinceladas,
        )
        prompt_final = PROMPT_INTELCOPS_PREFIX + prompt_base

        with st.spinner("Generando documento..."):
            texto = generar_texto_con_ia(api_key, prompt_final, bloque)
        guardar_log_generacion(prefijo_guardado, {"Datos de INTELCOPS": contenido}, bloque, texto)

        st.session_state[resultado_key] = texto
        st.session_state[datos_key] = {
            "_modo": "directo_intelcops",
            "Datos de INTELCOPS": contenido,
        }


def bloque_generacion_directa_atestado(api_key: str, key_prefix: str):
    st.caption("Pega aquí todos los datos de INTELCOPS (datos del atestado, manifestaciones, todo junto). La IA detecta el origen y genera exposición e inspección ocular.")

    reset_version = get_reset_version(key_prefix)
    clave_contenido = f"intelcops_datos_{key_prefix}_{reset_version}"
    clave_pinceladas = f"intelcops_pinceladas_{key_prefix}_{reset_version}"

    contenido = st.text_area(
        "Datos de INTELCOPS",
        height=260,
        key=clave_contenido,
        placeholder="Pega aquí el contenido copiado de INTELCOPS: datos del atestado, manifestaciones, lo que tengas.",
    )

    pinceladas = st.text_area(
        "Pinceladas o borrador del agente",
        height=160,
        key=clave_pinceladas,
        placeholder="Añade aquí la secuencia real de actuaciones, llamadas, citaciones, comparecencias, anexos o un borrador de exposición si lo tienes.",
    )

    _, intervencion_presencial, orden_autoridad = selector_contexto_actuacion_general(
        f"directo_{key_prefix}"
    )

    generar_inspeccion = st.checkbox(
        "Generar también inspección ocular",
        value=False,
        key=f"chk_inspeccion_{key_prefix}",
        help="Actívalo solo si el atestado incluye inspección ocular en el lugar de los hechos.",
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        generar_directo = st.button("Generar atestado", key=f"btn_directo_{key_prefix}")
    with col2:
        if st.button("🧹 Limpiar", key=f"btn_limpiar_directo_{key_prefix}"):
            resetear_formulario(key_prefix, ["resultado_atestado", "datos_atestado"])
            st.rerun()

    if generar_directo:
        if not contenido.strip():
            st.warning("Introduce los datos antes de generar.")
            return

        with st.spinner("Analizando texto..."):
            origen_detectado, presencial_detectado = detectar_contexto_actuacion(
                api_key,
                "\n\n".join(parte for parte in [pinceladas, contenido] if parte.strip()),
            )

        st.info(f"Origen detectado: **{origen_detectado}** · Personación en el lugar: **{presencial_detectado}**")

        bloque = _construir_contenido_directo(
            contenido,
            origen_detectado,
            presencial_detectado,
            orden_autoridad,
            pinceladas,
            priorizar_pinceladas=True,
        )
        prompt_exposicion = PROMPT_INTELCOPS_PREFIX + PROMPT_ATESTADO_EXPOSICION

        if generar_inspeccion:
            prompt_inspeccion = PROMPT_INTELCOPS_PREFIX + PROMPT_ATESTADO_INSPECCION
            with st.spinner("Generando exposición e inspección ocular..."):
                exposicion = generar_texto_con_ia(
                    api_key,
                    prompt_exposicion,
                    bloque,
                    BLOQUE_FIDELIDAD_ATESTADO_EXPOSICION,
                )
                inspeccion = generar_texto_con_ia(api_key, prompt_inspeccion, bloque)
                documento = (
                    "===== EXPOSICIÓN DE HECHOS =====\n\n"
                    + exposicion
                    + "\n\n===== INSPECCIÓN OCULAR =====\n\n"
                    + inspeccion
                )
            datos_ic = {"Datos de INTELCOPS": contenido}
            guardar_log_generacion("atestado_exposicion", datos_ic, bloque, exposicion)
            guardar_log_generacion("atestado_inspeccion", datos_ic, bloque, inspeccion)
        else:
            with st.spinner("Generando exposición de hechos..."):
                exposicion = generar_texto_con_ia(
                    api_key,
                    prompt_exposicion,
                    bloque,
                    BLOQUE_FIDELIDAD_ATESTADO_EXPOSICION,
                )
                documento = "===== EXPOSICIÓN DE HECHOS =====\n\n" + exposicion
            datos_ic = {"Datos de INTELCOPS": contenido}
            guardar_log_generacion("atestado_exposicion", datos_ic, bloque, exposicion)

        st.session_state["resultado_atestado"] = documento
        st.session_state["datos_atestado"] = {
            "_modo": "directo_intelcops",
            "Datos de INTELCOPS": contenido,
        }


# =========================================================
# MÓDULOS
# =========================================================

def generar_modulo_simple(
    api_key: str,
    key_prefix: str,
    titulo: str,
    icono: str,
    tipo_documento: str,
    campos: list[str],
    prompt_base: str,
    resultado_key: str,
    datos_key: str,
    prefijo_guardado: str,
    texto_boton_generar: str,
    spinner_texto: str,
    transformar_datos=None,
    secciones: list | None = None,
):
    cabecera_modulo(titulo, icono)

    tab_directo, tab_campos = st.tabs(["⚡ Desde INTELCOPS", "📝 Con campos"])

    with tab_directo:
        bloque_generacion_directa(
            api_key=api_key,
            key_prefix=key_prefix,
            tipo_documento=tipo_documento,
            prompt_base=prompt_base,
            resultado_key=resultado_key,
            datos_key=datos_key,
            prefijo_guardado=prefijo_guardado,
        )

    with tab_campos:
        bloque_texto_a_campos(api_key, key_prefix, tipo_documento, campos)

        origen_actuacion, intervencion_presencial, orden_autoridad = selector_contexto_actuacion_general(key_prefix)

        col_tools_1, col_tools_2 = st.columns(2)
        with col_tools_1:
            if st.button("🧹 Limpiar formulario", key=f"limpiar_{key_prefix}"):
                resetear_formulario(key_prefix, [resultado_key, datos_key])
                st.rerun()
        with col_tools_2:
            st.caption("Pega un texto base o rellena los campos manualmente.")

        if secciones:
            datos = {}
            for titulo_sec, campos_sec in secciones:
                datos.update(render_form_fields_grupo(titulo_sec, campos_sec, key_prefix))
        else:
            datos = render_form_fields(campos, key_prefix)

        if callable(transformar_datos):
            datos_transformados = transformar_datos(datos)
            if datos_transformados is not None:
                datos = datos_transformados

        generar = st.button(texto_boton_generar, key=f"btn_generar_{key_prefix}")

        if generar:
            prompt_final = prompt_base
            bloque = construir_bloque_usuario_con_contexto(
                datos,
                origen_actuacion,
                intervencion_presencial,
                orden_autoridad,
            )
            with st.spinner(spinner_texto):
                texto = generar_texto_con_ia(api_key, prompt_final, bloque)
            guardar_log_generacion(prefijo_guardado, datos, bloque, texto)

            st.session_state[resultado_key] = texto
            st.session_state[datos_key] = datos

    if st.session_state.get(resultado_key):
        mostrar_resultado(
            st.session_state[resultado_key],
            st.session_state.get(datos_key, {}),
            prefijo_guardado,
        )


def pagina_atestado(api_key: str):
    key_prefix = "atestado"
    cabecera_modulo("Atestado completo", "📄")

    tab_directo, tab_campos = st.tabs(["⚡ Desde INTELCOPS", "📝 Con campos"])

    with tab_directo:
        bloque_generacion_directa_atestado(api_key, key_prefix)

    with tab_campos:
        bloque_texto_a_campos(api_key, "atestado", "Atestado completo", CAMPOS_ATESTADO_COMPLETO)
        origen_actuacion, intervencion_presencial, orden_autoridad = selector_contexto_actuacion_general(key_prefix)

        col_tools_1, col_tools_2 = st.columns(2)
        with col_tools_1:
            if st.button("🧹 Limpiar formulario", key="limpiar_atestado"):
                resetear_formulario("atestado", ["resultado_atestado", "datos_atestado"])
                st.rerun()
        with col_tools_2:
            st.caption("Genera exposición e inspección ocular en un solo paso.")

        secciones_atestado = [
            ("🗂️ Identificación del atestado", [
                "Nº de atestado", "Municipio / Jefatura",
                "NIP del instructor", "NIP del secretario",
                "Destino (juzgado o unidad receptora)", "Delito o hecho imputado",
            ]),
            ("🕐 Fechas y horas", [
                "Fecha de inicio de diligencias", "Hora de inicio de diligencias",
                "Fecha del hecho", "Hora del hecho o franja horaria",
                "Fecha de personación del denunciante en jefatura (si procede)",
                "Hora de personación del denunciante en jefatura (si procede)",
                "Fecha de personación de los agentes en el lugar",
                "Hora de personación de los agentes en el lugar",
            ]),
            ("📍 Lugar y actuación", [
                "Lugar", "Agentes actuantes (NIP)", "Indicativo policial",
            ]),
            ("👤 Requirente / denunciante", [
                "Alertante o requirente", "DNI del alertante o requirente",
                "Teléfono del alertante o requirente",
            ]),
            ("👥 Personas implicadas", [
                "Personas implicadas", "DNI personas implicadas",
                "Teléfono personas implicadas",
            ]),
            ("📋 Hechos", [
                "Motivo del aviso", "Relato general de los hechos", "Actuaciones realizadas",
            ]),
            ("🔍 Inspección del lugar", [
                "Descripción del lugar", "Accesos", "Daños observados", "Elementos relevantes",
            ]),
            ("🏁 Pruebas y cierre", [
                "Reportaje fotográfico (sí/no)", "Observaciones adicionales",
            ]),
        ]
        datos = {}
        for titulo_sec, campos_sec in secciones_atestado:
            datos.update(render_form_fields_grupo(titulo_sec, campos_sec, key_prefix))

        generar = st.button("Generar atestado", key="btn_generar_atestado")

        if generar:
            bloque = construir_bloque_usuario_con_contexto(
                datos,
                origen_actuacion,
                intervencion_presencial,
                orden_autoridad,
            )
            with st.spinner("Generando exposición e inspección ocular..."):
                exposicion = generar_texto_con_ia(
                    api_key,
                    PROMPT_ATESTADO_EXPOSICION,
                    bloque,
                    BLOQUE_FIDELIDAD_ATESTADO_EXPOSICION,
                )
                inspeccion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_INSPECCION, bloque)
            guardar_log_generacion("atestado_exposicion", datos, bloque, exposicion)
            guardar_log_generacion("atestado_inspeccion", datos, bloque, inspeccion)

            nº_atestado = datos.get("Nº de atestado", "").strip()
            municipio = datos.get("Municipio / Jefatura", "").strip()
            nip_inst = datos.get("NIP del instructor", "").strip()
            nip_sec = datos.get("NIP del secretario", "").strip()
            destino = datos.get("Destino (juzgado o unidad receptora)", "").strip()
            delito = datos.get("Delito o hecho imputado", "").strip()
            fecha_ini = datos.get("Fecha de inicio de diligencias", "").strip()

            cabecera_partes = []
            if municipio:
                cabecera_partes.append(f"Policía Local de {municipio}")
            if nº_atestado:
                cabecera_partes.append(f"Atestado Nº {nº_atestado}")
            if nip_inst:
                cabecera_partes.append(f"Instructor: NIP {nip_inst}")
            if nip_sec:
                cabecera_partes.append(f"Secretario: NIP {nip_sec}")
            if destino:
                cabecera_partes.append(f"Destino: {destino}")
            if delito:
                cabecera_partes.append(f"Delito/Hecho: {delito}")
            if fecha_ini:
                cabecera_partes.append(f"Fecha: {fecha_ini}")

            cabecera_str = "\n".join(cabecera_partes)
            separador = "=" * 50

            documento = (
                separador + "\n"
                + cabecera_str + "\n"
                + separador + "\n\n"
                + "===== EXPOSICIÓN DE HECHOS =====\n\n"
                + exposicion
                + "\n\n===== INSPECCIÓN OCULAR =====\n\n"
                + inspeccion
            ) if cabecera_str else (
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



# =========================================================
# CONFIG DE MÓDULOS
# =========================================================

MODULOS = {
    "Accidente": {
        "tipo": "simple",
        "key_prefix": "accidente",
        "titulo": "Informe técnico de accidente",
        "icono": "🚗",
        "tipo_documento": "Informe técnico de accidente",
        "campos": CAMPOS_ACCIDENTE,
        "prompt": PROMPT_INFORME_ACCIDENTE,
        "resultado_key": "resultado_accidente",
        "datos_key": "datos_accidente",
        "prefijo_guardado": "accidente",
        "texto_boton_generar": "Generar informe de accidente",
        "spinner_texto": "Generando informe...",
        "transformar_datos": ajustar_datos_accidente_por_tipo,
        "secciones": [
            ("🕐 Fecha y hora", [
                "Fecha del accidente", "Hora del accidente",
                "Fecha del aviso", "Hora del aviso",
                "Hora de comparecencia en jefatura (si procede)",
                "Fecha de personación de los agentes", "Hora de personación de los agentes",
            ]),
            ("📍 Lugar y actuación", [
                "Lugar", "Agentes actuantes (NIP)", "Indicativo policial",
                "Tipo de accidente", "Número de vehículos implicados",
            ]),
            ("📞 Requirente", [
                "Alertante o requirente", "DNI del alertante o requirente",
                "Teléfono del alertante o requirente",
            ]),
            ("🚗 Vehículo A", [
                "Vehículo A - clase y matrícula", "Vehículo A - marca", "Vehículo A - modelo",
                "Vehículo A - color", "Conductor vehículo A", "DNI conductor vehículo A",
                "Teléfono conductor vehículo A", "Pasajeros vehículo A (indicar posición)",
                "DNI pasajeros vehículo A", "Teléfono pasajeros vehículo A",
            ]),
            ("🚙 Vehículo B", [
                "Vehículo B - clase y matrícula", "Vehículo B - marca", "Vehículo B - modelo",
                "Vehículo B - color", "Conductor vehículo B", "DNI conductor vehículo B",
                "Teléfono conductor vehículo B", "Pasajeros vehículo B (indicar posición)",
                "DNI pasajeros vehículo B", "Teléfono pasajeros vehículo B",
            ]),
            ("🚕 Vehículo C", [
                "Vehículo C - clase y matrícula", "Vehículo C - marca", "Vehículo C - modelo",
                "Vehículo C - color", "Conductor vehículo C", "DNI conductor vehículo C",
                "Teléfono conductor vehículo C", "Pasajeros vehículo C (indicar posición)",
                "DNI pasajeros vehículo C", "Teléfono pasajeros vehículo C",
            ]),
            ("👥 Otros implicados", [
                "Más implicados (si hubiere)", "DNI más implicados", "Teléfono más implicados",
                "Peatones (si los hubiere)", "DNI peatones", "Teléfono peatones",
                "Testigos (si los hubiere)", "DNI testigos", "Teléfono testigos",
            ]),
            ("🛣️ Vía y condiciones", [
                "Descripción de la vía", "Condiciones meteorológicas",
            ]),
            ("📋 Hechos y actuaciones", [
                "Daños observados", "Posición de los vehículos a la llegada de los agentes",
                "Relato técnico del accidente (¿Qué ha pasado?)", "Actuaciones realizadas",
            ]),
            ("🔬 Pruebas", [
                "Reportaje fotográfico (sí/no)",
                "Prueba de alcoholemia (indicar resultado)",
                "Prueba de drogas (signos, indicar resultado)",
            ]),
            ("🏁 Cierre", [
                "Asistencia sanitaria (personas asistidas, indicativo sanitario, hora de llegada, hora de salida, lugar de traslado)",
                "Conclusión técnica (¿Por qué ha pasado?)", "Observaciones adicionales",
            ]),
        ],
    },
    "Atestado completo": {
        "tipo": "atestado",
    },
    "Informe municipal": {
        "tipo": "simple",
        "key_prefix": "municipal",
        "titulo": "Informe municipal",
        "icono": "🏛️",
        "tipo_documento": "Informe municipal",
        "campos": CAMPOS_INFORME_MUNICIPAL,
        "prompt": PROMPT_INFORME_MUNICIPAL,
        "resultado_key": "resultado_municipal",
        "datos_key": "datos_municipal",
        "prefijo_guardado": "informe_municipal",
        "texto_boton_generar": "Generar informe municipal",
        "spinner_texto": "Generando informe...",
        "transformar_datos": None,
    },
    "Parte de servicio": {
        "tipo": "simple",
        "key_prefix": "servicio",
        "titulo": "Parte de servicio",
        "icono": "📝",
        "tipo_documento": "Parte de servicio",
        "campos": CAMPOS_PARTE_SERVICIO,
        "prompt": PROMPT_PARTE_SERVICIO,
        "resultado_key": "resultado_servicio",
        "datos_key": "datos_servicio",
        "prefijo_guardado": "parte_servicio",
        "texto_boton_generar": "Generar parte de servicio",
        "spinner_texto": "Generando parte...",
        "transformar_datos": None,
        "secciones": [
            ("🗂️ Identificación", [
                "Nº de expediente (si procede)", "Municipio / Jefatura",
                "NIP del agente redactor", "Categoría de los agentes", "Turno de servicio",
            ]),
            ("🕐 Datos del servicio", [
                "Fecha", "Hora del aviso", "Hora de personación de los agentes",
                "Hora de personación del requirente/alertante en jefatura (si procede)",
                "Lugar", "Agentes actuantes (NIP)", "Indicativo policial",
            ]),
            ("👥 Intervinientes", [
                "Alertante o requirente", "DNI del alertante o requirente",
                "Teléfono del alertante o requirente", "Personas implicadas",
                "DNI personas implicadas", "Teléfono personas implicadas",
            ]),
            ("🚗 Vehículo (si procede)", [
                "Vehículo - matrícula", "Vehículo - marca",
                "Vehículo - modelo", "Vehículo - titular",
            ]),
            ("📋 Hechos y actuaciones", [
                "Asunto o motivo", "Relato libre de lo sucedido o de la gestión realizada",
                "Actuaciones policiales realizadas", "Observaciones adicionales",
            ]),
        ],
    },
    "Anomalía": {
        "tipo": "simple",
        "key_prefix": "anomalia",
        "titulo": "Anomalía",
        "icono": "⚠️",
        "tipo_documento": "Anomalía",
        "campos": CAMPOS_ANOMALIA,
        "prompt": PROMPT_ANOMALIA,
        "resultado_key": "resultado_anomalia",
        "datos_key": "datos_anomalia",
        "prefijo_guardado": "anomalia",
        "texto_boton_generar": "Generar anomalía",
        "spinner_texto": "Generando anomalía...",
        "transformar_datos": None,
        "secciones": [
            ("🕐 Datos generales", [
                "Fecha", "Hora del aviso", "Hora de personación de los agentes",
                "Hora de personación del requirente/alertante en jefatura (si procede)",
                "Lugar exacto", "Agentes actuantes (NIP)", "Indicativo policial",
            ]),
            ("👥 Intervinientes", [
                "Alertante o requirente", "DNI del alertante o requirente",
                "Teléfono del alertante o requirente", "Personas implicadas",
                "DNI personas implicadas", "Teléfono personas implicadas",
            ]),
            ("⚠️ Incidencia y actuación", [
                "Tipo de anomalía", "Descripción breve de la incidencia observada",
                "Riesgo o afectación apreciada", "Actuaciones realizadas",
                "Servicio o departamento avisado", "Observaciones adicionales",
            ]),
        ],
    },
    "Informe personas": {
        "tipo": "simple",
        "key_prefix": "juzgado",
        "titulo": "Informe personas",
        "icono": "⚖️",
        "tipo_documento": "Informe al juzgado",
        "campos": CAMPOS_INFORME_JUZGADO,
        "prompt": PROMPT_INFORME_JUZGADO,
        "resultado_key": "resultado_juzgado",
        "datos_key": "datos_juzgado",
        "prefijo_guardado": "informe_juzgado",
        "texto_boton_generar": "Generar informe personas",
        "spinner_texto": "Generando informe personas...",
        "transformar_datos": None,
        "secciones": [
            ("🕐 Datos generales", [
                "Fecha", "Hora", "Hora de personación",
                "Lugar", "Agentes actuantes (NIP)", "Indicativo policial",
                "Tipo de informe al juzgado", "Órgano judicial", "Procedimiento / asunto",
            ]),
            ("👤 Persona afectada", [
                "Persona afectada", "DNI persona afectada", "Teléfono persona afectada",
                "Domicilio principal", "Otros domicilios consultados",
            ]),
            ("🔍 Gestiones realizadas", [
                "Teléfonos contactados", "Bases de datos consultadas",
                "Número de intentos realizados", "Fechas y horas de los intentos",
                "Comprobaciones realizadas", "Resultado de las gestiones",
                "Manifestaciones de terceros (si las hubiere)", "Observaciones adicionales",
            ]),
        ],
    },

    "Denuncia administrativa": {
        "tipo": "simple",
        "key_prefix": "denuncia_admin",
        "titulo": "Denuncia administrativa",
        "icono": "📄",
        "tipo_documento": "Denuncia administrativa",
        "campos": CAMPOS_DENUNCIA_ADMINISTRATIVA,
        "prompt": PROMPT_DENUNCIA_ADMINISTRATIVA,
        "resultado_key": "resultado_denuncia_admin",
        "datos_key": "datos_denuncia_admin",
        "prefijo_guardado": "denuncia_administrativa",
        "texto_boton_generar": "Generar descripción de hechos",
        "spinner_texto": "Generando descripción de hechos...",
        "transformar_datos": None,
        "secciones": [
            ("🕐 Datos generales", [
                "Fecha", "Hora", "Lugar",
                "Agentes actuantes (NIP)", "Indicativo policial", "Origen de la actuación",
            ]),
            ("👤 Persona denunciada", [
                "Persona denunciada / responsable",
                "DNI persona denunciada / responsable",
                "Teléfono persona denunciada / responsable",
            ]),
            ("📋 Infracción y hechos", [
                "Norma administrativa aplicada", "Precepto o artículo (si se conoce)",
                "Hecho observado", "Requerimientos realizados por los agentes",
                "Respuesta o actitud de la persona",
            ]),
            ("🏁 Actuación y cierre", [
                "Actuaciones policiales realizadas", "Testigos (si los hubiere)",
                "Documentación / reportaje fotográfico", "Observaciones adicionales",
            ]),
        ],
    },
}


# =========================================================
# ESTILOS
# =========================================================

def aplicar_estilos():
    st.markdown("""
    <style>

    /* ── SIDEBAR ─────────────────────────────── */
    [data-testid="stSidebar"] > div:first-child {
        background-color: #0067b1;
        padding-top: 1.2rem;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] .stMarkdown {
        color: #e8f0fb !important;
    }
    [data-testid="stSidebar"] input[type="password"],
    [data-testid="stSidebar"] input[type="text"] {
        background-color: rgba(255,255,255,0.12) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.25) !important;
        border-radius: 8px !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        background-color: rgba(255,255,255,0.12);
        color: #e8f0fb;
        border: 1px solid rgba(255,255,255,0.25);
        border-radius: 8px;
        width: 100%;
        font-size: 14px;
        padding: 8px 12px;
        margin-top: 4px;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: rgba(255,255,255,0.22);
        border-color: rgba(255,255,255,0.5);
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.2);
        margin: 12px 0;
    }

    /* ── TIPOGRAFÍA GENERAL ──────────────────── */
    html, body, [class*="css"] {
        font-size: 15px !important;
    }
    label {
        font-size: 14px !important;
        font-weight: 600 !important;
        color: #0067b1 !important;
    }
    textarea, input {
        font-size: 14px !important;
    }
    .stTextArea textarea {
        font-size: 14px !important;
        line-height: 1.55;
        border-radius: 8px !important;
    }

    /* ── BOTONES PRINCIPALES ─────────────────── */
    .stButton > button[kind="primary"],
    .stButton > button {
        font-size: 14px;
        border-radius: 8px;
        padding: 8px 18px;
        font-weight: 600;
        transition: all 0.15s ease;
    }

    /* ── CABECERA DE MÓDULO ──────────────────── */
    .modulo-header {
        background: linear-gradient(135deg, #0067b1 0%, #1a8ed4 100%);
        border-radius: 12px;
        padding: 16px 22px;
        margin-bottom: 18px;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .modulo-header-icon {
        font-size: 28px;
    }
    .modulo-header-titulo {
        font-size: 22px;
        font-weight: 700;
        color: #ffffff !important;
        letter-spacing: 0.3px;
    }

    /* ── TARJETAS HOME ───────────────────────── */
    .card-modulo {
        border: 1px solid #dde6f0;
        border-radius: 14px;
        padding: 22px 16px 14px;
        text-align: center;
        background: #ffffff;
        box-shadow: 0 2px 10px rgba(30,58,95,0.07);
        margin-bottom: 8px;
        transition: box-shadow 0.2s, transform 0.15s;
        cursor: default;
    }
    .card-modulo:hover {
        box-shadow: 0 6px 20px rgba(30,58,95,0.14);
        transform: translateY(-2px);
    }
    .card-modulo-icon {
        font-size: 36px;
        margin-bottom: 8px;
    }
    .card-modulo-titulo {
        font-size: 15px;
        font-weight: 700;
        color: #0067b1;
        margin-bottom: 4px;
    }
    .card-modulo-desc {
        font-size: 12px;
        color: #6b7c93;
        line-height: 1.4;
    }

    /* ── HOME HEADER ─────────────────────────── */
    .home-header {
        background: linear-gradient(135deg, #0067b1 0%, #1a8ed4 100%);
        border-radius: 14px;
        padding: 28px 32px;
        margin-bottom: 28px;
        text-align: center;
    }
    .home-header h1 {
        color: #ffffff !important;
        font-size: 28px !important;
        margin: 0 0 6px 0;
    }
    .home-header p {
        color: rgba(255,255,255,0.80) !important;
        font-size: 14px !important;
        margin: 0;
    }

    /* ── EXPANDERS ───────────────────────────── */
    [data-testid="stExpander"] {
        border: 1px solid #dde6f0 !important;
        border-radius: 10px !important;
        margin-bottom: 10px !important;
    }
    [data-testid="stExpander"] summary {
        font-weight: 600 !important;
        font-size: 14px !important;
        color: #0067b1 !important;
        padding: 10px 14px !important;
    }

    /* ── TABS ────────────────────────────────── */
    [data-testid="stTabs"] button[role="tab"] {
        font-weight: 600;
        font-size: 14px;
    }

    </style>
    """, unsafe_allow_html=True)


# =========================================================
# PANTALLA DE INICIO
# =========================================================

MODULOS_HOME = [
    {"nombre": "Accidente",             "icono": "🚗", "desc": "Informe técnico de tráfico"},
    {"nombre": "Atestado completo",     "icono": "📋", "desc": "Exposición de hechos e inspección ocular"},
    {"nombre": "Informe municipal",     "icono": "🏛️", "desc": "Incidencias e intervenciones municipales"},
    {"nombre": "Parte de servicio",     "icono": "📝", "desc": "Registro de actuación policial"},
    {"nombre": "Anomalía",              "icono": "⚠️", "desc": "Notificación de anomalías y riesgos"},
    {"nombre": "Informe personas",       "icono": "⚖️", "desc": "Informes y diligencias judiciales"},
    {"nombre": "Denuncia administrativa","icono": "📄", "desc": "Denuncia y acta de infracción"},
]


def pagina_inicio():
    st.markdown("""
    <div class="home-header">
        <h1>🚓 Policía Local IA</h1>
        <p>Selecciona el módulo con el que quieres trabajar</p>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(3)
    for i, mod in enumerate(MODULOS_HOME):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="card-modulo">
                <div class="card-modulo-icon">{mod['icono']}</div>
                <div class="card-modulo-titulo">{mod['nombre']}</div>
                <div class="card-modulo-desc">{mod['desc']}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Abrir", key=f"home_{mod['nombre']}", use_container_width=True):
                st.session_state["pagina_actual"] = mod["nombre"]
                st.rerun()


# =========================================================
# APP PRINCIPAL
# =========================================================

aplicar_estilos()

# ── Sidebar ──────────────────────────────────────────────
st.sidebar.markdown("## 🚓 Policía Local IA")
st.sidebar.markdown("---")

api_key = st.sidebar.text_input(
    "API key de OpenAI",
    type="password",
    help="Pega aquí tu clave. No se guarda fuera de tu sesión.",
)

if "pagina_actual" not in st.session_state:
    st.session_state["pagina_actual"] = "inicio"

pagina_actual = st.session_state["pagina_actual"]

if pagina_actual != "inicio":
    st.sidebar.markdown("---")
    if st.sidebar.button("← Volver al inicio"):
        st.session_state["pagina_actual"] = "inicio"
        st.rerun()
    st.sidebar.markdown(f"**Módulo activo:**  \n{pagina_actual}")

# ── Pantalla de inicio ────────────────────────────────────
if pagina_actual == "inicio":
    if not api_key:
        st.markdown("""
        <div class="home-header">
            <h1>🚓 Policía Local IA</h1>
            <p>Herramienta de redacción policial con inteligencia artificial</p>
        </div>
        """, unsafe_allow_html=True)
        st.info("Introduce tu API key de OpenAI en la barra lateral para empezar.")
        st.stop()
    pagina_inicio()
    st.stop()

# ── Módulo activo ─────────────────────────────────────────
if not api_key:
    st.info("Introduce tu API key en la barra lateral para empezar.")
    st.stop()

pagina = pagina_actual

if pagina == "Informe municipal":
    pagina_informe_municipal(api_key)

else:
    config = MODULOS.get(pagina)

    if not config:
        st.info("Selecciona un módulo.")
        st.stop()

    if config["tipo"] == "simple":
        generar_modulo_simple(
            api_key=api_key,
            key_prefix=config["key_prefix"],
            titulo=config["titulo"],
            icono=config["icono"],
            tipo_documento=config["tipo_documento"],
            campos=config["campos"],
            prompt_base=config["prompt"],
            resultado_key=config["resultado_key"],
            datos_key=config["datos_key"],
            prefijo_guardado=config["prefijo_guardado"],
            texto_boton_generar=config["texto_boton_generar"],
            spinner_texto=config["spinner_texto"],
            transformar_datos=config["transformar_datos"],
            secciones=config.get("secciones"),
        )

    elif config["tipo"] == "atestado":
        pagina_atestado(api_key)
