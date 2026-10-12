"""
Componente ingreso. Expone la interfaz IIngresoPaquetes.

Valida el paquete con las reglas de su tipo y, si pasa, le pide cupo al
componente admision. No guarda nada entre solicitudes, por eso se puede replicar.
"""

import socket

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import cliente_admision
from app.config import CINTA_POR_DEFECTO
from app.reglas.registro import obtener_regla

INSTANCIA = socket.gethostname()

app = FastAPI(
    title="Componente ingreso — API Cinta Transportadora",
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


@app.get("/health")
def health():
    return {"estado": "ok", "componente": "ingreso", "instancia": INSTANCIA}


@app.get("/")
def raiz():
    return health()


@app.get("/cintas/{cinta_id}")
def consultar_cinta(cinta_id: str):
    """Reexpone el estado de la cinta consultando IAdmisionCinta."""
    codigo, cuerpo = cliente_admision.estado_cinta(cinta_id)
    if codigo != 200:
        raise HTTPException(codigo, cuerpo)
    return {"cinta": cuerpo, "instancia": {"ingreso": INSTANCIA}}


@app.post("/paquetes")
def recibir_paquete(paquete: Paquete):
    """
    Ingreso de un paquete. Pasa por dos controles de proteccion en serie:

      1. el paquete es admisible para su tipo -> se resuelve aca (UT2)
      2. la cinta tiene cupo                  -> lo resuelve admision (UT3)

    El segundo es el que la UT2 no podia hacer: mil paquetes validos de a uno
    sobrecargan la cinta igual, y eso no se detecta sin estado compartido.
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

    return {
        "estado": "aceptado",
        "mensaje": "Paquete admitido en la cinta",
        "paquete_id": cuerpo["paquete_id"],
        "cinta": cuerpo["cinta"],
        "instancia": {"ingreso": INSTANCIA, "admision": cuerpo["instancia"]},
    }
