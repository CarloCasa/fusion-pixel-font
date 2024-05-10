import logging
import math
import os
import re
import unicodedata

import unidata_blocks
from pixel_font_builder import FontBuilder, FontCollectionBuilder, WeightName, SerifStyle, SlantStyle, Glyph
from pixel_font_builder.opentype import Flavor

from scripts import configs
from scripts.configs import FontConfig, path_define
from scripts.utils import fs_util, bitmap_util

logger = logging.getLogger('font_service')


class GlyphFile:
    @staticmethod
    def load(file_path: str) -> 'GlyphFile':
        tokens = re.split(r'\s+', os.path.basename(file_path).removesuffix('.png'), 1)

        if tokens[0] == 'notdef':
            code_point = -1
        else:
            code_point = int(tokens[0], 16)

        language_flavors = []
        if len(tokens) > 1:
            for language_flavor in tokens[1].lower().split(','):
                if language_flavor in language_flavors:
                    continue
                assert language_flavor in configs.language_file_flavors, f"Language flavor '{language_flavor}' undefined: '{file_path}'"
                language_flavors.append(language_flavor)
            language_flavors.sort(key=lambda x: configs.language_file_flavors.index(x))

        return GlyphFile(file_path, code_point, language_flavors)

    def __init__(self, file_path: str, code_point: int, language_flavors: list[str]):
        self.file_path = file_path
        self.bitmap, self.width, self.height = bitmap_util.load_png(file_path)
        self.code_point = code_point
        self.language_flavors = language_flavors

    @property
    def glyph_name(self) -> str:
        if self.code_point == -1:
            _glyph_name = '.notdef'
        else:
            _glyph_name = f'{self.code_point:04X}'
        if len(self.language_flavors) > 0:
            _glyph_name = f'{_glyph_name}-{''.join([str(configs.language_file_flavors.index(language_flavor)) for language_flavor in self.language_flavors])}'
        return _glyph_name


