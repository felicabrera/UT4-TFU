"""
Cliente de la interfaz IAdmisionCinta.

Es el unico punto donde el componente ingreso consume el componente admision.
Devuelve siempre (codigo, cuerpo) para que main.py decida que responder.
"""

import httpx

from app.config import ADMISION_URL, TIMEOUT_ADMISION_S


def _pedir(metodo, ruta, json=None):
    try:
        r = httpx.request(metodo, ADMISION_URL + ruta, json=json,
                          timeout=TIMEOUT_ADMISION_S)
    except httpx.HTTPError as error:
        # Si no se puede confirmar el cupo, no se admite: ante la duda la cinta
        # no avanza.
        return 503, f"no se pudo contactar al componente de admision: {error}"

    cuerpo = r.json()
    if r.status_code != 200:
        cuerpo = cuerpo.get("detail", cuerpo)
    return r.status_code, cuerpo


def admitir(cinta_id, tipo_paquete, peso_kg):
    """Pide cupo para un paquete."""
    return _pedir("POST", f"/cintas/{cinta_id}/admisiones",
                  {"tipo_paquete": tipo_paquete, "peso_kg": peso_kg})


def estado_cinta(cinta_id):
    """Consulta el estado de una cinta."""
    return _pedir("GET", f"/cintas/{cinta_id}")
