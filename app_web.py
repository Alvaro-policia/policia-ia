import os
import re
import json
import tempfile
from datetime import datetime, date
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
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

    campos_sensibles = {
        "agentes actuantes (nip)",
        "agentes",
        "agentes actuantes",
        "indicativo policial",
        "vehículo a - matrícula",
        "vehículo b - matrícula",
        "vehículo c - matrícula",
        "prueba de alcoholemia (indicar resultado o 'no procede')",
        "prueba de drogas (indicar resultado o 'no procede')",
    }

    if campo.lower() in campos_sensibles or "dni" in campo.lower() or "teléfono" in campo.lower():
        return valor

    # En textos muy largos es mejor no tocar demasiado
    if len(valor) > 120:
        return valor

    return valor[0].upper() + valor[1:] if valor else valor


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

    if campo == "Sentido de la vía según numeración (vehículo A)":
        if "ascend" in valor_limpio:
            return "Ascendente"
        if "descend" in valor_limpio:
            return "Descendente"
        return ""

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
            "Vehículo B - matrícula",
            "Vehículo B - marca",
            "Vehículo B - modelo",
            "Vehículo B - color",
            "Conductor vehículo B",
            "DNI conductor vehículo B",
            "Teléfono conductor vehículo B",
            "Pasajeros vehículo B (indicar posición)",
            "DNI pasajeros vehículo B",
            "Teléfono pasajeros vehículo B",
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

    return datos


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

    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            transcripcion = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file,
            )
        texto = getattr(transcripcion, "text", "") or ""
        return texto.strip()
    except Exception:
        return ""
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


# =========================================================
# MODOS DE REDACCIÓN
# =========================================================

