"""Integración segura con Meta Ads en modo simulado o real."""

import logging
from dataclasses import dataclass
from typing import Any

from src.config.settings import Configuracion, configuracion


logger = logging.getLogger(__name__)


class ErrorMetaAds(RuntimeError):
	"""Indica que Meta no devolvió una consulta confiable."""


@dataclass(frozen=True)
class AnuncioMeta:
	"""Representa un anuncio individual devuelto por Meta."""

	identificador: str
	nombre: str
	estado: str
	identificador_campana: str


class GestorMetaAds:
	"""Ejecuta operaciones sobre anuncios dentro de campañas autorizadas."""

	def __init__(self, ajustes: Configuracion = configuracion, cliente_api: Any = None) -> None:
		self.ajustes = ajustes
		self.cliente_api = cliente_api
		self._cuenta = None
		self._estados_simulados: dict[str, str] = {}
		if not ajustes.MODO_SIMULACION:
			self._inicializar_api()

	def pausar_anuncio(self, identificador: str, nombre_anuncio: str = "") -> None:
		"""Pausa únicamente un anuncio, sin modificar su campaña padre."""
		self._actualizar_estado_anuncio(identificador, nombre_anuncio, "PAUSED")

	def activar_anuncio(self, identificador: str, nombre_anuncio: str = "") -> None:
		"""Activa únicamente un anuncio, sin modificar su campaña padre."""
		self._actualizar_estado_anuncio(identificador, nombre_anuncio, "ACTIVE")

	def pausar_campana(self, nombre_campana: str) -> None:
		"""Compatibilidad: busca un anuncio homónimo, nunca pausa la campaña."""
		anuncio = self._buscar_anuncio_por_nombre(nombre_campana)
		self.pausar_anuncio(anuncio["id"], anuncio["name"])

	def activar_campana(self, nombre_campana: str) -> None:
		"""Compatibilidad: busca un anuncio homónimo, nunca activa la campaña."""
		anuncio = self._buscar_anuncio_por_nombre(nombre_campana)
		self.activar_anuncio(anuncio["id"], anuncio["name"])

	def pausar_anuncio_por_nombre(self, nombre_anuncio: str) -> None:
		"""Pausa un anuncio resolviendo su ID por nombre."""
		anuncio = self._buscar_anuncio_por_nombre(nombre_anuncio)
		self.pausar_anuncio(anuncio["id"], anuncio["name"])

	def activar_anuncio_por_nombre(self, nombre_anuncio: str) -> None:
		"""Activa un anuncio resolviendo su ID por nombre."""
		anuncio = self._buscar_anuncio_por_nombre(nombre_anuncio)
		self.activar_anuncio(anuncio["id"], anuncio["name"])

	def obtener_anuncios(self) -> list[dict[str, str]]:
		"""Consulta los anuncios hijos de las campañas configuradas."""
		if self.ajustes.MODO_SIMULACION:
			return [
				{
					"id": f"simulado-{identificador}",
					"name": nombre,
					"status": self._estados_simulados.get(
						f"simulado-{identificador}", "PAUSED"
					),
					"campaign_id": identificador,
				}
				for nombre, identificador in self.ajustes.campanas.items()
			]
		if self._cuenta is None:
			raise ErrorMetaAds("El cliente de Meta Ads no está inicializado")
		try:
			from facebook_business.adobjects.campaign import Campaign

			anuncios: list[dict[str, str]] = []
			for identificador_campana in self.ajustes.campanas.values():
				if not identificador_campana:
					continue
				campana = Campaign(identificador_campana)
				for anuncio in campana.get_ads(fields=["id", "name", "status", "campaign_id"]):
					anuncios.append(
						{
							"id": str(anuncio.get("id", "")),
							"name": str(anuncio.get("name", "")),
							"status": str(anuncio.get("status", "PAUSED")),
							"campaign_id": str(
								anuncio.get("campaign_id", identificador_campana)
							),
						}
					)
			return anuncios
		except Exception as error:
			logger.exception("No se pudieron consultar los anuncios de Meta")
			raise ErrorMetaAds("No se pudieron consultar los anuncios de Meta") from error

	def obtener_conjuntos(self) -> list[dict[str, str]]:
		"""Descubre todos los conjuntos de la campaña principal."""
		if self.ajustes.MODO_SIMULACION:
			return []
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

	def _buscar_anuncio_por_nombre(self, nombre_anuncio: str) -> dict[str, str]:
		"""Resuelve un nombre para compatibilidad con la API anterior."""
		nombre_normalizado = " ".join(nombre_anuncio.casefold().split())
		for anuncio in self.obtener_anuncios():
			if " ".join(anuncio["name"].casefold().split()) == nombre_normalizado:
				logger.warning(
					"Se seleccionó el primer anuncio coincidente para '%s' (ad_id=%s)",
					nombre_anuncio,
					anuncio["id"],
				)
				return anuncio
		raise ValueError(f"Anuncio no autorizado o inexistente: '{nombre_anuncio}'")

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
		self.ajustes.validar_campana_principal()
		if self.cliente_api is not None:
			self._cuenta = self.cliente_api
			return
		from facebook_business.api import FacebookAdsApi
		from facebook_business.adobjects.adaccount import AdAccount

		FacebookAdsApi.init(access_token=self.ajustes.META_ACCESS_TOKEN)
		self._cuenta = AdAccount(self.ajustes.identificador_cuenta_meta)

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

	def _actualizar_estado_anuncio(
		self, identificador: str, nombre_anuncio: str, estado: str
	) -> None:
		"""Actualiza el estado de un Ad, nunca el de su Campaign padre."""
		if not identificador:
			raise ValueError("El anuncio no tiene un identificador de Meta")
		if self.ajustes.MODO_SIMULACION:
			self._estados_simulados[identificador] = estado
			logger.info(
				"DRY-RUN Meta Ads: %s anuncio '%s' (ID: %s); campaña intacta",
				estado,
				nombre_anuncio or "sin nombre",
				identificador,
			)
			return

		from facebook_business.adobjects.ad import Ad

		anuncio = Ad(identificador)
		anuncio.api_update(params={"status": estado})
		logger.info("Meta Ads: anuncio '%s' actualizado a %s; campaña intacta", nombre_anuncio, estado)

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
		conjunto.api_update(params={"status": estado})
		logger.info("Meta Ads: conjunto '%s' actualizado a %s; campaña intacta", nombre, estado)
