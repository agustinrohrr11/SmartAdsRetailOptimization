"""Configuración de la aplicación."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _obtener_booleano(nombre: str, valor_predeterminado: bool) -> bool:
	"""Convierte una variable de entorno en booleano."""
	valor = os.getenv(nombre)
	if valor is None:
		return valor_predeterminado
	return valor.strip().lower() in {"1", "true", "sí", "si", "yes", "on"}


def _obtener_float(nombre: str, valor_predeterminado: float) -> float:
	"""Convierte una variable numérica o devuelve su valor predeterminado."""
	try:
		return float(os.getenv(nombre, str(valor_predeterminado)))
	except ValueError:
		return valor_predeterminado


@dataclass(frozen=True)
class Configuracion:
	"""Credenciales y parámetros de los servicios externos."""

	META_ACCESS_TOKEN: str = field(default_factory=lambda: os.getenv("META_ACCESS_TOKEN", ""))
	META_ACCOUNT_ID: str = field(default_factory=lambda: os.getenv("META_ACCOUNT_ID", ""))
	META_CAMPAIGN_ID: str = field(default_factory=lambda: os.getenv("META_CAMPAIGN_ID", ""))
	META_CAMPAIGN_ASADO_ID: str = field(default_factory=lambda: os.getenv("META_CAMPAIGN_ASADO_ID", ""))
	META_CAMPAIGN_ESTOFADO_ID: str = field(default_factory=lambda: os.getenv("META_CAMPAIGN_ESTOFADO_ID", ""))
	META_CAMPAIGN_ECONOMICOS_ID: str = field(default_factory=lambda: os.getenv("META_CAMPAIGN_ECONOMICOS_ID", ""))
	META_MAX_BUDGET: float = field(default_factory=lambda: _obtener_float("META_MAX_BUDGET", 100000.0))
	META_MAX_INCREASE_PERCENT: float = field(default_factory=lambda: _obtener_float("META_MAX_INCREASE_PERCENT", 50.0))
	MODO_SIMULACION: bool = field(default_factory=lambda: _obtener_booleano("MODO_SIMULACION", True))

	TELEGRAM_BOT_TOKEN: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
	TELEGRAM_CHAT_ID: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
	ENVIAR_TELEGRAM: bool = field(default_factory=lambda: _obtener_booleano("ENVIAR_TELEGRAM", False))

	LATITUD: float = field(default_factory=lambda: _obtener_float("LATITUD", 0.0))
	LONGITUD: float = field(default_factory=lambda: _obtener_float("LONGITUD", 0.0))
	OPEN_METEO_URL: str = field(
		default_factory=lambda: os.getenv(
			"OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast"
		)
	)
	TIMEOUT_RED: float = field(default_factory=lambda: _obtener_float("TIMEOUT_RED", 10.0))

	@property
	def campanas(self) -> dict[str, str]:
		"""Devuelve las campañas autorizadas por nombre lógico."""
		return {
			"Asado": self.META_CAMPAIGN_ASADO_ID,
			"Estofado": self.META_CAMPAIGN_ESTOFADO_ID,
			"Económicos/Picada": self.META_CAMPAIGN_ECONOMICOS_ID,
		}

	@property
	def identificador_cuenta_meta(self) -> str:
		"""Devuelve el ID de cuenta en el formato requerido por Meta."""
		identificador = self.META_ACCOUNT_ID.strip()
		return identificador if identificador.startswith("act_") else f"act_{identificador}"

	def validar_campana_principal(self) -> None:
		"""Valida la campaña única administrada por el bot."""
		faltantes = [
			nombre
			for nombre, valor in {
				"META_ACCESS_TOKEN": self.META_ACCESS_TOKEN,
				"META_ACCOUNT_ID": self.META_ACCOUNT_ID,
				"META_CAMPAIGN_ID": self.META_CAMPAIGN_ID,
			}.items()
			if not valor
		]
		if faltantes:
			raise ValueError("Falta configuración de Meta Ads: " + ", ".join(faltantes))

	def validar_meta(self) -> None:
		"""Valida la configuración necesaria para ejecutar Meta Ads realmente."""
		faltantes = [
			nombre
			for nombre, valor in {
				"META_ACCESS_TOKEN": self.META_ACCESS_TOKEN,
				"META_ACCOUNT_ID": self.META_ACCOUNT_ID,
				**{f"ID de campaña {nombre}": identificador for nombre, identificador in self.campanas.items()},
			}.items()
			if not valor
		]
		if faltantes:
			raise ValueError("Falta configuración de Meta Ads: " + ", ".join(faltantes))

	def validar_telegram(self) -> None:
		"""Valida la configuración necesaria para enviar un mensaje de Telegram."""
		faltantes = [
			nombre
			for nombre, valor in {
				"TELEGRAM_BOT_TOKEN": self.TELEGRAM_BOT_TOKEN,
				"TELEGRAM_CHAT_ID": self.TELEGRAM_CHAT_ID,
			}.items()
			if not valor
		]
		if faltantes:
			raise ValueError("Falta configuración de Telegram: " + ", ".join(faltantes))


configuracion = Configuracion()

