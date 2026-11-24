import os
import requests

URL_ORIGEN = os.environ.get("URL_ORIGEN", "").strip()
ARCHIVO_SALIDA = "c3v3nt0s.m3u"
PREFIJO_HTTP = "http://127.0.0.1:6878/ace/getstream?id="


def generar_m3u():
    if not URL_ORIGEN:
        raise ValueError("Falta configurar la variable de entorno URL_ORIGEN.")

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

    with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
        f.writelines(salida)

    print(f"Listo: se generaron {total} eventos HTTP (?id=) en {ARCHIVO_SALIDA}.")


if __name__ == "__main__":
    generar_m3u()
