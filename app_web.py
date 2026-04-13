import os
import json
import tempfile
from datetime import datetime

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

    return valor[0].upper() + valor[1:] if valor else valor


def normalizar_datos(diccionario: dict) -> dict:
    return {k: capitalizar_si_corresponde(k, v) for k, v in diccionario.items()}


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
    "Debe integrar hora del aviso y hora de personación si constan.\n"
    "No uses subtítulos como 'Conclusión:'.\n"
    "No atribuyas la dinámica literalmente a lo que dicen los conductores; basa la reconstrucción en datos objetivos facilitados.\n"
    "La conclusión debe empezar por 'Que a la vista de todo lo expuesto, se concluye que...'.\n"
    "Finaliza exactamente con: 'Y para que así conste, se extiende el presente informe técnico policial, que se emite en base a la inspección ocular, manifestaciones recabadas y análisis de las circunstancias concurrentes, quedando sometido a cualquier otro mejor fundado.'\n\n"

    + BLOQUE_TIEMPO_PRESENTE + "\n"
    + TRATAMIENTO_PERSONAS_GENERAL + "\n"

    "INTERVENCIÓN POLICIAL:\n"
    "- La llegada de los agentes debe redactarse con la fórmula: 'los agentes con NIP XXXX y NIP XXXX, uniformados reglamentariamente, se personan en el lugar del accidente en vehículo oficial rotulado bajo el indicativo policial XXXX'.\n"
    "- Si no se facilita el indicativo, omítelo sin inventarlo.\n"
    "- La referencia a los agentes debe aparecer preferentemente en el primer párrafo.\n\n"

    "TIPO DE ACCIDENTE:\n"
    "- Debes atender al campo 'Tipo de accidente'.\n"
    "- Si el accidente es SIMPLE, solo debes usar vehículo A y las personas asociadas a vehículo A, además de peatones o testigos si constan.\n"
    "- Si el accidente es COMPLEJO, debes estructurar los implicados por vehículo: vehículo A, vehículo B, vehículo C y después más implicados si los hubiere.\n"
    "- No menciones vehículos, conductores o pasajeros cuyos campos estén vacíos.\n\n"

    "IDENTIFICACIÓN DE VEHÍCULOS:\n"
    "- Cada vehículo debe describirse con matrícula, marca, modelo y color si constan.\n"
    "- Ejemplo: 'vehículo A, marca Seat, modelo León, color rojo, matrícula XXXX'.\n\n"

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
    "- Debes concretar la dinámica: alcance, marcha atrás, giro, incorporación, invasión de trayectoria, etc.\n"
    "- Debes describir trayectorias, posiciones relativas y puntos de impacto.\n\n"

    "PRUEBAS DE ALCOHOLEMIA Y DROGAS:\n"
    "- Si se realizan pruebas, debes redactarlo conforme al Real Decreto Legislativo 6/2015.\n"
    "- Debes indicar que, al tratarse de un accidente de circulación, se informa a las partes de la realización de las pruebas reglamentarias.\n"
    "- Debes indicar los resultados en mg/l si constan.\n"
    "- No debes afirmar infracción si el resultado no supera el límite sancionador.\n"
    "- Solo debes mencionar denuncia administrativa si procede realmente.\n\n"

    "ESTILO TÉCNICO PROFESIONAL:\n"
    "- Debes utilizar redacción equivalente a informes reales de Policía Local.\n"
    "- Evita expresiones poco técnicas.\n"
    "- Usa lenguaje preciso, formal y estructurado.\n\n"

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
    "Fecha",
    "Hora del aviso",
    "Hora de personación",
    "Lugar",
    "Agentes actuantes (NIP)",
    "Indicativo policial",
    "Tipo de accidente",
    "Alertante o requirente",
    "DNI del alertante o requirente",
    "Teléfono del alertante o requirente",
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
    "Peatones (si los hubiere)",
    "DNI peatones",
    "Teléfono peatones",
    "Testigos (si los hubiere)",
    "DNI testigos",
    "Teléfono testigos",
    "Descripción de la vía",
    "Sentido de la vía según numeración (vehículo A)",
    "Condiciones meteorológicas",
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

    opciones_select = {
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

    for campo in campos:
        clave = f"{key_prefix}_{campo}"
        clave_widget = f"widget_{clave}"

        if campo.lower() == "fecha":
            valor_actual = st.session_state.get(clave, "")
            fecha_inicial = datetime.today().date()

            if isinstance(valor_actual, str) and valor_actual.strip():
                texto = valor_actual.strip()
                for formato in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
                    try:
                        fecha_inicial = datetime.strptime(texto, formato).date()
                        break
                    except ValueError:
                        pass
            elif hasattr(valor_actual, "year") and hasattr(valor_actual, "month") and hasattr(valor_actual, "day"):
                fecha_inicial = valor_actual

            valor_widget = st.date_input(
                campo,
                value=fecha_inicial,
                key=clave_widget,
                format="DD/MM/YYYY",
            )

            if isinstance(valor_widget, str):
                texto = valor_widget.strip()
                fecha_final = None
                for formato in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
                    try:
                        fecha_final = datetime.strptime(texto, formato).date()
                        break
                    except ValueError:
                        pass
                if fecha_final is None:
                    fecha_final = datetime.today().date()
            else:
                fecha_final = valor_widget

            valor = fecha_final.strftime("%d/%m/%Y")

        elif campo in opciones_select:
            valor_actual = st.session_state.get(clave, "")
            opciones = opciones_select[campo]
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
                value=st.session_state.get(clave, ""),
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

        # Guardar valor base
        st.session_state[clave_base] = valor

        # Guardar valor también en el widget para que Streamlit lo muestre
        if campo.lower() == "fecha":
            if valor:
                fecha_convertida = None
                for formato in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
                    try:
                        fecha_convertida = datetime.strptime(valor, formato).date()
                        break
                    except ValueError:
                        pass

                if fecha_convertida is not None:
                    st.session_state[clave_widget] = fecha_convertida
                else:
                    # Si viene mal la fecha, dejamos la base en texto y no forzamos el widget
                    if clave_widget in st.session_state:
                        del st.session_state[clave_widget]
            else:
                if clave_widget in st.session_state:
                    del st.session_state[clave_widget]

        else:
            st.session_state[clave_widget] = valor

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
- No escribas texto antes ni después del JSON.
- Usa exactamente como claves los nombres de los campos proporcionados.
- Si un dato no aparece claro, deja su valor como cadena vacía "".
- No inventes datos.
- Si el dictado menciona agentes, horas, lugar, daños o motivo del aviso, colócalos en el campo más adecuado.
- En los campos narrativos amplios, resume fielmente el dictado con lenguaje claro y útil para redacción policial.

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
                {"role": "system", "content": "Devuelve solo JSON válido, sin texto adicional y sin inventar datos."},
                {"role": "user", "content": prompt},
            ],
        )

        contenido = (respuesta.choices[0].message.content or "").strip()

        # Limpiar posibles fences ```json ... ```
        if contenido.startswith("```"):
            contenido = contenido.strip("`")
            contenido = contenido.replace("json", "", 1).strip()

        datos = json.loads(contenido)

        if not isinstance(datos, dict):
            return esquema

        resultado = {}
        for campo in campos_objetivo:
            valor = datos.get(campo, "")
            resultado[campo] = str(valor).strip() if valor is not None else ""

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

            st.write("DEBUG CAMPOS EXTRAÍDOS:", datos_extraidos)

            aplicar_datos_a_session_state(datos_extraidos, key_prefix)

            st.success("Campos rellenados automáticamente. Revisa y corrige lo que haga falta.")
            st.rerun()


