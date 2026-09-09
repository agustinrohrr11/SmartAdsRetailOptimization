"""Integración segura con Meta Ads en modo simulado o real."""

import logging
from typing import Any

from src.config.settings import Configuracion, configuracion


logger = logging.getLogger(__name__)


class GestorMetaAds:
	"""Ejecuta operaciones sobre campañas autorizadas de Meta Ads."""

	def __init__(self, ajustes: Configuracion = configuracion, cliente_api: Any = None) -> None:
		self.ajustes = ajustes
		self.cliente_api = cliente_api
		self._cuenta = None
		if not ajustes.MODO_SIMULACION:
			self._inicializar_api()

	def pausar_campana(self, nombre_campana: str) -> None:
		"""Pausa una campaña o registra la operación en dry-run."""
		self._actualizar_estado(nombre_campana, "PAUSED")

	def activar_campana(self, nombre_campana: str) -> None:
		"""Activa una campaña o registra la operación en dry-run."""
		self._actualizar_estado(nombre_campana, "ACTIVE")

	def modificar_presupuesto(
		self, nombre_campana: str, porcentaje_aumento: float
	) -> None:
		"""Aumenta el presupuesto respetando los límites configurados."""
		if porcentaje_aumento <= 0:
			logger.warning("Aumento ignorado para '%s': porcentaje no positivo", nombre_campana)
			return
		if porcentaje_aumento > self.ajustes.META_MAX_INCREASE_PERCENT:
			logger.warning(
				"Aumento limitado de %.1f%% a %.1f%% para '%s'",
				porcentaje_aumento,
				self.ajustes.META_MAX_INCREASE_PERCENT,
				nombre_campana,
			)
			porcentaje_aumento = self.ajustes.META_MAX_INCREASE_PERCENT

		identificador = self._obtener_id_campana(nombre_campana)
		if self.ajustes.MODO_SIMULACION:
			logger.info(
				"DRY-RUN Meta Ads: aumentar presupuesto de '%s' (ID: %s) en %.1f%%",
				nombre_campana,
				identificador or "sin ID",
				porcentaje_aumento,
			)
			return

		campana = self._obtener_campana(identificador)
		datos = campana.api_get(fields=["daily_budget"])
		presupuesto_actual = float(datos.get("daily_budget", 0))
		if presupuesto_actual <= 0:
			raise ValueError(f"La campaña '{nombre_campana}' no tiene presupuesto válido")
		nuevo_presupuesto = presupuesto_actual * (1 + porcentaje_aumento / 100)
		nuevo_presupuesto = min(nuevo_presupuesto, self.ajustes.META_MAX_BUDGET)
		campana.api_update(params={"daily_budget": int(nuevo_presupuesto)})
		logger.info(
			"Meta Ads: presupuesto actualizado para '%s' de %.0f a %.0f",
			nombre_campana,
			presupuesto_actual,
			nuevo_presupuesto,
		)

	def _inicializar_api(self) -> None:
		"""Inicializa el SDK real únicamente fuera de simulación."""
		self.ajustes.validar_meta()
		if self.cliente_api is not None:
			self._cuenta = self.cliente_api
			return
		from facebook_business.api import FacebookAdsApi
		from facebook_business.adobjects.adaccount import AdAccount

		FacebookAdsApi.init(access_token=self.ajustes.META_ACCESS_TOKEN)
		self._cuenta = AdAccount(self.ajustes.META_ACCOUNT_ID)

	def _obtener_id_campana(self, nombre_campana: str) -> str:
		"""Obtiene un ID allowlisted y evita operar por nombre ambiguo."""
		identificador = self.ajustes.campanas.get(nombre_campana, "")
		if not identificador and not self.ajustes.MODO_SIMULACION:
			raise ValueError(f"Campaña no autorizada: '{nombre_campana}'")
		return identificador

	def _obtener_campana(self, identificador: str) -> Any:
		"""Construye el objeto Campaign del SDK para un ID autorizado."""
		if self._cuenta is None:
			raise RuntimeError("El cliente de Meta Ads no está inicializado")
		from facebook_business.adobjects.campaign import Campaign

		return Campaign(identificador)

	def _actualizar_estado(self, nombre_campana: str, estado: str) -> None:
		"""Actualiza el estado o registra el cambio en dry-run."""
		identificador = self._obtener_id_campana(nombre_campana)
		if self.ajustes.MODO_SIMULACION:
			logger.info(
				"DRY-RUN Meta Ads: %s campaña '%s' (ID: %s)",
				estado,
				nombre_campana,
				identificador or "sin ID",
			)
			return

		campana = self._obtener_campana(identificador)
		campana.api_update(params={"status": estado})
		logger.info("Meta Ads: campaña '%s' actualizada a %s", nombre_campana, estado)
