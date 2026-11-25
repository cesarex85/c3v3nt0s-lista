from datetime import datetime
import hashlib
import os
import re
from urllib.parse import urljoin
import requests

URL_ORIGEN = os.environ.get("URL_ORIGEN", "").strip()
URL_PETICIONES = os.environ.get("URL_PETICIONES", "").strip()
PALABRA_CLAVE = os.environ.get("PALABRA_CLAVE", "").strip()

PREFIJO_HTTP = "http://127.0.0.1:6878/ace/getstream?id="
GRUPO_EVENTOS = "EVENTOS_HOY"

INICIALES_DIA = {
    0: "L",  # Lunes
    1: "M",  # Martes
    2: "X",  # Miércoles
    3: "J",  # Jueves
    4: "V",  # Viernes
    5: "S",  # Sábado
    6: "D",  # Domingo
}

HASH_REGEX = re.compile(r"^[a-fA-F0-9]{40}$")
URL_TVG_REGEX = re.compile(r'url-tvg="([^"]+)"')
EVENTO_KEYWORD_REGEX = re.compile(r"\b(evento|eventos|eventual)\b", re.IGNORECASE)


def obtener_nombre_archivo() -> str:
    if not PALABRA_CLAVE:
        raise ValueError("Falta configurar la variable de entorno PALABRA_CLAVE.")

    ahora = datetime.now()
    inicial_dia = INICIALES_DIA[ahora.weekday()]
    ddmmyy = ahora.strftime("%d%m%y")

    texto_base = f"{PALABRA_CLAVE}{inicial_dia}{ddmmyy}"
    hash_corto = hashlib.sha256(texto_base.encode("utf-8")).hexdigest()[:12]

    return f"{hash_corto}.m3u"


def normalizar_a_http_ace(enlace: str) -> str | None:
    enlace = enlace.strip()
    if not enlace:
        return None

    if enlace.startswith("acestream://"):
        hash_id = (
            enlace.replace("acestream://", "", 1)
            .split("?")[0]
            .split("#")[0]
            .strip()
        )
        if HASH_REGEX.match(hash_id):
            return f"{PREFIJO_HTTP}{hash_id}"
        return None

    if enlace.startswith(PREFIJO_HTTP):
        hash_id = (
            enlace.replace(PREFIJO_HTTP, "", 1)
            .split("&")[0]
            .split("?")[0]
            .strip()
        )
        if HASH_REGEX.match(hash_id):
            return f"{PREFIJO_HTTP}{hash_id}"
        return None

    return None


def es_url_m3u(enlace: str) -> bool:
    limpio = enlace.strip().split("?")[0].lower()
    return limpio.endswith(".m3u") or limpio.endswith(".m3u8")


def extraer_url_tvg(contenido: str) -> list[str]:
    urls: list[str] = []
    for linea in contenido.splitlines():
        linea_s = linea.strip()
        if linea_s.startswith("#EXTM3U"):
            match = URL_TVG_REGEX.search(linea_s)
            if match:
                for u in match.group(1).split(","):
                    u_limpia = u.strip()
                    if u_limpia and u_limpia not in urls:
                        urls.append(u_limpia)
    return urls


def asignar_grupo_evento(linea_extinf: str, forzar_evento: bool = False) -> str:
    if not forzar_evento and not EVENTO_KEYWORD_REGEX.search(linea_extinf):
        return linea_extinf

    if 'group-title="' in linea_extinf:
        return re.sub(
            r'group-title="[^"]*"',
            f'group-title="{GRUPO_EVENTOS}"',
            linea_extinf,
            count=1,
        )

    if "," in linea_extinf:
        metadatos, nombre = linea_extinf.split(",", 1)
        return f'{metadatos} group-title="{GRUPO_EVENTOS}",{nombre}'

    return f'{linea_extinf} group-title="{GRUPO_EVENTOS}"'


