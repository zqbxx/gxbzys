import json
from pathlib import Path
from typing import Dict

from gxbzys.smpv import SMPV
from gxbzys.utils import get_abs_path


def import_class(cl):
    d = cl.rfind(".")
    classname = cl[d+1:len(cl)]
    m = __import__(cl[0:d], globals(), locals(), [classname])
    return getattr(m, classname)


class Plugin:

    def __init__(self, smpv: SMPV):
        self.smpv = smpv

    def start(self):
        pass

    def destroy(self):
        pass


class Plugins:

    def __init__(self, plugin_config: str, smpv: SMPV):
        self.plugin_config = plugin_config
        self.smpv = smpv
        self.plugin_data:Dict[str, Plugin] = dict()

    def load_all(self):

        if len(self.plugin_data) > 0:
            self.destroy_all()
            self.plugin_data.clear()

        plugin_config_path = get_abs_path(self.plugin_config)
        config_content = plugin_config_path.read_text(encoding='utf-8')
        raw_data = json.loads(config_content)
        for rd in raw_data:
            n = rd.get('name')
            p = Plugins.create_plugin(rd.get('class'), self.smpv)
            self.plugin_data[n] = p

    def start_all(self):
        for n, p in self.plugin_data.items():
            p.start()

    def destroy_all(self):
        for n, p in self.plugin_data.items():
            p.destroy()

    @staticmethod
    def create_plugin(cls: str, smpv: SMPV) -> Plugin:
        plugin_cls = import_class(cls)
        return plugin_cls(smpv)
