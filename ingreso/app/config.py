import os

from dotenv import load_dotenv

load_dotenv()


def _limite(nombre_var: str, valor_default: float) -> float:
    """Lee una variable de entorno numérica, con fallback a un default."""
    return float(os.getenv(nombre_var, valor_default))


LIMITES = {
    "normal": {
        "peso_kg_max": _limite("LIMITE_NORMAL_PESO_KG_MAX", 25),
        "alto_cm_max": _limite("LIMITE_NORMAL_ALTO_CM_MAX", 60),
        "ancho_cm_max": _limite("LIMITE_NORMAL_ANCHO_CM_MAX", 60),
        "largo_cm_max": _limite("LIMITE_NORMAL_LARGO_CM_MAX", 80),
    },
    "fragil": {
        "peso_kg_max": _limite("LIMITE_FRAGIL_PESO_KG_MAX", 8),
        "alto_cm_max": _limite("LIMITE_FRAGIL_ALTO_CM_MAX", 40),
        "ancho_cm_max": _limite("LIMITE_FRAGIL_ANCHO_CM_MAX", 40),
        "largo_cm_max": _limite("LIMITE_FRAGIL_LARGO_CM_MAX", 50),
    },
}

# ---------------------------------------------------------------------------
# UT3: configuración del componente de admisión que este servicio consume.
#
# Misma táctica de binding en tiempo de configuración que se usó en la UT2 para
# los límites de paquete: ningún valor queda literal en el código.
# ---------------------------------------------------------------------------

ADMISION_URL = os.getenv("ADMISION_URL", "http://admision:8000")
CINTA_POR_DEFECTO = os.getenv("CINTA_ID", "C1")
TIMEOUT_ADMISION_S = float(os.getenv("TIMEOUT_ADMISION_S", 10))
