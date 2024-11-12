import itertools
import shutil
from pathlib import Path

from pixel_font_knife import glyph_file_util

from tools import configs
from tools.configs import path_define
from tools.configs.font import FontConfig


def _is_empty_dir(path: Path) -> bool:
    for item_path in path.iterdir():
        if item_path.name == '.DS_Store':
            continue
        return False
    return True


def format_glyphs(font_config: FontConfig):
    for width_mode_dir_name in itertools.chain(['common'], configs.width_modes):
        width_mode_dir = path_define.patch_glyphs_dir.joinpath(str(font_config.font_size), width_mode_dir_name)
        context = glyph_file_util.load_context(width_mode_dir)
        glyph_file_util.normalize_context(context, width_mode_dir, configs.language_file_flavors)

        for file_dir, _, _ in width_mode_dir.walk(top_down=False):
            if _is_empty_dir(file_dir):
                shutil.rmtree(file_dir)