class DesignContext:
    @staticmethod
    def load(font_config: FontConfig, glyphs_dir: str) -> 'DesignContext':
        glyph_file_registry = {}

        root_dir = os.path.join(glyphs_dir, str(font_config.font_size))
        for width_mode_dir_name in os.listdir(root_dir):
            width_mode_dir = os.path.join(root_dir, width_mode_dir_name)
            if not os.path.isdir(width_mode_dir):
                continue
            assert width_mode_dir_name == 'common' or width_mode_dir_name in configs.width_modes, f"Width mode '{width_mode_dir_name}' undefined: '{width_mode_dir}'"

            code_point_registry = {}
            for file_dir, _, file_names in os.walk(width_mode_dir):
                for file_name in file_names:
                    if not file_name.endswith('.png'):
                        continue
                    file_path = os.path.join(file_dir, file_name)
                    glyph_file = GlyphFile.load(file_path)

                    if glyph_file.code_point not in code_point_registry:
                        language_flavor_registry = {}
                        code_point_registry[glyph_file.code_point] = language_flavor_registry
                    else:
                        language_flavor_registry = code_point_registry[glyph_file.code_point]

                    if len(glyph_file.language_flavors) > 0:
                        for language_flavor in glyph_file.language_flavors:
                            assert language_flavor not in language_flavor_registry, f"Language flavor '{language_flavor}' already exists: '{glyph_file.file_path}' -> '{language_flavor_registry[language_flavor].file_path}'"
                            language_flavor_registry[language_flavor] = glyph_file
                    else:
                        assert '' not in language_flavor_registry, f"Default language flavor already exists: '{glyph_file.file_path}' -> '{language_flavor_registry[''].file_path}'"
                        language_flavor_registry[''] = glyph_file

            for code_point, glyph_files in code_point_registry.items():
                if '' in glyph_files:
                    continue
                for language_flavor in configs.language_file_flavors:
                    if language_flavor in glyph_files:
                        glyph_files[''] = glyph_files[language_flavor]
                        break
            glyph_file_registry[width_mode_dir_name] = code_point_registry

        return DesignContext(font_config, glyphs_dir, glyph_file_registry)

    def __init__(
            self,
            font_config: FontConfig,
            glyphs_dir: str,
            glyph_file_registry: dict[str, dict[int, dict[str, GlyphFile]]],
    ):
        self.font_config = font_config
        self.glyphs_dir = glyphs_dir
        self._glyph_file_registry = glyph_file_registry
        self._sequence_pool: dict[str, list[int]] = {}
        self._alphabet_pool: dict[str, set[str]] = {}
        self._character_mapping_pool: dict[str, dict[int, str]] = {}
        self._glyph_files_pool: dict[str, list[GlyphFile]] = {}

    def standardize(self):
        root_dir = os.path.join(self.glyphs_dir, str(self.font_config.font_size))
        for width_mode_dir_name, code_point_registry in self._glyph_file_registry.items():
            width_mode_dir = os.path.join(root_dir, width_mode_dir_name)
            for language_flavor_registry in code_point_registry.values():
                for glyph_file in set(language_flavor_registry.values()):
                    if glyph_file.code_point == -1:
                        east_asian_width = 'F'
                        block = None
                        file_name = 'notdef.png'
                        file_dir = width_mode_dir
                    else:
                        east_asian_width = unicodedata.east_asian_width(chr(glyph_file.code_point))
                        block = unidata_blocks.get_block_by_code_point(glyph_file.code_point)
                        hex_name = f'{glyph_file.code_point:04X}'
                        file_name = f'{hex_name}{' ' if len(glyph_file.language_flavors) > 0 else ''}{','.join(glyph_file.language_flavors)}.png'
                        file_dir = os.path.join(width_mode_dir, f'{block.code_start:04X}-{block.code_end:04X} {block.name}')
                        if block.code_start == 0x4E00:  # CJK Unified Ideographs
                            file_dir = os.path.join(file_dir, f'{hex_name[0:-2]}-')

                    if width_mode_dir_name == 'common' or width_mode_dir_name == 'monospaced':
                        assert glyph_file.height == self.font_config.font_size, f"Glyph data error: '{glyph_file.file_path}'"

                        # H/Halfwidth or Na/Narrow
                        if east_asian_width == 'H' or east_asian_width == 'Na':
                            assert glyph_file.width == self.font_config.font_size / 2, f"Glyph data error: '{glyph_file.file_path}'"
                        # F/Fullwidth or W/Wide
                        elif east_asian_width == 'F' or east_asian_width == 'W':
                            assert glyph_file.width == self.font_config.font_size, f"Glyph data error: '{glyph_file.file_path}'"
                        # A/Ambiguous or N/Neutral
                        else:
                            assert glyph_file.width == self.font_config.font_size / 2 or glyph_file.width == self.font_config.font_size, f"Glyph data error: '{glyph_file.file_path}'"

                        if block is not None:
                            if 'CJK Unified Ideographs' in block.name:
                                assert all(alpha == 0 for alpha in glyph_file.bitmap[0]), f"Glyph data error: '{glyph_file.file_path}'"
                                assert all(glyph_file.bitmap[i][-1] == 0 for i in range(0, len(glyph_file.bitmap))), f"Glyph data error: '{glyph_file.file_path}'"

                    if width_mode_dir_name == 'proportional':
                        assert glyph_file.height == self.font_config.line_height, f"Glyph data error: '{glyph_file.file_path}'"

                    bitmap_util.save_png(glyph_file.bitmap, glyph_file.file_path)

                    file_path = os.path.join(file_dir, file_name)
                    if glyph_file.file_path != file_path:
                        assert not os.path.exists(file_path), f"Glyph file duplication: '{glyph_file.file_path}' -> '{file_path}'"
                        fs_util.make_dir(file_dir)
                        os.rename(glyph_file.file_path, file_path)
                        glyph_file.file_path = file_path
                        logger.info(f"Standardize glyph file path: '{glyph_file.file_path}'")

        for file_dir, _, _ in os.walk(root_dir, topdown=False):
            file_names = os.listdir(file_dir)
            if '.DS_Store' in file_names:
                file_names.remove('.DS_Store')
            if len(file_names) == 0:
                fs_util.delete_dir(file_dir)

    def fallback(self, other: 'DesignContext'):
        for width_mode, other_code_point_registry in other._glyph_file_registry.items():
            code_point_registry = dict(other_code_point_registry)
            if width_mode in self._glyph_file_registry:
                code_point_registry.update(self._glyph_file_registry[width_mode])
            self._glyph_file_registry[width_mode] = code_point_registry
        self._sequence_pool.clear()
        self._alphabet_pool.clear()
        self._character_mapping_pool.clear()
        self._glyph_files_pool.clear()

    def _get_sequence(self, width_mode: str) -> list[int]:
        if width_mode in self._sequence_pool:
            sequence = self._sequence_pool[width_mode]
        else:
            sequence = set(self._glyph_file_registry['common'])
            sequence.update(self._glyph_file_registry[width_mode])
            sequence = list(sequence)
            sequence.sort()
            self._sequence_pool[width_mode] = sequence
        return sequence

    def get_alphabet(self, width_mode: str) -> set[str]:
        if width_mode in self._alphabet_pool:
            alphabet = self._alphabet_pool[width_mode]
        else:
            alphabet = set([chr(code_point) for code_point in self._get_sequence(width_mode) if code_point >= 0])
            self._alphabet_pool[width_mode] = alphabet
        return alphabet

    @staticmethod
    def _compat_language_flavor(language_flavor: str):
        if language_flavor == 'zh_hans':
            return 'zh_cn'
        elif language_flavor == 'zh_hant':
            return 'zh_tr'
        else:
            return language_flavor

    def get_character_mapping(self, width_mode: str, language_flavor: str) -> dict[int, str]:
        language_flavor = DesignContext._compat_language_flavor(language_flavor)
        key = f'{width_mode}#{language_flavor}'
        if key in self._character_mapping_pool:
            character_mapping = self._character_mapping_pool[key]
        else:
            character_mapping = {}
            for code_point in self._get_sequence(width_mode):
                if code_point < 0:
                    continue
                language_flavor_registry = self._glyph_file_registry[width_mode].get(code_point, None)
                if language_flavor_registry is None:
                    language_flavor_registry = self._glyph_file_registry['common'][code_point]
                glyph_file = language_flavor_registry.get(language_flavor, language_flavor_registry[''])
                character_mapping[code_point] = glyph_file.glyph_name
            self._character_mapping_pool[key] = character_mapping
        return character_mapping

    def get_glyph_files(self, width_mode: str, language_flavor: str = None) -> list[GlyphFile]:
        language_flavor = DesignContext._compat_language_flavor(language_flavor)
        key = f'{width_mode}#{'' if language_flavor is None else language_flavor}'
        if key in self._glyph_files_pool:
            glyph_files = self._glyph_files_pool[key]
        else:
            glyph_files = []
            if language_flavor is None:
                language_flavors = [DesignContext._compat_language_flavor(language_flavor) for language_flavor in configs.language_flavors]
            else:
                language_flavors = [language_flavor]
            sequence = self._get_sequence(width_mode)
            for language_flavor in language_flavors:
                for code_point in sequence:
                    language_flavor_registry = self._glyph_file_registry[width_mode].get(code_point, None)
                    if language_flavor_registry is None:
                        language_flavor_registry = self._glyph_file_registry['common'][code_point]
                    glyph_file = language_flavor_registry.get(language_flavor, language_flavor_registry[''])
                    if glyph_file not in glyph_files:
                        glyph_files.append(glyph_file)
            self._glyph_files_pool[key] = glyph_files
        return glyph_files


