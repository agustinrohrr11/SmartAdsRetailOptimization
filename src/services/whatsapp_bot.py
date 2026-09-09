"""Notificador de reportes mediante Twilio WhatsApp."""

import logging

from twilio.rest import Client

from src.config.settings import Configuracion, configuracion
from src.core.brain import AccionPublicitaria
from src.services.context_api import DatosContexto


logger = logging.getLogger(__name__)


class NotificadorWhatsApp:
	"""Envía el resumen de decisiones al cliente por WhatsApp."""

	def __init__(self, ajustes: Configuracion = configuracion) -> None:
		self.ajustes = ajustes
		self.cliente = Client(
			ajustes.TWILIO_ACCOUNT_SID,
			ajustes.TWILIO_AUTH_TOKEN,
		)

	def enviar_reporte(
		self, contexto: DatosContexto, acciones: list[AccionPublicitaria]
	) -> None:
		"""Forma y envía el reporte diario, registrando los errores de red."""
		resumen_acciones = "\n".join(
			f"- {accion.accion}: {accion.nombre_campana}"
			+ (
				f" (presupuesto x{accion.factor_presupuesto:.1f})"
				if accion.factor_presupuesto != 1.0
				else ""
			)
			for accion in acciones
		) or "- No hubo cambios de campañas."
		mensaje = (
			"📊 Reporte Smart-Ads Retail\n\n"
			f"🌦️ Clima: {contexto.descripcion_clima}\n"
			f"🌧️ Probabilidad de lluvia: {contexto.probabilidad_lluvia:.0f}%\n\n"
			f"✅ Acciones tomadas:\n{resumen_acciones}"
		)
		try:
			self.cliente.messages.create(
				body=mensaje,
				from_=self.ajustes.TWILIO_FROM_WHATSAPP,
				to=self.ajustes.TWILIO_TO_WHATSAPP,
			)
			logger.info("Reporte de WhatsApp enviado correctamente")
		except Exception:
			logger.exception("No se pudo enviar el reporte por WhatsApp")
