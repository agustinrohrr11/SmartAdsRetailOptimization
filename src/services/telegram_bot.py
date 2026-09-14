"""Notificador de reportes mediante Telegram Bot API."""

import logging
import re
from pathlib import Path
from typing import Any

from src.config.settings import Configuracion, configuracion
from src.services.meta_api import ErrorMetaAds


logger = logging.getLogger(__name__)


class BotTelegram:
    """Bot asíncrono para comandos y configuración de anuncios."""

    PLANTILLA_CONFIGURACION = """CONFIGURACION DEL ANUNCIO \"{nombre}\".
+ Desactivar anuncio: []. Rellenar con un punto para desactivar.
+ Hora de funcionamiento. Activación: []. Desactivación: []. formato 24hs, ej: \"[00:00]\"
+ Temperatura de activación en grados C. minima: [] y maxima[].
+ Probabilid de lluvia minima: [] y maxima: [] para activación.
+ Dias de la semana: L[], MA[], MI[], J[], V[], S[], D[]. rellenar con un punto.
"""

    def __init__(
        self,
        ajustes: Configuracion = configuracion,
        reglas: Any = None,
        meta: Any = None,
    ) -> None:
        from src.config.reglas_negocio import GestorReglasNegocio

        self.ajustes = ajustes
        self.reglas = reglas or GestorReglasNegocio(
            Path(__file__).parents[1] / "config" / "reglas_conjuntos.json",
            clave_principal="conjuntos",
        )
        self.meta = meta

    def construir_aplicacion(self) -> Any:
        """Construye la aplicación de python-telegram-bot v20+ y sus handlers."""
        try:
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError as error:
            raise RuntimeError(
                "Instala python-telegram-bot>=20 para iniciar el bot"
            ) from error
        if not self.ajustes.TELEGRAM_BOT_TOKEN:
            raise ValueError("Falta TELEGRAM_BOT_TOKEN")
        aplicacion = Application.builder().token(self.ajustes.TELEGRAM_BOT_TOKEN).build()
        aplicacion.add_handler(CommandHandler("comandos", self.comandos))
        aplicacion.add_handler(CommandHandler("ads", self.ads))
        aplicacion.add_handler(CommandHandler("adsconfig", self.ads_config))
        aplicacion.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.procesar_mensaje)
        )
        return aplicacion

    async def comandos(self, actualizacion: Any, contexto: Any) -> None:
        """Lista los comandos disponibles."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        await actualizacion.message.reply_text(
            "/comandos - Lista los comandos disponibles.\n"
            "/ads - Lista anuncios y su configuración.\n"
            "/adsconfig [nombre_anuncio] - Muestra la plantilla de configuración."
        )

    async def ads(self, actualizacion: Any, contexto: Any) -> None:
        """Lista anuncios de Meta cruzados con las reglas JSON."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        try:
            anuncios = self.meta.obtener_conjuntos()
        except ErrorMetaAds:
            logger.exception("No se pudo generar /ads por un error de Meta")
            await actualizacion.message.reply_text(
                "No se pudo consultar Meta Ads. No se modificó ningún anuncio."
            )
            return
        lineas = []
        for anuncio in anuncios:
            configurado = self.reglas.obtener(str(anuncio.get("name", "")))
            estado = "Activado" if anuncio.get("status") == "ACTIVE" else "Desactivado"
            texto_configuracion = self._estado_configuracion(configurado)
            lineas.append(
                f"{str(anuncio.get('name', '')).upper()} - Status: "
                f"[{estado} en Meta] - Configuración: "
                f"[{texto_configuracion}]"
            )
        await actualizacion.message.reply_text("\n".join(lineas) or "No hay anuncios.")

    async def ads_config(self, actualizacion: Any, contexto: Any) -> None:
        """Entrega la plantilla y recuerda el anuncio a configurar."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        texto = actualizacion.message.text if actualizacion.message is not None else ""
        nombre = texto.split(None, 1)[1].strip() if len(texto.split(None, 1)) > 1 else ""
        if not nombre:
            await actualizacion.message.reply_text("Uso: /adsconfig [nombre_anuncio]")
            return
        contexto.user_data["anuncio_configuracion"] = nombre
        try:
            configuracion = self.reglas.obtener(nombre)
        except (OSError, ValueError, KeyError):
            logger.exception("No se pudo leer la configuración de '%s'", nombre)
            await actualizacion.message.reply_text(
                "No se pudo leer la configuración. Volvé a intentar en unos minutos."
            )
            return
        if actualizacion.message is not None:
            await actualizacion.message.reply_text(
                self._formatear_plantilla(nombre, configuracion)
            )

    async def procesar_mensaje(self, actualizacion: Any, contexto: Any) -> None:
        """Procesa una plantilla rellenada y la guarda o desactiva."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        nombre = contexto.user_data.get("anuncio_configuracion")
        if not nombre or actualizacion.message is None:
            return
        configuracion = self._parsear_plantilla(actualizacion.message.text, nombre)
        if configuracion is None:
            await actualizacion.message.reply_text(
                "No pude interpretar la plantilla. Revisa el formato y vuelve a enviarla."
            )
            return
        try:
            if configuracion == {}:
                if self.reglas.obtener(nombre) is None:
                    await actualizacion.message.reply_text(
                        f"No existe una configuración guardada para '{nombre}' que conservar."
                    )
                    return
                self.meta.pausar_conjunto_por_nombre(nombre)
                self.reglas.actualizar_estado(nombre, False)
                await actualizacion.message.reply_text(
                    f"La configuración de '{nombre}' se conservó, el conjunto quedó pausado "
                    "y la campaña permanece activa."
                )
            else:
                self.reglas.guardar(nombre, configuracion)
                await actualizacion.message.reply_text(
                    f"Configuración de '{nombre}' guardada correctamente."
                )
        except (ErrorMetaAds, ValueError, KeyError, OSError):
            logger.exception("No se pudo procesar la configuración de '%s'", nombre)
            if actualizacion.message is not None:
                await actualizacion.message.reply_text(
                    "No se pudo guardar la configuración. Revisá los valores y volvé a intentarlo."
                )
            return
        contexto.user_data.pop("anuncio_configuracion", None)

    async def _exigir_chat_autorizado(self, actualizacion: Any) -> bool:
        """Permite operar únicamente al chat configurado en TELEGRAM_CHAT_ID."""
        chat = getattr(actualizacion, "effective_chat", None)
        identificador_chat = getattr(chat, "id", None)
        autorizado = (
            bool(self.ajustes.TELEGRAM_CHAT_ID)
            and str(identificador_chat) == self.ajustes.TELEGRAM_CHAT_ID.strip()
        )
        if autorizado:
            return True
        mensaje = getattr(actualizacion, "message", None)
        if mensaje is not None:
            await mensaje.reply_text("Acceso denegado.")
        logger.warning("Intento de acceso no autorizado desde chat_id=%s", identificador_chat)
        return False

    @classmethod
    def _formatear_plantilla(
        cls, nombre: str, configuracion: dict[str, Any] | None
    ) -> str:
        """Rellena la plantilla con la configuración guardada del anuncio."""
        if not isinstance(configuracion, dict):
            return cls.PLANTILLA_CONFIGURACION.format(nombre=nombre)

        def valor(clave: str, predeterminado: str = "") -> str:
            dato = configuracion.get(clave, predeterminado)
            return str(dato)

        dias = configuracion.get("dias", {})
        valores_dias = {
            dia: ("" if dias.get(dia, False) else ".")
            for dia in ("L", "MA", "MI", "J", "V", "S", "D")
        }
        desactivar = "." if configuracion.get("activo") is False else ""
        return (
            f'CONFIGURACION DEL ANUNCIO "{nombre}".\n'
            f"+ Desactivar anuncio: [{desactivar}]. Rellenar con un punto para desactivar.\n"
            f"+ Hora de funcionamiento. Activación: [{valor('hora_activacion')}]. "
            f"Desactivación: [{valor('hora_desactivacion')}]. formato 24hs, ej: \"[00:00]\"\n"
            f"+ Temperatura de activación en grados C. minima: [{valor('temperatura_minima')}] "
            f"y maxima[{valor('temperatura_maxima')}].\n"
            f"+ Probabilid de lluvia minima: [{valor('lluvia_minima')}] y maxima: "
            f"[{valor('lluvia_maxima')}] para activación.\n"
            f"+ Dias de la semana: "
            + ", ".join(f"{dia}[{valores_dias[dia]}]" for dia in valores_dias)
            + ". rellenar con un punto.\n"
        )

    async def enviar_reporte_diario(
        self,
        contexto_clima: Any,
        anuncios: list[dict[str, str]],
    ) -> None:
        """Envía el clima, anuncios activos y alerta de faltantes al chat configurado."""
        activos = [
            str(anuncio.get("name", ""))
            for anuncio in anuncios
            if anuncio.get("status") == "ACTIVE"
        ]
        sin_configurar = [
            str(anuncio.get("name", ""))
            for anuncio in anuncios
            if self.reglas.obtener(str(anuncio.get("name", ""))) is None
        ]
        mensaje = (
            "Reporte Smart-Ads Retail\n\n"
            f"Clima: {contexto_clima.descripcion_clima}\n"
            f"Temperatura: {contexto_clima.temperatura if contexto_clima.temperatura is not None else 'Sin datos'} °C\n"
            f"Probabilidad de lluvia: {contexto_clima.probabilidad_lluvia:.0f}%\n\n"
            "Anuncios corriendo:\n"
            + ("\n".join(f"- {nombre}" for nombre in activos) or "- Ninguno")
            + "\n\nAlerta, anuncios Sin configurar:\n"
            + ("\n".join(f"- {nombre}" for nombre in sin_configurar) or "- Ninguno")
        )
        if not self.ajustes.TELEGRAM_CHAT_ID:
            logger.warning("No se puede enviar reporte: falta TELEGRAM_CHAT_ID")
            return
        await self._enviar_mensaje(mensaje)

    async def enviar_alerta(self, mensaje: str) -> None:
        """Envía una alerta operativa al chat autorizado."""
        if not self.ajustes.TELEGRAM_CHAT_ID:
            logger.warning("No se puede enviar alerta: falta TELEGRAM_CHAT_ID")
            return
        try:
            await self._enviar_mensaje("ALERTA Smart-Ads Retail\n\n" + mensaje)
        except Exception:
            logger.exception("No se pudo enviar la alerta operativa por Telegram")

    async def _enviar_mensaje(self, mensaje: str) -> None:
        """Envía un mensaje usando el bot asíncrono de la aplicación."""
        from telegram import Bot

        async with Bot(self.ajustes.TELEGRAM_BOT_TOKEN) as bot:
            await bot.send_message(chat_id=self.ajustes.TELEGRAM_CHAT_ID, text=mensaje)

    @classmethod
    def _parsear_plantilla(cls, texto: str, nombre: str) -> dict[str, Any] | None:
        """Extrae todos los campos de la plantilla mediante expresiones regulares."""
        def campo(expresion: str) -> str | None:
            coincidencia = re.search(expresion, texto, re.IGNORECASE)
            return coincidencia.group(1).strip() if coincidencia else None

        desactivar = campo(r"Desactivar anuncio:\s*\[([^]]*)\]")
        if desactivar is None:
            return None
        if desactivar == ".":
            return {}
        valores = {
            "hora_activacion": campo(r"Activación:\s*\[([^]]*)\]"),
            "hora_desactivacion": campo(r"Desactivación:\s*\[([^]]*)\]"),
            "temperatura_minima": campo(r"Temperatura.*?minima:\s*\[([^]]*)\]"),
            "temperatura_maxima": campo(r"minima:.*?maxima\s*\[([^]]*)\]"),
            "lluvia_minima": campo(r"lluvia minima:\s*\[([^]]*)\]"),
            "lluvia_maxima": campo(r"lluvia minima:.*?maxima:\s*\[([^]]*)\]"),
        }
        dias: dict[str, bool] = {}
        for dia in ("L", "MA", "MI", "J", "V", "S", "D"):
            valor = campo(rf"\b{dia}\s*\[([^]]*)\]")
            if valor is None:
                return None
            dias[dia] = valor != "."
        if all(not valor for valor in valores.values()) and not any(dias.values()):
            return {}
        if any(valor in (None, "") for valor in valores.values()):
            return None
        try:
            return {
                "activo": True,
                **valores,
                "temperatura_minima": float(valores["temperatura_minima"]),
                "temperatura_maxima": float(valores["temperatura_maxima"]),
                "lluvia_minima": float(valores["lluvia_minima"]),
                "lluvia_maxima": float(valores["lluvia_maxima"]),
                "dias": dias,
            }
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _estado_configuracion(configuracion: dict[str, Any] | None) -> str:
        """Describe la configuración sin confundirla con el estado de Meta."""
        if not isinstance(configuracion, dict):
            return "Sin configurar"
        if configuracion.get("activo") is False:
            return "Configurado - Desactivado"
        return "Configurado - Activo"