def _create_builder(
        design_context: DesignContext,
        glyph_pool: dict[str, Glyph],
        width_mode: str,
        language_flavor: str,
        is_collection: bool,
) -> FontBuilder:
    layout_param = design_context.font_config.layout_params[width_mode]

    builder = FontBuilder()
    builder.font_metric.font_size = design_context.font_config.font_size
    builder.font_metric.horizontal_layout.ascent = layout_param.ascent
    builder.font_metric.horizontal_layout.descent = layout_param.descent
    builder.font_metric.vertical_layout.ascent = math.ceil(layout_param.line_height / 2)
    builder.font_metric.vertical_layout.descent = math.floor(layout_param.line_height / 2)
    builder.font_metric.x_height = layout_param.x_height
    builder.font_metric.cap_height = layout_param.cap_height

    builder.meta_info.version = FontConfig.VERSION
    builder.meta_info.created_time = FontConfig.VERSION_TIME
    builder.meta_info.modified_time = FontConfig.VERSION_TIME
    builder.meta_info.family_name = f'{FontConfig.FAMILY_NAME} {design_context.font_config.font_size}px {width_mode.capitalize()} {language_flavor}'
    builder.meta_info.weight_name = WeightName.REGULAR
    builder.meta_info.serif_style = SerifStyle.SANS_SERIF
    builder.meta_info.slant_style = SlantStyle.NORMAL
    builder.meta_info.width_mode = width_mode.capitalize()
    builder.meta_info.manufacturer = FontConfig.MANUFACTURER
    builder.meta_info.designer = FontConfig.DESIGNER
    builder.meta_info.description = FontConfig.DESCRIPTION
    builder.meta_info.copyright_info = FontConfig.COPYRIGHT_INFO
    builder.meta_info.license_info = FontConfig.LICENSE_INFO
    builder.meta_info.vendor_url = FontConfig.VENDOR_URL
    builder.meta_info.designer_url = FontConfig.DESIGNER_URL
    builder.meta_info.license_url = FontConfig.LICENSE_URL

    character_mapping = design_context.get_character_mapping(width_mode, language_flavor)
    builder.character_mapping.update(character_mapping)

    glyph_files = design_context.get_glyph_files(width_mode, None if is_collection else language_flavor)
    for glyph_file in glyph_files:
        if glyph_file.file_path in glyph_pool:
            glyph = glyph_pool[glyph_file.file_path]
        else:
            horizontal_origin_y = math.floor((layout_param.ascent + layout_param.descent - glyph_file.height) / 2)
            vertical_origin_y = (design_context.font_config.font_size - glyph_file.height) // 2 - 1
            glyph = Glyph(
                name=glyph_file.glyph_name,
                advance_width=glyph_file.width,
                advance_height=design_context.font_config.font_size,
                horizontal_origin=(0, horizontal_origin_y),
                vertical_origin_y=vertical_origin_y,
                bitmap=glyph_file.bitmap,
            )
            glyph_pool[glyph_file.file_path] = glyph
        builder.glyphs.append(glyph)

    return builder


