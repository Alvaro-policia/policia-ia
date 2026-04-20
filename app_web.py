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


def guardar_txt_con_nombre(documento: str, nombre: str) -> str:
    asegurar_carpeta("informes")
    ruta = os.path.join("informes", f"{nombre}.txt")
    with open(ruta, "w", encoding="utf-8") as archivo:
        archivo.write(documento)
    return ruta


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


def generar_texto_con_ia(api_key: str, prompt_sistema: str, datos_usuario: str) -> str:
    client = get_client(api_key)

    # Añadimos bloque común de fidelidad y extensión a TODOS los prompts
    prompt_final = prompt_sistema + "\n\n" + BLOQUE_FIDELIDAD_Y_EXTENSION

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

BLOQUE_CONTEXTO_JEFATURA = (
    "CONTEXTO DE ACTUACIÓN:\n"
    "- Debes atender a los campos 'Origen de la actuación' e 'Intervención presencial en el lugar'.\n"
    "- El origen de la actuación puede ser comparecencia en jefatura, aviso telefónico, aviso en la calle, actuación de oficio u orden jerárquica.\n"
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
    "TIEMPO VERBAL:\n"
    "- Toda la redacción debe realizarse en tiempo presente narrativo policial.\n"
    "- Ejemplos correctos: 'se recibe aviso', 'se personan los agentes', 'se observa', 'se realiza', 'donde ocurre el siniestro'.\n"
    "- No utilices pasado en ningún caso.\n"
)

