"""Obtención del contexto de clima y calendario para las decisiones."""

import calendar
from dataclasses import dataclass
from datetime import date
import logging
from typing import Any

import requests

from src.config.settings import Configuracion, configuracion


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatosContexto:
	"""Datos que el motor necesita para evaluar las campañas."""

	probabilidad_lluvia: float
	es_fin_de_semana: bool
	es_quincena_o_fin_de_mes: bool
	descripcion_clima: str = "Sin datos"
	temperatura: float | None = None


class GestorContexto:
	"""Obtiene el contexto actual de clima y calendario desde Open-Meteo."""

	def __init__(
		self,
		ajustes: Configuracion = configuracion,
		cliente_http: Any = requests,
		fecha_actual: date | None = None,
	) -> None:
		self.ajustes = ajustes
		self.cliente_http = cliente_http
		self.fecha_actual = fecha_actual

	def obtener_contexto(self) -> DatosContexto:
		"""Devuelve clima y calendario, usando un fallback si Open-Meteo falla."""
		hoy = self.fecha_actual or date.today()
		try:
			respuesta = self.cliente_http.get(
				self.ajustes.OPEN_METEO_URL,
				params={
					"latitude": self.ajustes.LATITUD,
					"longitude": self.ajustes.LONGITUD,
					"daily": "precipitation_probability_max,weather_code,temperature_2m_max",
					"timezone": "auto",
					"forecast_days": 1,
				},
				timeout=self.ajustes.TIMEOUT_RED,
			)
			respuesta.raise_for_status()
			clima = self._extraer_clima(respuesta.json())
			return self._crear_contexto(hoy, **clima)
		except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
			logger.exception("No se pudo obtener el clima; se usará un fallback conservador")
			return self._crear_contexto(
				hoy,
				probabilidad_lluvia=0.0,
				descripcion_clima="Clima no disponible",
				temperatura=None,
			)

	def _extraer_clima(self, datos: dict[str, Any]) -> dict[str, float | str | None]:
		"""Extrae el primer pronóstico diario de la respuesta de Open-Meteo."""
		diario = datos["daily"]
		probabilidad = float(diario["precipitation_probability_max"][0])
		codigo = int(diario["weather_code"][0])
		temperatura = float(diario["temperature_2m_max"][0])
		return {
			"probabilidad_lluvia": probabilidad,
			"descripcion_clima": self._describir_clima(codigo),
			"temperatura": temperatura,
		}

	def _crear_contexto(
		self,
		fecha: date,
		probabilidad_lluvia: float,
		descripcion_clima: str,
		temperatura: float | None,
	) -> DatosContexto:
		"""Combina el pronóstico con las reglas de calendario."""
		ultimo_dia = calendar.monthrange(fecha.year, fecha.month)[1]
		return DatosContexto(
			probabilidad_lluvia=probabilidad_lluvia,
			es_fin_de_semana=fecha.weekday() >= 5,
			es_quincena_o_fin_de_mes=fecha.day in {15, ultimo_dia},
			descripcion_clima=descripcion_clima,
			temperatura=temperatura,
		)

	@staticmethod
	def _describir_clima(codigo: int) -> str:
		"""Traduce códigos meteorológicos WMO a una descripción breve."""
		if codigo == 0:
			return "Despejado"
		if codigo in {1, 2, 3}:
			return "Parcialmente nublado"
		if codigo in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}:
			return "Lluvia"
		if codigo in {71, 73, 75, 77, 85, 86}:
			return "Nieve"
		if codigo in {95, 96, 99}:
			return "Tormenta"
		return "Condiciones variables"
