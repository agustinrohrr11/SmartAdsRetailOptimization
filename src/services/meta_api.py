"""Integración segura con Meta Ads en modo simulado o real."""

import logging
from typing import Any, Callable

from src.config.settings import Configuracion, configuracion


logger = logging.getLogger(__name__)


class ErrorMetaAds(RuntimeError):
	"""Indica que Meta no devolvió una consulta confiable."""


class GestorMetaAds:
	"""Ejecuta operaciones sobre conjuntos dentro de la campaña autorizada."""

	def __init__(
		self,
		ajustes: Configuracion = configuracion,
		cliente_api: Any = None,
		nombres_adsets_simulados: Callable[[], list[str]] | None = None,
	) -> None:
		self.ajustes = ajustes
		self.cliente_api = cliente_api
		self.nombres_adsets_simulados = nombres_adsets_simulados
		self._cuenta = None
		self._estados_simulados: dict[str, str] = {}
		if not ajustes.MODO_SIMULACION:
			self._inicializar_api()

	def obtener_conjuntos(self) -> list[dict[str, str]]:
		"""Descubre todos los conjuntos de la campaña principal."""
		if self.ajustes.MODO_SIMULACION:
			return self._conjuntos_simulados()
		if self._cuenta is None:
			raise ErrorMetaAds("El cliente de Meta Ads no está inicializado")
		if not self.ajustes.META_CAMPAIGN_ID:
			raise ErrorMetaAds("Falta META_CAMPAIGN_ID")
		try:
			from facebook_business.adobjects.campaign import Campaign

			campana = Campaign(self.ajustes.META_CAMPAIGN_ID)
			return [
				{
					"id": str(conjunto.get("id", "")),
					"name": str(conjunto.get("name", "")),
					"status": str(conjunto.get("status", "PAUSED")),
					"campaign_id": str(
						conjunto.get("campaign_id", self.ajustes.META_CAMPAIGN_ID)
					),
				}
				for conjunto in campana.get_ad_sets(
					fields=["id", "name", "status", "campaign_id"]
				)
			]
		except Exception as error:
			logger.exception("No se pudieron consultar los conjuntos de Meta")
			raise ErrorMetaAds(
				f"No se pudieron consultar los conjuntos de Meta: {error}"
			) from error

	def _conjuntos_simulados(self) -> list[dict[str, str]]:
		"""Construye los conjuntos simulados según los nombres de las reglas."""
		nombres = (
			self.nombres_adsets_simulados()
			if self.nombres_adsets_simulados is not None
			else []
		)
		return [
			{
				"id": f"simulado-{nombre}",
				"name": nombre,
				"status": self._estados_simulados.get(f"simulado-{nombre}", "PAUSED"),
				"campaign_id": self.ajustes.META_CAMPAIGN_ID or "",
			}
			for nombre in nombres
		]

	def pausar_conjunto(self, identificador: str, nombre: str = "") -> None:
		"""Pausa un conjunto sin modificar la campaña ni sus anuncios directamente."""
		self._actualizar_estado_conjunto(identificador, nombre, "PAUSED")

	def activar_conjunto(self, identificador: str, nombre: str = "") -> None:
		"""Activa un conjunto sin modificar la campaña ni sus anuncios directamente."""
		self._actualizar_estado_conjunto(identificador, nombre, "ACTIVE")

	def pausar_conjunto_por_nombre(self, nombre: str) -> None:
		"""Pausa un conjunto localizado por nombre."""
		conjunto = self._buscar_conjunto_por_nombre(nombre)
		self.pausar_conjunto(conjunto["id"], conjunto["name"])

	def activar_conjunto_por_nombre(self, nombre: str) -> None:
		"""Activa un conjunto localizado por nombre."""
		conjunto = self._buscar_conjunto_por_nombre(nombre)
		self.activar_conjunto(conjunto["id"], conjunto["name"])

	def _buscar_conjunto_por_nombre(self, nombre: str) -> dict[str, str]:
		"""Resuelve el primer conjunto coincidente y advierte sobre la ambigüedad."""
		normalizado = " ".join(nombre.casefold().split())
		coincidencias = [
			conjunto
			for conjunto in self.obtener_conjuntos()
			if " ".join(conjunto["name"].casefold().split()) == normalizado
		]
		if not coincidencias:
			raise ValueError(f"Conjunto no autorizado o inexistente: '{nombre}'")
		if len(coincidencias) > 1:
			logger.warning("Hay %d conjuntos con el nombre '%s'; se usa el primero", len(coincidencias), nombre)
		return coincidencias[0]

	def _inicializar_api(self) -> None:
		"""Inicializa el SDK real únicamente fuera de simulación."""
		self.ajustes.validar_campana_principal()
		if self.cliente_api is not None:
			self._cuenta = self.cliente_api
			return
		from facebook_business.api import FacebookAdsApi
		from facebook_business.adobjects.adaccount import AdAccount

		FacebookAdsApi.init(access_token=self.ajustes.META_ACCESS_TOKEN)
		self._cuenta = AdAccount(self.ajustes.identificador_cuenta_meta)

	def _actualizar_estado_conjunto(
		self, identificador: str, nombre: str, estado: str
	) -> None:
		"""Actualiza un AdSet sin tocar la campaña padre."""
		if not identificador:
			raise ValueError("El conjunto no tiene un identificador de Meta")
		if self.ajustes.MODO_SIMULACION:
			self._estados_simulados[identificador] = estado
			logger.info(
				"DRY-RUN Meta Ads: %s conjunto '%s' (ID: %s); campaña intacta",
				estado,
				nombre or "sin nombre",
				identificador,
			)
			return
		from facebook_business.adobjects.adset import AdSet

		conjunto = AdSet(identificador)
		try:
			conjunto.api_update(params={"status": estado})
		except Exception as error:
			logger.exception(
				"Meta rechazó la actualización de '%s' a %s", nombre, estado
			)
			raise ErrorMetaAds(
				self._mensaje_error_meta(error, nombre, estado)
			) from error
		logger.info("Meta Ads: conjunto '%s' actualizado a %s; campaña intacta", nombre, estado)

	@staticmethod
	def _mensaje_error_meta(error: Exception, nombre: str, estado: str) -> str:
		"""Extrae el motivo amigable de un fallo de la API de Meta."""
		detalle = None
		funcion = getattr(error, "api_error_message", None)
		if callable(funcion):
			try:
				detalle = str(funcion())
			except Exception:
				detalle = None
		if not detalle:
			detalle = str(error)
		if len(detalle) > 200:
			detalle = detalle[:200] + "..."
		return (
			f"No se pudo actualizar el conjunto "
			f"'{nombre or 'sin nombre'}' a {estado}: {detalle}"
		)