def obtener_instruccion_modo_redaccion(modo_redaccion: str) -> str:
    if modo_redaccion == "Ampliado":
        return (
            "Redacta de forma detallada, desarrollando las actuaciones policiales, la descripción del lugar, la dinámica y los daños observados, "
            "manteniendo un lenguaje técnico policial. NO inventes datos. Si un dato no consta, omítelo del texto o déjalo en blanco si se trata de un campo."
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

BLOQUE_TIEMPO_PRESENTE = (
    "TIEMPO VERBAL:\n"
    "- Toda la redacción debe realizarse en tiempo presente narrativo policial.\n"
    "- Ejemplos correctos: 'se recibe aviso', 'se personan los agentes', 'se observa', 'se realiza', 'donde ocurre el siniestro'.\n"
    "- No utilices pasado en ningún caso.\n"
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

PROMPT_ACCIDENTE = (
    "Eres un asistente de redacción policial especializado en informes técnicos de accidentes para la Policía Local de Poio.\n\n"

    "Debes redactar un INFORME TÉCNICO DE ACCIDENTE con estilo policial real, técnico, formal y objetivo.\n"
    "Debe comenzar exactamente con: 'Los instructores en funciones de Policía Judicial de Tráfico, pertenecientes al Cuerpo de la Policía Local de Poio, hacen constar mediante el presente informe técnico:'\n"
    "Usa párrafos narrativos que comiencen por 'Que...'.\n"
    "No uses subtítulos como 'Conclusión:'.\n"
    "No atribuyas la dinámica literalmente a lo que dicen los conductores; basa la reconstrucción en datos objetivos facilitados.\n"
    "La conclusión debe empezar por 'Que a la vista de todo lo expuesto, se concluye que...'.\n"
    "Finaliza exactamente con: 'Y para que así conste, se extiende el presente informe técnico policial, que se emite en base a la inspección ocular, manifestaciones recabadas y análisis de las circunstancias concurrentes, quedando sometido a cualquier otro mejor fundado.'\n\n"

    + BLOQUE_TIEMPO_PRESENTE + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL + "\n"

    "TRATAMIENTO TEMPORAL Y DE LA FORMA DE CONOCIMIENTO:\n"
    "- Debes diferenciar claramente entre la fecha y hora del accidente, la fecha y hora del aviso, la fecha y hora de comparecencia en jefatura y la fecha y hora de personación de los agentes, si constan.\n"
    "- Debes detectar si el accidente se comunica en el mismo momento de su ocurrencia o si se pone en conocimiento con posterioridad.\n"
    "- Si el accidente se comunica con posterioridad, debes dejarlo claro en la redacción con fórmulas técnicas equivalentes a: 'hechos ocurridos con anterioridad y puestos posteriormente en conocimiento policial'.\n"
    "- Si consta comparecencia en jefatura, debes reflejarlo de forma clara y técnica, indicando que la persona comparece en dependencias policiales para poner los hechos en conocimiento.\n"
    "- Si el accidente ocurre en una fecha y hora anteriores y la comparecencia o aviso se produce después, debes ordenar cronológicamente la redacción sin generar contradicciones.\n"
    "- No debes confundir la hora del accidente con la hora del aviso, ni con la hora de comparecencia en dependencias, ni con la hora de personación de los agentes.\n"
    "- Si solo constan algunos de esos momentos temporales, utiliza únicamente los que figuren en los datos.\n"
    "- Si no existe actuación inmediata en el lugar y lo que existe es una comparecencia posterior en dependencias, debes reflejarlo expresamente.\n\n"

    "INTERVENCIÓN POLICIAL:\n"
    "- Si existe personación de los agentes en el lugar, la llegada de los agentes debe redactarse con la fórmula: 'los agentes con NIP XXXX y NIP XXXX, uniformados reglamentariamente, se personan en el lugar del accidente en vehículo oficial rotulado bajo el indicativo policial XXXX'.\n"
    "- Si no se facilita el indicativo, omítelo sin inventarlo.\n"
    "- La referencia a los agentes debe aparecer preferentemente en el primer párrafo cuando exista actuación presencial en el lugar.\n"
    "- Si no hay personación inmediata en el lugar y la actuación se inicia mediante comparecencia posterior en dependencias, debes reflejarlo de forma técnica y clara.\n"
    "- Si tras la comparecencia se practican gestiones documentales, consultas en bases de datos, reportaje fotográfico o comprobaciones posteriores, debes integrarlo en la narración policial de manera ordenada.\n\n"

    "TIPO DE ACCIDENTE:\n"
    "- Debes atender al campo 'Tipo de accidente'.\n"
    "- Si el accidente es SIMPLE, solo debes usar vehículo A y las personas asociadas a vehículo A, además de peatones o testigos si constan.\n"
    "- Si el accidente es COMPLEJO, debes estructurar los implicados por vehículo: vehículo A, vehículo B, vehículo C y después más implicados si los hubiere.\n"
    "- No menciones vehículos, conductores o pasajeros cuyos campos estén vacíos.\n\n"

    "IDENTIFICACIÓN DE VEHÍCULOS:\n"
    "- Cada vehículo debe describirse con matrícula, marca, modelo y color si constan.\n"
    "- Ejemplo: 'vehículo A, marca Seat, modelo León, color rojo, matrícula XXXX'.\n"
    "- No utilices tipos genéricos como 'furgoneta', 'turismo' o 'camión' como si fueran marca del vehículo.\n"
    "- Si la marca o el modelo no constan con claridad, omítelos.\n\n"

    "SENTIDO DE LA VÍA:\n"
    "- Debes integrar el sentido de la vía según numeración si consta.\n"
    "- El sentido ascendente o descendente se refiere exclusivamente a la numeración de la vía, normalmente en el sentido de marcha del vehículo A.\n"
    "- Nunca debes interpretarlo como pendiente, rampa o inclinación del terreno.\n"
    "- Nunca debes usar expresiones como 'pendiente', 'en cuesta', 'ascenso del terreno' o similares.\n"
    "- Debes redactar expresiones como 'presentando el vehículo A sentido ascendente según numeración de la vía' o 'sentido descendente según numeración de la vía'.\n\n"

    "CONDICIONES DE LA VÍA:\n"
    "- Debes describir tipo de vía, sentido de circulación, estado del firme y condiciones meteorológicas si constan.\n"
    "- Utiliza lenguaje técnico y objetivo.\n\n"

    "PASAJEROS:\n"
    "- Debes indicar la posición de cada pasajero dentro del vehículo si consta (delantero derecho, trasero izquierdo, etc.).\n"
    "- Debes integrarlo de forma técnica en la redacción.\n"
    "- Ejemplo: 'ocupando el mismo en calidad de pasajero, en el asiento delantero derecho, D....'\n"
    "- Si la posición no consta, no la inventes.\n\n"

    "RECONSTRUCCIÓN DE LA DINÁMICA:\n"
    "- Debes reconstruir técnicamente el accidente.\n"
    "- Debes basarte en daños, manifestaciones y configuración de la vía.\n"
    "- No utilices expresiones genéricas como 'conducción negligente' sin explicar la maniobra.\n"
    "- Debes concretar la dinámica: alcance, marcha atrás, giro, incorporación, estacionamiento antirreglamentario, invasión de trayectoria, etc.\n"
    "- Debes describir trayectorias, posiciones relativas y puntos de impacto.\n"
    "- Si se trata de un accidente comunicado con posterioridad y no presenciado directamente por los agentes, debes reflejar la reconstrucción de forma prudente, apoyándote en daños observados, manifestaciones y demás datos objetivos facilitados.\n"
    "- En supuestos de accidente con conductor ausente o desconocido, debes integrarlo con formulaciones técnicas y objetivas, sin afirmar extremos que no consten acreditados más allá de lo facilitado.\n\n"

    "PRUEBAS DE ALCOHOLEMIA Y DROGAS:\n"
    "- Si se realizan pruebas, debes redactarlo conforme al Real Decreto Legislativo 6/2015.\n"
    "- Debes indicar que, al tratarse de un accidente de circulación, se informa a las partes de la realización de las pruebas reglamentarias.\n"
    "- Debes indicar los resultados en mg/l si constan.\n"
    "- No debes afirmar infracción si el resultado no supera el límite sancionador.\n"
    "- Solo debes mencionar denuncia administrativa si procede realmente.\n\n"

    "ESTILO TÉCNICO PROFESIONAL:\n"
    "- Debes utilizar redacción equivalente a informes reales de Policía Local.\n"
    "- Evita expresiones poco técnicas.\n"
    "- Usa lenguaje preciso, formal y estructurado.\n"
    "- Cuando el accidente no se comunica en el mismo momento de su ocurrencia, debes dejarlo claro en la narrativa temporal, sin generar contradicciones.\n"
    "- Si la actuación se inicia por comparecencia en dependencias, debes hacer que la redacción refleje con naturalidad ese inicio, en lugar de simular una actuación inmediata en vía pública si no consta.\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_ATESTADO_EXPOSICION = (
    "Eres un asistente de redacción policial para la Policía Local de Poio.\n\n"

    "Debes redactar una EXPOSICIÓN DE HECHOS para atestado, en castellano, con tono policial formal, técnico y cronológico.\n"
    "Debe estructurarse en párrafos que comiencen por 'Que...'.\n"
    "Debe reflejar de forma clara y ordenada la actuación policial.\n"
    "Debe integrar hora del aviso y hora de personación si constan.\n"
    "No incluir valoraciones jurídicas ni conclusiones.\n"
    "No incluir manifestaciones literales salvo que se indique expresamente.\n"
    "No usar subtítulos adicionales.\n\n"

    + BLOQUE_TIEMPO_PRESENTE + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL + "\n"

    "INTERVENCIÓN POLICIAL:\n"
    "- Cuando la actuación comienza en dependencias, debes indicar que el compareciente se persona en dependencias policiales.\n"
    "- Cuando la actuación es en vía pública, debes indicar que se recibe aviso y los agentes se personan.\n"
    "- Los agentes deben figurar como 'los agentes con NIP XXXX y NIP XXXX'.\n"
    "- Si se facilita indicativo, integrar la fórmula: 'uniformados reglamentariamente, se personan en vehículo oficial rotulado bajo el indicativo policial XXXX'.\n\n"

    "TRATAMIENTO DEL COMPARECIENTE:\n"
    "- La persona debe figurar inicialmente como requirente o compareciente, no como denunciante.\n"
    "- Ejemplo correcto: 'quien comparece como requirente al objeto de poner en conocimiento...'\n\n"

    "CALIDAD DE REDACCIÓN POLICIAL:\n"
    "- Debes evitar expresiones coloquiales como 'le han robado', 'sospecha que alguien', etc.\n"
    "- Debes utilizar fórmulas técnicas como 'manifiesta haber sido víctima de', 'manifiesta la sustracción de', 'no pudiendo concretar el momento exacto'.\n"
    "- La redacción debe ser limpia, objetiva y sin explicaciones innecesarias.\n"
    "- Debes evitar redundancias y frases superfluas.\n"
    "- No debes incluir frases innecesarias como que el compareciente abandona dependencias por sus propios medios.\n\n"

    "CONTENIDO DE LOS HECHOS:\n"
    "- Debes describir los efectos sustraídos o hechos comunicados con precisión.\n"
    "- Debes recoger la manifestación del compareciente de forma técnica.\n"
    "- Si no se conoce el lugar exacto de los hechos, debes indicarlo de forma técnica.\n"
    "- Ejemplo: 'no pudiendo concretar el momento exacto en que se produce la sustracción'.\n\n"

    "ACTUACIÓN POLICIAL:\n"
    "- Debes reflejar que se recogen las manifestaciones.\n"
    "- Debes reflejar las gestiones realizadas por los agentes.\n"
    "- En casos de hurto de cartera o similares, debes incluir que se informa al compareciente de la conveniencia de proceder a la anulación de las tarjetas bancarias a la mayor brevedad posible, a fin de evitar un posible uso fraudulento de las mismas.\n"
    "- Si no existe lugar concreto de los hechos, puedes indicar que no procede inspección ocular.\n\n"

    "TIPO DE HECHO DENUNCIADO:\n"
    "- Si los hechos se refieren a daños, debes integrar, si constan, referencias al estado previo del bien afectado, al momento en que se detectan los daños, a la ausencia de sospechosos y a la inexistencia de cámaras de vigilancia en las inmediaciones.\n"
    "- Si los hechos se refieren a hurto o sustracción, debes integrar, si constan, los efectos sustraídos, la imposibilidad de concretar el momento exacto y la conveniencia de anular tarjetas bancarias si las hubiere.\n"
    "- Debes desarrollar el relato con lenguaje técnico aunque la información sea escasa, sin inventar datos.\n"
    "- Puedes cerrar la exposición con fórmulas como 'sin que se aporten más datos de interés en este momento'.\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_ATESTADO_INSPECCION = (
    "Eres un asistente de redacción policial para la Policía Local de Poio.\n\n"

    "Debes redactar una INSPECCIÓN OCULAR para atestado, en castellano, con lenguaje técnico, objetivo, descriptivo y estrictamente policial.\n"
    "Debe estructurarse en párrafos que comiencen por 'Que...'.\n"
    "No debes incluir encabezados tipo ficha como fecha, hora, lugar o agentes.\n"
    "No debes incluir valoraciones jurídicas ni conclusiones.\n"
    "No debes mezclar la inspección ocular con la comparecencia inicial o con diligencias posteriores.\n\n"

    + BLOQUE_TIEMPO_PRESENTE + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL + "\n"

    "OBJETO DE LA INSPECCIÓN:\n"
    "- Debes describir únicamente lo observado por los agentes en el lugar.\n"
    "- Debes detallar accesos, daños, distribución, estado del lugar y elementos relevantes si constan.\n"
    "- No debes inventar elementos no facilitados.\n\n"

    "DAÑOS Y ELEMENTOS MATERIALES:\n"
    "- Si existen daños en puertas, ventanas, cerraduras, cristales, marcos, persianas, accesos u otros elementos, descríbelos con precisión material.\n"
    "- Debes usar fórmulas técnicas y prudentes.\n"
    "- En supuestos de daños, puedes utilizar expresiones como 'siendo dicho daño compatible con la acción de un objeto contundente' si así consta en los datos.\n"
    "- No debes utilizar expresiones como 'acceso no autorizado' salvo que realmente conste o encaje con los hechos denunciados.\n\n"

    "CÁMARAS Y ELEMENTOS DE INTERÉS:\n"
    "- Debes indicar la existencia o inexistencia de cámaras de vigilancia en las inmediaciones si consta.\n"
    "- Debes indicar si se localizan o no objetos relacionados con los daños o hechos observados, si consta.\n\n"

    "REPORTAJE FOTOGRÁFICO:\n"
    "- Si se indica, debes incluir expresamente que se realiza reportaje fotográfico de los daños o del lugar, quedando a disposición para su incorporación a las diligencias.\n\n"

    "CALIDAD DE REDACCIÓN POLICIAL:\n"
    "- La redacción debe ser limpia, objetiva y sin frases superfluas.\n"
    "- No debes cerrar con fórmulas como 'se concluye la inspección ocular' o similares.\n"
    "- Debes limitarte a describir lo observado de forma profesional.\n\n"

    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_INFORME_MUNICIPAL = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. Debes redactar un INFORME MUNICIPAL en castellano, con tono formal, objetivo, técnico y administrativo. "
    "Integra hora del aviso y hora de personación si constan. Debe ser apto para conflictos entre particulares, incidencias en inmuebles, requerimientos vecinales o incidencias municipales.\n\n"
    + BLOQUE_TIEMPO_PRESENTE
    + "\n"
    + TRATAMIENTO_PERSONAS_MUNICIPAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_PARTE_SERVICIO = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. Debes redactar un PARTE DE SERVICIO interno, en castellano, con tono formal, claro, objetivo y operativo. "
    "Integra hora del aviso y hora de personación si constan.\n\n"
    + BLOQUE_TIEMPO_PRESENTE
    + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
)

PROMPT_ANOMALIA = (
    "Eres un asistente de redacción policial para la Policía Local de Poio. Debes redactar una ANOMALÍA o comunicación breve de incidencia en vía pública o elementos urbanos, en castellano, con tono claro, breve, técnico y operativo. "
    "Integra hora del aviso y hora de personación si constan.\n\n"
    + BLOQUE_TIEMPO_PRESENTE
    + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL
    + "\n"
    + REGLAS_COMUNES_NO_INVENTAR
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
    "Fecha de comparecencia en jefatura (si procede)",
    "Hora de comparecencia en jefatura (si procede)",
    "Fecha de personación de los agentes",
    "Hora de personación de los agentes",

    # ===== LUGAR Y ACTUACIÓN =====
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Tipo de accidente",

    # ===== REQUIRIMIENTO =====
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",

    # ===== VEHÍCULO A =====
    "Vehículo A - matrícula",
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
    "Vehículo B - matrícula",
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
    "Sentido de la vía según numeración (vehículo A)",
    "Condiciones meteorológicas",

    # ===== HECHOS =====
    "Daños observados",
    "Relato técnico del accidente",
    "Actuaciones realizadas",

    # ===== PRUEBAS =====
    "Reportaje fotográfico (sí/no)",
    "Prueba de alcoholemia (indicar resultado o 'no procede')",
    "Prueba de drogas (indicar resultado o 'no procede')",

    # ===== FINAL =====
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
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes",
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
    "Hora",
    "Hora de personación",
    "Lugar",
    "Agentes",
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",
    "Personas implicadas o comparecientes",
    "DNI personas implicadas o comparecientes",
    "Teléfono personas implicadas o comparecientes",
    "Asunto o motivo",
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


# =========================================================
# OPCIONES DE SELECT
# =========================================================

OPCIONES_SELECT = {
    "Tipo de accidente": ["", "Simple", "Complejo"],
    "Sentido de la vía según numeración (vehículo A)": ["", "Ascendente", "Descendente"],
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


# =========================================================
# COMPONENTES UI
# =========================================================

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


def selector_modo_redaccion(clave: str, modulo: str) -> str:
    pagina_actual = st.session_state.get("pagina_movil", "normal")
    return st.selectbox(
        "Modo de redacción",
        ["Técnico", "Ampliado"],
        index=0,
        key=f"{clave}_{modulo}_{pagina_actual}",
    )


def render_form_fields(campos: list[str], key_prefix: str) -> dict:
    datos = {}

    for campo in campos:
        clave = f"{key_prefix}_{campo}"
        clave_widget = f"widget_{clave}"

        if campo.lower() == "fecha":
            valor_actual = st.session_state.get(clave_widget, st.session_state.get(clave, ""))
            fecha_inicial = parsear_fecha(valor_actual) or datetime.today().date()

            valor_widget = st.date_input(
                campo,
                value=fecha_inicial,
                key=clave_widget,
                format="DD/MM/YYYY",
            )
            valor = formatear_fecha(valor_widget)

        elif campo in OPCIONES_SELECT:
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

        else:
            valor = st.text_area(
                campo,
                value=st.session_state.get(clave_widget, st.session_state.get(clave, "")),
                key=clave_widget,
                height=80,
            )

        st.session_state[clave] = valor
        datos[campo] = valor

    return normalizar_datos(datos)


def aplicar_datos_a_session_state(datos_extraidos: dict, key_prefix: str):
    if not isinstance(datos_extraidos, dict):
        return

    for campo, valor in datos_extraidos.items():
        clave_base = f"{key_prefix}_{campo}"
        clave_widget = f"widget_{clave_base}"

        valor = "" if valor is None else str(valor).strip()

        if campo in OPCIONES_SELECT:
            valor = normalizar_valor_select(campo, valor)

        st.session_state[clave_base] = valor

        if campo.lower() == "fecha":
            fecha_convertida = parsear_fecha(valor)
            if fecha_convertida is not None:
                st.session_state[clave_widget] = fecha_convertida
            else:
                if clave_widget in st.session_state:
                    del st.session_state[clave_widget]
        else:
            st.session_state[clave_widget] = valor


def resetear_formulario(campos: list[str], key_prefix: str, claves_resultado: list[str] | None = None):
    for campo in campos:
        clave_base = f"{key_prefix}_{campo}"
        clave_widget = f"widget_{clave_base}"

        if clave_base in st.session_state:
            del st.session_state[clave_base]
        if clave_widget in st.session_state:
            del st.session_state[clave_widget]

    claves_extra = [
        f"audio_campos_{key_prefix}",
        f"dictado_campos_{key_prefix}",
        f"texto_dictado_{key_prefix}",
    ]

    for clave in claves_extra:
        if clave in st.session_state:
            del st.session_state[clave]

    if claves_resultado:
        for clave in claves_resultado:
            if clave in st.session_state:
                del st.session_state[clave]


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
  - "Sentido de la vía según numeración (vehículo A)": "Ascendente" o "Descendente"
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
- Si del dictado se desprende que el accidente ocurrió antes y que posteriormente la persona acude a jefatura a comunicarlo, debes separar correctamente ambos momentos.
- Si el dictado menciona expresamente que la persona se persona en jefatura o en dependencias policiales para contar un accidente ocurrido con anterioridad, debes rellenar los campos de comparecencia en jefatura si existen entre los campos objetivo.
- Si el dictado menciona que los agentes se personan en el lugar en otro momento distinto, debes rellenar aparte la fecha y hora de personación de los agentes si esos campos existen entre los campos objetivo.
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
Eres un asistente policial que extrae datos estructurados desde un dictado libre.

TIPO DE DOCUMENTO:
{tipo_documento}

CAMPOS A RELLENAR:
{json.dumps(campos_objetivo, ensure_ascii=False, indent=2)}

INSTRUCCIONES:
- Devuelve EXCLUSIVAMENTE un objeto JSON válido.
- No escribas texto antes ni después del JSON.
- Usa exactamente como claves los nombres de los campos proporcionados.
- Si un dato no aparece claro, deja su valor como cadena vacía "".
- No inventes datos.
- Si el dictado menciona agentes, horas, lugar, daños, dinámica o motivo del aviso, colócalos en el campo más adecuado.
- En los campos narrativos amplios, resume fielmente el dictado con lenguaje claro, técnico y útil para redacción policial.
{instrucciones_select}
{instrucciones_tiempo}
{instrucciones_logica}
{instrucciones_vehiculos}

JSON base esperado:
{json.dumps(esquema, ensure_ascii=False, indent=2)}

DICTADO:
{texto_dictado}
"""

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Devuelve solo JSON válido, sin texto adicional y sin inventar datos. "
                        "Respeta exactamente las claves pedidas. "
                        "Distingue correctamente accidente, aviso, comparecencia en jefatura y personación de los agentes cuando aparezcan en el dictado. "
                        "Si el accidente se comunica posteriormente, separa correctamente los momentos temporales."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        contenido = (respuesta.choices[0].message.content or "").strip()
        contenido = limpiar_json_respuesta(contenido)

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
        st.warning(f"No se pudieron extraer campos desde el dictado. Error: {e}")
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
        pause_threshold=4.0,
        sample_rate=41000,
        key=f"audio_campos_{key_prefix}",
    )

    if audio_bytes:
        st.session_state[f"audio_campos_{key_prefix}"] = audio_bytes

    audio_guardado = st.session_state.get(f"audio_campos_{key_prefix}")
    texto_guardado = st.session_state.get(f"dictado_campos_{key_prefix}", "")

    col_a, col_b = st.columns(2)

    with col_a:
        if st.button("Transcribir dictado", key=f"transcribir_campos_{key_prefix}"):
            if not audio_guardado:
                st.warning("Primero graba un audio.")
            else:
                with st.spinner("Transcribiendo audio..."):
                    texto = transcribir_audio_con_openai(api_key, audio_guardado)

                if texto.strip():
                    st.session_state[f"dictado_campos_{key_prefix}"] = texto
                    texto_guardado = texto
                    st.success("Dictado transcrito.")
                else:
                    st.warning("No se pudo transcribir el audio o no se detectó voz clara.")

    with col_b:
        if st.button("Rellenar campos desde dictado", key=f"rellenar_campos_{key_prefix}"):
            texto_actual = st.session_state.get(f"texto_dictado_{key_prefix}", texto_guardado)
            if not str(texto_actual).strip():
                st.warning("Primero graba o escribe un dictado.")
            else:
                with st.spinner("Extrayendo campos desde el dictado..."):
                    datos_extraidos = extraer_campos_desde_dictado(
                        api_key=api_key,
                        tipo_documento=tipo_documento,
                        texto_dictado=texto_actual,
                        campos_objetivo=campos_objetivo,
                    )

                debug_log("CAMPOS EXTRAÍDOS", datos_extraidos)
                aplicar_datos_a_session_state(datos_extraidos, key_prefix)
                st.success("Campos rellenados automáticamente. Revisa y corrige lo que haga falta.")
                st.rerun()

    texto_guardado = st.text_area(
        "Texto dictado",
        value=texto_guardado,
        height=140,
        key=f"texto_dictado_{key_prefix}",
    )

    st.session_state[f"dictado_campos_{key_prefix}"] = texto_guardado


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
    modo_key: str,
    texto_boton_generar: str,
    texto_boton_regenerar: str,
    spinner_texto: str,
    transformar_datos=None,
):
    cabecera_modulo(titulo, icono)
    modo_redaccion = selector_modo_redaccion(modo_key, key_prefix)

    bloque_dictado_a_campos(api_key, key_prefix, tipo_documento, campos)

    col_tools_1, col_tools_2 = st.columns(2)
    with col_tools_1:
        if st.button("🧹 Limpiar formulario", key=f"limpiar_{key_prefix}"):
            resetear_formulario(campos, key_prefix, [resultado_key, datos_key])
            st.rerun()
    with col_tools_2:
        st.caption("Usa el dictado o rellena los campos manualmente.")

    datos = render_form_fields(campos, key_prefix)

    if callable(transformar_datos):
        datos = transformar_datos(datos)

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button(texto_boton_generar, key=f"btn_generar_{key_prefix}")

    with col2:
        regenerar = st.button(texto_boton_regenerar, key=f"btn_regenerar_{key_prefix}")

    if generar or regenerar:
        prompt_final = prompt_base + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        bloque = construir_bloque_usuario(datos)
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
    modo_redaccion = selector_modo_redaccion("modo_atestado", "atestado")

    bloque_dictado_a_campos(api_key, key_prefix, "Atestado completo", CAMPOS_ATESTADO_COMPLETO)

    col_tools_1, col_tools_2 = st.columns(2)
    with col_tools_1:
        if st.button("🧹 Limpiar formulario", key="limpiar_atestado"):
            resetear_formulario(CAMPOS_ATESTADO_COMPLETO, key_prefix, ["resultado_atestado", "datos_atestado"])
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
        bloque = construir_bloque_usuario(datos)
        instruccion = obtener_instruccion_modo_redaccion(modo_redaccion)
        debug_log("DATOS PARA IA ATESTADO", bloque)

        with st.spinner("Generando exposición e inspección ocular..."):
            exposicion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_EXPOSICION + "\n\n" + instruccion, bloque)
            inspeccion = generar_texto_con_ia(api_key, PROMPT_ATESTADO_INSPECCION + "\n\n" + instruccion, bloque)
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

    col1, col2 = st.columns(2)

    with col1:
        tarjeta_modulo_movil("Accidente", "Informe técnico", "🚗", "movil_accidente", "Accidente")
        tarjeta_modulo_movil("Municipal", "Informe administrativo", "🏛️", "movil_municipal", "Informe municipal")
        tarjeta_modulo_movil("Anomalía", "Incidencia municipal", "⚠️", "movil_anomalia", "Anomalía")

    with col2:
        tarjeta_modulo_movil("Atestado", "Hechos e inspección", "📄", "movil_atestado", "Atestado completo")
        tarjeta_modulo_movil("Servicio", "Parte rápido", "📝", "movil_servicio", "Parte de servicio")
        tarjeta_modulo_movil("Juzgado", "Gestiones judiciales", "⚖️", "movil_juzgado", "Informes al juzgado")

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
        "modo_key": "modo_accidente",
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
        "modo_key": "modo_municipal",
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
        "modo_key": "modo_servicio",
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
        "modo_key": "modo_anomalia",
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
        "modo_key": "modo_juzgado",
        "texto_boton_generar": "Generar informe al juzgado",
        "texto_boton_regenerar": "Regenerar informe al juzgado",
        "spinner_texto": "Generando informe al juzgado...",
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
        st.markdown(
            """
            <style>
            .bloque-modulo {
                border: 1px solid rgba(128,128,128,0.25);
                border-radius: 18px;
                padding: 14px 16px;
                margin-bottom: 12px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )


# =========================================================
# APP PRINCIPAL
# =========================================================

st.sidebar.title("Policía IA")
st.sidebar.caption("Versión web para ordenador y móvil")

modo_patrulla = st.sidebar.toggle("Modo patrulla / móvil", value=True)
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

st.title("🚓 Policía IA - Policía Local de Poio")
st.write("App web operativa para ordenador y móvil, con redacción policial, dictado a campos.")

if not api_key:
    st.info("Introduce tu API key en la barra lateral para empezar.")
    st.stop()

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
        modo_key=config["modo_key"],
        texto_boton_generar=config["texto_boton_generar"],
        texto_boton_regenerar=config["texto_boton_regenerar"],
        spinner_texto=config["spinner_texto"],
        transformar_datos=config["transformar_datos"],
    )
elif config["tipo"] == "atestado":
    pagina_atestado(api_key)
