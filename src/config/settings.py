"""Configuración de la aplicación."""

import os

from dotenv import load_dotenv

load_dotenv()


class Configuracion:
	"""Agrupa las credenciales y parámetros de los servicios externos."""

	META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
	META_ACCOUNT_ID: str = os.getenv("META_ACCOUNT_ID", "")
	TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
	TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
	TWILIO_FROM_WHATSAPP: str = os.getenv("TWILIO_FROM_WHATSAPP", "")
	TWILIO_TO_WHATSAPP: str = os.getenv("TWILIO_TO_WHATSAPP", "")


configuracion = Configuracion()

