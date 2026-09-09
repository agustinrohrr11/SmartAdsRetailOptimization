from datetime import date
import unittest
from unittest.mock import Mock

from src.config.settings import Configuracion
from src.core.brain import MotorDecisiones
from src.services.context_api import DatosContexto, GestorContexto
from src.services.meta_api import GestorMetaAds
from src.services.whatsapp_bot import NotificadorWhatsApp


class TestMotorDecisiones(unittest.TestCase):
    def test_lluvia_activa_estofado_y_pausa_asado(self) -> None:
        acciones = MotorDecisiones().obtener_acciones(
            DatosContexto(61, False, False)
        )
        self.assertEqual(
            [(accion.nombre_campana, accion.accion) for accion in acciones],
            [("Asado", "PAUSAR"), ("Estofado", "ACTIVAR")],
        )

    def test_fin_de_semana_aumenta_asado(self) -> None:
        acciones = MotorDecisiones().obtener_acciones(
            DatosContexto(0, True, False)
        )
        self.assertEqual(acciones[1].factor_presupuesto, 1.3)

    def test_quincena_activa_economicos(self) -> None:
        acciones = MotorDecisiones().obtener_acciones(
            DatosContexto(0, False, True)
        )
        self.assertEqual(acciones[0].nombre_campana, "Económicos/Picada")


class TestGestorContexto(unittest.TestCase):
    def test_parsea_open_meteo_y_ultimo_dia_del_mes(self) -> None:
        respuesta = Mock()
        respuesta.json.return_value = {
            "daily": {
                "precipitation_probability_max": [70],
                "weather_code": [61],
                "temperature_2m_max": [20],
            }
        }
        cliente = Mock()
        cliente.get.return_value = respuesta
        contexto = GestorContexto(
            cliente_http=cliente,
            fecha_actual=date(2026, 2, 28),
        ).obtener_contexto()
        self.assertEqual(contexto.probabilidad_lluvia, 70)
        self.assertTrue(contexto.es_quincena_o_fin_de_mes)
        cliente.get.assert_called_once()


class TestIntegracionesSeguras(unittest.TestCase):
    def test_meta_simulada_no_requiere_credenciales(self) -> None:
        gestor = GestorMetaAds(Configuracion(MODO_SIMULACION=True))
        gestor.activar_campana("Asado")
        gestor.modificar_presupuesto("Asado", 30)

    def test_twilio_desactivado_no_crea_cliente(self) -> None:
        notificador = NotificadorWhatsApp(
            Configuracion(ENVIAR_WHATSAPP=False)
        )
        self.assertIsNone(
            notificador.enviar_reporte(DatosContexto(0, False, False), [])
        )
        self.assertIsNone(notificador.cliente)

    def test_twilio_se_puede_habilitar_con_meta_simulada(self) -> None:
        cliente = Mock()
        cliente.messages.create.return_value.sid = "SM-prueba"
        notificador = NotificadorWhatsApp(
            Configuracion(MODO_SIMULACION=True, ENVIAR_WHATSAPP=True),
            cliente=cliente,
        )
        resultado = notificador.enviar_reporte(
            DatosContexto(0, False, False), []
        )
        self.assertEqual(resultado, "SM-prueba")
        cliente.messages.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
