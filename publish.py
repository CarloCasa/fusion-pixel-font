import logging
import os
import shutil

from configs import workspace_define
from services import publish_service

logging.basicConfig(level=logging.DEBUG)


def main():
    if os.path.exists(workspace_define.releases_dir):
        shutil.rmtree(workspace_define.releases_dir)
    os.makedirs(workspace_define.releases_dir)

    if not os.path.exists(workspace_define.docs_dir):
        os.makedirs(workspace_define.docs_dir)

    if os.path.exists(workspace_define.www_dir):
        shutil.rmtree(workspace_define.www_dir)
    shutil.copytree(workspace_define.www_static_dir, workspace_define.www_dir)

    publish_service.copy_release_files()
    publish_service.copy_docs_files()
    publish_service.copy_www_files()
    publish_service.deploy_www()


if __name__ == '__main__':
    main()
