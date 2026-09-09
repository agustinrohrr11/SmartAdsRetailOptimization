"""Notificador de reportes mediante Twilio WhatsApp."""

import logging
from typing import Any

from twilio.rest import Client

from src.config.settings import Configuracion, configuracion
from src.core.brain import AccionPublicitaria
from src.services.context_api import DatosContexto


logger = logging.getLogger(__name__)


class NotificadorWhatsApp:
	"""Envía el resumen de decisiones al cliente por WhatsApp."""

	def __init__(
		self,
		ajustes: Configuracion = configuracion,
		cliente: Any = None,
	) -> None:
		self.ajustes = ajustes
		self.cliente = cliente
		if ajustes.ENVIAR_WHATSAPP:
			ajustes.validar_twilio()
			self.cliente = cliente or Client(
				ajustes.TWILIO_ACCOUNT_SID,
				ajustes.TWILIO_AUTH_TOKEN,
			)

	def enviar_reporte(
		self, contexto: DatosContexto, acciones: list[AccionPublicitaria]
	) -> str | None:
		"""Forma y envía el reporte diario cuando el envío está habilitado."""
		mensaje = self._formatear_mensaje(contexto, acciones)
		if not self.ajustes.ENVIAR_WHATSAPP:
			logger.info("WhatsApp: envío desactivado")
			return None

		if self.cliente is None:
			raise RuntimeError("El cliente de Twilio no está inicializado")
		try:
			parametros = {
				"from_": self.ajustes.TWILIO_FROM_WHATSAPP,
				"to": self.ajustes.TWILIO_TO_WHATSAPP,
			}
			if self.ajustes.TWILIO_CONTENT_SID:
				parametros["content_sid"] = self.ajustes.TWILIO_CONTENT_SID
			else:
				parametros["body"] = mensaje
			respuesta = self.cliente.messages.create(**parametros)
			sid = getattr(respuesta, "sid", None)
			logger.info("Reporte de WhatsApp enviado correctamente (SID: %s)", sid or "desconocido")
			return sid
		except Exception:
			logger.exception("No se pudo enviar el reporte por WhatsApp")
			return None

	@staticmethod
	def _formatear_mensaje(
		contexto: DatosContexto, acciones: list[AccionPublicitaria]
	) -> str:
		"""Construye el mensaje sin realizar ninguna operación de red."""
		resumen_acciones = "\n".join(
			f"- {accion.accion}: {accion.nombre_campana}"
			+ (
				f" (presupuesto x{accion.factor_presupuesto:.1f})"
				if accion.factor_presupuesto != 1.0
				else ""
			)
			for accion in acciones
		) or "- No hubo cambios de campañas."
		temperatura = (
			f"\n🌡️ Temperatura máxima: {contexto.temperatura:.1f} °C"
			if contexto.temperatura is not None
			else ""
		)
		return (
			"📊 Reporte Smart-Ads Retail\n\n"
			f"🌦️ Clima: {contexto.descripcion_clima}{temperatura}\n"
			f"🌧️ Probabilidad de lluvia: {contexto.probabilidad_lluvia:.0f}%\n\n"
			f"✅ Acciones tomadas:\n{resumen_acciones}"
		)
