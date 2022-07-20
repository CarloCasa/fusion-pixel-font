import logging
import os
import shutil

import configs
from configs import workspace_define
from services import dump_service, font_service, info_service, publish_service

logging.basicConfig(level=logging.DEBUG)


def main():
    if os.path.exists(workspace_define.build_dir):
        shutil.rmtree(workspace_define.build_dir)
    os.makedirs(workspace_define.dump_dir)
    os.makedirs(workspace_define.outputs_dir)
    os.makedirs(workspace_define.releases_dir)

    glyphs_dirs = [workspace_define.glyphs_dir]
    for dump_config in configs.dump_configs:
        glyphs_dirs.append(dump_service.dump_font(dump_config))

    alphabet, glyph_file_paths = font_service.collect_glyph_files(glyphs_dirs)
    font_service.make_fonts(alphabet, glyph_file_paths)
    info_service.make_info_file(alphabet)
    info_service.make_preview_image_file()
    info_service.make_alphabet_txt_file(alphabet)
    info_service.make_alphabet_html_file(alphabet)
    publish_service.copy_release_files()


if __name__ == '__main__':
    main()
