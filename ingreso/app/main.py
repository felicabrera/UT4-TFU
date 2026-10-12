"""
Componente ingreso. Expone la interfaz IIngresoPaquetes.

Valida el paquete con las reglas de su tipo y, si pasa, le pide cupo al
componente admision. No guarda nada entre solicitudes, por eso se puede replicar.
"""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import cliente_admision
from app.cache import cache_cintas
from app.config import CACHE_HABILITADA, CACHE_TTL_S, CINTA_POR_DEFECTO
from app.reglas.registro import obtener_regla
from app.salud import INSTANCIA, vivo
from app.salud import router as router_salud
from app.seguridad import autenticar_cliente

app = FastAPI(
    title="Componente ingreso - API Cinta Transportadora",
    description="Interfaz IIngresoPaquetes. Consume IAdmisionCinta.",
    version="2.0.0",
)


class Paquete(BaseModel):
    tipo_paquete: str
    peso_kg: float
    alto_cm: float
    ancho_cm: float
    largo_cm: float
    cinta_id: str = CINTA_POR_DEFECTO


# UT4 - Health Endpoint Monitoring.
app.include_router(router_salud)


@app.get("/health")
def health():
    """Compatibilidad con la UT3. Equivale a /health/live."""
    return vivo()


@app.get("/")
def raiz():
    return health()


@app.get("/cache/metricas")
def metricas_cache():
    """Metricas de rendimiento del patron Cache-Aside."""
    return cache_cintas.metricas()


@app.post("/cintas/{cinta_id}/cache/invalidar")
def invalidar_cache_cinta(cinta_id: str):
    """Invalida explicitamente la cache de una cinta (Cache-Aside)."""
    invalidada = cache_cintas.invalidar(f"cinta:{cinta_id}")
    return {"cinta_id": cinta_id, "invalidada": invalidada}


@app.get("/cintas/{cinta_id}")
def consultar_cinta(cinta_id: str):
    """
    Estado actual de la cinta.
    Aplica el patron Cache-Aside (rendimiento):
    - Si el dato esta en cache (HIT), se devuelve sin consultar a admision.
    - Si no esta o expiro (MISS), se consulta a admision y se guarda en cache.
    """
    clave = f"cinta:{cinta_id}"
    if CACHE_HABILITADA:
        datos, hit = cache_cintas.obtener(clave)
        if hit:
            return JSONResponse(
                content={"cinta": datos, "instancia": {"ingreso": INSTANCIA, "cache": "hit"}},
                headers={"X-Cache": "HIT"},
            )

    codigo, cuerpo = cliente_admision.estado_cinta(cinta_id)
    if codigo != 200:
        raise HTTPException(codigo, cuerpo)

    if CACHE_HABILITADA:
        cache_cintas.guardar(clave, cuerpo, CACHE_TTL_S)

    return JSONResponse(
        content={"cinta": cuerpo, "instancia": {"ingreso": INSTANCIA, "cache": "miss"}},
        headers={"X-Cache": "MISS"},
    )


@app.post("/paquetes")
def recibir_paquete(paquete: Paquete, cliente_autenticado: str = Depends(autenticar_cliente)):
    """
    Ingreso de un paquete. Aplica:
      - Gateway Offloading (seguridad): autenticacion del cliente en la frontera.
      - Gatekeeper (seguridad): validacion exhaustiva de reglas de dominio antes
        de reenviar a admision con credencial interna.
      - Cache-Aside (rendimiento): invalidacion de cache tras admision exitosa.
    """
    # Control 1: reglas del tipo de paquete (codigo de la UT2, sin cambios).
    regla = obtener_regla(paquete.tipo_paquete)
    if regla is None:
        raise HTTPException(
            422, f"tipo_paquete '{paquete.tipo_paquete}' no está registrado")

    es_valido, motivo = regla.es_valido(paquete.model_dump())
    if not es_valido:
        raise HTTPException(422, motivo)

    # Control 2: cupo de la cinta (interfaz IAdmisionCinta).
    codigo, cuerpo = cliente_admision.admitir(
        paquete.cinta_id, paquete.tipo_paquete, paquete.peso_kg)
    if codigo != 200:
        raise HTTPException(codigo, cuerpo)

    # Cache-Aside: al admitir un paquete, se invalida la cache de la cinta afectada
    # para garantizar consistencia en la proxima lectura.
    if CACHE_HABILITADA:
        cache_cintas.invalidar(f"cinta:{paquete.cinta_id}")

    return {
        "estado": "aceptado",
        "mensaje": "Paquete admitido en la cinta",
        "paquete_id": cuerpo["paquete_id"],
        "cinta": cuerpo["cinta"],
        "cliente": cliente_autenticado,
        "instancia": {"ingreso": INSTANCIA, "admision": cuerpo["instancia"]},
    }

