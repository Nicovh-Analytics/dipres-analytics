"""
mapa_flujo.py — Mapa del flujo de datos del pipeline
====================================================
Lee el código de pipeline/ y dipres/ (sin ejecutarlo) y reconstruye qué
archivo lee y qué archivo escribe cada script. Con eso arma el grafo de
dependencias entre scripts y revisa cuatro cosas:

  1. Entradas sin productor: archivos que se leen y ningún script escribe
     (fuentes externas descargadas a mano, o salidas de scripts borrados).
  2. Salidas sin consumidor: archivos que se escriben y ningún script lee
     (pueden ser entregables finales, respaldos o código muerto).
  3. Orden: un script que lee la salida de otro que run.py ejecuta después.
     Con una corrida desde cero, leería un archivo viejo o inexistente.
  4. Ciclos: A necesita a B y B necesita a A.

La detección es estática y aproximada: reconoce nombres de archivo escritos
en el código (también en f-strings, como patrón con *) y los que pasan por
una constante del módulo. Un nombre armado en tiempo de ejecución de otra
forma no se ve; esos casos se listan como "lecturas no resueltas".

Salida:
  consola             informe de dependencias y alertas
  docs/flujo.md       diagrama Mermaid (GitHub lo dibuja) + tablas

Uso (desde la raíz del repo):
    python herramientas/mapa_flujo.py
"""

import ast
import fnmatch
import re
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PIPELINE = RAIZ / "pipeline"
ETAPAS = ["extraccion", "consolidacion", "validacion", "analisis", "informe"]
SALIDA = RAIZ / "docs" / "flujo.md"

EXT = (".csv", ".parquet", ".json", ".md", ".pdf", ".txt", ".png", ".html",
       ".xlsx")
LEE = {"read_csv", "read_parquet", "read_json", "read_excel", "leer",
       "leer_csv_robusto", "read_text", "glob", "rglob", "open"}
ESCRIBE = {"to_csv", "to_parquet", "to_json", "to_excel", "write_text",
           "write_html", "write_image", "write_bytes"}
# Funciones propias que agregan la extensión al nombre (viz.leer)
SIN_EXTENSION = {"leer": ".csv"}


def literales(nodo, constantes: dict) -> list[str]:
    """Strings (o patrones de f-string) dentro de una expresión."""
    out = []
    for n in ast.walk(nodo):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
        elif isinstance(n, ast.JoinedStr):
            out.append("".join(v.value if isinstance(v, ast.Constant) else "*"
                               for v in n.values))
        elif isinstance(n, ast.Name) and n.id in constantes:
            out.extend(constantes[n.id])
    return out


def es_archivo(s: str) -> bool:
    """Nombre de archivo con extensión conocida y al menos 3 caracteres
    propios (descarta patrones genéricos como "*.csv" o ".json")."""
    if not s.lower().endswith(EXT):
        return False
    base = re.sub(r"\.\w+$", "", Path(s).name)
    return len(re.sub(r"[*_\W]", "", base)) >= 3


