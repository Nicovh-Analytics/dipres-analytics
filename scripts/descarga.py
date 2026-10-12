"""
descarga.py — Funciones compartidas por los scripts de descarga (02, 03)
========================================================================
  buscar_ckan          búsqueda paginada en datos.gob.cl
  descargar_archivo    descarga atómica: escribe en <archivo>.part, valida
                       y recién entonces renombra. Un archivo final nunca
                       queda a medias.
  tamano_remoto        Content-Length vía HEAD, para auditar archivos
                       descargados antes de existir el .part
  LogDescarga          log JSON resumible, escrito de forma atómica
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import CKAN, HTTP

TIPOS_NO_CSV = ("text/html", "application/json")
TAMANO_MINIMO = 100  # bytes; menos que esto no es un CSV con datos


def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update(HTTP["headers"])
    return s


SESION = _sesion()


# =====================================================
# CKAN
# =====================================================
def buscar_ckan(queries: list[str], filtro=None) -> list[dict]:
    """Datasets únicos (por id) de todas las queries, paginando.
    `filtro(ds) -> bool` descarta los que no interesan."""
    encontrados = {}
    for q in queries:
        offset = 0
        while True:
            try:
                r = SESION.get(f"{CKAN['base_url']}/package_search",
                               params={"q": q, "rows": CKAN["rows_por_pagina"],
                                       "start": offset},
                               timeout=30)
                r.raise_for_status()
                data = r.json()["result"]
            except Exception as e:
                print(f"   ⚠ Error consultando '{q}' (offset={offset}): {e}")
                break
            res = data["results"]
            if not res:
                break
            for ds in res:
                if filtro is None or filtro(ds):
                    encontrados[ds["id"]] = ds
            offset += len(res)
            if offset >= data["count"]:
                break
    return list(encontrados.values())


# =====================================================
# Descarga
# =====================================================
def _esperado(resp: requests.Response) -> int | None:
    """Content-Length utilizable. Con Content-Encoding (gzip) el largo
    informado es el comprimido y no sirve para comparar."""
    cl = resp.headers.get("Content-Length")
    if cl is None or resp.headers.get("Content-Encoding"):
        return None
    return int(cl)


def descargar_archivo(url: str, destino: Path) -> tuple[bool, str | None]:
    """Descarga atómica con reintentos. (ok, motivo_error)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".part")
    motivo = "reintentos agotados"

    for intento in range(1, HTTP["max_reintentos"] + 1):
        try:
            with SESION.get(url, timeout=HTTP["timeout"], stream=True) as r:
                r.raise_for_status()
                ct = r.headers.get("content-type", "").lower()
                if any(t in ct for t in TIPOS_NO_CSV):
                    return False, f"Content-Type inesperado: {ct}"
                esperado = _esperado(r)
                escritos = 0
                with open(parcial, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
                            escritos += len(chunk)

            if esperado is not None and escritos != esperado:
                motivo = f"incompleto: {escritos:,} de {esperado:,} bytes"
            elif escritos < TAMANO_MINIMO:
                motivo = f"archivo muy pequeño ({escritos} bytes)"
            else:
                os.replace(parcial, destino)   # atómico en el mismo disco
                return True, None
        except Exception as e:
            motivo = str(e)

        parcial.unlink(missing_ok=True)
        if intento < HTTP["max_reintentos"]:
            time.sleep(2 ** intento)

    return False, motivo


def tamano_remoto(url: str) -> int | None:
    """Content-Length informado por el servidor (None si no lo da)."""
    try:
        r = SESION.head(url, timeout=30, allow_redirects=True)
        r.raise_for_status()
        return _esperado(r)
    except Exception:
        return None


# =====================================================
# Log
# =====================================================
class LogDescarga:
    """{ruta: {ok, motivo_error, url, dataset, bytes, timestamp}}"""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.datos = (json.loads(ruta.read_text(encoding="utf-8"))
                      if ruta.exists() else {})

    def registrar(self, destino: Path, ok: bool, motivo, url: str,
                  dataset: str) -> None:
        self.datos[str(destino)] = {
            "ok": ok, "motivo_error": motivo, "url": url, "dataset": dataset,
            "bytes": destino.stat().st_size if ok else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.guardar()

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, self.ruta)


# =====================================================
# Orquestación común
# =====================================================
def ejecutar_tareas(tareas: list[tuple[Path, str, str]], log: LogDescarga,
                    base: Path, sobrescribir=False,
                    revisar_tamano=False) -> dict[str, int]:
    """tareas = [(destino, url, titulo_dataset)].

    Se salta un archivo si ya existe, salvo `sobrescribir`. Con
    `revisar_tamano` se compara cada archivo existente con el
    Content-Length remoto y se vuelve a bajar si no coincide (archivos
    cortados de antes del .part)."""
    n = {"descargados": 0, "saltados": 0, "errores": 0, "reparados": 0}
    total = len(tareas)
    print(f"\n📥 {total} archivos a procesar\n")

    for i, (destino, url, titulo) in enumerate(tareas, start=1):
        rel = destino.relative_to(base)
        if destino.exists() and not sobrescribir:
            if not revisar_tamano:
                n["saltados"] += 1
                continue
            remoto = tamano_remoto(url)
            local = destino.stat().st_size
            if remoto is None or remoto == local:
                n["saltados"] += 1
                continue
            print(f"[{i}/{total}] {rel}  ⚠ local {local:,} ≠ remoto "
                  f"{remoto:,} bytes: se vuelve a bajar")
            n["reparados"] += 1
        else:
            print(f"[{i}/{total}] {rel}")

        ok, motivo = descargar_archivo(url, destino)
        if ok:
            n["descargados"] += 1
            print(f"   ✅ {destino.stat().st_size:,} bytes")
        else:
            n["errores"] += 1
            print(f"   ❌ {motivo}")
        log.registrar(destino, ok, motivo, url, titulo)
        time.sleep(HTTP["pausa_entre_descargas"])

    return n


def imprimir_conteo(n: dict[str, int]) -> None:
    print(f"  ✅ Descargados:  {n['descargados']}"
          + (f"  (de ellos {n['reparados']} reparados)" if n["reparados"] else ""))
    print(f"  ⏭  Ya existían: {n['saltados']}")
    print(f"  ❌ Errores:     {n['errores']}")