import logging
import math
import os
import unicodedata

import unidata_blocks
from pixel_font_builder import FontBuilder, FontCollectionBuilder, Glyph, StyleName, SerifMode
from pixel_font_builder.opentype import Flavor

from scripts import configs
from scripts.configs import FontConfig, path_define
from scripts.utils import fs_util, glyph_util

logger = logging.getLogger('font-service')


def _parse_glyph_file_name(glyph_file_name: str) -> tuple[int, list[str]]:
    tokens = glyph_file_name.removesuffix('.png').split(' ')
    assert 1 <= len(tokens) <= 2, f"Glyph file name '{glyph_file_name}': illegal format"
    code_point = int(tokens[0], 16)
    language_flavors = []
    if len(tokens) == 2:
        language_flavor_tokens = tokens[1].lower().split(',')
        for language_flavor in configs.language_file_flavors:
            if language_flavor in language_flavor_tokens:
                language_flavors.append(language_flavor)
        assert len(language_flavors) == len(language_flavor_tokens), f"Glyph file name '{glyph_file_name}': unknown language flavors"
    return code_point, language_flavors


def format_patch_glyph_files(font_config: FontConfig):
    root_dir = os.path.join(path_define.patch_glyphs_dir, str(font_config.size))
    for width_mode_dir_name in configs.width_mode_dir_names:
        width_mode_dir = os.path.join(root_dir, width_mode_dir_name)
        for glyph_file_from_dir, _, glyph_file_names in list(os.walk(width_mode_dir, topdown=False)):
            for glyph_file_name in glyph_file_names:
                if not glyph_file_name.endswith('.png'):
                    continue
                glyph_file_from_path = os.path.join(glyph_file_from_dir, glyph_file_name)
                if glyph_file_name == 'notdef.png':
                    east_asian_width = 'F'
                    block = None
                    glyph_file_to_dir = width_mode_dir
                else:
                    code_point, language_flavors = _parse_glyph_file_name(glyph_file_name)
                    c = chr(code_point)
                    east_asian_width = unicodedata.east_asian_width(c)
                    hex_name = f'{code_point:04X}'
                    glyph_file_name = f'{hex_name}{" " if len(language_flavors) > 0 else ""}{",".join(language_flavors)}.png'
                    block = unidata_blocks.get_block_by_code_point(code_point)
                    block_dir_name = f'{block.code_start:04X}-{block.code_end:04X} {block.name}'
                    glyph_file_to_dir = os.path.join(width_mode_dir, block_dir_name)
                    if block.code_start == 0x4E00:  # CJK Unified Ideographs
                        glyph_file_to_dir = os.path.join(glyph_file_to_dir, f'{hex_name[0:-2]}-')
                glyph_file_to_path = os.path.join(glyph_file_to_dir, glyph_file_name)
                glyph_data, glyph_width, glyph_height = glyph_util.load_glyph_data_from_png(glyph_file_from_path)

                if width_mode_dir_name == 'common' or width_mode_dir_name == 'monospaced':
                    assert glyph_height == font_config.size, f"Incorrect glyph data: '{glyph_file_from_path}'"

                    # H/Halfwidth or Na/Narrow
                    if east_asian_width == 'H' or east_asian_width == 'Na':
                        assert glyph_width == font_config.size / 2, f"Incorrect glyph data: '{glyph_file_from_path}'"
                    # F/Fullwidth or W/Wide
                    elif east_asian_width == 'F' or east_asian_width == 'W':
                        assert glyph_width == font_config.size, f"Incorrect glyph data: '{glyph_file_from_path}'"
                    # A/Ambiguous or N/Neutral
                    else:
                        assert glyph_width == font_config.size / 2 or glyph_width == font_config.size, f"Incorrect glyph data: '{glyph_file_from_path}'"

                    if block is not None:
                        if block.code_start == 0x4E00:  # CJK Unified Ideographs
                            if any(alpha != 0 for alpha in glyph_data[0]):
                                raise AssertionError(f"Incorrect glyph data: '{glyph_file_from_path}'")
                            if any(glyph_data[i][-1] != 0 for i in range(0, len(glyph_data))):
                                raise AssertionError(f"Incorrect glyph data: '{glyph_file_from_path}'")

                if width_mode_dir_name == 'proportional':
                    assert glyph_height >= font_config.size, f"Incorrect glyph data: '{glyph_file_from_path}'"
                    assert (glyph_height - font_config.size) % 2 == 0, f"Incorrect glyph data: '{glyph_file_from_path}'"

                    if glyph_height > font_config.line_height:
                        for i in range((glyph_height - font_config.line_height) // 2):
                            glyph_data.pop(0)
                            glyph_data.pop()
                    elif glyph_height < font_config.line_height:
                        for i in range((font_config.line_height - glyph_height) // 2):
                            glyph_data.insert(0, [0 for _ in range(glyph_width)])
                            glyph_data.append([0 for _ in range(glyph_width)])

                if glyph_file_to_path != glyph_file_from_path:
                    assert not os.path.exists(glyph_file_to_path), f"Glyph file duplication: '{glyph_file_from_path}'"
                    fs_util.make_dirs(glyph_file_to_dir)
                    os.remove(glyph_file_from_path)
                glyph_util.save_glyph_data_to_png(glyph_data, glyph_file_to_path)
                logger.info("Format glyph file: '%s'", glyph_file_to_path)

            entry_names = os.listdir(glyph_file_from_dir)
            if '.DS_Store' in entry_names:
                os.remove(os.path.join(glyph_file_from_dir, '.DS_Store'))
                entry_names.remove('.DS_Store')
            if len(entry_names) == 0:
                os.rmdir(glyph_file_from_dir)


class DesignContext:
    def __init__(self, registry: dict[str, dict[int, dict[str, tuple[str, str]]]]):
        self._registry = registry
        self._sequence_cacher: dict[str, list[int]] = {}
        self._alphabet_cacher: dict[str, set[str]] = {}
        self._character_mapping_cacher: dict[str, dict[int, str]] = {}
        self._glyph_file_infos_cacher: dict[str, list[tuple[str, str]]] = {}
        self._glyph_data_cacher: dict[str, tuple[list[list[int]], int, int]] = {}

    def patch(self, other: 'DesignContext'):
        self._sequence_cacher.clear()
        self._alphabet_cacher.clear()
        self._character_mapping_cacher.clear()
        self._glyph_file_infos_cacher.clear()
        for width_mode in configs.width_modes:
            self._registry[width_mode].update(other._registry[width_mode])

    def get_sequence(self, width_mode: str) -> list[int]:
        if width_mode in self._sequence_cacher:
            sequence = self._sequence_cacher[width_mode]
        else:
            sequence = list(self._registry[width_mode].keys())
            sequence.sort()
            self._sequence_cacher[width_mode] = sequence
        return sequence

    def get_alphabet(self, width_mode: str) -> set[str]:
        if width_mode in self._alphabet_cacher:
            alphabet = self._alphabet_cacher[width_mode]
        else:
            alphabet = set()
            for code_point in self._registry[width_mode]:
                if code_point < 0:
                    continue
                alphabet.add(chr(code_point))
            self._alphabet_cacher[width_mode] = alphabet
        return alphabet

    def get_character_mapping(self, width_mode: str, language_flavor: str) -> dict[int, str]:
        cache_name = f'{width_mode}#{language_flavor}'
        if cache_name in self._character_mapping_cacher:
            character_mapping = self._character_mapping_cacher[cache_name]
        else:
            character_mapping = {}
            for code_point, glyph_source in self._registry[width_mode].items():
                if code_point < 0:
                    continue
                character_mapping[code_point] = glyph_source.get(language_flavor, glyph_source['default'])[0]
            self._character_mapping_cacher[cache_name] = character_mapping
        return character_mapping

    def get_glyph_file_infos(self, width_mode: str, language_flavor: str = None) -> list[tuple[str, str]]:
        cache_name = f'{width_mode}#{"" if language_flavor is None else language_flavor}'
        if cache_name in self._glyph_file_infos_cacher:
            glyph_file_infos = self._glyph_file_infos_cacher[cache_name]
        else:
            glyph_file_infos = []
            sequence = self.get_sequence(width_mode)
            if language_flavor is None:
                language_flavors = configs.language_file_flavors
            else:
                language_flavors = [language_flavor]
            for language_flavor in language_flavors:
                for code_point in sequence:
                    glyph_source = self._registry[width_mode][code_point]
                    info = glyph_source.get(language_flavor, glyph_source['default'])
                    if info not in glyph_file_infos:
                        glyph_file_infos.append(info)
            self._glyph_file_infos_cacher[cache_name] = glyph_file_infos
        return glyph_file_infos

    def load_glyph_data(self, glyph_file_path: str) -> tuple[list[list[int]], int, int]:
        if glyph_file_path in self._glyph_data_cacher:
            glyph_data, glyph_width, glyph_height = self._glyph_data_cacher[glyph_file_path]
        else:
            glyph_data, glyph_width, glyph_height = glyph_util.load_glyph_data_from_png(glyph_file_path)
            self._glyph_data_cacher[glyph_file_path] = glyph_data, glyph_width, glyph_height
            logger.info("Load glyph file: '%s'", glyph_file_path)
        return glyph_data, glyph_width, glyph_height


def collect_glyph_files(font_config: FontConfig, glyphs_dir: str) -> DesignContext:
    root_dir = os.path.join(glyphs_dir, str(font_config.size))

    cellar = {}
    for width_mode_dir_name in configs.width_mode_dir_names:
        cellar[width_mode_dir_name] = {}
        width_mode_dir = os.path.join(root_dir, width_mode_dir_name)
        for glyph_file_dir, _, glyph_file_names in os.walk(width_mode_dir):
            for glyph_file_name in glyph_file_names:
                if not glyph_file_name.endswith('.png'):
                    continue
                glyph_file_path = os.path.join(glyph_file_dir, glyph_file_name)
                if glyph_file_name == 'notdef.png':
                    code_point = -1
                    language_flavors = []
                    glyph_name = '.notdef'
                else:
                    code_point, language_flavors = _parse_glyph_file_name(glyph_file_name)
                    glyph_name = f'uni{code_point:04X}'
                if code_point not in cellar[width_mode_dir_name]:
                    cellar[width_mode_dir_name][code_point] = {}
                if len(language_flavors) > 0:
                    glyph_name = f'{glyph_name}-{language_flavors[0]}'
                else:
                    language_flavors.append('default')
                for language_flavor in language_flavors:
                    assert language_flavor not in cellar[width_mode_dir_name][code_point], f"Glyph flavor already exists: '{code_point:04X}' '{width_mode_dir_name}.{language_flavor}'"
                    cellar[width_mode_dir_name][code_point][language_flavor] = glyph_name, glyph_file_path
        for code_point, glyph_source in cellar[width_mode_dir_name].items():
            if 'default' in glyph_source:
                continue
            for language_flavor in configs.language_file_flavors:
                if language_flavor in glyph_source:
                    glyph_source['default'] = glyph_source[language_flavor]
                    break

    registry = {}
    for width_mode in configs.width_modes:
        registry[width_mode] = dict(cellar['common'])
        registry[width_mode].update(cellar[width_mode])

    return DesignContext(registry)


def _create_builder(
        font_config: FontConfig,
        context: DesignContext,
        glyph_cacher: dict[str, Glyph],
        width_mode: str,
        language_flavor: str,
        is_collection: bool,
) -> FontBuilder:
    if language_flavor == 'zh_hans':
        language_file_flavor = 'zh_cn'
    elif language_flavor == 'zh_hant':
        language_file_flavor = 'zh_tr'
    else:
        language_file_flavor = language_flavor

    builder = FontBuilder(font_config.size)

    builder.meta_infos.version = FontConfig.VERSION
    builder.meta_infos.family_name = f'{FontConfig.FAMILY_NAME} {font_config.size}px {width_mode.capitalize()} {language_flavor}'
    builder.meta_infos.style_name = StyleName.REGULAR
    builder.meta_infos.serif_mode = SerifMode.SANS_SERIF
    builder.meta_infos.width_mode = width_mode.capitalize()
    builder.meta_infos.manufacturer = FontConfig.MANUFACTURER
    builder.meta_infos.designer = FontConfig.DESIGNER
    builder.meta_infos.description = FontConfig.DESCRIPTION
    builder.meta_infos.copyright_info = FontConfig.COPYRIGHT_INFO
    builder.meta_infos.license_info = FontConfig.LICENSE_INFO
    builder.meta_infos.vendor_url = FontConfig.VENDOR_URL
    builder.meta_infos.designer_url = FontConfig.DESIGNER_URL
    builder.meta_infos.license_url = FontConfig.LICENSE_URL

    if is_collection:
        builder.opentype_configs.cff_family_name = f'{FontConfig.FAMILY_NAME} {font_config.size}px {width_mode.capitalize()}'

    layout_params = font_config.get_layout_params(width_mode)

    builder.horizontal_header.ascent = layout_params.ascent
    builder.horizontal_header.descent = layout_params.descent

    builder.vertical_header.ascent = layout_params.ascent
    builder.vertical_header.descent = layout_params.descent

    builder.properties.x_height = layout_params.x_height
    builder.properties.cap_height = layout_params.cap_height

    character_mapping = context.get_character_mapping(width_mode, language_file_flavor)
    builder.character_mapping.update(character_mapping)

    glyph_file_infos = context.get_glyph_file_infos(width_mode, None if is_collection else language_file_flavor)
    for glyph_name, glyph_file_path in glyph_file_infos:
        if glyph_file_path in glyph_cacher:
            glyph = glyph_cacher[glyph_file_path]
        else:
            glyph_data, glyph_width, glyph_height = context.load_glyph_data(glyph_file_path)
            horizontal_origin_y = math.floor((layout_params.ascent + layout_params.descent - glyph_height) / 2)
            vertical_origin_y = (glyph_height - font_config.size) // 2
            glyph = Glyph(
                name=glyph_name,
                advance_width=glyph_width,
                advance_height=font_config.size,
                horizontal_origin=(0, horizontal_origin_y),
                vertical_origin_y=vertical_origin_y,
                data=glyph_data,
            )
            glyph_cacher[glyph_file_path] = glyph
        builder.glyphs.append(glyph)

    return builder


def make_font_files(font_config: FontConfig, context: DesignContext, width_mode: str):
    fs_util.make_dirs(path_define.outputs_dir)

    glyph_cacher = {}

    for language_flavor in configs.language_flavors:
        builder = _create_builder(font_config, context, glyph_cacher, width_mode, language_flavor, is_collection=False)

        otf_file_path = os.path.join(path_define.outputs_dir, font_config.get_font_file_name(width_mode, language_flavor, 'otf'))
        builder.save_otf(otf_file_path)
        logger.info("Make font file: '%s'", otf_file_path)

        woff2_file_path = os.path.join(path_define.outputs_dir, font_config.get_font_file_name(width_mode, language_flavor, 'woff2'))
        builder.save_otf(woff2_file_path, flavor=Flavor.WOFF2)
        logger.info("Make font file: '%s'", woff2_file_path)

        ttf_file_path = os.path.join(path_define.outputs_dir, font_config.get_font_file_name(width_mode, language_flavor, 'ttf'))
        builder.save_ttf(ttf_file_path)
        logger.info("Make font file: '%s'", ttf_file_path)

        bdf_file_path = os.path.join(path_define.outputs_dir, font_config.get_font_file_name(width_mode, language_flavor, 'bdf'))
        builder.save_bdf(bdf_file_path)
        logger.info("Make font file: '%s'", bdf_file_path)

    collection_builder = FontCollectionBuilder()
    for language_flavor in configs.language_flavors:
        builder = _create_builder(font_config, context, glyph_cacher, width_mode, language_flavor, is_collection=True)
        collection_builder.font_builders.append(builder)

    otc_file_path = os.path.join(path_define.outputs_dir, font_config.get_font_collection_file_name(width_mode, 'otc'))
    collection_builder.save_otc(otc_file_path)
    logger.info("Make font collection file: '%s'", otc_file_path)

    ttc_file_path = os.path.join(path_define.outputs_dir, font_config.get_font_collection_file_name(width_mode, 'ttc'))
    collection_builder.save_ttc(ttc_file_path)
    logger.info("Make font collection file: '%s'", ttc_file_path)