def nombre_func(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")


def analizar(ruta: Path) -> tuple[set, set, list]:
    arbol = ast.parse(ruta.read_text(encoding="utf-8", errors="replace"))
    # Constantes del módulo: NOMBRE = <expresión con un nombre de archivo>
    constantes = {}
    for n in arbol.body:
        if isinstance(n, ast.Assign):
            vals = [v for v in literales(n.value, {}) if es_archivo(v)]
            for t in n.targets:
                if isinstance(t, ast.Name) and vals:
                    constantes[t.id] = vals
    lee, escribe, sin_resolver = set(), set(), []
    for n in ast.walk(arbol):
        if not isinstance(n, ast.Call):
            continue
        fn = nombre_func(n)
        if fn not in LEE | ESCRIBE:
            continue
        # Para métodos (df.to_csv(x), ruta.write_text()) el archivo puede
        # estar en el objeto o en los argumentos
        partes = list(n.args) + [k.value for k in n.keywords]
        if isinstance(n.func, ast.Attribute):
            partes.append(n.func.value)
        vals = []
        for p in partes:
            for v in literales(p, constantes):
                if es_archivo(v):
                    vals.append(Path(v).name)
                elif fn in SIN_EXTENSION and n.args and p is n.args[0] \
                        and re.fullmatch(r"[\w*]+", v):
                    vals.append(v + SIN_EXTENSION[fn])
        if not vals:
            if fn in {"read_csv", "read_parquet", "leer"}:
                sin_resolver.append(f"línea {n.lineno}: {fn}(...)")
            continue
        (escribe if fn in ESCRIBE else lee).update(vals)
    return lee, escribe, sin_resolver


def orden(ruta: Path) -> tuple[int, str]:
    for i, e in enumerate(ETAPAS):
        if ruta.parent.name.endswith(e):
            return i, ruta.name
    return len(ETAPAS), ruta.name


def coincide(archivo: str, patron: str) -> bool:
    return archivo == patron or fnmatch.fnmatch(archivo, patron) \
        or fnmatch.fnmatch(patron, archivo)


def main() -> None:
    scripts = sorted((p for p in PIPELINE.rglob("*.py")
                      if re.match(r"\d", p.name)), key=orden)
    modulos = sorted((RAIZ / "dipres").glob("*.py"))
    info = {}
    for p in scripts + modulos:
        lee, esc, sr = analizar(p)
        info[p] = {"lee": lee, "escribe": esc, "sin_resolver": sr}

    nombre = {p: (p.stem if p in scripts else f"dipres.{p.stem}") for p in info}
    productores = defaultdict(set)
    for p, d in info.items():
        for a in d["escribe"]:
            productores[a].add(p)

    def quien_produce(a: str) -> set:
        return {q for pat, qs in productores.items() if coincide(a, pat)
                for q in qs}

    aristas = defaultdict(set)             # (de, a) → archivos
    externos, fuera_de_orden = defaultdict(set), []
    for p, d in info.items():
        for a in d["lee"]:
            prods = quien_produce(a) - {p}
            if not prods:
                externos[a].add(nombre[p])
            for q in prods:
                aristas[(q, p)].add(a)
                if p in scripts and q in scripts and orden(q) > orden(p):
                    fuera_de_orden.append((nombre[p], nombre[q], a))

    consumidos = {a for d in info.values() for a in d["lee"]}
    sin_uso = sorted(a for a in productores
                     if not any(coincide(c, a) for c in consumidos))

    # Ciclos (DFS sobre el grafo de scripts)
    grafo = defaultdict(set)
    for (q, p) in aristas:
        grafo[q].add(p)
    ciclos, color = [], {}

    def dfs(u, pila):
        color[u] = 1
        for v in grafo[u]:
            if color.get(v) == 1:
                ciclos.append([nombre[x] for x in pila[pila.index(v):]] + [nombre[v]])
            elif not color.get(v):
                dfs(v, pila + [v])
        color[u] = 2
    for u in list(grafo):
        if not color.get(u):
            dfs(u, [u])

    # ---------- consola ----------
    print("=" * 78)
    print("  MAPA DEL FLUJO DE DATOS")
    print("=" * 78)
    for p in scripts:
        d = info[p]
        print(f"\n  {p.parent.name}/{p.name}")
        print(f"    lee:     {', '.join(sorted(d['lee'])) or '—'}")
        print(f"    escribe: {', '.join(sorted(d['escribe'])) or '—'}")
        if d["sin_resolver"]:
            print(f"    no resuelto: {'; '.join(d['sin_resolver'])}")
    print("\n  1. Entradas sin productor (externas o faltantes)")
    for a, quienes in sorted(externos.items()):
        print(f"    · {a:42} ← {', '.join(sorted(quienes))}")
    print("\n  2. Salidas sin consumidor (entregables, respaldos o sin uso)")
    for a in sin_uso:
        print(f"    · {a:42} → {', '.join(sorted(nombre[q] for q in productores[a]))}")
    print("\n  3. Orden: lee la salida de un script que corre después")
    for p, q, a in fuera_de_orden or [("", "", "")]:
        print(f"    ⚠ {p} lee {a} de {q}" if p else "    ✓ ninguno")
    print("\n  4. Ciclos")
    for c in ciclos or [[]]:
        print(f"    ⚠ {' → '.join(c)}" if c else "    ✓ ninguno")

    # ---------- docs/flujo.md ----------
    ls = ["# Flujo de datos del pipeline", "",
          "> Generado por `herramientas/mapa_flujo.py` desde el código. "
          "No editar a mano.", "", "```mermaid", "flowchart LR"]
    ident = {p: "s_" + re.sub(r"\W", "_", nombre[p]) for p in info}
    for e in ETAPAS:
        miembros = [p for p in scripts if p.parent.name.endswith(e)]
        if miembros:
            ls.append(f"  subgraph {e}")
            ls += [f"    {ident[p]}[{p.stem}]" for p in miembros]
            ls.append("  end")
    usados = {q for q, _ in aristas} | {p for _, p in aristas}
    for p in modulos:
        if p in usados:
            ls.append(f"  {ident[p]}([{nombre[p]}])")
    for (q, p), archivos in sorted(aristas.items(), key=lambda x: orden(x[0][0])):
        estilo = "-.->" if (p in scripts and q in scripts
                            and orden(q) > orden(p)) else "-->"
        ls.append(f"  {ident[q]} {estilo} {ident[p]}")
    ls += ["```", "", "Flecha punteada: el script lee la salida de otro que "
           "corre después.", "", "## Entradas externas", "",
           "| Archivo | Lo usa |", "|---|---|"]
    ls += [f"| `{a}` | {', '.join(sorted(q))} |" for a, q in sorted(externos.items())]
    ls += ["", "## Archivos por script", "", "| Script | Lee | Escribe |",
           "|---|---|---|"]
    ls += [f"| `{p.parent.name}/{p.name}` | {', '.join(sorted(info[p]['lee'])) or '—'} "
           f"| {', '.join(sorted(info[p]['escribe'])) or '—'} |" for p in scripts]
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("\n".join(ls) + "\n", encoding="utf-8")
    print(f"\n  Diagrama: {SALIDA}")


if __name__ == "__main__":
    main()
