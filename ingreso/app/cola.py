"""Publicacion durable y difusion de invalidaciones de Cache-Aside."""

import json
import logging
import threading
import time

import pika

from app.config import (CLAVE_INTERNA, COLA_INVALIDACIONES, COLA_NOMBRE,
                        RABBITMQ_URL)

LOG = logging.getLogger("cola_ingreso")


def _parametros():
    parametros = pika.URLParameters(RABBITMQ_URL)
    parametros.heartbeat = 30
    parametros.blocked_connection_timeout = 5
    return parametros


def verificar_broker():
    conexion = pika.BlockingConnection(_parametros())
    conexion.close()


def publicar(solicitud: dict):
    with pika.BlockingConnection(_parametros()) as conexion:
        canal = conexion.channel()
        canal.confirm_delivery()
        canal.queue_declare(queue=COLA_NOMBRE, durable=True, arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": f"{COLA_NOMBRE}.fallidos",
        })
        canal.basic_publish(
            exchange="",
            routing_key=COLA_NOMBRE,
            body=json.dumps(solicitud).encode(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=2,
                headers={"clave_interna": CLAVE_INTERNA},
            ),
            mandatory=True,
        )


def _escuchar_invalidaciones(cache):
    while True:
        conexion = None
        try:
            conexion = pika.BlockingConnection(_parametros())
            canal = conexion.channel()
            canal.exchange_declare(exchange=COLA_INVALIDACIONES, exchange_type="fanout", durable=True)
            cola = canal.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
            canal.queue_bind(exchange=COLA_INVALIDACIONES, queue=cola)

            def invalidar(_canal, _metodo, _propiedades, cuerpo):
                cinta_id = json.loads(cuerpo)["cinta_id"]
                cache.invalidar(f"cinta:{cinta_id}")

            canal.basic_consume(queue=cola, on_message_callback=invalidar, auto_ack=True)
            LOG.info("Escuchando invalidaciones de cache")
            canal.start_consuming()
        except Exception:
            LOG.exception("Listener de invalidacion desconectado; reintentando")
            time.sleep(2)
        finally:
            if conexion is not None and conexion.is_open:
                conexion.close()


def iniciar_listener_cache(cache):
    threading.Thread(
        target=_escuchar_invalidaciones, args=(cache,), daemon=True,
        name="cache-invalidation-listener",
    ).start()