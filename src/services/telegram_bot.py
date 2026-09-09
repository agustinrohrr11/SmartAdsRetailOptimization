"""Notificador de reportes mediante Telegram Bot API."""

import logging
from typing import Any

import requests

from src.config.settings import Configuracion, configuracion
from src.core.brain import AccionPublicitaria
from src.services.context_api import DatosContexto


logger = logging.getLogger(__name__)


class NotificadorTelegram:
    """Envía reportes mediante la API HTTP de Telegram."""

    LIMITE_MENSAJE = 4096

    def __init__(
        self,
        ajustes: Configuracion = configuracion,
        cliente_http: Any = requests,
    ) -> None:
        self.ajustes = ajustes
        self.cliente_http = cliente_http
        if ajustes.ENVIAR_TELEGRAM:
            ajustes.validar_telegram()

    def enviar_reporte(
        self, contexto: DatosContexto, acciones: list[AccionPublicitaria]
    ) -> int | None:
        """Envía el reporte y devuelve el último identificador de mensaje."""
        if not self.ajustes.ENVIAR_TELEGRAM:
            logger.info("Telegram: envío desactivado")
            return None

        mensaje = self._formatear_mensaje(contexto, acciones)
        ultimo_message_id: int | None = None
        url = (
            f"https://api.telegram.org/bot{self.ajustes.TELEGRAM_BOT_TOKEN}"
            "/sendMessage"
        )
        try:
            for inicio in range(0, len(mensaje), self.LIMITE_MENSAJE):
                respuesta = self.cliente_http.post(
                    url,
                    json={
                        "chat_id": self.ajustes.TELEGRAM_CHAT_ID,
                        "text": mensaje[inicio:inicio + self.LIMITE_MENSAJE],
                    },
                    timeout=self.ajustes.TIMEOUT_RED,
                )
                respuesta.raise_for_status()
                datos = respuesta.json()
                message_id = datos.get("result", {}).get("message_id")
                if datos.get("ok") is not True or not isinstance(message_id, int):
                    logger.error("Telegram devolvió una respuesta inválida")
                    return None
                ultimo_message_id = message_id
            logger.info("Reporte enviado por Telegram (message_id: %s)", ultimo_message_id)
            return ultimo_message_id
        except requests.exceptions.RequestException:
            logger.error("Error de conexión al enviar el reporte por Telegram", exc_info=True)
            return None
        except (ValueError, TypeError, AttributeError, KeyError):
            logger.error("Respuesta inválida de Telegram", exc_info=True)
            return None

    @staticmethod
    def _formatear_mensaje(
        contexto: DatosContexto, acciones: list[AccionPublicitaria]
    ) -> str:
        """Construye un reporte legible para Telegram."""
        resumen = "\n".join(
            f"• {accion.accion}: {accion.nombre_campana}"
            + (
                f" (presupuesto x{accion.factor_presupuesto:.1f})"
                if accion.factor_presupuesto != 1.0
                else ""
            )
            for accion in acciones
        ) or "• No hubo cambios de campañas."
        temperatura = (
            f"\n🌡️ Temperatura máxima: {contexto.temperatura:.1f} °C"
            if contexto.temperatura is not None
            else ""
        )
        return (
            "📊 Reporte Smart-Ads Retail\n\n"
            f"🌦️ Clima: {contexto.descripcion_clima}{temperatura}\n"
            f"🌧️ Probabilidad de lluvia: {contexto.probabilidad_lluvia:.0f}%\n\n"
            f"✅ Acciones tomadas:\n{resumen}"
        )