def selector_modo_redaccion(clave: str, modulo: str) -> str:
    pagina_actual = st.session_state.get("pagina_movil", "normal")
    return st.selectbox(
        "Modo de redacción",
        ["Técnico", "Ampliado"],
        index=0,
        key=f"{clave}_{modulo}_{pagina_actual}",
    )


def cabecera_modulo(titulo: str, icono: str):
    st.markdown(
        f'''
        <div class="bloque-modulo">
            <div style="font-size:30px; font-weight:700;">{icono} {titulo}</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )


# =========================================================
# PÁGINAS DOCUMENTALES
# =========================================================

def pagina_accidente(api_key: str):
    cabecera_modulo("Informe técnico de accidente", "🚗")
    modo_redaccion = selector_modo_redaccion("modo_accidente", "accidente")
    campos_accidente = CAMPOS_ACCIDENTE

    bloque_dictado_a_campos(api_key, "accidente", "Informe técnico de accidente", campos_accidente)
    datos = render_form_fields(campos_accidente, "accidente")
    datos = ajustar_datos_accidente_por_tipo(datos)

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button("Generar informe de accidente", key="btn_generar_accidente")

    with col2:
        regenerar = st.button("Regenerar informe de accidente", key="btn_regenerar_accidente")

    if generar or regenerar:
        prompt_final = PROMPT_ACCIDENTE + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando informe..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_accidente"] = texto
        st.session_state["datos_accidente"] = datos

    if st.session_state.get("resultado_accidente"):
        mostrar_resultado(
            st.session_state["resultado_accidente"],
            st.session_state.get("datos_accidente", {}),
            "accidente"
        )


def pagina_atestado(api_key: str):
    cabecera_modulo("Atestado completo", "📄")
    modo_redaccion = selector_modo_redaccion("modo_atestado", "atestado")
    campos_atestado = CAMPOS_ATESTADO_COMPLETO

    bloque_dictado_a_campos(api_key, "atestado", "Atestado completo", campos_atestado)
    datos = render_form_fields(campos_atestado, "atestado")

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button("Generar atestado", key="btn_generar_atestado")

    with col2:
        regenerar = st.button("Regenerar atestado", key="btn_regenerar_atestado")

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
    cabecera_modulo("Informe municipal", "🏛️")
    modo_redaccion = selector_modo_redaccion("modo_municipal", "municipal")
    campos_municipal = CAMPOS_INFORME_MUNICIPAL

    bloque_dictado_a_campos(api_key, "municipal", "Informe municipal", campos_municipal)
    datos = render_form_fields(campos_municipal, "municipal")

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button("Generar informe municipal", key="btn_generar_municipal")

    with col2:
        regenerar = st.button("Regenerar informe municipal", key="btn_regenerar_municipal")

    if generar or regenerar:
        prompt_final = PROMPT_INFORME_MUNICIPAL + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando informe..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_municipal"] = texto
        st.session_state["datos_municipal"] = datos

    if st.session_state.get("resultado_municipal"):
        mostrar_resultado(st.session_state["resultado_municipal"], st.session_state.get("datos_municipal", {}), "informe_municipal")


def pagina_parte_servicio(api_key: str):
    cabecera_modulo("Parte de servicio", "📝")
    modo_redaccion = selector_modo_redaccion("modo_servicio", "parte_servicio")
    campos_servicio = CAMPOS_PARTE_SERVICIO

    bloque_dictado_a_campos(api_key, "servicio", "Parte de servicio", campos_servicio)
    datos = render_form_fields(campos_servicio, "servicio")

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button("Generar parte de servicio", key="btn_generar_servicio")

    with col2:
        regenerar = st.button("Regenerar parte de servicio", key="btn_regenerar_servicio")

    if generar or regenerar:
        prompt_final = PROMPT_PARTE_SERVICIO + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando parte..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_servicio"] = texto
        st.session_state["datos_servicio"] = datos

    if st.session_state.get("resultado_servicio"):
        mostrar_resultado(st.session_state["resultado_servicio"], st.session_state.get("datos_servicio", {}), "parte_servicio")


def pagina_anomalia(api_key: str):
    cabecera_modulo("Anomalía", "⚠️")
    modo_redaccion = selector_modo_redaccion("modo_anomalia", "anomalia")
    campos_anomalia = CAMPOS_ANOMALIA

    bloque_dictado_a_campos(api_key, "anomalia", "Anomalía", campos_anomalia)
    datos = render_form_fields(campos_anomalia, "anomalia")

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button("Generar anomalía", key="btn_generar_anomalia")

    with col2:
        regenerar = st.button("Regenerar anomalía", key="btn_regenerar_anomalia")

    if generar or regenerar:
        prompt_final = PROMPT_ANOMALIA + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)
        with st.spinner("Generando anomalía..."):
            texto = generar_texto_con_ia(api_key, prompt_final, construir_bloque_usuario(datos))
        st.session_state["resultado_anomalia"] = texto
        st.session_state["datos_anomalia"] = datos

    if st.session_state.get("resultado_anomalia"):
        mostrar_resultado(st.session_state["resultado_anomalia"], st.session_state.get("datos_anomalia", {}), "anomalia")

def pagina_informe_juzgado(api_key: str):
    cabecera_modulo("Informes al juzgado", "⚖️")
    modo_redaccion = selector_modo_redaccion("modo_juzgado", "juzgado")
    campos_juzgado = CAMPOS_INFORME_JUZGADO

    bloque_dictado_a_campos(api_key, "juzgado", "Informe al juzgado", campos_juzgado)
    datos = render_form_fields(campos_juzgado, "juzgado")

    col1, col2 = st.columns(2)

    with col1:
        generar = st.button("Generar informe al juzgado", key="btn_generar_juzgado")

    with col2:
        regenerar = st.button("Regenerar informe al juzgado", key="btn_regenerar_juzgado")

    if generar or regenerar:
        prompt_final = PROMPT_INFORME_JUZGADO + "\n\n" + obtener_instruccion_modo_redaccion(modo_redaccion)

        with st.spinner("Generando informe al juzgado..."):
            texto = generar_texto_con_ia(
                api_key,
                prompt_final,
                construir_bloque_usuario(datos)
            )

        st.session_state["resultado_juzgado"] = texto
        st.session_state["datos_juzgado"] = datos

    if st.session_state.get("resultado_juzgado"):
        mostrar_resultado(
            st.session_state["resultado_juzgado"],
            st.session_state.get("datos_juzgado", {}),
            "informe_juzgado"
        )

def selector_modulo_movil() -> str:
    st.markdown("## 🚓 Modo patrulla")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🚗\nAccidente", key="movil_accidente"):
            st.session_state["pagina_movil"] = "Accidente"

    with col2:
        if st.button("📄\nAtestado", key="movil_atestado"):
            st.session_state["pagina_movil"] = "Atestado completo"

    with col3:
        if st.button("🏛️\nMunicipal", key="movil_municipal"):
            st.session_state["pagina_movil"] = "Informe municipal"

    col4, col5, col6 = st.columns(3)

    with col4:
        if st.button("📝\nServicio", key="movil_servicio"):
            st.session_state["pagina_movil"] = "Parte de servicio"

    with col5:
        if st.button("⚠️\nAnomalía", key="movil_anomalia"):
            st.session_state["pagina_movil"] = "Anomalía"

    with col6:
        if st.button("⚖️\nJuzgado", key="movil_juzgado"):
            st.session_state["pagina_movil"] = "Informes al juzgado"

    return st.session_state.get("pagina_movil", "Inicio")


# =========================================================
# SIDEBAR / APP PRINCIPAL
# =========================================================

st.sidebar.title("Policía IA")
st.sidebar.caption("Versión web para ordenador y móvil")
modo_patrulla = st.sidebar.toggle("Modo patrulla / móvil", value=True)

if "ultimo_modo_patrulla" not in st.session_state:
    st.session_state["ultimo_modo_patrulla"] = modo_patrulla

if modo_patrulla != st.session_state["ultimo_modo_patrulla"]:
    if modo_patrulla:
        st.session_state["pagina_movil"] = "Inicio"
    st.session_state["ultimo_modo_patrulla"] = modo_patrulla

if modo_patrulla:
    st.sidebar.success("Modo patrulla activo")
    st.markdown(
        """
        <style>
        .stButton > button {
            width: 100%;
            min-height: 78px;
            font-size: 20px;
            font-weight: 700;
            border-radius: 18px;
            margin-top: 6px;
            margin-bottom: 6px;
            white-space: pre-line;
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
            min-height: 56px;
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
        </style>
        """,
        unsafe_allow_html=True,
    )

api_key = st.sidebar.text_input(
    "API key de OpenAI",
    type="password",
    help="Pega aquí tu clave. No se guarda fuera de tu sesión.",
)

modulos = [
    "Accidente",
    "Atestado completo",
    "Informe municipal",
    "Parte de servicio",
    "Anomalía",
    "Informes al juzgado",
]

# Inicialización de estado
if "pagina_movil" not in st.session_state:
    st.session_state["pagina_movil"] = "Inicio"

if "ultimo_modo_patrulla" not in st.session_state:
    st.session_state["ultimo_modo_patrulla"] = modo_patrulla

# Detectar cambio de modo
if modo_patrulla != st.session_state["ultimo_modo_patrulla"]:
    if modo_patrulla:
        st.session_state["pagina_movil"] = "Inicio"
    st.session_state["ultimo_modo_patrulla"] = modo_patrulla

# Navegación
if modo_patrulla:
    st.sidebar.markdown("### Navegación rápida")

    if st.sidebar.button("🏠 Inicio", key="inicio_movil"):
        st.session_state["pagina_movil"] = "Inicio"

    if st.session_state["pagina_movil"] == "Inicio":
        pagina = selector_modulo_movil()
    else:
        pagina = st.session_state["pagina_movil"]
else:
    pagina = st.sidebar.radio("Módulos", modulos)

st.title("🚓 Policía IA - Policía Local de Poio")
st.write("App web operativa para ordenador y móvil, con redacción policial, dictado a campos.")

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
elif pagina == "Informes al juzgado":
    pagina_informe_juzgado(api_key)