BLOQUE_PERSONACION_OBLIGATORIA = (
    "PERSONACIÓN POLICIAL (OBLIGATORIO):\n"
    "- Si existe intervención presencial en el lugar, debes reflejar la personación de los agentes.\n"
    "- Si en los datos aparece una 'FRASE DE PERSONACIÓN OBLIGATORIA', debes integrarla obligatoriamente.\n"
    "- Debes reproducirla de forma literal o muy próxima.\n"
    "- Está prohibido omitirla si está presente.\n\n"
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

BLOQUE_AVISOS = (
    "AVISOS:\n"
    "- Si el origen de la actuación es 'Aviso telefónico', debes iniciar la redacción como recepción de aviso o llamada telefónica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que se recibe aviso en el teléfono oficial...' o 'Que se recibe llamada...'.\n"
    "- Si consta la hora del aviso, debes integrarla expresamente en la redacción.\n"
    "- Si el origen de la actuación es 'Aviso en la calle', debes iniciar la redacción como requerimiento directo en vía pública.\n"
    "- Debes usar fórmulas equivalentes a: 'Que los agentes son requeridos en vía pública...' o 'Que un ciudadano requiere la presencia policial en el lugar...'.\n"
    "- Si en el campo 'Alertante o requirente' consta que se trata de un ciudadano no identificado o de un viandante, debes mantener coherencia con dicha circunstancia.\n"
    "- Está prohibido redactar como aviso telefónico un supuesto de aviso en la calle.\n"
    "- Está prohibido redactar como aviso en la calle un supuesto de aviso telefónico.\n\n"
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

TIEMPO VERBAL:
- Toda la redacción debe realizarse en tiempo presente narrativo policial.

TRATAMIENTO DE PERSONAS:
- Todas las personas físicas deben figurar siempre como 'D.' o 'Dña.' seguido del nombre completo.
- Está prohibido omitir el tratamiento en cualquier mención.

ORIGEN DE LA ACTUACIÓN:
- El origen puede ser comparecencia en jefatura, aviso telefónico, aviso en la calle, actuación de oficio u orden jerárquica.
- Debes adaptar la redacción estrictamente al tipo de origen.
- Está prohibido mezclar tipos de origen.
- Si es comparecencia en jefatura, está prohibido indicar que se recibe aviso o llamada.
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

PROMPT_ACCIDENTE = (
    "Eres un asistente de redacción policial especializado en informes técnicos de accidentes de tráfico para Policía Local.\n\n"

    "Debes redactar un INFORME TÉCNICO DE ACCIDENTE en castellano, con estilo policial real, técnico, formal y objetivo.\n"
    "Debe comenzar exactamente con: 'Los instructores en funciones de Policía Judicial de Tráfico, pertenecientes al Cuerpo de la Policía Local, hacen constar mediante el presente informe técnico:'\n"
    "El texto debe ir íntegramente en prosa y todos los párrafos deben comenzar por 'Que'.\n"
    "No uses subtítulos.\n"
    "No inventes datos.\n"
    "Si un dato no consta, se omite.\n\n"

    + BLOQUE_TIEMPO_PRESENTE + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL + "\n"

    "TRATAMIENTO TEMPORAL:\n"
    "- Debes diferenciar claramente entre la fecha y hora del accidente, la fecha y hora del aviso, la comparecencia en dependencias y la personación de los agentes, si constan.\n"
    "- Si el accidente se comunica con posterioridad a su ocurrencia, debes dejarlo claro en la redacción.\n"
    "- No debes confundir la hora del accidente con la del aviso, la comparecencia o la personación policial.\n\n"
    
    "OBLIGACIÓN DE INTEGRIDAD DE DATOS:\n"
    "- Todos los datos proporcionados en los campos deben aparecer reflejados en el informe si son relevantes.\n"
    "- No debes omitir datos de identificación como DNI o teléfono cuando consten.\n"
    "- No debes simplificar ni resumir eliminando información relevante.\n\n"
    "- El campo 'Indicativo policial' es de carácter obligatorio en la redacción si consta.\n"
    "- No puede ser omitido bajo ningún concepto.\n"

    "INTEGRACIÓN DEL MOMENTO DEL SINIESTRO:\n"
    "- Debes mencionar expresamente la fecha y hora del accidente si constan en los datos.\n"
    "- Si la fecha y hora del accidente son distintas de la fecha y hora del aviso, debes reflejar ambos momentos de forma diferenciada.\n"
    "- No debes omitir la hora del accidente cuando conste.\n"
    "- En supuestos de aviso posterior, debes dejar claro que el accidente ocurre a una hora y el aviso se recibe en otra posterior.\n\n"
    
    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Debes atender obligatoriamente al campo 'Origen de la actuación'.\n"
    "- Si consta la hora del aviso, debes integrarla obligatoriamente en ese primer párrafo.\n"
    "- Si el origen es 'Comparecencia en jefatura', debes iniciar como comparecencia en dependencias.\n"
    + BLOQUE_AVISOS +
    "- Si el origen es 'Actuación de oficio', está prohibido indicar que se recibe aviso o llamada.\n"
    "- En actuación de oficio debes usar fórmulas como 'Que realizando labores propias del cargo...' o 'Que los agentes observan...'.\n"
    "- Debes atender también al campo 'Intervención presencial en el lugar'.\n"
    "- Si el origen es 'Orden jerárquica', debes iniciar la redacción indicando que la actuación se realiza por orden jerárquica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que por orden jerárquica...' o 'Que en cumplimiento de orden jerárquica...'.\n"
    "- Si consta el campo 'Orden jerárquica (autoridad que la dicta)', debes indicar expresamente dicha autoridad.\n"
    "- Debes integrarlo con una fórmula equivalente a: 'Que en cumplimiento de orden jerárquica dictada por [autoridad]...'.\n"
    "- Está prohibido indicar que se recibe llamada, aviso o comparecencia cuando el origen sea orden jerárquica.\n"
    "- Si NO existe intervención presencial, no debes simular que los agentes se personan en el lugar.\n"
    "- Si SÍ existe intervención, debes integrarla de forma cronológica coherente tras el inicio.\n\n"

    "INTERVENCIÓN POLICIAL:\n"
    "- Si existe personación en el lugar, debes integrar la intervención de los agentes con fórmula técnica policial.\n"
    "- Si la actuación se inicia por comparecencia posterior en dependencias, debes reflejarlo con naturalidad y sin simular una intervención inmediata en vía pública.\n"
    "- La personación de los agentes debe figurar obligatoriamente en el primer bloque narrativo del informe, inmediatamente después de la recepción del aviso o de la comparecencia en dependencias.\n"
    "- Está prohibido situar la personación policial en párrafos posteriores si ya constan fecha, hora e indicativo policial.\n"
    "- La frase de personación debe integrarse de forma natural dentro del párrafo, no como cita independiente ni entrecomillada.\n"
    "- Si se practican gestiones posteriores, debes integrarlas de forma ordenada.\n\n"

    "IDENTIFICACIÓN DE AGENTES:\n"
    "- Debes referirte a ellos como 'los agentes con NIP XXXX y NIP XXXX'.\n"
    "- No debes usar fórmulas como 'los agentes, identificados con los NIP...'.\n\n"

    "ESTRUCTURA DE IDENTIFICACIÓN DE VEHÍCULOS Y CONDUCTORES:\n"
    "- Cada vehículo debe ir seguido inmediatamente de su conductor con todos los datos disponibles.\n"
    "- No debes separar la identificación del vehículo de la del conductor en párrafos distintos.\n"
    "- Si un conductor es además el alertante, debes indicarlo en esa misma frase de identificación.\n"
    "- Esta mención debe formar parte de la primera descripción del conductor.\n\n"

    "ORDEN DE LAS ACTUACIONES POLICIALES:\n"
    "- Debes respetar el orden cronológico en que aparezcan reflejadas en el campo 'Actuaciones realizadas'.\n"
    "- Si en dicho campo primero se indica restablecimiento de la circulación, después identificación, luego recogida de manifestaciones, asistencia sanitaria, información de trámites y abandono del lugar, debes mantener ese mismo orden en la redacción.\n"
    "- No debes adelantar la recogida de manifestaciones ni otras actuaciones si en los datos aparecen después.\n\n"

    "ACTUACIONES POLICIALES:\n"
    "- Debes redactar las actuaciones en lenguaje técnico-policial real.\n"
    "- Está prohibido usar expresiones genéricas como 'gestiones pertinentes'.\n"
    "- Debes describir las actuaciones concretas realizadas por los agentes.\n"
    "- Las actuaciones deben integrarse en la narrativa, no enumerarse.\n\n"
   
    "TIPO DE ACCIDENTE E IMPLICADOS:\n"
    "- Debes atender al tipo de accidente indicado.\n"
    "- Si es SIMPLE, solo debes usar vehículo A y los implicados asociados al mismo, además de peatones o testigos si constan.\n"
    "- Si es COMPLEJO, debes estructurar los implicados por vehículos A y B.\n"
    "- Si es MÚLTIPLE, debes estructurar los implicados por vehículo A, B, C y más implicados si los hubiere.\n"
    "- Debes mantener orden técnico en la identificación de todos los implicados.\n"
    "- No menciones personas o vehículos cuyos campos estén vacíos.\n\n"

    "ASOCIACIÓN DEL ALERTANTE O REQUIRENTE:\n"
    "- Debes atender obligatoriamente al campo 'Alertante o requirente'.\n"
    "- Si el alertante coincide con uno de los conductores implicados, debes identificarlo expresamente como tal.\n"
    "- Esta identificación es obligatoria y no puede omitirse.\n"
    "- Debes integrarlo en el mismo párrafo de identificación del conductor.\n"
    "- Debes usar una fórmula equivalente a: 'resulta ser asimismo el alertante del siniestro'.\n"
    "- Está prohibido omitir esta información cuando exista coincidencia.\n"
    "- Está prohibido colocar esta información en un párrafo distinto al de identificación del conductor.\n\n"

    "NÚMERO DE VEHÍCULOS IMPLICADOS:\n"
    "- Debes integrar expresamente el número de vehículos implicados si consta en los datos.\n"
    "- Si consta 'Número de vehículos implicados', debes reflejarlo en el párrafo inicial de identificación del siniestro.\n\n"
    
   "VEHÍCULOS Y VÍA:\n"
    "- Cada vehículo debe describirse con su clase, matrícula, marca, modelo y color si constan.\n"
    "- No utilices tipos genéricos como si fueran marca.\n"
    "- Debes describir tipo de vía, condiciones del firme y meteorología si constan.\n"
    "- Si consta el campo 'Condiciones meteorológicas', debes mencionarlo expresamente en el informe.\n"
    "- Debes integrarlo con una fórmula técnica equivalente a: 'siendo las condiciones meteorológicas existentes en el momento del accidente...' o 'presentando en el momento del accidente condiciones meteorológicas...'.\n"
    "- No debes omitir dicho dato cuando conste en los campos.\n\n"

    "OBJETIVIDAD TÉCNICA:\n"
    "- La descripción debe ser objetiva y basada en hechos observables.\n"
    "- No debes incluir valoraciones subjetivas ni explicaciones innecesarias.\n"
    "- Debes describir las condiciones de la vía sin justificar ni interpretar.\n"
    "- Está prohibido añadir consecuencias o valoraciones como 'lo que favorece la visibilidad'.\n"
    "- Debes limitarte a describir el estado real de la vía.\n\n"

    "DESCRIPCIÓN DE LA VÍA (IMPORTANTE):\n"
    "- Debes ampliar la descripción con elementos técnicos habituales aunque no consten expresamente.\n"
    "- Puedes incluir de forma neutra: visibilidad, señalización horizontal/vertical, anchura suficiente, configuración típica.\n"
    "- No debes inventar datos concretos no facilitados (como señales específicas inexistentes).\n"
    "- Debes incluir si hay aceras, altura de las aceras si están al mismo nivel de la calzada o diferente nivel, arcenes, carriles, mediana, isleta o elementos similares si constan.\n"
    "- Debes evitar descripciones pobres o excesivamente breves.\n\n"

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

    "DINÁMICA DEL SINIESTRO:\n"
    "- Cuando la dinámica se apoye en las manifestaciones de las partes, debes introducirla preferentemente con fórmulas como: 'Que recogidas manifestaciones a las partes implicadas...' o 'Que recogidas manifestaciones de las partes implicadas...'.\n"
    "- Debes evitar fórmulas artificiales como 'Que el relato técnico del accidente (¿Qué ha pasado?) indica...'.\n"
    "- Debes reconstruir el accidente de forma técnica completa.\n"
    "- Debes describir:\n"
    "  1. Situación previa de los vehículos.\n"
    "  2. Maniobra realizada.\n"
    "  3. Punto exacto de impacto.\n"
    "  4. Posición final.\n"
    "- Debes basarte en daños y configuración de la vía.\n"
    "- No puedes usar causas genéricas.\n"
    "- Debes describir únicamente hechos técnicos, no valoraciones.\n"
    "- La causa debe deducirse de la maniobra, no afirmarse directamente.\n\n"

    "PASAJEROS Y PERSONAS IMPLICADAS:\n"
    "- Debes indicar la posición de los pasajeros si consta.\n"
    "- Si no consta, no la inventes.\n\n"

   "PRUEBAS DE ALCOHOLEMIA Y DROGAS:\n"
    "- Solo debes hacer mención a pruebas de alcoholemia si el campo 'Prueba de alcoholemia (indicar resultado)' contiene información expresa y concreta.\n"
    "- Si dicho campo está vacío, no consta o no aporta contenido material suficiente, está prohibido mencionar la realización de pruebas de alcoholemia, aunque en otros campos del formulario aparezcan referencias indirectas, consecuencias administrativas, denuncias o sospechas relacionadas.\n"
    "- Si se realizan pruebas de alcoholemia y así consta en ese campo específico, debes redactar obligatoriamente un párrafo específico de alcoholemia.\n"
    "- En ese párrafo debes indicar expresamente, de forma obligatoria y no resumible, que se informa a los conductores de su obligación de someterse a las pruebas por estar implicados en un siniestro vial, en base al artículo 14 del Real Decreto Legislativo 6/2015, de 30 de octubre, por el que se aprueba el texto refundido de la Ley sobre Tráfico, Circulación de Vehículos a Motor y Seguridad Vial.\n"
    "- Está prohibido omitir la referencia al artículo 14 del Real Decreto Legislativo 6/2015 si en el campo específico consta que se realizaron pruebas de alcoholemia.\n"
    "- Está prohibido redactar un párrafo de alcoholemia sin incluir esa referencia legal completa.\n"
    "- La referencia legal de alcoholemia debe aparecer antes de indicar los resultados.\n"
    "- Si constan resultados de alcoholemia, debes indicarlos expresamente con su unidad y con la fórmula 'mg/L en aire espirado'. Ejemplo: '0,48 mg/L en aire espirado'.\n"
    "- Solo debes hacer mención a pruebas de drogas si el campo 'Prueba de drogas (signos, indicar resultado)' contiene información expresa y concreta.\n"
    "- Si dicho campo está vacío, no consta o no aporta contenido material suficiente, está prohibido mencionar la realización de pruebas de drogas, aunque en otros campos del formulario aparezcan referencias indirectas, denuncias, signos, sospechas, resultados o consecuencias administrativas relacionadas con drogas.\n"
    "- Si se realizan pruebas de drogas y así consta en ese campo específico, debes redactar obligatoriamente un párrafo específico indicando que se informa a los conductores de su obligación de someterse a una prueba para la detección de sustancias estupefacientes, psicotrópicos, estimulantes u otras sustancias análogas por estar implicados en un siniestro vial, y que dicha prueba se realiza en base a los artículos 27 y 28 del Real Decreto 1428/2003, de 21 de noviembre, por el que se aprueba el Reglamento General de Circulación.\n"
    "- Si en el campo específico de prueba de drogas constan signos externos compatibles con el consumo (por ejemplo: ojos vidriosos, habla pastosa, nerviosismo, pupilas dilatadas, incoherencias, etc.), debes mencionarlos obligatoriamente en el mismo párrafo, incluso si el resultado es negativo.\n"
    "- Si constan resultados de la prueba de drogas, debes indicarlos expresamente.\n"
    "- La referencia legal es obligatoria y debe mantenerse siempre, independientemente del resultado de la prueba.\n"
    "- Está prohibido omitir, resumir o integrar de forma incompleta la referencia legal bajo ningún concepto.\n"
    "- No debes afirmar infracción si no procede.\n\n"

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
    "- La conclusión debe comenzar con: 'Que a la vista de todo lo expuesto, se concluye que...'.\n"
    "- Debes evitar expresiones genéricas como 'no circula con la diligencia debida'.\n"
    "- Debes formular la causa en términos técnicos de conducción y dinámica del siniestro.\n"
    "- Debe ser técnica, prudente y basada en los datos facilitados.\n\n"
    "- Debes basarte en daños, manifestaciones y configuración de la vía.\n"
    "- Debes explicar la dinámica antes de concluir.\n"
    "- Evita conclusiones genéricas.\n"
    "- Debes evitar expresiones genéricas como 'no circula con la diligencia debida'.\n"
    "- Debes describir la causa del siniestro en términos técnicos de conducción (alcance, falta de distancia de seguridad, no adaptación a las circunstancias del tráfico, etc.).\n"
    "- Si existen infracciones administrativas derivadas de las actuaciones realizadas (alcoholemia, drogas, documentación, señalización, maniobras, etc.), debes mencionarlas expresamente en una frase independiente dentro de la conclusión.\n"
    "- Si en los datos consta una sola denuncia administrativa, debes utilizar una estructura equivalente a: "
    "'Que por otro lado, como resultado de las actuaciones practicadas, se formula denuncia administrativa a [persona] por [hecho concreto]'.\n"
    "- Si en los datos constan varias denuncias administrativas, debes reflejarlo expresamente en plural, respetando el número indicado en los datos.\n"
    "- En caso de plural, debes utilizar una estructura equivalente a: "
    "'Que por otro lado, como resultado de las actuaciones practicadas, se formulan dos denuncias administrativas a [persona] por [hechos concretos]'.\n\n"
    "- Está prohibido vincular la denuncia administrativa como causa del accidente si no existe relación directa.\n"
    "- Debe tener nivel técnico real de informe policial de tráfico.\n\n"

    "ESTILO:\n"
    "- Usa lenguaje técnico-policial real.\n"
    "- Evita expresiones coloquiales o poco técnicas.\n"
    "- No sobreexplicar.\n"
    "- No usar fórmulas artificiales ni repetitivas.\n\n"

    "INTEGRIDAD DE LA INFORMACIÓN (CRÍTICO):\n"
    "- Todos los campos proporcionados deben ser tratados como fuente obligatoria de información.\n"
    "- Ningún campo debe ser considerado secundario.\n"
    "- Está prohibido omitir información relevante contenida en cualquier campo.\n"
    "- El modelo no puede decidir ignorar información por considerarla redundante o poco importante.\n\n"

    "CONSECUENCIAS ADMINISTRATIVAS Y ACTUACIONES DERIVADAS:\n"
    "- Solo debes mencionar denuncias administrativas si constan de forma expresa y literal en los datos proporcionados.\n"
    "- Está prohibido inferir, deducir o suponer la existencia de una denuncia administrativa a partir de la dinámica del accidente, daños, actuaciones o circunstancias del siniestro.\n"
    "- Si en los datos no consta de forma expresa una denuncia administrativa, no debes mencionarla bajo ningún concepto.\n"
    "- Si consta en los datos, debes reflejarla de forma literal, respetando el hecho infractor indicado.\n"
    "- Está prohibido inventar, deducir o generar denuncias administrativas que no estén expresamente indicadas en los datos proporcionados.\n"
    "- Está prohibido generar denuncias administrativas basadas en interpretaciones del modelo. Solo pueden redactarse si están expresamente indicadas en los datos de entrada.\n"
    "- Debes utilizar una estructura equivalente a: 'Que por otro lado, como resultado de las actuaciones practicadas, se formula denuncia administrativa a [persona] por [hecho literal indicado en los datos]'.\n\n"
    
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
    "El texto debe ir íntegramente en prosa, sin listas, sin guiones y sin separaciones artificiales.\n"
    "Todos los párrafos deben comenzar por 'Que'.\n"
    "Debe poder copiarse directamente a un atestado real.\n\n"

    "FINALIDAD:\n"
    "- Relatar de forma cronológica, clara y objetiva la actuación policial.\n"
    "- Debes integrar aviso, intervención, manifestaciones, actuaciones y gestiones posteriores si constan.\n\n"

    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Debes atender estrictamente al campo 'Origen de la actuación'.\n"
    "- Si el origen es 'Comparecencia en jefatura', debes iniciar el relato como comparecencia en dependencias policiales.\n"
    + BLOQUE_AVISOS +
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

    "INICIO:\n"
    "- Debes comenzar con una fórmula coherente con los datos facilitados, por ejemplo: "
    "'Que en la Jefatura de la Policía Local, siendo aproximadamente las XX:XX horas del día XX/XX/XXXX, se recibe aviso...'\n"
    "- Si la actuación se inicia en dependencias, debes reflejarlo.\n"
    "- Si la actuación se inicia en vía pública, debes reflejar el aviso o la observación directa.\n\n"

    "CRONOLOGÍA:\n"
    "- Debes redactar los hechos en orden cronológico.\n"
    "- Debes distinguir entre recepción del aviso, desplazamiento, actuación policial, manifestaciones y gestiones posteriores.\n"
    "- Si existen actuaciones en días u horas posteriores, debes integrarlas ordenadamente.\n\n"

    "INTERVENCIÓN POLICIAL:\n"
    "- Los agentes deben figurar como 'los agentes con NIP XXXX y NIP XXXX', integrados de forma natural en el relato.\n"
    "- Puedes incluir indicativos, unidades y servicios intervinientes si constan.\n"
    "- Debes integrar correctamente la participación de 061, Protección Civil, GES, Policía Nacional u otros servicios si aparecen.\n\n"

    "MANIFESTACIONES:\n"
    "- Deben integrarse dentro del relato sin romper la fluidez.\n"
    "- Puedes usar fórmulas como 'Que D. ... manifiesta que...', 'Que PREGUNTADO...', 'Que entrevistados con... manifiestan...'.\n"
    "- No debes presentar como hecho constatado aquello que solo consta por manifestación de una persona.\n\n"

    "ESTILO:\n"
    "- Redacción limpia, continua, profesional y objetiva.\n"
    "- Debe sonar a documento policial real.\n"
    "- No usar lenguaje literario, explicativo ni frases genéricas de IA.\n"
    "- No inventar datos.\n"
    "- Si un dato no consta, se omite.\n\n"

    "CIERRE:\n"
    "- Debes finalizar con una fórmula coherente de cierre policial, como: "
    "'Que se procede a la confección de las presentes diligencias a los efectos oportunos.'\n\n"

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

    "Debes redactar una INSPECCIÓN OCULAR para atestado, en castellano, con lenguaje técnico, objetivo, descriptivo y estrictamente policial.\n"
    "El texto debe ir íntegramente en prosa y todos los párrafos deben comenzar por 'Que'.\n"
    "No debes incluir encabezados tipo ficha, valoraciones jurídicas ni conclusiones.\n"
    "No debes mezclar la inspección ocular con la comparecencia inicial ni con diligencias posteriores.\n\n"

    "TIEMPO VERBAL (OBLIGATORIO Y CRÍTICO):\n"
    "- Toda la inspección ocular debe redactarse en tiempo presente narrativo policial.\n"
    "- Está prohibido utilizar el pasado en cualquier forma verbal.\n"
    "- Ejemplos correctos: 'se persona', 'se observa', 'se constata', 'se localiza'.\n"
    "- Ejemplos incorrectos: 'se personaron', 'se observó', 'se constató'.\n"
    "- El uso del pasado en la inspección ocular se considera un error grave de redacción y debe evitarse en todo caso.\n"
    "- Antes de generar la respuesta final, debes revisar que todos los verbos estén en presente.\n\n"

    "FINALIDAD:\n"
    "- Describir exclusivamente lo observado por los agentes en el lugar.\n"
    "- Debes centrarte en accesos, estado general, daños, distribución, elementos de interés y demás extremos materiales que consten.\n\n"

    "ORDEN DESCRIPTIVO:\n"
    "- Debes describir de forma ordenada el acceso o localización del lugar, el estado observado, los daños concretos y los elementos relevantes.\n"
    "- Si existen varios daños o elementos, debes integrarlos de forma clara y técnica.\n\n"

    "DAÑOS Y ELEMENTOS MATERIALES:\n"
    "- Si existen daños en puertas, ventanas, cerraduras, cristales, marcos, persianas, accesos u otros elementos, descríbelos con precisión material.\n"
    "- Debes usar fórmulas prudentes y técnicas.\n"
    "- Si consta, puedes usar expresiones como 'siendo dicho daño compatible con la acción de un objeto contundente'.\n"
    "- No debes afirmar extremos no observados directamente.\n"
    "- No debes usar expresiones como 'acceso no autorizado' salvo que realmente conste o encaje de forma objetiva con los hechos.\n\n"

    "ELEMENTOS DE INTERÉS:\n"
    "- Debes indicar la existencia o inexistencia de cámaras de vigilancia si consta.\n"
    "- Debes indicar si se localizan o no objetos relacionados con los daños o con los hechos observados, si consta.\n\n"

    "REPORTAJE FOTOGRÁFICO:\n"
    "- Si se indica, debes incluir expresamente que se realiza reportaje fotográfico del lugar o de los daños, quedando a disposición para su incorporación a las diligencias.\n\n"

    "ESTILO:\n"
    "- Redacción limpia, objetiva, técnica y sin frases superfluas.\n"
    "- Debes limitarte a describir lo observado de forma profesional.\n"
    "- No debes cerrar con fórmulas de conclusión ni de valoración.\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
    + "\n\n"
    + BLOQUE_REGLAS_POLICIALES
    + "\n"
    + BLOQUE_PERSONACION_OBLIGATORIA
    + "\n"
    + BLOQUE_ORDEN_JERARQUICA
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

    "Debes redactar un PARTE DE SERVICIO en castellano, en estilo técnico, claro, objetivo y en prosa.\n"
    "Todos los párrafos deben comenzar obligatoriamente por 'Que'.\n\n"

    "FINALIDAD:\n"
    "- Dejar constancia de una actuación policial.\n"
    "- Recoger hechos, manifestaciones y actuaciones sin calificación jurídica.\n\n"

    "ORIGEN DE LA ACTUACIÓN:\n"
    "- Debes atender estrictamente al campo 'Origen de la actuación'.\n"
    "- Si el origen es 'Comparecencia en jefatura', debes iniciar el relato como comparecencia en dependencias policiales.\n"
    + BLOQUE_AVISOS +
    "- Si el origen es 'Actuación de oficio', está prohibido redactar que se recibe llamada, aviso o requerimiento.\n"
    "- En actuación de oficio debes usar fórmulas como 'Que realizando labores propias del cargo...' o 'Que los agentes actuantes observan...'.\n"
    "- Debes atender también al campo 'Intervención presencial en el lugar?'.\n"
    "- Si no existe intervención presencial, no debes simular personación policial en el lugar.\n"
    "- Si el origen es 'Orden jerárquica', debes iniciar la redacción indicando que la actuación se realiza por orden jerárquica.\n"
    "- Debes usar fórmulas equivalentes a: 'Que por orden jerárquica...' o 'Que en cumplimiento de orden jerárquica...'.\n"
    "- Si consta el campo 'Orden jerárquica (autoridad que la dicta)', debes indicar expresamente dicha autoridad.\n"
    "- Debes integrarlo con una fórmula equivalente a: 'Que en cumplimiento de orden jerárquica dictada por [autoridad]...'.\n"
    "- Está prohibido indicar que se recibe llamada, aviso o comparecencia cuando el origen sea orden jerárquica.\n"
    "- Si existe intervención presencial, debes integrarla de forma cronológica y coherente.\n\n"

    "ESTRUCTURA:\n"
    "- Recepción de aviso o actuación directa.\n"
    "- Personación de la patrulla.\n"
    "- Descripción de lo observado.\n"
    "- Manifestaciones de las personas implicadas.\n"
    "- Actuaciones realizadas.\n\n"

    "ESTILO:\n"
    "- Redacción objetiva y cronológica.\n"
    "- No valorar ni interpretar.\n"
    "- No inventar datos.\n"
    "- Si un dato no consta, se omite.\n\n"

    "MANIFESTACIONES:\n"
    "- Usar formato técnico:\n"
    "  'Que PREGUNTADO...', 'MANIFIESTA que...'\n\n"

    "CIERRE:\n"
    "- Finalizar con:\n"
    "  'Que se procede a la confección del presente parte de servicio a los efectos oportunos.'\n\n"
    
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
    "Fecha de inicio de diligencias",
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
    "Asunto o motivo",
    "Relato libre de lo sucedido o de la gestión realizada",
    "Actuaciones policiales realizadas",
    "Documentación o imágenes adjuntas",
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
}


# =========================================================
# COMPONENTES UI
# =========================================================
def render_form_fields_grupo(titulo: str, campos: list[str], key_prefix: str) -> dict:
    st.markdown(
        f"""
        <div class="bloque-seccion">
            <div style="font-size: 18px; font-weight: 700; margin-bottom: 6px;">
                {titulo}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return render_form_fields(campos, key_prefix)

def selector_contexto_actuacion_general(key_prefix: str) -> tuple[str, str, str]:
    col1, col2 = st.columns(2)

    with col1:
        origen = st.radio(
            "Origen de la actuación",
            [
                "Comparecencia en jefatura",
                "Aviso telefónico",
                "Aviso en la calle",
                "Actuación de oficio",
                "Orden jerárquica",
            ],
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
            ["Sí", "No"],
            key=f"intervencion_presencial_{key_prefix}",
        )

    return origen, intervencion, orden_autoridad


def pagina_informe_municipal(api_key: str):
    key_prefix = "municipal"
    cabecera_modulo("Informe municipal", "🏛️")

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

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button("Generar informe municipal", key="btn_generar_municipal")

    with col2:
        regenerar = st.button("Regenerar informe municipal", key="btn_regenerar_municipal")

    if generar or regenerar:
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

        if st.session_state.get("debug_mode", False):
            st.write("DEBUG - DATOS PARA IA INFORME MUNICIPAL:")
            st.text(bloque)

        with st.spinner("Generando informe..."):
            texto = generar_texto_con_ia(api_key, prompt_final, bloque)


        st.session_state["resultado_municipal"] = texto
        st.session_state["datos_municipal"] = datos

    if st.session_state.get("resultado_municipal"):
        mostrar_resultado(
            st.session_state["resultado_municipal"],
            st.session_state.get("datos_municipal", {}),
            "informe_municipal",
            resultado_key="resultado_municipal",
            datos_key="datos_municipal",
        )


def debug_log(titulo: str, dato: Any):
    if st.session_state.get("debug_mode", False):
        st.write(f"DEBUG - {titulo}:", dato)


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


def cabecera_modulo(titulo: str, icono: str):
    st.markdown(
        f"""
        <div class="bloque-modulo">
            <div style="font-size:30px; font-weight:700;">{icono} {titulo}</div>
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
        ):
            claves_a_borrar.append(clave)

    if claves_resultado:
        claves_a_borrar.extend(claves_resultado)

    for clave in set(claves_a_borrar):
        if clave in st.session_state:
            del st.session_state[clave]

    # Fuerza recreación de widgets con claves nuevas
    bump_reset_version(key_prefix)


def mostrar_resultado(texto: str, datos: dict, prefijo: str, resultado_key: str | None = None, datos_key: str | None = None):
    st.subheader("Resultado")
    altura = 320 if st.session_state.get("modo_patrulla_activo", False) else 450
    st.text_area("Documento generado", texto, height=altura)

    modo_patrulla = st.session_state.get("modo_patrulla_activo", False)

    if modo_patrulla:
        boton_copiar_web(texto, prefijo)

        col1, col2 = st.columns(2)

        with col1:
            if resultado_key and st.button("🗑️ Nuevo", key=f"nuevo_{prefijo}"):
                if resultado_key in st.session_state:
                    del st.session_state[resultado_key]
                if datos_key and datos_key in st.session_state:
                    del st.session_state[datos_key]
                st.rerun()

        with col2:
            st.download_button(
                "Descargar TXT",
                data=texto.encode("utf-8"),
                file_name=f"{prefijo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
            )

    else:
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
        if st.session_state.get("debug_mode", False):
            st.write("DEBUG - Entrando en extraer_campos_desde_dictado")
            st.write("DEBUG - Tipo documento:", tipo_documento)
            st.write("DEBUG - Primeros 300 caracteres del texto:")
            st.write(texto_dictado[:300])

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

        if st.session_state.get("debug_mode", False):
            st.write("DEBUG - RESPUESTA RAW IA:")
            st.code(contenido, language="json")

        datos = json.loads(contenido)

        if not isinstance(datos, dict):
            if st.session_state.get("debug_mode", False):
                st.write("DEBUG - ERROR: la respuesta no es un diccionario")
            return esquema

        resultado = {}
        for campo in campos_objetivo:
            valor = datos.get(campo, "")
            valor = str(valor).strip() if valor is not None else ""

            if campo in OPCIONES_SELECT:
                valor = normalizar_valor_select(campo, valor)

            resultado[campo] = valor

        if st.session_state.get("debug_mode", False):
            st.write("DEBUG - RESULTADO FINAL:")
            st.json(resultado)

        return resultado

    except Exception as e:
        if st.session_state.get("debug_mode", False):
            st.write("DEBUG - EXCEPCIÓN EN extraer_campos_desde_dictado:")
            st.write(str(e))

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
            if st.session_state.get("debug_mode", False):
                st.write("DEBUG - Entró en rellenar campos")

            with st.spinner("Extrayendo campos desde el texto..."):
                datos_extraidos = extraer_campos_desde_dictado(
                    api_key=api_key,
                    tipo_documento=tipo_documento,
                    texto_dictado=texto,
                    campos_objetivo=campos_objetivo,
                )

            if st.session_state.get("debug_mode", False):
                st.write("DEBUG - CAMPOS EXTRAÍDOS:")
                st.json(datos_extraidos)

            aplicar_datos_a_session_state(datos_extraidos, key_prefix)

            st.success("Campos rellenados automáticamente.")
            # st.rerun()

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
    texto_boton_regenerar: str,
    spinner_texto: str,
    transformar_datos=None,
):
    cabecera_modulo(titulo, icono)

    bloque_texto_a_campos(api_key, key_prefix, tipo_documento, campos)

    origen_actuacion, intervencion_presencial, orden_autoridad = selector_contexto_actuacion_general(key_prefix)

    col_tools_1, col_tools_2 = st.columns(2)
    with col_tools_1:
        if st.button("🧹 Limpiar formulario", key=f"limpiar_{key_prefix}"):
            resetear_formulario(key_prefix, [resultado_key, datos_key])
            st.rerun()
    with col_tools_2:
        st.caption("Pega un texto base o rellena los campos manualmente.")

    datos = render_form_fields(campos, key_prefix)
    
    if callable(transformar_datos):
        datos_transformados = transformar_datos(datos)
        if datos_transformados is not None:
            datos = datos_transformados

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button(texto_boton_generar, key=f"btn_generar_{key_prefix}")

    with col2:
        regenerar = st.button(texto_boton_regenerar, key=f"btn_regenerar_{key_prefix}")

    if generar or regenerar:
        prompt_final = prompt_base
        bloque = construir_bloque_usuario_con_contexto(
            datos,
            origen_actuacion,
            intervencion_presencial,
            orden_autoridad,
        )
        debug_log("DATOS PARA IA", bloque)

        with st.spinner(spinner_texto):
            texto = generar_texto_con_ia(api_key, prompt_final, bloque)

        st.session_state[resultado_key] = texto
        st.session_state[datos_key] = datos

    if st.session_state.get(resultado_key):
        mostrar_resultado(
            st.session_state[resultado_key],
            st.session_state.get(datos_key, {}),
            prefijo_guardado,
            resultado_key=resultado_key,
            datos_key=datos_key,
        )


def pagina_atestado(api_key: str):
    key_prefix = "atestado"
    cabecera_modulo("Atestado completo", "📄")
    
    bloque_texto_a_campos(api_key, "atestado", "Atestado completo", CAMPOS_ATESTADO_COMPLETO)
    origen_actuacion, intervencion_presencial, orden_autoridad = selector_contexto_actuacion_general(key_prefix)

    col_tools_1, col_tools_2 = st.columns(2)
    with col_tools_1:
        if st.button("🧹 Limpiar formulario", key="limpiar_atestado"):
            resetear_formulario("atestado", ["resultado_atestado", "datos_atestado"])
            st.rerun()
    with col_tools_2:
        st.caption("Genera exposición e inspección ocular en un solo paso.")
    datos = render_form_fields(CAMPOS_ATESTADO_COMPLETO, key_prefix)

    col1, col2 = st.columns(2)
    with col1:
        generar = st.button("Generar atestado", key="btn_generar_atestado")
    with col2:
        regenerar = st.button("Regenerar atestado", key="btn_regenerar_atestado")

    if generar or regenerar:
        bloque = construir_bloque_usuario_con_contexto(
            datos,
            origen_actuacion,
            intervencion_presencial,
            orden_autoridad,
        )
        debug_log("DATOS PARA IA ATESTADO", bloque)

        with st.spinner("Generando exposición e inspección ocular..."):
            exposicion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_EXPOSICION, bloque)
            inspeccion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_INSPECCION, bloque)
            documento = "===== EXPOSICIÓN DE HECHOS =====\n\n" + exposicion + "\n\n===== INSPECCIÓN OCULAR =====\n\n" + inspeccion

        st.session_state["resultado_atestado"] = documento
        st.session_state["datos_atestado"] = datos

    if st.session_state.get("resultado_atestado"):
        mostrar_resultado(
            st.session_state["resultado_atestado"],
            st.session_state.get("datos_atestado", {}),
            "atestado_completo",
            resultado_key="resultado_atestado",
            datos_key="datos_atestado",
        )