def extraer_elementos_m3u(
    contenido: str,
    url_base: str,
    visitadas: set[str],
    epg_acumulado: list[str],
    forzar_evento: bool = False,
    profundidad: int = 0,
    max_profundidad: int = 2,
) -> list[tuple[str, str]]:
    """
    Devuelve una lista ordenada de elementos:
    - ("GRP", "#EXTGRP: ...")
    - ("CANAL", "#EXTINF:...\nhttp://127.0.0.1:6878/ace/getstream?id=...")
    """
    for u_epg in extraer_url_tvg(contenido):
        if u_epg not in epg_acumulado:
            epg_acumulado.append(u_epg)

    elementos: list[tuple[str, str]] = []
    lineas = contenido.splitlines()

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()

        if not linea:
            i += 1
            continue

        if linea.startswith("#EXTGRP"):
            if not forzar_evento:
                elementos.append(("GRP", linea))
            i += 1
            continue

        if linea.startswith("#EXTINF"):
            meta = linea
            objetivo = ""
            j = i + 1

            while j < len(lineas):
                siguiente = lineas[j].strip()
                if not siguiente:
                    j += 1
                    continue
                if siguiente.startswith("#EXTINF") or siguiente.startswith("#EXTGRP"):
                    break
                if not siguiente.startswith("#"):
                    objetivo = siguiente
                    i = j
                    break
                j += 1

            if objetivo:
                ace_http = normalizar_a_http_ace(objetivo)
                if ace_http:
                    meta_final = asignar_grupo_evento(meta, forzar_evento=forzar_evento)
                    elementos.append(("CANAL", f"{meta_final}\n{ace_http}"))
                elif (
                    objetivo.startswith(("http://", "https://"))
                    and es_url_m3u(objetivo)
                    and profundidad < max_profundidad
                ):
                    url_sublista = urljoin(url_base, objetivo)
                    if url_sublista not in visitadas:
                        visitadas.add(url_sublista)
                        print(f"Descargando sublista M3U: {url_sublista}")
                        try:
                            resp_sub = requests.get(url_sublista, timeout=25)
                            resp_sub.raise_for_status()
                            sub_elems = extraer_elementos_m3u(
                                resp_sub.text,
                                url_sublista,
                                visitadas,
                                epg_acumulado,
                                forzar_evento=forzar_evento,
                                profundidad=profundidad + 1,
                                max_profundidad=max_profundidad,
                            )
                            elementos.extend(sub_elems)
                        except Exception as exc:
                            print(f"Aviso: no se pudo cargar {url_sublista} ({exc})")

        i += 1

    return elementos


def generar_m3u():
    fuentes: list[tuple[str, bool]] = []
    if URL_PETICIONES:
        fuentes.append((URL_PETICIONES, False))
    if URL_ORIGEN and URL_ORIGEN != URL_PETICIONES:
        fuentes.append((URL_ORIGEN, True))

    if not fuentes:
        raise ValueError(
            "Falta configurar al menos una variable de entorno: URL_PETICIONES o URL_ORIGEN."
        )

    archivo_salida = obtener_nombre_archivo()
    visitadas: set[str] = set()
    epg_acumulado: list[str] = []
    elementos: list[tuple[str, str]] = []

    for url_fuente, es_fuente_eventos in fuentes:
        if url_fuente in visitadas:
            continue
        visitadas.add(url_fuente)
        print(f"Descargando fuente: {url_fuente}")
        try:
            response = requests.get(url_fuente, timeout=25)
            response.raise_for_status()
            elementos.extend(
                extraer_elementos_m3u(
                    response.text,
                    url_fuente,
                    visitadas,
                    epg_acumulado,
                    forzar_evento=es_fuente_eventos,
                )
            )
        except Exception as exc:
            if len(fuentes) == 1:
                raise
            print(f"Aviso: no se pudo cargar fuente {url_fuente} ({exc})")

    if epg_acumulado:
        cabecera = f'#EXTM3U url-tvg="{",".join(epg_acumulado)}"\n'
    else:
        cabecera = "#EXTM3U\n"

    salida = [cabecera]
    vistos_canales: set[str] = set()
    vistos_grupos: set[str] = set()
    total = 0

    for tipo, contenido_elem in elementos:
        if tipo == "GRP":
            if contenido_elem not in vistos_grupos:
                vistos_grupos.add(contenido_elem)
                salida.append(contenido_elem + "\n")
        elif tipo == "CANAL":
            if contenido_elem in vistos_canales:
                continue
            vistos_canales.add(contenido_elem)
            salida.append(contenido_elem + "\n")
            total += 1

    with open(archivo_salida, "w", encoding="utf-8") as f:
        f.writelines(salida)

    print(
        f"Listo: se generaron {total} canales HTTP (?id=) y {len(epg_acumulado)} fuentes EPG en {archivo_salida}."
    )


if __name__ == "__main__":
    generar_m3u()
