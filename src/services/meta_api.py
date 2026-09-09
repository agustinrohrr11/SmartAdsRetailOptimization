"""Integración simulada con la API de Meta Ads."""

import logging

from src.config.settings import Configuracion, configuracion


logger = logging.getLogger(__name__)


class GestorMetaAds:
	"""Ejecuta operaciones sobre campañas de Meta Ads."""

	def __init__(self, ajustes: Configuracion = configuracion) -> None:
		self.ajustes = ajustes

	def pausar_campana(self, nombre_campana: str) -> None:
		"""Simula la pausa de una campaña."""
		logger.info("POST Meta Ads: pausar campaña '%s'", nombre_campana)

	def activar_campana(self, nombre_campana: str) -> None:
		"""Simula la activación de una campaña."""
		logger.info("POST Meta Ads: activar campaña '%s'", nombre_campana)

	def modificar_presupuesto(
		self, nombre_campana: str, porcentaje_aumento: float
	) -> None:
		"""Simula el aumento porcentual del presupuesto."""
		logger.info(
			"POST Meta Ads: aumentar presupuesto de '%s' en %.0f%%",
			nombre_campana,
			porcentaje_aumento,
		)
