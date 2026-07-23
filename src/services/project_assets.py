"""Copiar arquivos escolhidos/arrastados para dentro da pasta do projeto.

Sem isso, cada editor (Itens, Habilidades, Mobs, Construções, Dungeons)
gravava o caminho absoluto do arquivo original direto no banco — se o
usuário movesse ou apagasse o arquivo original, a referência quebrava
silenciosamente. Este módulo é o único lugar que sabe copiar; os
consumidores só leem/escrevem um caminho utilizável.
"""

from __future__ import annotations

import shutil
from pathlib import Path


def import_asset(project_dir: Path | str | None, source: str, folder_name: str, stem: str) -> str:
    """Copia `source` para <project_dir>/<folder_name>/<stem><ext>.

    Remove qualquer arquivo antigo do mesmo `stem` com outra extensão (troca
    de .png para .jpg não deixa o arquivo velho para trás). Devolve o
    caminho relativo a `project_dir`, com barras normais, para gravar no
    banco/JSON. Sem projeto aberto (`project_dir` falsy) ou sem `source`,
    devolve `source` sem alterar — mantém a escolha do usuário sem tentar
    persistir uma cópia que não tem onde morar.
    """
    if not project_dir or not source:
        return source
    folder = Path(project_dir) / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{stem}{Path(source).suffix.lower()}"
    for old in folder.glob(f"{stem}.*"):
        if old != dest:
            old.unlink(missing_ok=True)
    if Path(source).resolve() != dest.resolve():
        shutil.copyfile(source, dest)
    return f"{folder_name}/{dest.name}"


def resolve_asset_path(project_dir: Path | str | None, stored_path: str) -> str:
    """Caminho gravado no banco -> caminho absoluto utilizável (QPixmap,
    QFileInfo, etc). Caminhos relativos (o formato que `import_asset`
    produz) são resolvidos contra `project_dir`; caminhos já absolutos
    (dados legados de antes desta mudança, ou sem projeto aberto) voltam
    inalterados."""
    if not stored_path:
        return ""
    path = Path(stored_path)
    if path.is_absolute() or not project_dir:
        return stored_path
    return str(Path(project_dir) / path)
