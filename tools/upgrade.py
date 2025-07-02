from tools.configs.update import UpdateConfig
from tools.services import update_service


def main():
    update_service.update_ark_pixel_glyphs_version()
    update_service.setup_ark_pixel_glyphs()

    update_configs = UpdateConfig.load()
    for update_config in update_configs:
        update_service.update_fonts(update_config)


if __name__ == '__main__':
    main()
