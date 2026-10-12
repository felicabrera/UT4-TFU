"""
Componente admision. Expone la interfaz IAdmisionCinta.

Administra el cupo de carga de la cinta, que es el recurso compartido y finito
del sistema. Es el unico componente que escribe estado, y siempre lo hace dentro
de una transaccion.

El servicio en si no guarda nada en memoria: todo el estado esta en PostgreSQL.
Por eso tambien se puede replicar, ya que dos replicas que compiten por la misma
cinta se serializan en la base y no en el proceso.
"""

import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.db import INSTANCIA, Sesion, repo, sembrar_cinta, vista_cinta
from app.demo import router as router_demo
from app.modelos import PaqueteEnTransito


@asynccontextmanager
async def ciclo_de_vida(_):
    # La base ya esta sana por el depends_on del compose, pero puede tardar unos
    # segundos mas en aceptar conexiones.
    for intento in range(10):
        try:
            sembrar_cinta()
            break
        except Exception:
            if intento == 9:
                raise
            time.sleep(2)
    yield


app = FastAPI(
    title="Componente admision — Cupo de cinta transportadora",
    description="Interfaz IAdmisionCinta. Consume IRepositorioCinta.",
    version="1.0.0",
    lifespan=ciclo_de_vida,
)


class SolicitudAdmision(BaseModel):
    tipo_paquete: str
    peso_kg: float = Field(gt=0)


class SolicitudEgreso(BaseModel):
    paquete_id: uuid.UUID


@app.get("/health")
def health():
    try:
        with Sesion() as sesion:
            sesion.execute(text("SELECT 1"))
    except Exception as error:
        raise HTTPException(503, f"base no disponible: {error}")
    return {"estado": "ok", "componente": "admision", "instancia": INSTANCIA}


@app.get("/")
def raiz():
    return health()


@app.get("/cintas/{cinta_id}")
def consultar(cinta_id: str):
    """Estado actual de la cinta. Lectura sin bloqueo."""
    with Sesion() as sesion:
        cinta = repo.obtener(sesion, cinta_id)
        if cinta is None:
            raise HTTPException(404, f"cinta {cinta_id} no existe")

        cantidad = sesion.scalar(
            select(func.count()).select_from(PaqueteEnTransito)
            .where(PaqueteEnTransito.cinta_id == cinta_id))
        vista = vista_cinta(cinta)

    vista["paquetes_en_transito"] = int(cantidad or 0)
    vista["instancia"] = INSTANCIA
    return vista


@app.post("/cintas/{cinta_id}/admisiones")
def admitir(cinta_id: str, solicitud: SolicitudAdmision):
    """
    Reserva cupo para un paquete. Esta es la transaccion ACID del sistema:

        BEGIN
          SELECT ... FOR UPDATE   -> bloquea la fila de la cinta
          verificar cupo
          INSERT paquete_en_transito
          UPDATE cinta.carga_kg
        COMMIT

    Si dos replicas piden el mismo ultimo lugar, la segunda espera el bloqueo,
    lee la carga ya actualizada y es rechazada. La cinta nunca se pasa de su
    capacidad.
    """
    peso = Decimal(str(solicitud.peso_kg))

    with Sesion() as sesion:
        try:
            with sesion.begin():
                cinta = repo.obtener_para_actualizar(sesion, cinta_id)
                if cinta is None:
                    raise HTTPException(404, f"cinta {cinta_id} no existe")

                disponible = cinta.capacidad_kg - cinta.carga_kg
                if peso > disponible:
                    # Si no hay cupo no se admite, y se dice por que.
                    raise HTTPException(409, {
                        "motivo": "cupo insuficiente en la cinta",
                        "cinta_id": cinta_id,
                        "peso_solicitado_kg": float(peso),
                        "disponible_kg": float(disponible),
                        "capacidad_kg": float(cinta.capacidad_kg),
                        "carga_kg": float(cinta.carga_kg),
                    })

                paquete_id = repo.registrar_admision(
                    sesion, cinta, solicitud.tipo_paquete, peso)
                vista = vista_cinta(cinta)
        except IntegrityError as error:
            # Red de seguridad: si por algun camino se intentara confirmar una
            # carga fuera de rango, la restriccion CHECK aborta la transaccion.
            raise HTTPException(409, {
                "motivo": "la restriccion cupo_no_excedido rechazo la escritura",
                "error": str(error.orig),
            })

    return {"paquete_id": str(paquete_id), "cinta": vista, "instancia": INSTANCIA}


@app.post("/cintas/{cinta_id}/egresos")
def egresar(cinta_id: str, solicitud: SolicitudEgreso):
    """Un paquete sale de la cinta y libera su peso. Tambien es transaccional."""
    with Sesion() as sesion:
        with sesion.begin():
            cinta = repo.obtener_para_actualizar(sesion, cinta_id)
            if cinta is None:
                raise HTTPException(404, f"cinta {cinta_id} no existe")

            peso = repo.registrar_egreso(sesion, cinta, solicitud.paquete_id)
            if peso is None:
                raise HTTPException(
                    404, f"el paquete {solicitud.paquete_id} no esta en la cinta")
            vista = vista_cinta(cinta)

    return {"estado": "egresado", "peso_liberado_kg": float(peso),
            "cinta": vista, "instancia": INSTANCIA}


# Endpoints de las demostraciones. No son parte de IAdmisionCinta.
app.include_router(router_demo)
