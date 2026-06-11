"""
chm_de_lidar.py
===============
Gera o Canopy Height Model (CHM) a partir de uma nuvem de pontos LiDAR
(.las ou .laz), sem dependência de ferramentas externas além do Python.

O que é o CHM?
--------------
  CHM = DSM − DTM

  DSM (Digital Surface Model) — altura do retorno mais alto por pixel (dossel,
                                 telhados, objetos).
  DTM (Digital Terrain Model) — altura do retorno mais baixo por pixel
                                 (aproximação do solo).
  CHM — altura da vegetação/objetos acima do solo.

Funcionalidades
---------------
  - Lê arquivos .las e .laz (via laspy)
  - Gera DSM, DTM e CHM como GeoTIFF
  - Exporta estatísticas de cobertura vegetal (% acima de limiares)
  - Gera mapa de cobertura do dossel (binário: vegetado/não vegetado)
  - Visualização opcional do CHM em PNG

Dependências
------------
  pip install laspy lazrs-python rasterio numpy matplotlib
  (lazrs-python é necessário para ler arquivos .laz comprimidos)
"""

from __future__ import annotations
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS

try:
    import laspy
except ImportError:
    raise ImportError(
        "laspy não encontrado. Instale com: pip install laspy lazrs-python"
    )

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════════════════════════

CONFIG = {
    # Arquivo LiDAR de entrada (.las ou .laz)
    "arquivo_las":      r"caminho/para/nuvem_pontos.las",

    # Pasta de saída (criada automaticamente)
    "dir_saida":        r"saida_chm/",

    # Resolução do raster de saída (metros)
    # 0.5m → altamente detalhado (indicado para nuvens densas > 10 pts/m²)
    # 1.0m → uso geral
    # 2.0m → nuvens esparsas
    "resolucao_m":      1.0,

    # EPSG do sistema de coordenadas projetado de saída
    # Se o .las já tiver CRS embutido, informe o mesmo aqui para garantir
    "epsg_saida":       31983,

    # Limiares de altura para análise de vegetação
    "limiar_arbusto_m": 0.5,   # acima disso: vegetação rasteira/arbusto
    "limiar_arvore_m":  3.0,   # acima disso: dossel arbóreo

    # Exportar rasters intermediários (DSM e DTM)?
    "exportar_dsm_dtm": True,

    # Gerar visualização PNG do CHM?
    "gerar_png":        True,

    # Paleta de cores do PNG: "viridis", "YlGn", "terrain", "hot_r"
    "paleta_png":       "YlGn",
}

# ══════════════════════════════════════════════════════════════════════════════
# FUNÇÕES
# ══════════════════════════════════════════════════════════════════════════════