class FontContext:
    def __init__(self, design_context: DesignContext, width_mode: str):
        self.design_context = design_context
        self.width_mode = width_mode
        self._glyph_pool: dict[str, Glyph] = {}
        self._builders: dict[str, FontBuilder] = {}
        self._collection_builder: FontCollectionBuilder | None = None

    def _get_builder(self, language_flavor: str) -> FontBuilder:
        if language_flavor in self._builders:
            builder = self._builders[language_flavor]
        else:
            builder = _create_builder(self.design_context, self._glyph_pool, self.width_mode, language_flavor, is_collection=False)
            self._builders[language_flavor] = builder
        return builder

    def make_otf(self):
        fs_util.make_dir(path_define.outputs_dir)
        for language_flavor in configs.language_flavors:
            builder = self._get_builder(language_flavor)
            file_path = os.path.join(path_define.outputs_dir, self.design_context.font_config.get_font_file_name(self.width_mode, language_flavor, 'otf'))
            builder.save_otf(file_path)
            logger.info("Make font file: '%s'", file_path)

    def make_woff2(self):
        fs_util.make_dir(path_define.outputs_dir)
        for language_flavor in configs.language_flavors:
            builder = self._get_builder(language_flavor)
            file_path = os.path.join(path_define.outputs_dir, self.design_context.font_config.get_font_file_name(self.width_mode, language_flavor, 'woff2'))
            builder.save_otf(file_path, flavor=Flavor.WOFF2)
            logger.info("Make font file: '%s'", file_path)

    def make_ttf(self):
        fs_util.make_dir(path_define.outputs_dir)
        for language_flavor in configs.language_flavors:
            builder = self._get_builder(language_flavor)
            file_path = os.path.join(path_define.outputs_dir, self.design_context.font_config.get_font_file_name(self.width_mode, language_flavor, 'ttf'))
            builder.save_ttf(file_path)
            logger.info("Make font file: '%s'", file_path)

    def make_bdf(self):
        fs_util.make_dir(path_define.outputs_dir)
        for language_flavor in configs.language_flavors:
            builder = self._get_builder(language_flavor)
            file_path = os.path.join(path_define.outputs_dir, self.design_context.font_config.get_font_file_name(self.width_mode, language_flavor, 'bdf'))
            builder.save_bdf(file_path)
            logger.info("Make font file: '%s'", file_path)

    def make_pcf(self):
        fs_util.make_dir(path_define.outputs_dir)
        for language_flavor in configs.language_flavors:
            builder = self._get_builder(language_flavor)
            file_path = os.path.join(path_define.outputs_dir, self.design_context.font_config.get_font_file_name(self.width_mode, language_flavor, 'pcf'))
            builder.save_pcf(file_path)
            logger.info("Make font file: '%s'", file_path)

    def _get_collection_builder(self) -> FontCollectionBuilder:
        if self._collection_builder is None:
            collection_builder = FontCollectionBuilder()
            for language_flavor in configs.language_flavors:
                builder = _create_builder(self.design_context, self._glyph_pool, self.width_mode, language_flavor, is_collection=True)
                collection_builder.append(builder)
            self._collection_builder = collection_builder
        return self._collection_builder

    def make_otc(self):
        fs_util.make_dir(path_define.outputs_dir)
        collection_builder = self._get_collection_builder()
        file_path = os.path.join(path_define.outputs_dir, self.design_context.font_config.get_font_collection_file_name(self.width_mode, 'otc'))
        collection_builder.save_otc(file_path)
        logger.info("Make font collection file: '%s'", file_path)

    def make_ttc(self):
        fs_util.make_dir(path_define.outputs_dir)
        collection_builder = self._get_collection_builder()
        file_path = os.path.join(path_define.outputs_dir, self.design_context.font_config.get_font_collection_file_name(self.width_mode, 'ttc'))
        collection_builder.save_ttc(file_path)
        logger.info("Make font collection file: '%s'", file_path)
