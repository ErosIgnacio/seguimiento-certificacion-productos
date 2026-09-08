from __future__ import annotations

import unittest
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
WIX = RAIZ / "installer" / "msi" / "CertificacionCarga.wxs"
SCRIPT = RAIZ / "scripts" / "build_msi.ps1"
SPEC = RAIZ / "certificacion_carga.spec"


class PruebasContratoMsi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wix = WIX.read_text(encoding="utf-8")
        cls.script = SCRIPT.read_text(encoding="utf-8")
        cls.spec = SPEC.read_text(encoding="utf-8")

    def test_instala_onedir_por_usuario(self):
        self.assertIn('Scope="perUser"', self.wix)
        self.assertIn('Id="LocalAppDataFolder"', self.wix)
        self.assertIn('Name="certificacion_carga"', self.wix)
        self.assertNotIn("ProgramFilesFolder", self.wix)

    def test_crea_accesos_directos_en_escritorio_y_menu(self):
        self.assertIn('Id="DesktopShortcut"', self.wix)
        self.assertIn('Directory="DesktopFolder"', self.wix)
        self.assertIn('Id="StartMenuShortcut"', self.wix)
        self.assertIn('Directory="ProgramMenuVendorFolder"', self.wix)

    def test_configuracion_plana_no_queda_en_onedir(self):
        self.assertNotIn("config.json", self.spec)
        self.assertIn("--provision-config-and-delete", self.wix)
        self.assertIn('HideTarget="yes"', self.wix)
        self.assertIn("PlainConfigs", self.script)

    def test_construccion_usa_temporal_y_wix_local_fijado(self):
        self.assertIn("CertificacionCargaMsi", self.script)
        self.assertIn("$DotNet tool restore", self.script)
        manifiesto = (RAIZ / ".config" / "dotnet-tools.json").read_text(
            encoding="utf-8"
        )
        self.assertIn('"version": "5.0.2"', manifiesto)


if __name__ == "__main__":
    unittest.main()