def ler_las(caminho: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Lê nuvem de pontos LiDAR. Retorna arrays (x, y, z) como float64.
    Suporta .las e .laz (requer lazrs-python para .laz).
    """
    cam = Path(caminho)
    print(f"  Lendo {cam.name}...")
    with laspy.open(cam) as f:
        las = f.read()
    return np.array(las.x), np.array(las.y), np.array(las.z)


def construir_dsm_dtm(xs, ys, zs, resolucao_m: float):
    """
    Constrói DSM (máx por pixel) e DTM (mín por pixel) a partir da nuvem.

    Para nuvens não classificadas, o DTM representa o retorno mais baixo,
    que é uma aproximação aceitável para áreas sem obstruções densas.
    Para maior precisão do DTM, use nuvens classificadas e filtre apenas
    os pontos de solo (classification == 2 no padrão LAS).

    Retorna: dsm, dtm (arrays 2D float32), transform, (n_rows, n_cols)
    """
    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()

    n_cols = int(np.ceil((x_max - x_min) / resolucao_m)) + 1
    n_rows = int(np.ceil((y_max - y_min) / resolucao_m)) + 1

    dsm = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
    dtm = np.full((n_rows, n_cols), np.nan, dtype=np.float32)

    col_idx = np.clip(((xs - x_min) / resolucao_m).astype(int), 0, n_cols - 1)
    row_idx = np.clip(((y_max - ys) / resolucao_m).astype(int), 0, n_rows - 1)

    print(f"  Construindo DSM/DTM ({n_rows}×{n_cols} pixels, {resolucao_m}m)...")
    for r, c, z in zip(row_idx, col_idx, zs):
        if np.isnan(dsm[r, c]) or z > dsm[r, c]:
            dsm[r, c] = z
        if np.isnan(dtm[r, c]) or z < dtm[r, c]:
            dtm[r, c] = z

    transform = from_origin(x_min, y_max, resolucao_m, resolucao_m)
    return dsm, dtm, transform, (n_rows, n_cols)


def salvar_raster(arr: np.ndarray, caminho: str | Path,
                  transform, epsg: int, nodata: float = -9999.0):
    """Salva array 2D como GeoTIFF com compressão LZW."""
    arr_out = np.where(np.isnan(arr), nodata, arr).astype("float32")
    with rasterio.open(
        caminho, "w", driver="GTiff", dtype="float32",
        count=1, width=arr.shape[1], height=arr.shape[0],
        crs=CRS.from_epsg(epsg), transform=transform,
        nodata=nodata, compress="lzw",
    ) as dst:
        dst.write(arr_out, 1)


def estatisticas_chm(chm: np.ndarray, limiar_arbusto: float,
                     limiar_arvore: float) -> dict:
    """Calcula estatísticas de cobertura e altura a partir do CHM."""
    validos = chm[~np.isnan(chm) & (chm >= 0)]
    if len(validos) == 0:
        return {}
    total = len(validos)
    veg_baixa = np.sum((validos >= limiar_arbusto) & (validos < limiar_arvore))
    veg_alta  = np.sum(validos >= limiar_arvore)
    return {
        "pixels_totais":       total,
        "altura_max_m":        round(float(np.nanmax(validos)), 2),
        "altura_media_m":      round(float(np.mean(validos)), 2),
        "altura_mediana_m":    round(float(np.median(validos)), 2),
        "cobertura_arbusto_pct": round(veg_baixa / total * 100, 1),
        "cobertura_arvore_pct":  round(veg_alta  / total * 100, 1),
        f"media_acima_{limiar_arvore}m": round(
            float(np.mean(validos[validos >= limiar_arvore]))
            if veg_alta > 0 else np.nan, 2),
    }


def gerar_png(chm: np.ndarray, caminho_png: str | Path,
              paleta: str = "YlGn", resolucao_m: float = 1.0):
    """Salva visualização do CHM como PNG com barra de cores."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        chm_plot = np.where(chm < 0, np.nan, chm)
        vmax = float(np.nanpercentile(chm_plot, 98))

        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.imshow(chm_plot, cmap=paleta, vmin=0, vmax=vmax,
                       interpolation="nearest")
        cbar = plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cbar.set_label("Altura (m)", fontsize=10)
        ax.set_title(f"CHM — resolução {resolucao_m}m", fontsize=12)
        ax.set_xlabel("Coluna (pixel)")
        ax.set_ylabel("Linha (pixel)")
        plt.tight_layout()
        fig.savefig(caminho_png, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  PNG salvo: {caminho_png}")
    except Exception as e:
        print(f"  ⚠ Não foi possível gerar PNG: {e}")


def main():
    dir_saida = Path(CONFIG["dir_saida"])
    dir_saida.mkdir(parents=True, exist_ok=True)

    xs, ys, zs = ler_las(CONFIG["arquivo_las"])
    print(f"  Pontos lidos: {len(xs):,}")

    dsm, dtm, transform, _ = construir_dsm_dtm(xs, ys, zs, CONFIG["resolucao_m"])

    chm = dsm - dtm
    chm[chm < 0] = 0          # remove artefatos negativos

    # Salvar CHM
    cam_chm = dir_saida / "chm.tif"
    salvar_raster(chm, cam_chm, transform, CONFIG["epsg_saida"])
    print(f"  ✓ CHM salvo: {cam_chm}")

    # Salvar DSM e DTM (opcionais)
    if CONFIG["exportar_dsm_dtm"]:
        salvar_raster(dsm, dir_saida / "dsm.tif", transform, CONFIG["epsg_saida"])
        salvar_raster(dtm, dir_saida / "dtm.tif", transform, CONFIG["epsg_saida"])
        print(f"  ✓ DSM e DTM salvos em {dir_saida}")

    # Mapa binário de cobertura do dossel
    cobertura = (chm >= CONFIG["limiar_arvore_m"]).astype(np.uint8)
    salvar_raster(cobertura.astype(np.float32),
                  dir_saida / "cobertura_dossel.tif", transform,
                  CONFIG["epsg_saida"], nodata=255)
    print(f"  ✓ Mapa de cobertura salvo.")

    # Estatísticas
    stats = estatisticas_chm(chm, CONFIG["limiar_arbusto_m"],
                              CONFIG["limiar_arvore_m"])
    print("\n  ── Estatísticas do CHM ──────────────────")
    for k, v in stats.items():
        print(f"     {k:<35} {v}")

    # Visualização
    if CONFIG["gerar_png"]:
        gerar_png(chm, dir_saida / "chm.png", CONFIG["paleta_png"],
                  CONFIG["resolucao_m"])


if __name__ == "__main__":
    main()
