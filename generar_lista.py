from datetime import datetime
import hashlib
import os
import requests

URL_ORIGEN = os.environ.get("URL_ORIGEN", "").strip()
PALABRA_CLAVE = os.environ.get("PALABRA_CLAVE", "").strip()
PREFIJO_HTTP = "http://127.0.0.1:6878/ace/getstream?id="
INICIALES_DIA = {
    0: "L",  # Lunes
    1: "M",  # Martes
    2: "X",  # Miércoles
    3: "J",  # Jueves
    4: "V",  # Viernes
    5: "S",  # Sábado
    6: "D",  # Domingo
}


def obtener_nombre_archivo() -> str:
    if not PALABRA_CLAVE:
        raise ValueError("Falta configurar la variable de entorno PALABRA_CLAVE.")

    ahora = datetime.now()
    inicial_dia = INICIALES_DIA[ahora.weekday()]
    ddmmyy = ahora.strftime("%d%m%y")

    texto_base = f"{PALABRA_CLAVE}{inicial_dia}{ddmmyy}"
    hash_corto = hashlib.sha256(texto_base.encode("utf-8")).hexdigest()[:12]

    return f"{hash_corto}.m3u"


def generar_m3u():
    if not URL_ORIGEN:
        raise ValueError("Falta configurar la variable de entorno URL_ORIGEN.")

    archivo_salida = obtener_nombre_archivo()

    print("Descargando lista origen...")
    response = requests.get(URL_ORIGEN, timeout=20)
    response.raise_for_status()
    contenido = response.text

    lineas = contenido.splitlines()
    salida = ["#EXTM3U\n"]
    total = 0

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()
        if linea.startswith("#EXTINF"):
            meta = linea
            enlace = ""
            j = i + 1

            while j < len(lineas):
                siguiente = lineas[j].strip()
                if siguiente and not siguiente.startswith("#"):
                    enlace = siguiente
                    i = j
                    break
                if siguiente.startswith("#EXTINF"):
                    break
                j += 1

            if enlace.startswith("acestream://"):
                hash_id = enlace.replace("acestream://", "").strip()
                enlace_http = f"{PREFIJO_HTTP}{hash_id}"
                salida.append(meta + "\n")
                salida.append(enlace_http + "\n")
                total += 1

        i += 1

    with open(archivo_salida, "w", encoding="utf-8") as f:
        f.writelines(salida)

    print(f"Listo: se generaron {total} eventos HTTP (?id=) en {archivo_salida}.")


if __name__ == "__main__":
    generar_m3u()
