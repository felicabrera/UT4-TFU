"""Configuración del componente `admision`.

Igual que en la UT2, ningún valor operativo queda literal en el código: todos se
resuelven en tiempo de arranque desde el entorno, con un valor por defecto
conocido. Cambiar la capacidad de la cinta no requiere tocar código ni
reconstruir la imagen.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://cinta:cinta@db:5432/cinta"
)

CINTA_ID = os.getenv("CINTA_ID", "C1")
CINTA_CAPACIDAD_KG = float(os.getenv("CINTA_CAPACIDAD_KG", 100))

# Ventana artificial que el endpoint de instrumentación sin transacción deja
# abierta entre la lectura y la escritura, para que la condición de carrera
# sea observable de forma reproducible en la demostración.
VENTANA_CARRERA_S = float(os.getenv("VENTANA_CARRERA_S", 0.15))

# UT4 - Plazo de los chequeos de /health/ready (PostgreSQL exige minimo 2 s).
TIMEOUT_SALUD_S = max(2, int(float(os.getenv("TIMEOUT_SALUD_S", 2))))
