"""
Generador de carga para las demostraciones.

Corre dentro de la red de Docker y no en la maquina anfitriona: lanzar decenas
de procesos curl desde Windows mide sobre todo el costo de crear procesos, no la
capacidad de los servicios.

  rafaga       N solicitudes a la vez. Cuenta las respuestas por codigo HTTP.
  rendimiento  N solicitudes con concurrencia C. Mide solicitudes por segundo.
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

    return codigo, (time.perf_counter() - inicio) * 1000, instancia_de(texto)


def correr(args, concurrencia):
    cuerpo = json.loads(args.cuerpo) if args.cuerpo else None
    with ThreadPoolExecutor(max_workers=concurrencia) as pool:
        inicio = time.perf_counter()
        resultados = list(pool.map(
            lambda _: solicitar(args.url, cuerpo, args.timeout), range(args.n)))
    return resultados, time.perf_counter() - inicio


def rafaga(args):
    resultados, segundos = correr(args, args.n)
    print(f"  {args.n} solicitudes simultaneas en {segundos:.2f} s")
    for codigo, cantidad in sorted(Counter(c for c, _, _ in resultados).items()):
        print(f"      HTTP {codigo}  x{cantidad:<4} {ETIQUETAS.get(codigo, '')}")


def rendimiento(args):
    resultados, segundos = correr(args, args.c)
    latencias = [ms for _, ms, _ in resultados]
    codigos = Counter(c for c, _, _ in resultados)
    instancias = Counter(i for _, _, i in resultados if i)

    print(f"  solicitudes     : {args.n} (concurrencia {args.c})")
    print(f"  tiempo total    : {segundos:.2f} s")
    print(f"  throughput      : {args.n / segundos:.1f} solicitudes/segundo")
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

args = analizador.parse_args()
{"rafaga": rafaga, "rendimiento": rendimiento}[args.modo](args)
