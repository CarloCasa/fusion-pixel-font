import yaml

from tools.configs import path_define


class DownloadAssetConfig:
    file_name: str | None
    copy_list: list[tuple[str, str]]

    def __init__(self, file_name: str | None, copy_list: list[tuple[str, str]]):
        self.file_name = file_name
        self.copy_list = copy_list


class UpdateConfig:
    @staticmethod
    def load() -> list['UpdateConfig']:
        configs_data = yaml.safe_load(path_define.assets_dir.joinpath('update-configs.yml').read_bytes())
        update_configs = []
        for config_data in configs_data:
            name = config_data['name']
            repository_name = config_data['repository-name']
            tag_name = config_data['tag-name']
            asset_configs = []
            for asset_data in config_data['asset-configs']:
                file_name = asset_data.get('file-name', None)
                copy_list = []
                for from_path, to_path in asset_data['copy-list'].items():
                    if to_path is None:
                        to_path = from_path
                    copy_list.append((from_path, to_path))
                asset_configs.append(DownloadAssetConfig(file_name, copy_list))
            update_configs.append(UpdateConfig(name, repository_name, tag_name, asset_configs))
        return update_configs

    name: str
    repository_name: str
    tag_name: str | None
    asset_configs: list[DownloadAssetConfig]

    def __init__(
            self,
            name: str,
            repository_name: str,
            tag_name: str | None,
            asset_configs: list[DownloadAssetConfig],
    ):
        self.name = name
        self.repository_name = repository_name
        self.tag_name = tag_name
        self.asset_configs = asset_configs
