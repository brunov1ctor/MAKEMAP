"""Pacote de efeitos animados do pincel.

Para adicionar um novo efeito: crie um arquivo neste diretório com uma função
de assinatura `(painter, cache, layer, path, bounds, color) -> None` e
registre-a em ANIMATED_EFFECTS e EFFECT_COLORS abaixo.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QColor

from .nevoa import paint_nevoa
from .poeira import paint_poeira
from .polen import paint_polen
from .insetos import paint_insetos
from .cinzas import paint_cinzas
from .folhas import paint_folhas
from .esporos import paint_esporos
from .chuva import paint_chuva
from .garoa import paint_garoa
from .neve import paint_neve
from .tempestade_areia import paint_tempestade_areia
from .fumaca import paint_fumaca
from .gas_toxico import paint_gas_toxico
from .cinzas_vulcanicas import paint_cinzas_vulcanicas
from .regiao_fria import paint_regiao_fria
from .regiao_quente import paint_regiao_quente
from .regiao_magica import paint_regiao_magica
from .regiao_radioativa import paint_regiao_radioativa
from .regiao_sonho import paint_regiao_sonho
from .regiao_amaldicoada import paint_regiao_amaldicoada
from .regiao_subaquatica import paint_regiao_subaquatica

ANIMATED_EFFECTS: dict[str, Callable] = {
    "Névoa": paint_nevoa,
    "Poeira": paint_poeira,
    "Pólen": paint_polen,
    "Insetos": paint_insetos,
    "Cinzas": paint_cinzas,
    "Folhas": paint_folhas,
    "Chuva localizada": paint_chuva,
    "Garoa": paint_garoa,
    "Neve": paint_neve,
    "Tempestade de areia": paint_tempestade_areia,
    "Fumaça": paint_fumaca,
    "Gás tóxico": paint_gas_toxico,
    "Esporos": paint_esporos,
    "Cinzas vulcânicas": paint_cinzas_vulcanicas,
    "Região fria": paint_regiao_fria,
    "Região quente": paint_regiao_quente,
    "Região mágica": paint_regiao_magica,
    "Região radioativa": paint_regiao_radioativa,
    "Região de sonho": paint_regiao_sonho,
    "Região amaldiçoada": paint_regiao_amaldicoada,
    "Região subaquática": paint_regiao_subaquatica,
}

EFFECT_COLORS: dict[str, QColor] = {
    "Névoa": QColor(210, 220, 230),
    "Poeira": QColor(200, 190, 160),
    "Insetos": QColor(255, 240, 180),
    "Cinzas": QColor(120, 110, 110),
    "Folhas": QColor(110, 150, 70),
    "Chuva localizada": QColor(150, 180, 210),
    "Garoa": QColor(170, 190, 210),
    "Neve": QColor(240, 245, 255),
    "Tempestade de areia": QColor(200, 170, 110),
    "Fumaça": QColor(120, 120, 120),
    "Esporos": QColor(150, 210, 160),
    "Cinzas vulcânicas": QColor(60, 55, 55),
    "Região fria": QColor(190, 220, 255),
    "Região quente": QColor(255, 150, 90),
    "Região mágica": QColor(160, 140, 255),
    "Região radioativa": QColor(160, 230, 90),
    "Região de sonho": QColor(230, 180, 255),
    "Região amaldiçoada": QColor(80, 60, 90),
    "Região subaquática": QColor(70, 170, 170),
}


def effect_color(key: str) -> QColor:
    return QColor(EFFECT_COLORS.get(key, QColor(200, 200, 200)))
