"""Notificador de reportes mediante Telegram Bot API."""

import logging
import re
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.config.gestor_reportes import GestorReportes
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

    PREFIJO_REPORTE: str = "reporte_"

    def __init__(
        self,
        ajustes: Configuracion = configuracion,
        reglas: Any = None,
        meta: Any = None,
        funcion_medicion: Any = None,
        gestor_reportes: Any = None,
        funcion_reporte: Any = None,
    ) -> None:
        from src.config.reglas_negocio import GestorReglasNegocio

        self.ajustes = ajustes
        self.reglas = reglas or GestorReglasNegocio(
            Path(__file__).parents[1] / "config" / "reglas_conjuntos.json",
            clave_principal="conjuntos",
        )
        self.meta = meta
        self.funcion_medicion = funcion_medicion
        self.gestor_reportes = gestor_reportes or GestorReportes(
            Path(__file__).parents[1] / "config" / "horarios_reportes.json"
        )
        self.funcion_reporte = funcion_reporte
        self.ultimo_estado: dict[str, Any] = {"clima": None, "anuncios": []}
        if self.ajustes.ENVIAR_TELEGRAM:
            self.ajustes.validar_telegram()

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
        aplicacion.add_handler(CommandHandler("adsinfo", self.adsinfo))
        aplicacion.add_handler(CommandHandler("medir", self.medir))
        aplicacion.add_handler(CommandHandler("reportes", self.reportes))
        aplicacion.add_handler(CommandHandler("setreporte", self.setreporte))
        aplicacion.add_handler(CommandHandler("delreporte", self.delreporte))
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
            "/adsconfig [nombre_anuncio] - Muestra la plantilla de configuración.\n"
            "/adsinfo - Muestra el reporte actual con clima y estado de anuncios.\n"
            "/medir - Fuerza una medición completa ahora.\n"
            "/reportes - Lista los horarios de reporte diario.\n"
            "/setreporte HH:MM - Agrega un horario de reporte diario.\n"
            "/delreporte HH:MM - Elimina un horario de reporte diario."
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

    async def adsinfo(self, actualizacion: Any, contexto: Any) -> None:
        """Reporte bajo demanda: clima y estado de anuncios desde la última lectura."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        clima = self.ultimo_estado["clima"]
        anuncios = self.ultimo_estado["anuncios"]
        if clima is None or not anuncios:
            texto_aviso = "Aún no hay datos disponibles."
            minutos = self._calcular_proxima_lectura(contexto)
            if minutos is not None:
                texto_aviso += (
                    f"\nLa próxima lectura será en aproximadamente "
                    f"{minutos} minuto{'s' if minutos != 1 else ''}."
                )
            else:
                texto_aviso += "\nEl próximo ciclo ocurrirá en breve."
            await actualizacion.message.reply_text(texto_aviso)
            return
        await actualizacion.message.reply_text(
            self._construir_reporte(clima, anuncios)
        )

    async def medir(self, actualizacion: Any, contexto: Any) -> None:
        """Fuerza una medición completa ahora y responde el reporte fresco."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        mensaje = getattr(actualizacion, "message", None)
        if mensaje is None:
            return
        if self.funcion_medicion is None:
            await mensaje.reply_text(
                "La medición forzada no está configurada en este bot."
            )
            return
        try:
            await self.funcion_medicion(contexto)
        except Exception:
            logger.exception("No se pudo completar la medición forzada")
            await mensaje.reply_text(
                "No se pudo completar la medición. Revisá los logs."
            )
            return
        clima = self.ultimo_estado["clima"]
        anuncios = self.ultimo_estado["anuncios"]
        if clima is None or not anuncios:
            await mensaje.reply_text(
                "Medición realizada, pero aún no hay datos disponibles.\n"
                "El próximo ciclo ocurrirá en breve."
            )
            return
        await mensaje.reply_text(self._construir_reporte(clima, anuncios))

    async def reportes(self, actualizacion: Any, contexto: Any) -> None:
        """Lista los horarios de reporte configurados."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        try:
            horarios = self.gestor_reportes.listar()
        except (OSError, ValueError, KeyError):
            logger.exception("No se pudo leer los horarios de reporte")
            await actualizacion.message.reply_text(
                "No se pudo leer la configuración de horarios. Revisá el archivo."
            )
            return
        if not horarios:
            await actualizacion.message.reply_text(
                "No hay reportes diarios configurados."
            )
            return
        lineas = "\n".join(f"- {horario}" for horario in horarios)
        await actualizacion.message.reply_text(
            "HORARIOS DE REPORTE\n\n" + lineas
        )

    async def setreporte(self, actualizacion: Any, contexto: Any) -> None:
        """Agrega un horario de reporte (ej: /setreporte 6:00)."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        texto = actualizacion.message.text if actualizacion.message is not None else ""
        argumento = texto.split(None, 1)[1].strip() if len(texto.split(None, 1)) > 1 else ""
        try:
            exito, mensaje = self.gestor_reportes.agregar(argumento)
        except (OSError, ValueError, KeyError):
            logger.exception("No se pudo guardar el horario de reporte")
            await actualizacion.message.reply_text(
                "No se pudo guardar el horario. Revisá los logs."
            )
            return
        if exito:
            self.reprogramar_reportes(contexto.job_queue)
        await actualizacion.message.reply_text(mensaje)

    async def delreporte(self, actualizacion: Any, contexto: Any) -> None:
        """Elimina un horario de reporte (ej: /delreporte 6:00)."""
        if not await self._exigir_chat_autorizado(actualizacion):
            return
        texto = actualizacion.message.text if actualizacion.message is not None else ""
        argumento = texto.split(None, 1)[1].strip() if len(texto.split(None, 1)) > 1 else ""
        try:
            exito, mensaje = self.gestor_reportes.eliminar(argumento)
        except (OSError, ValueError, KeyError):
            logger.exception("No se pudo eliminar el horario de reporte")
            await actualizacion.message.reply_text(
                "No se pudo eliminar el horario. Revisá los logs."
            )
            return
        if exito:
            self.reprogramar_reportes(contexto.job_queue)
        await actualizacion.message.reply_text(mensaje)

    def reprogramar_reportes(self, cola_jobs: Any) -> None:
        """Recrea los jobs de reporte según los horarios guardados."""
        if cola_jobs is None or self.funcion_reporte is None:
            logger.warning("Sin JobQueue o función de reporte; no se reprograman reportes")
            return
        for job in cola_jobs.jobs():
            nombre = getattr(job, "name", "") or ""
            if nombre.startswith(self.PREFIJO_REPORTE):
                job.schedule_removal()
        zona = self._zona_horaria(self.ajustes.ZONA_HORARIA)
        for horario in self.gestor_reportes.listar():
            horas, minutos = horario.split(":")
            nombre = f"{self.PREFIJO_REPORTE}{horario.replace(':', '')}"
            cola_jobs.run_daily(
                self.funcion_reporte,
                time=time(
                    hour=int(horas),
                    minute=int(minutos),
                    tzinfo=zona,
                ),
                name=nombre,
            )
            logger.info("Reporte diario programado a las %s", horario)

    @classmethod
    def _zona_horaria(cls, nombre_zona: str) -> ZoneInfo:
        """Devuelve la zona IANA configurada, con respaldo si es inválida."""
        try:
            return ZoneInfo(nombre_zona)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning(
                "ZONA_HORARIA inválida '%s'; se usa America/Argentina/Buenos_Aires",
                nombre_zona,
            )
            return ZoneInfo("America/Argentina/Buenos_Aires")

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
                logger.info("Conjunto '%s' desactivado: regla conservada, conjunto pausado", nombre)
                await actualizacion.message.reply_text(
                    f"La configuración de '{nombre}' se conservó, el conjunto quedó pausado "
                    "y la campaña permanece activa."
                )
            else:
                self.reglas.guardar(nombre, configuracion)
                logger.info("Configuración de '%s' guardada en reglas", nombre)
                await actualizacion.message.reply_text(
                    f"Configuración de '{nombre}' guardada correctamente."
                )
        except (ErrorMetaAds, ValueError, KeyError, OSError) as error:
            logger.exception("No se pudo procesar la configuración de '%s'", nombre)
            if actualizacion.message is not None:
                if isinstance(error, ErrorMetaAds):
                    await actualizacion.message.reply_text(
                        "Meta rechazó la operación, no se guardó ningún cambio.\n"
                        + str(error)
                    )
                else:
                    await actualizacion.message.reply_text(
                        "No se pudo guardar la configuración. Revisá los valores y volvé a intentarlo."
                    )
            return
        contexto.user_data.pop("anuncio_configuracion", None)

    async def _exigir_chat_autorizado(self, actualizacion: Any) -> bool:
        """Permite operar únicamente a chats autorizados (TELEGRAM_CHAT_ID)."""
        chat = getattr(actualizacion, "effective_chat", None)
        identificador_chat = getattr(chat, "id", None)
        autorizado = str(identificador_chat) in self.ajustes.chats_autorizados
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
            dia: ("." if dias.get(dia, False) else "")
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

    def _construir_reporte(
        self, contexto_clima: Any, anuncios: list[dict[str, str]]
    ) -> str:
        """Construye el texto del reporte para uso manual y automático."""
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
        return (
            "Reporte Smart-Ads Retail\n\n"
            f"Clima: {contexto_clima.descripcion_clima}\n"
            f"Temperatura: {contexto_clima.temperatura if contexto_clima.temperatura is not None else 'Sin datos'} °C\n"
            f"Probabilidad de lluvia: {contexto_clima.probabilidad_lluvia:.0f}%\n\n"
            "Anuncios corriendo:\n"
            + ("\n".join(f"- {nombre}" for nombre in activos) or "- Ninguno")
            + "\n\nAlerta, anuncios Sin configurar:\n"
            + ("\n".join(f"- {nombre}" for nombre in sin_configurar) or "- Ninguno")
        )

    async def enviar_reporte_diario(
        self,
        contexto_clima: Any,
        anuncios: list[dict[str, str]],
    ) -> None:
        """Envía el reporte a todos los chats autorizados."""
        if not self.ajustes.chats_autorizados:
            logger.warning("No se puede enviar reporte: no hay chats autorizados")
            return
        mensaje = self._construir_reporte(contexto_clima, anuncios)
        await self._enviar_mensaje(mensaje)
        logger.info(
            "Reporte diario enviado a %d chat(s)", len(self.ajustes.chats_autorizados)
        )

    async def enviar_alerta(self, mensaje: str) -> None:
        """Envía una alerta operativa a los chats autorizados."""
        if not self.ajustes.chats_autorizados:
            logger.warning("No se puede enviar alerta: no hay chats autorizados")
            return
        try:
            await self._enviar_mensaje("ALERTA Smart-Ads Retail\n\n" + mensaje)
            logger.info(
                "Alerta operativa enviada a %d chat(s)", len(self.ajustes.chats_autorizados)
            )
        except Exception:
            logger.exception("No se pudo enviar la alerta operativa por Telegram")

    async def _enviar_mensaje(self, mensaje: str) -> None:
        """Envía un mensaje a todos los chats autorizados."""
        from telegram import Bot

        async with Bot(self.ajustes.TELEGRAM_BOT_TOKEN) as bot:
            for chat_id in self.ajustes.chats_autorizados:
                try:
                    await bot.send_message(chat_id=chat_id, text=mensaje)
                except Exception:
                    logger.exception("No se pudo enviar mensaje a chat_id=%s", chat_id)

    @classmethod
    def _calcular_proxima_lectura(cls, contexto: Any) -> int | None:
        """Devuelve los minutos hasta la próxima lectura, o None si no se puede saber."""
        job_queue = getattr(contexto, "job_queue", None)
        if job_queue is None:
            return None
        ahora = datetime.now(timezone.utc)
        proximas = []
        for job in job_queue.jobs():
            nombre = getattr(job, "name", None) or ""
            next_t = getattr(job, "next_t", None)
            if not next_t:
                continue
            if nombre == "evaluar_anuncios" or nombre.startswith(cls.PREFIJO_REPORTE):
                proximas.append(next_t)
        if not proximas:
            return None
        diff = min(proximas) - ahora
        total_segundos = max(diff.total_seconds(), 0)
        if total_segundos <= 0:
            return None
        minutos = int(total_segundos // 60)
        if total_segundos % 60 > 30:
            minutos += 1
        return minutos if minutos > 0 else 1

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
            dias[dia] = valor == "."
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