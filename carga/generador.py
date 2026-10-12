"""
Generador de carga para las demostraciones.

Corre dentro de la red de Docker y no en la maquina anfitriona: lanzar decenas
de procesos curl desde Windows mide sobre todo el costo de crear procesos, no la
capacidad de los servicios.

  rafaga       N solicitudes a la vez. Cuenta las respuestas por codigo HTTP.
  rendimiento  N solicitudes con concurrencia C. Mide solicitudes por segundo.
               Con --segundos S manda sin parar durante S segundos.
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ETIQUETAS = {
    200: "admitido",
    409: "rechazado por falta de cupo",
    422: "rechazado por la validacion del paquete",
    429: "rechazado por throttling",
    503: "servicio no disponible",
    0: "sin respuesta",
}


def instancia_de(texto):
    """Saca de la respuesta el nombre de la replica que la atendio."""
    try:
        valor = json.loads(texto).get("instancia", "")
        return valor.get("ingreso", "") if isinstance(valor, dict) else valor
    except Exception:
        return ""


def solicitar(url, cuerpo, timeout):
    datos = json.dumps(cuerpo).encode() if cuerpo else None
    cabeceras = {"Content-Type": "application/json"} if datos else {}
    pedido = urllib.request.Request(url, data=datos, headers=cabeceras)

    inicio = time.perf_counter()
    try:
        respuesta = urllib.request.urlopen(pedido, timeout=timeout)
        codigo, texto = respuesta.status, respuesta.read().decode()
    except urllib.error.HTTPError as error:
        codigo, texto = error.code, error.read().decode()
    except Exception:
        codigo, texto = 0, ""

    return codigo, (time.perf_counter() - inicio) * 1000, instancia_de(texto), texto


def correr(args, concurrencia):
    cuerpo = json.loads(args.cuerpo) if args.cuerpo else None
    with ThreadPoolExecutor(max_workers=concurrencia) as pool:
        inicio = time.perf_counter()
        if args.segundos:
            # Cada hilo manda solicitudes una tras otra hasta que se acaba el tiempo.
            fin = inicio + args.segundos

            def hasta_el_final(_):
                propios = []
                while time.perf_counter() < fin:
                    propios.append(solicitar(args.url, cuerpo, args.timeout))
                return propios

            resultados = [r for lote in pool.map(hasta_el_final, range(concurrencia))
                          for r in lote]
        else:
            resultados = list(pool.map(
                lambda _: solicitar(args.url, cuerpo, args.timeout), range(args.n)))
    return resultados, time.perf_counter() - inicio


def mostrar_ejemplos(resultados):
    """Una respuesta de ejemplo por cada codigo distinto."""
    vistos = {}
    for codigo, _, _, texto in resultados:
        vistos.setdefault(codigo, texto)
    for codigo, texto in sorted(vistos.items()):
        if texto:
            print(f"      ejemplo HTTP {codigo}: {texto[:150]}")


def rafaga(args):
    resultados, segundos = correr(args, args.n)
    print(f"  {args.n} solicitudes simultaneas en {segundos:.2f} s")
    for codigo, cantidad in sorted(Counter(c for c, _, _, _ in resultados).items()):
        print(f"      HTTP {codigo}  x{cantidad:<4} {ETIQUETAS.get(codigo, '')}")
    if args.ejemplos:
        mostrar_ejemplos(resultados)


def rendimiento(args):
    resultados, segundos = correr(args, args.c)
    latencias = [ms for _, ms, _, _ in resultados]
    codigos = Counter(c for c, _, _, _ in resultados)
    instancias = Counter(i for _, _, i, _ in resultados if i)

    print(f"  solicitudes     : {len(resultados)} (concurrencia {args.c})")
    print(f"  tiempo total    : {segundos:.2f} s")
    print(f"  throughput      : {len(resultados) / segundos:.1f} solicitudes/segundo")
    print(f"  latencia media  : {sum(latencias) / len(latencias):.1f} ms")
    print(f"  codigos         : {dict(sorted(codigos.items()))}")
    for instancia, cantidad in sorted(instancias.items()):
        print(f"      {instancia}  ->  {cantidad} solicitudes")


analizador = argparse.ArgumentParser(description="Generador de carga")
analizador.add_argument("modo", choices=["rafaga", "rendimiento"])
analizador.add_argument("--url", required=True)
analizador.add_argument("--cuerpo", help="cuerpo JSON de la solicitud")
analizador.add_argument("--n", type=int, default=50, help="cantidad de solicitudes")
analizador.add_argument("--c", type=int, default=30, help="concurrencia")
analizador.add_argument("--timeout", type=float, default=30)
analizador.add_argument("--segundos", type=float, help="mandar durante S segundos en vez de N solicitudes")
analizador.add_argument("--ejemplos", action="store_true", help="mostrar una respuesta por codigo")

args = analizador.parse_args()
{"rafaga": rafaga, "rendimiento": rendimiento}[args.modo](args)