# =========================================================
# MENÚ MÓVIL
# =========================================================

def tarjeta_modulo_movil(titulo: str, subtitulo: str, icono: str, clave: str, destino: str):
    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 20px;
            padding: 14px;
            margin-bottom: 8px;
            background: rgba(255,255,255,0.03);
            text-align: center;
        ">
            <div style="font-size: 34px; margin-bottom: 6px;">{icono}</div>
            <div style="font-size: 22px; font-weight: 700;">{titulo}</div>
            <div style="font-size: 14px; opacity: 0.8;">{subtitulo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button(f"Abrir {titulo}", key=clave):
        st.session_state["pagina_movil"] = destino
        st.rerun()


def selector_modulo_movil() -> str:
    st.markdown("## 🚓 Modo patrulla")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        if st.button("🚗\nAccidente", key="movil_accidente", use_container_width=True):
            st.session_state["pagina_movil"] = "Accidente"
            st.rerun()

        if st.button("🏛️\nInforme municipal", key="movil_municipal", use_container_width=True):
            st.session_state["pagina_movil"] = "Informe municipal"
            st.rerun()

        if st.button("⚠️\nAnomalía", key="movil_anomalia", use_container_width=True):
            st.session_state["pagina_movil"] = "Anomalía"
            st.rerun()

        if st.button("📋\nDenuncia administrativa", key="movil_denuncia_admin", use_container_width=True):
            st.session_state["pagina_movil"] = "Denuncia administrativa"
            st.rerun()

    with col2:
        if st.button("📄\nAtestado", key="movil_atestado", use_container_width=True):
            st.session_state["pagina_movil"] = "Atestado completo"
            st.rerun()

        if st.button("📝\nParte de servicio", key="movil_servicio", use_container_width=True):
            st.session_state["pagina_movil"] = "Parte de servicio"
            st.rerun()

        if st.button("⚖️\nInformes al juzgado", key="movil_juzgado", use_container_width=True):
            st.session_state["pagina_movil"] = "Informes al juzgado"
            st.rerun()

    return st.session_state.get("pagina_movil", "Inicio")


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
        "prompt": PROMPT_ACCIDENTE,
        "resultado_key": "resultado_accidente",
        "datos_key": "datos_accidente",
        "prefijo_guardado": "accidente",
        "texto_boton_generar": "Generar informe de accidente",
        "texto_boton_regenerar": "Regenerar informe de accidente",
        "spinner_texto": "Generando informe...",
        "transformar_datos": ajustar_datos_accidente_por_tipo,
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
        "texto_boton_regenerar": "Regenerar informe municipal",
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
        "texto_boton_regenerar": "Regenerar parte de servicio",
        "spinner_texto": "Generando parte...",
        "transformar_datos": None,
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
        "texto_boton_regenerar": "Regenerar anomalía",
        "spinner_texto": "Generando anomalía...",
        "transformar_datos": None,
    },
    "Informes al juzgado": {
        "tipo": "simple",
        "key_prefix": "juzgado",
        "titulo": "Informes al juzgado",
        "icono": "⚖️",
        "tipo_documento": "Informe al juzgado",
        "campos": CAMPOS_INFORME_JUZGADO,
        "prompt": PROMPT_INFORME_JUZGADO,
        "resultado_key": "resultado_juzgado",
        "datos_key": "datos_juzgado",
        "prefijo_guardado": "informe_juzgado",
        "texto_boton_generar": "Generar informe al juzgado",
        "texto_boton_regenerar": "Regenerar informe al juzgado",
        "spinner_texto": "Generando informe al juzgado...",
        "transformar_datos": None,
    },

    "Denuncia administrativa": {
        "tipo": "simple",
        "key_prefix": "denuncia_admin",
        "titulo": "Denuncia administrativa",
        "icono": "📋",
        "tipo_documento": "Denuncia administrativa",
        "campos": CAMPOS_DENUNCIA_ADMINISTRATIVA,
        "prompt": PROMPT_DENUNCIA_ADMINISTRATIVA,
        "resultado_key": "resultado_denuncia_admin",
        "datos_key": "datos_denuncia_admin",
        "prefijo_guardado": "denuncia_administrativa",
        "texto_boton_generar": "Generar descripción de hechos",
        "texto_boton_regenerar": "Regenerar descripción de hechos",
        "spinner_texto": "Generando descripción de hechos...",
        "transformar_datos": None,
    },
}


