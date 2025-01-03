from pixel_font_knife import glyph_mapping_util

from tools import configs
from tools.configs.font import FontConfig
from tools.services import update_service, check_service


def main():
    update_service.setup_ark_pixel_glyphs()

    mappings = [glyph_mapping_util.load_mapping(mapping_file_path) for mapping_file_path in configs.mapping_file_paths]
    for font_size in configs.font_sizes:
        font_config = FontConfig.load(font_size)
        check_service.check_font_config(font_config)
        check_service.check_glyph_files(font_config, mappings)


if __name__ == '__main__':
    main()
