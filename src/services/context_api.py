"""Obtención del contexto de clima y calendario para las decisiones."""

from dataclasses import dataclass
from datetime import date
import logging


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
	"""Obtiene el contexto actual de clima y calendario.

	La integración externa queda preparada para conectarse a Open-Meteo;
	mientras tanto devuelve un contexto conservador para permitir ejecutar el flujo.
	"""

	def obtener_contexto(self) -> DatosContexto:
		"""Devuelve el contexto del día actual sin detener el proceso ante errores."""
		try:
			hoy = date.today()
			fin_de_mes = hoy.day >= 28
			return DatosContexto(
				probabilidad_lluvia=0.0,
				es_fin_de_semana=hoy.weekday() >= 5,
				es_quincena_o_fin_de_mes=hoy.day in {15, 30, 31} or fin_de_mes,
				descripcion_clima="No se consultó el servicio meteorológico",
			)
		except Exception:
			logger.exception("No se pudo obtener el contexto del día")
			return DatosContexto(0.0, False, False)