# =========================================================
# ESTILOS
# =========================================================

def aplicar_estilos(modo_patrulla: bool):
    if modo_patrulla:
        st.markdown(
            """
            <style>
            .stButton > button {
                width: 100%;
                min-height: 64px;
                font-size: 18px;
                font-weight: 700;
                border-radius: 18px;
                margin-top: 4px;
                margin-bottom: 10px;
                white-space: normal;
            }

            textarea {
                font-size: 18px !important;
                line-height: 1.5 !important;
            }

            .stTextInput input {
                font-size: 18px !important;
            }

            .stSelectbox div[data-baseweb="select"] > div {
                font-size: 18px !important;
                min-height: 54px;
            }

            label, .stMarkdown, .stCaption {
                font-size: 17px !important;
            }

            .bloque-modulo {
                border: 1px solid rgba(128,128,128,0.25);
                border-radius: 18px;
                padding: 14px 16px;
                margin-bottom: 12px;
            }

            .stTextArea textarea {
                min-height: 120px !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown("""
        <style>

        /* Texto general más grande */
        html, body, [class*="css"]  {
            font-size: 16px !important;
        }

        /* Títulos de campos */
        label {
            font-size: 16px !important;
            font-weight: 600 !important;
        }

        /* Inputs más cómodos */
        textarea, input {
            font-size: 15px !important;
        }

        /* Bloques visuales */
        .bloque-seccion {
            border: 1px solid rgba(0,0,0,0.15);
            border-radius: 12px;
            padding: 14px;
            margin-bottom: 12px;
            background-color: #fafafa;
        }

        /* Botones más grandes */
        .stButton > button {
            font-size: 16px;
            padding: 10px;
            border-radius: 10px;
        }

        /* Resultado más cómodo */
        .stTextArea textarea {
            font-size: 15px !important;
            line-height: 1.5;
        }

        </style>
        """, unsafe_allow_html=True)


# =========================================================
# APP PRINCIPAL
# =========================================================

st.sidebar.title("Policía Local IA")
st.sidebar.caption("Versión web para ordenador y móvil")

modo_patrulla = st.sidebar.toggle("Modo patrulla / móvil", value=False)
st.session_state["modo_patrulla_activo"] = modo_patrulla

debug_mode = st.sidebar.toggle("Modo debug", value=False)
st.session_state["debug_mode"] = debug_mode

api_key = st.sidebar.text_input(
    "API key de OpenAI",
    type="password",
    help="Pega aquí tu clave. No se guarda fuera de tu sesión.",
)

if "pagina_movil" not in st.session_state:
    st.session_state["pagina_movil"] = "Inicio"

if "ultimo_modo_patrulla" not in st.session_state:
    st.session_state["ultimo_modo_patrulla"] = modo_patrulla

if modo_patrulla != st.session_state["ultimo_modo_patrulla"]:
    if modo_patrulla:
        st.session_state["pagina_movil"] = "Inicio"
    st.session_state["ultimo_modo_patrulla"] = modo_patrulla

aplicar_estilos(modo_patrulla)

modulos_orden = [
    "Accidente",
    "Atestado completo",
    "Informe municipal",
    "Parte de servicio",
    "Anomalía",
    "Informes al juzgado",
    "Denuncia administrativa",
]

if modo_patrulla:
    st.sidebar.success("Modo patrulla activo")
    st.sidebar.markdown("### Navegación rápida")

    if st.sidebar.button("🏠 Inicio", key="inicio_movil"):
        st.session_state["pagina_movil"] = "Inicio"
        st.rerun()

    if st.session_state["pagina_movil"] == "Inicio":
        pagina = selector_modulo_movil()
    else:
        pagina = st.session_state["pagina_movil"]
else:
    pagina = st.sidebar.radio("Módulos", modulos_orden)

st.title("🚓 Policía Local IA")
st.write("App web operativa para ordenador y móvil, con redacción policial y autocompletado de campos desde texto.")

if not api_key:
    st.info("Introduce tu API key en la barra lateral para empezar.")
    st.stop()

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
            texto_boton_regenerar=config["texto_boton_regenerar"],
            spinner_texto=config["spinner_texto"],
            transformar_datos=config["transformar_datos"],
        )

    elif config["tipo"] == "atestado":
        pagina_atestado(api_key)
