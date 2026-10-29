"""
hallazgos.py — Registro estructurado de hallazgos
==================================================
Módulo compartido por profiler, validación y análisis.

En vez de imprimir a consola y perder el resultado, cada check
registra un hallazgo con estructura. Al final se emiten:

  - reporte_<nombre>.md  → legible, agrupado por severidad
  - hallazgos_<nombre>.csv → tabular, para cruzar entre corridas
  - _controles/<script>__<nombre>.json → resumen que lee run.py para
    informar al final de la corrida qué scripts tuvieron errores

El script se identifica por la variable de entorno DIPRES_SCRIPT, que
pone run.py; si se corre a mano, por el nombre del archivo ejecutado.

Uso:
    from dipres.hallazgos import Registro

    reg = Registro("validacion")
    reg.ok("cobertura", "2024: 12 meses completos", nivel="partida")
    reg.warn("encoding", "cp1252 detectado", nivel="ley", archivos=40)
    reg.error("duplicados", "46 filas duplicadas", nivel="programa", n=46)
    reg.emitir()

Eco a consola: por defecto, error y warn se imprimen al registrarse. Un
script que ya imprime sus propios mensajes usa Registro(..., eco=False), o
eco=False en una llamada puntual, para no duplicarlos.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

SEVERIDADES = ["error", "warn", "info", "ok"]
ICONOS = {"error": "❌", "warn": "⚠", "info": "ℹ", "ok": "✓"}


class Registro:
    def __init__(self, nombre: str, salida_dir: Path | str = ".",
                 versionar: bool = False, eco: bool = True):
        self.nombre = nombre
        self.eco = eco
        if versionar:
            self.nombre = f"{nombre}_{datetime.now():%Y%m%d_%H%M}"
        self.salida_dir = Path(salida_dir)
        self.salida_dir.mkdir(parents=True, exist_ok=True)
        self.items: list[dict] = []
        self.inicio = datetime.now()

    # ── Registro ──────────────────────────────────────
    def _add(self, sev, check, mensaje, **meta):
        eco = meta.pop("eco", self.eco)
        self.items.append({
            "severidad": sev,
            "check": check,
            "mensaje": mensaje,
            **meta,
        })
        # Eco a consola solo para error y warn; ok e info quedan en el archivo
        if eco and sev in ("error", "warn"):
            ctx = meta.get("nivel") or meta.get("archivo") or ""
            ctx = f"[{ctx}] " if ctx else ""
            print(f"  {ICONOS[sev]} {ctx}{mensaje}")

    def ok(self, check, mensaje, **meta):
        self._add("ok", check, mensaje, **meta)

    def info(self, check, mensaje, **meta):
        self._add("info", check, mensaje, **meta)

    def warn(self, check, mensaje, **meta):
        self._add("warn", check, mensaje, **meta)

    def error(self, check, mensaje, **meta):
        self._add("error", check, mensaje, **meta)

    # ── Agrupación ────────────────────────────────────
    def agrupar(self, check: str, clave: str = "patron"):
        """
        Colapsa hallazgos repetidos del mismo check que comparten
        el valor de `clave`. Devuelve lista de (patron, n, ejemplos).
        Útil cuando 50 archivos tienen el mismo problema.
        """
        grupos = defaultdict(list)
        for it in self.items:
            if it["check"] == check and clave in it:
                grupos[it[clave]].append(it)
        return [
            (k, len(v), [x.get("archivo", "") for x in v[:3]])
            for k, v in sorted(grupos.items(), key=lambda kv: -len(kv[1]))
        ]

    # ── Conteos ───────────────────────────────────────
    def resumen(self) -> dict:
        c = defaultdict(int)
        for it in self.items:
            c[it["severidad"]] += 1
        return dict(c)

    # ── Salida ────────────────────────────────────────
    def emitir(self, verbose_ok: bool = False):
        self._emitir_md(verbose_ok)
        self._emitir_csv()
        self._emitir_resumen()
        r = self.resumen()
        print(f"\n  {ICONOS['ok']} {r.get('ok',0)}  "
              f"{ICONOS['info']} {r.get('info',0)}  "
              f"{ICONOS['warn']} {r.get('warn',0)}  "
              f"{ICONOS['error']} {r.get('error',0)}")
        print(f"  Reporte: {self.salida_dir / f'reporte_{self.nombre}.md'}")

    def _emitir_md(self, verbose_ok: bool):
        ruta = self.salida_dir / f"reporte_{self.nombre}.md"
        r = self.resumen()
        dur = (datetime.now() - self.inicio).total_seconds()

        L = []
        L.append(f"# Reporte de {self.nombre}")
        L.append("")
        L.append(f"Generado: {self.inicio:%Y-%m-%d %H:%M} · {dur:.1f}s")
        L.append("")
        L.append("| Severidad | Cantidad |")
        L.append("|---|---:|")
        for s in SEVERIDADES:
            L.append(f"| {ICONOS[s]} {s} | {r.get(s, 0)} |")
        L.append("")

        # Errores y advertencias primero, agrupados por check
        for sev in ["error", "warn", "info"]:
            items = [i for i in self.items if i["severidad"] == sev]
            if not items:
                continue

            L.append(f"## {ICONOS[sev]} {sev.upper()} ({len(items)})")
            L.append("")

            por_check = defaultdict(list)
            for i in items:
                por_check[i["check"]].append(i)

            for check, lst in por_check.items():
                L.append(f"### {check} ({len(lst)})")
                L.append("")

                # Si hay muchos del mismo check, colapsar por patrón
                patrones = defaultdict(list)
                for i in lst:
                    patrones[i.get("patron", i["mensaje"])].append(i)

                if len(patrones) < len(lst):
                    L.append("| Patrón | Casos | Ejemplos |")
                    L.append("|---|---:|---|")
                    for pat, ocur in sorted(patrones.items(), key=lambda kv: -len(kv[1])):
                        ejs = ", ".join(_ejemplo(o) for o in ocur[:3])
                        extra = f" (+{len(ocur)-3})" if len(ocur) > 3 else ""
                        L.append(f"| {pat} | {len(ocur)} | {ejs}{extra} |")
                else:
                    for i in lst:
                        ctx = i.get("nivel") or i.get("archivo") or ""
                        ctx = f"`{ctx}` — " if ctx else ""
                        L.append(f"- {ctx}{i['mensaje']}")
                L.append("")

        # OK solo si se pide
        if verbose_ok:
            oks = [i for i in self.items if i["severidad"] == "ok"]
            L.append(f"## {ICONOS['ok']} OK ({len(oks)})")
            L.append("")
            por_check = defaultdict(list)
            for i in oks:
                por_check[i["check"]].append(i)
            for check, lst in por_check.items():
                L.append(f"- **{check}**: {len(lst)} checks pasados")
            L.append("")

        ruta.write_text("\n".join(L), encoding="utf-8")

    def _emitir_csv(self):
        ruta = self.salida_dir / f"hallazgos_{self.nombre}.csv"
        pd.DataFrame(self.items).to_csv(ruta, index=False, encoding="utf-8-sig")

    def _emitir_resumen(self):
        """Resumen para run.py: conteos y el detalle de errores y avisos."""
        script = os.environ.get("DIPRES_SCRIPT") or Path(sys.argv[0]).stem
        carpeta = self.salida_dir / "_controles"
        carpeta.mkdir(parents=True, exist_ok=True)
        detalle = lambda sev: [f"[{i['check']}] {i['mensaje']}"
                               for i in self.items if i["severidad"] == sev]
        datos = {"script": script, "registro": self.nombre,
                 "fecha": f"{datetime.now():%Y-%m-%d %H:%M}",
                 "resumen": self.resumen(),
                 "errores": detalle("error")[:50],
                 "avisos": detalle("warn")[:50]}
        (carpeta / f"{script}__{self.nombre}.json").write_text(
            json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def _ejemplo(item: dict) -> str:
    """Contexto corto de un hallazgo para la columna de ejemplos."""
    for k in ("archivo", "nivel", "anio"):
        if item.get(k) not in (None, ""):
            return str(item[k])
    m = str(item.get("mensaje", ""))
    return m if len(m) <= 40 else m[:37] + "…"